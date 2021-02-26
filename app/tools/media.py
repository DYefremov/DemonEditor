import os
import sys
from datetime import datetime

from app.commons import run_task, log, _DATE_FORMAT


class Player:
    """ Simple wrapper for GStreamer playbin. """
    __INSTANCE = None

    def __init__(self, mode, rewind_cb, position_cb, error_cb, playing_cb):
        try:
            import gi

            gi.require_version("Gst", "1.0")
            gi.require_version("GstVideo", "1.0")
            from gi.repository import Gst, GstVideo
        except OSError as e:
            log("{}: Load library error: {}".format(__class__.__name__, e))
            raise ImportError
        else:
            # initialize GStreamer
            Gst.init(sys.argv)
            self.STATE = Gst.State
            self.STAT_RETURN = Gst.StateChangeReturn

            self._mode = mode
            self._is_playing = False
            self._player = Gst.ElementFactory.make("playbin", "player")

            bus = self._player.get_bus()
            bus.add_signal_watch()
            bus.connect("message::error", error_cb)
            bus.connect("message::state-changed", playing_cb)

    @classmethod
    def get_instance(cls, mode, rewind_cb=None, position_cb=None, error_cb=None, playing_cb=None):
        if not cls.__INSTANCE:
            cls.__INSTANCE = Player(mode, rewind_cb, position_cb, error_cb, playing_cb)
        return cls.__INSTANCE

    def get_play_mode(self):
        return self._mode

    def play(self, mrl=None):
        self.stop()

        if mrl:
            self._player.set_property("uri", mrl)

        ret = self._player.set_state(self.STATE.PLAYING)

        if ret == self.STAT_RETURN.FAILURE:
            log("ERROR: Unable to set the 'PLAYING' state for '{}'.".format(mrl))
        else:
            self._is_playing = True

    def stop(self):
        if self._is_playing:
            self._player.set_state(self.STATE.READY)
            self._is_playing = False

    def pause(self):
        self._player.set_state(self.STATE.PAUSED)

    def set_time(self, time):
        pass

    def release(self):
        if self._player:
            self._is_playing = False
            self.stop()
            self._player.set_state(self.STATE.NULL)
            self.__INSTANCE = None

    def set_xwindow(self, xid):
        self._player.set_xwindow(xid)

    def set_handle(self, widget):
        """ Used on Windows to set window pointer.

            Based on gtkvlc.py[get_window_pointer] example from here:
            https://github.com/oaubert/python-vlc/tree/master/examples
        """
        try:
            import ctypes

            libgdk = ctypes.CDLL("libgdk-3-0.dll")
        except OSError as e:
            log("{}: Load library error: {}".format(__class__.__name__, e))
        else:
            # https://gitlab.gnome.org/GNOME/pygobject/-/issues/112
            ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
            ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object]
            gpointer = ctypes.pythonapi.PyCapsule_GetPointer(widget.get_window().__gpointer__, None)
            libgdk.gdk_win32_window_get_handle.restype = ctypes.c_void_p
            libgdk.gdk_win32_window_get_handle.argtypes = [ctypes.c_void_p]
            handle = libgdk.gdk_win32_window_get_handle(gpointer)

            self._player.set_window_handle(handle)

    def set_mrl(self, mrl):
        self._player.set_property("uri", mrl)

    def is_playing(self):
        return self._is_playing

    def set_full_screen(self, full):
        self._player.set_fullscreen(full)


class Recorder:
    __VLC_REC_INSTANCE = None

    _CMD = "sout=#std{{access=file,mux=ts,dst={}.ts}}"
    _TR_CMD = "sout=#transcode{{{}}}:file{{mux=mp4,dst={}.mp4}}"

    def __init__(self, settings):
        try:
            from app.tools import vlc
            from app.tools.vlc import EventType
        except OSError as e:
            log("{}: Load library error: {}".format(__class__.__name__, e))
            raise ImportError
        else:
            self._settings = settings
            self._is_record = False
            args = "--quiet {}".format("" if sys.platform == "darwin" else "--no-xlib")
            self._recorder = vlc.Instance(args).media_player_new()

    @classmethod
    def get_instance(cls, settings):
        if not cls.__VLC_REC_INSTANCE:
            cls.__VLC_REC_INSTANCE = Recorder(settings)
        return cls.__VLC_REC_INSTANCE

    @run_task
    def record(self, url, name):
        if self._recorder:
            self._recorder.stop()

        path = self._settings.records_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        d_now = datetime.now().strftime(_DATE_FORMAT)
        path = "{}{}_{}".format(path, name.replace(" ", "_"), d_now.replace(" ", "_"))
        cmd = self.get_transcoding_cmd(path) if self._settings.activate_transcoding else self._CMD.format(path)
        media = self._recorder.get_instance().media_new(url, cmd)
        media.get_mrl()

        self._recorder.set_media(media)
        self._is_record = True
        self._recorder.play()
        log("Record started {}".format(d_now))

    @run_task
    def stop(self):
        self._recorder.stop()
        self._is_record = False
        log("Recording stopped.")

    def is_record(self):
        return self._is_record

    @run_task
    def release(self):
        if self._recorder:
            self._recorder.stop()
            self._recorder.release()
            self._is_record = False
            log("Recording stopped. Releasing...")

    def get_transcoding_cmd(self, path):
        presets = self._settings.transcoding_presets
        prs = presets.get(self._settings.active_preset)
        return self._TR_CMD.format(",".join("{}={}".format(k, v) for k, v in prs.items()), path)


if __name__ == "__main__":
    pass

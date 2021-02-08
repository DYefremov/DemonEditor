import os
import sys
from datetime import datetime

from app.commons import run_task, log, _DATE_FORMAT


class Player:
    """ Simple wrapper for VLC media player. """
    __VLC_INSTANCE = None

    def __init__(self, mode, rewind_cb, position_cb, error_cb, playing_cb):
        try:
            from app.tools import vlc
            from app.tools.vlc import EventType
        except OSError as e:
            log("{}: Load library error: {}".format(__class__.__name__, e))
            raise ImportError
        else:
            self._mode = mode
            self._is_playing = False
            args = "--quiet {}".format("" if sys.platform == "darwin" else "--no-xlib")
            self._player = vlc.Instance(args).media_player_new()
            ev_mgr = self._player.event_manager()

            if rewind_cb:
                # TODO look other EventType options
                ev_mgr.event_attach(EventType.MediaPlayerBuffering,
                                    lambda et, p: rewind_cb(p.get_media().get_duration()),
                                    self._player)
            if position_cb:
                ev_mgr.event_attach(EventType.MediaPlayerTimeChanged,
                                    lambda et, p: position_cb(p.get_time()),
                                    self._player)

            if error_cb:
                ev_mgr.event_attach(EventType.MediaPlayerEncounteredError,
                                    lambda et, p: error_cb(),
                                    self._player)
            if playing_cb:
                ev_mgr.event_attach(EventType.MediaPlayerPlaying,
                                    lambda et, p: playing_cb(),
                                    self._player)

    @classmethod
    def get_instance(cls, mode, rewind_cb=None, position_cb=None, error_cb=None, playing_cb=None):
        if not cls.__VLC_INSTANCE:
            cls.__VLC_INSTANCE = Player(mode, rewind_cb, position_cb, error_cb, playing_cb)
        return cls.__VLC_INSTANCE

    def get_play_mode(self):
        return self._mode

    @run_task
    def play(self, mrl=None):
        if mrl:
            self._player.set_mrl(mrl)
        self._player.play()
        self._is_playing = True

    @run_task
    def stop(self):
        if self._is_playing:
            self._player.stop()
            self._is_playing = False

    def pause(self):
        self._player.pause()

    def set_time(self, time):
        self._player.set_time(time)

    @run_task
    def release(self):
        if self._player:
            self._is_playing = False
            self._player.stop()
            self._player.release()
            self.__VLC_INSTANCE = None

    def set_xwindow(self, xid):
        self._player.set_xwindow(xid)

    def set_nso(self, widget):
        """ Used on MacOS to set NSObject.

            Based on gtkvlc.py[get_window_pointer] example from here:
            https://github.com/oaubert/python-vlc/tree/master/examples
        """
        try:
            import ctypes
            g_dll = ctypes.CDLL("libgdk-3.0.dylib")
        except OSError as e:
            log("{}: Load library error: {}".format(__class__.__name__, e))
        else:
            get_nsview = g_dll.gdk_quartz_window_get_nsview
            get_nsview.restype, get_nsview.argtypes = ctypes.c_void_p, [ctypes.c_void_p]
            ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
            ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object]
            # Get the C void* pointer to the window
            pointer = ctypes.pythonapi.PyCapsule_GetPointer(widget.get_window().__gpointer__, None)
            self._player.set_nsobject(get_nsview(pointer))

    def set_mrl(self, mrl):
        self._player.set_mrl(mrl)

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

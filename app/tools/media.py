import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime

from app.commons import run_task, log, _DATE_FORMAT


class Player(ABC):
    """ Base player class. Also used as a factory. """

    @abstractmethod
    def get_play_mode(self):
        pass

    @abstractmethod
    def play(self, mrl=None):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def pause(self):
        pass

    @abstractmethod
    def set_time(self, time):
        pass

    @abstractmethod
    def release(self):
        pass

    @abstractmethod
    def is_playing(self):
        pass

    @abstractmethod
    def get_instance(self, mode, widget, buf_cb, position_cb, error_cb, playing_cb):
        pass

    @staticmethod
    def make(name, mode, widget, buf_cb=None, position_cb=None, error_cb=None, playing_cb=None):
        """ Factory method. We will not use a separate factory to return a specific implementation.

            @param name: implementation name.
            @param mode: current player mode [Built-in or windowed].
            @param widget: parent of video widget.
            @param buf_cb: buffering callback.
            @param position_cb: time (position) callback.
            @param error_cb: error callback.
            @param playing_cb: playing state callback.

            Throws a NameError if there is no implementation for the given name.
        """
        if name == "gst":
            return GstPlayer.get_instance(mode, widget, buf_cb, position_cb, error_cb, playing_cb)
        elif name == "vlc":
            return VlcPlayer.get_instance(mode, widget, buf_cb, position_cb, error_cb, playing_cb)
        else:
            raise NameError("There is no such [{}] implementation.".format(name))


class GstPlayer(Player):
    """ Simple wrapper for GStreamer playbin. """

    __INSTANCE = None

    def __init__(self, mode, widget, buf_cb, position_cb, error_cb, playing_cb):
        try:
            import gi

            gi.require_version("Gst", "1.0")
            gi.require_version("GstVideo", "1.0")
            from gi.repository import Gst, GstVideo
            # Initialization of GStreamer.
            Gst.init(sys.argv)
            gtk_sink = Gst.ElementFactory.make("gtksink")
            if not gtk_sink:
                msg = "GStreamer error: gtksink plugin not installed!"
                log(msg)
                raise ImportError(msg)
        except OSError as e:
            log("{}: Load library error: {}".format(__class__.__name__, e))
            raise ImportError("No GStreamer is found. Check that it is installed!")
        else:
            self._error_cb = error_cb
            self._playing_cb = playing_cb

            self.STATE = Gst.State
            self.STAT_RETURN = Gst.StateChangeReturn

            self._mode = mode
            self._is_playing = False
            self._player = Gst.ElementFactory.make("playbin", "player")
            # Initialization of the playback widget.
            self._player.set_property("video-sink", gtk_sink)
            vid_widget = gtk_sink.props.widget
            widget.add(vid_widget)
            vid_widget.show()

            bus = self._player.get_bus()
            bus.add_signal_watch()
            bus.connect("message::error", self.on_error)
            bus.connect("message::state-changed", self.on_state_changed)
            bus.connect("message::eos", self.on_eos)

    @classmethod
    def get_instance(cls, mode, widget, buf_cb=None, position_cb=None, error_cb=None, playing_cb=None):
        if not cls.__INSTANCE:
            cls.__INSTANCE = GstPlayer(mode, widget, buf_cb, position_cb, error_cb, playing_cb)
        return cls.__INSTANCE

    def get_play_mode(self):
        return self._mode

    def play(self, mrl=None):
        self._player.set_state(self.STATE.READY)
        if not mrl:
            return

        self._player.set_property("uri", mrl)

        log("Setting the URL for playback: {}".format(mrl))
        ret = self._player.set_state(self.STATE.PLAYING)

        if ret == self.STAT_RETURN.FAILURE:
            log("ERROR: Unable to set the 'PLAYING' state for '{}'.".format(mrl))
        else:
            self._is_playing = True

    def stop(self):
        log("Stop playback...")
        self._player.set_state(self.STATE.READY)
        self._is_playing = False

    def pause(self):
        self._player.set_state(self.STATE.PAUSED)

    def set_time(self, time):
        pass

    @run_task
    def release(self):
        self._is_playing = False
        self._player.set_state(self.STATE.NULL)
        self.__INSTANCE = None

    def set_mrl(self, mrl):
        self._player.set_property("uri", mrl)

    def is_playing(self):
        return self._is_playing

    def on_error(self, bus, msg):
        err, dbg = msg.parse_error()
        log(err)
        self._error_cb()

    def on_state_changed(self, bus, msg):
        if not msg.src == self._player:
            # Not from the player.
            return

        old_state, new_state, pending = msg.parse_state_changed()
        if new_state is self.STATE.PLAYING:
            log("Starting playback...")
            self._playing_cb()
            self.get_stream_info()

    def on_eos(self, bus, msg):
        """ Called when an end-of-stream message appears. """
        self._player.set_state(self.STATE.READY)
        self._is_playing = False

    def get_stream_info(self):
        log("Getting stream info...")
        nr_video = self._player.get_property("n-video")
        for i in range(nr_video):
            # Retrieve the stream's video tags.
            tags = self._player.emit("get-video-tags", i)
            if tags:
                _, cod = tags.get_string("video-codec")
                log("Video codec: {}".format(cod or "unknown"))

        nr_audio = self._player.get_property("n-audio")
        for i in range(nr_audio):
            # Retrieve the stream's video tags.
            tags = self._player.emit("get-audio-tags", i)
            if tags:
                _, cod = tags.get_string("audio-codec")
                log("Audio codec: {}".format(cod or "unknown"))


class VlcPlayer(Player):
    """ Simple wrapper for VLC media player. """

    __VLC_INSTANCE = None

    def __init__(self, mode, widget, buf_cb, position_cb, error_cb, playing_cb):
        try:
            from app.tools import vlc
            from app.tools.vlc import EventType

            args = "--quiet {}".format("" if sys.platform == "darwin" else "--no-xlib")
            self._player = vlc.Instance(args).media_player_new()
        except (OSError, AttributeError) as e:
            log("{}: Load library error: {}".format(__class__.__name__, e))
            raise ImportError("No VLC is found. Check that it is installed!")
        else:
            self._mode = mode
            self._is_playing = False

            ev_mgr = self._player.event_manager()

            if buf_cb:
                # TODO look other EventType options
                ev_mgr.event_attach(EventType.MediaPlayerBuffering,
                                    lambda et, p: buf_cb(p.get_media().get_duration()),
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

            self.init_video_widget(widget)

    @classmethod
    def get_instance(cls, mode, widget, buf_cb=None, position_cb=None, error_cb=None, playing_cb=None):
        if not cls.__VLC_INSTANCE:
            cls.__VLC_INSTANCE = VlcPlayer(mode, widget, buf_cb, position_cb, error_cb, playing_cb)
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

    def set_mrl(self, mrl):
        self._player.set_mrl(mrl)

    def is_playing(self):
        return self._is_playing

    def init_video_widget(self, widget):
        from gi.repository import Gtk, Gdk

        area = Gtk.DrawingArea(visible=True)
        area.connect("draw", self.on_drawing_area_draw)
        area.set_events(Gdk.ModifierType.BUTTON1_MASK)
        widget.add(area)
        if sys.platform == "linux":
            self._player.set_xwindow(area.get_window().get_xid())

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

    def on_drawing_area_draw(self,  widget, cr):
        """ Used for black background drawing in the player drawing area. """
        allocation = widget.get_allocation()
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(0, 0, allocation.width, allocation.height)
        cr.fill()

        return False


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

import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime

from gi.repository import Gdk, Gtk

from app.commons import run_task, log, _DATE_FORMAT, run_with_delay


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

    def get_window_handle(self, widget):
        """ Returns the identifier [pointer] for the window.

            Based on gtkvlc.py[get_window_pointer] example from here:
            https://github.com/oaubert/python-vlc/tree/master/examples
        """
        if sys.platform == "linux":
            return widget.get_window().get_xid()
        else:
            is_darwin = sys.platform == "darwin"
            try:
                import ctypes

                libgdk = ctypes.CDLL("libgdk-3.0.dylib" if is_darwin else "libgdk-3-0.dll")
            except OSError as e:
                log("{}: Load library error: {}".format(__class__.__name__, e))
            else:
                # https://gitlab.gnome.org/GNOME/pygobject/-/issues/112
                ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
                ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object]
                gpointer = ctypes.pythonapi.PyCapsule_GetPointer(widget.get_window().__gpointer__, None)
                get_pointer = libgdk.gdk_quartz_window_get_nsview if is_darwin else libgdk.gdk_win32_window_get_handle
                get_pointer.restype = ctypes.c_void_p
                get_pointer.argtypes = [ctypes.c_void_p]

                return get_pointer(gpointer)

    def get_video_widget(self, widget):
        area = Gtk.DrawingArea(visible=True)
        area.connect("draw", self.on_drawing_area_draw)
        area.connect("motion-notify-event", self.on_mouse_motion)
        area.set_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        widget.add(area)

        return area

    def on_drawing_area_draw(self, widget, cr):
        """ Used for black background drawing in the player drawing area. """
        cr.set_source_rgb(0, 0, 0)
        cr.paint()

    def on_mouse_motion(self, widget, event):
        display = widget.get_display()
        window = widget.get_window()
        cursor = Gdk.Cursor.new_from_name(display, "default")
        window.set_cursor(cursor)

        self.hide_mouse_cursor(window, display)

    @run_with_delay(3)
    def hide_mouse_cursor(self, window, display):
        cursor = Gdk.Cursor.new_for_display(display, Gdk.CursorType.BLANK_CURSOR)
        window.set_cursor(cursor)

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
        if name == "mpv":
            return MpvPlayer.get_instance(mode, widget, buf_cb, position_cb, error_cb, playing_cb)
        elif name == "gst":
            return GstPlayer.get_instance(mode, widget, buf_cb, position_cb, error_cb, playing_cb)
        elif name == "vlc":
            return VlcPlayer.get_instance(mode, widget, buf_cb, position_cb, error_cb, playing_cb)
        else:
            raise NameError("There is no such [{}] implementation.".format(name))


class MpvPlayer(Player):
    """ Simple wrapper for MPV media player.

        Uses python-mvp [https://github.com/jaseg/python-mpv].
    """
    __INSTANCE = None

    def __init__(self, mode, widget, buf_cb, position_cb, error_cb, playing_cb):
        try:
            from app.tools import mpv

            self._player = mpv.MPV(wid=str(self.get_window_handle(self.get_video_widget(widget), )),
                                   input_default_bindings=False,
                                   input_cursor=False,
                                   cursor_autohide="no")
        except OSError as e:
            log("{}: Load library error: {}".format(__class__.__name__, e))
            raise ImportError("No libmpv is found. Check that it is installed!")
        else:
            self._mode = mode
            self._is_playing = False

            @self._player.event_callback(mpv.MpvEventID.FILE_LOADED)
            def on_open(event):
                log("Starting playback...")
                playing_cb()

            @self._player.event_callback(mpv.MpvEventID.END_FILE)
            def on_end(event):
                event = event.get("event", {})
                if event.get("reason", mpv.MpvEventEndFile.ERROR) == mpv.MpvEventEndFile.ERROR:
                    log("Stream playback error: {}".format(event.get("error", mpv.ErrorCode.GENERIC)))
                    error_cb()

    @classmethod
    def get_instance(cls, mode, widget, buf_cb, position_cb, error_cb, playing_cb):
        if not cls.__INSTANCE:
            cls.__INSTANCE = MpvPlayer(mode, widget, buf_cb, position_cb, error_cb, playing_cb)
        return cls.__INSTANCE

    def get_play_mode(self):
        return self._mode

    @run_task
    def play(self, mrl=None):
        if not mrl:
            return

        self._player.play(mrl)
        self._is_playing = True

    @run_task
    def stop(self):
        self._player.stop()
        self._is_playing = True

    def pause(self):
        pass

    def set_time(self, time):
        pass

    @run_task
    def release(self):
        self._player.terminate()
        self.__INSTANCE = None

    def is_playing(self):
        return self._is_playing


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
        except (OSError, ValueError) as e:
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
            vid_widget = gtk_sink.get_property("widget")
            vid_widget.connect("motion-notify-event", self.on_mouse_motion)
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
    """ Simple wrapper for VLC media player.

        Uses python-vlc [https://github.com/oaubert/python-vlc].
    """

    __VLC_INSTANCE = None

    def __init__(self, mode, widget, buf_cb, position_cb, error_cb, playing_cb):
        try:
            from app.tools import vlc
            from app.tools.vlc import EventType

            args = "--quiet {}".format("" if sys.platform == "darwin" else "--no-xlib")
            self._player = vlc.Instance(args).media_player_new()
            vlc.libvlc_video_set_key_input(self._player, False)
            vlc.libvlc_video_set_mouse_input(self._player, False)
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
        video_widget = self.get_video_widget(widget)
        if sys.platform == "linux":
            self._player.set_xwindow(video_widget.get_window().get_xid())
        elif sys.platform == "darwin":
            self._player.set_nsobject(self.get_window_handle(video_widget))
        else:
            log("Video widget initialization error: platform '{}' is not supported. ".format(sys.platform))


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

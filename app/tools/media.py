# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2022 Dmitriy Yefremov
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Author: Dmitriy Yefremov
#


import os
import sys
from datetime import datetime

from gi.repository import Gdk, Gtk, GObject

from app.commons import run_task, log, _DATE_FORMAT, run_with_delay
from app.settings import IS_DARWIN, IS_LINUX, IS_WIN


class Player(Gtk.DrawingArea):
    """ Base player class. Also used as a factory. """

    def __init__(self, mode, widget, **kwargs):
        super().__init__(**kwargs)

        GObject.signal_new("error", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("message", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("position", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("played", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("audio-track", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("subtitle-track", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))

        self.connect("draw", self.on_draw)
        self.connect("motion-notify-event", self.on_mouse_motion)
        self.set_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        widget.add(self)

        parent = widget.get_parent()
        parent.connect("play", self.on_play)
        parent.connect("stop", self.on_stop)
        self.show()

    def get_play_mode(self):
        pass

    def play(self, mrl=None):
        pass

    def stop(self):
        pass

    def pause(self):
        pass

    def set_time(self, time):
        pass

    def release(self):
        pass

    def is_playing(self):
        pass

    def set_audio_track(self, track):
        pass

    def get_audio_track(self):
        pass

    def set_subtitle_track(self, track):
        pass

    def set_aspect_ratio(self, ratio):
        pass

    def get_instance(self, mode, widget):
        pass

    def on_play(self, widget, url):
        self.play(url)

    def on_stop(self, widget, state):
        self.stop()

    def on_release(self, widget, state):
        self.release()

    def get_window_handle(self):
        """ Returns the identifier [pointer] for the window.

            Based on gtkvlc.py[get_window_pointer] example from here:
            https://github.com/oaubert/python-vlc/tree/master/examples
        """
        if IS_LINUX:
            return self.get_window().get_xid()
        else:
            try:
                import ctypes

                libgdk = ctypes.CDLL("libgdk-3.0.dylib" if IS_DARWIN else "libgdk-3-0.dll")
            except OSError as e:
                log(f"{__class__.__name__}: Load library error: {e}")
            else:
                # https://gitlab.gnome.org/GNOME/pygobject/-/issues/112
                ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
                ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object]
                gpointer = ctypes.pythonapi.PyCapsule_GetPointer(self.get_window().__gpointer__, None)
                get_pointer = libgdk.gdk_quartz_window_get_nsview if IS_DARWIN else libgdk.gdk_win32_window_get_handle
                get_pointer.restype = ctypes.c_void_p
                get_pointer.argtypes = [ctypes.c_void_p]

                return get_pointer(gpointer)

    def on_draw(self, widget, cr):
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
    def make(name, mode, widget):
        """ Factory method. We will not use a separate factory to return a specific implementation.

            @param name: implementation name.
            @param mode: current player mode [Built-in or windowed].
            @param widget: parent of video widget.

            Throws a NameError if there is no implementation for the given name.
        """
        if name == "mpv":
            return MpvPlayer.get_instance(mode, widget)
        elif name == "gst":
            return GstPlayer.get_instance(mode, widget)
        elif name == "vlc":
            return VlcPlayer.get_instance(mode, widget)
        else:
            raise NameError(f"There is no such [{name}] implementation.")


class MpvPlayer(Player):
    """ Simple wrapper for MPV media player.

        Uses python-mvp [https://github.com/jaseg/python-mpv].
    """
    __INSTANCE = None

    def __init__(self, mode, widget):
        super().__init__(mode, widget)
        try:
            from app.tools import mpv

            self._player = mpv.MPV(wid=str(self.get_window_handle()),
                                   input_default_bindings=False,
                                   input_cursor=False,
                                   cursor_autohide="no")
        except OSError as e:
            log(f"{__class__.__name__}: Load library error: {e}")
            raise ImportError("No libmpv is found. Check that it is installed!")
        else:
            self._mode = mode
            self._is_playing = False

            @self._player.event_callback(mpv.MpvEventID.FILE_LOADED)
            def on_open(event):
                log("Starting playback...")
                self.emit("played", 0)

                t_list = self._player._get_property("track-list")
                if t_list:
                    # Audio tracks.
                    a_tracks = filter(lambda t: t.get("type", "") == "audio", t_list)
                    self.emit("audio-track", ((t.get("id", 1), t.get("lang", "Unknown")) for t in a_tracks))
                    # Subtitle.
                    sub_tracks = [(0, "no")]
                    tracks = filter(lambda t: t.get("type", "") == "sub", t_list)
                    [sub_tracks.append((t.get("id", 1), t.get("lang", "Unknown"))) for t in tracks]
                    self.emit("subtitle-track", sub_tracks)

            @self._player.event_callback(mpv.MpvEventID.END_FILE)
            def on_end(event):
                event = event.get("event", {})
                if event.get("reason", mpv.MpvEventEndFile.ERROR) == mpv.MpvEventEndFile.ERROR:
                    log(f"Stream playback error: {event.get('error', mpv.ErrorCode.GENERIC)}")
                    self.emit("error", "Can't Playback!")

    @classmethod
    def get_instance(cls, mode, widget):
        if not cls.__INSTANCE:
            cls.__INSTANCE = MpvPlayer(mode, widget)
        return cls.__INSTANCE

    def get_play_mode(self):
        return self._mode

    def play(self, mrl=None):
        if not mrl:
            return

        self._player.play(mrl)
        self._is_playing = True

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

    def set_audio_track(self, track):
        self._player._set_property("aid", track)

    def set_subtitle_track(self, track):
        self._player._set_property("sub", track)

    def set_aspect_ratio(self, ratio):
        self._player._set_property("aspect", ratio or "-1.0")


class GstPlayer(Player):
    """ Simple wrapper for GStreamer playbin. """

    __INSTANCE = None

    def __init__(self, mode, widget):
        super().__init__(mode, widget)
        try:
            import gi

            gi.require_version("Gst", "1.0")
            gi.require_version("GstVideo", "1.0")
            from gi.repository import Gst, GstVideo
            # Initialization of GStreamer.
            Gst.init(sys.argv)
        except (OSError, ValueError) as e:
            log(f"{__class__.__name__}: Load library error: {e}")
            raise ImportError("No GStreamer is found. Check that it is installed!")
        else:
            self.STATE = Gst.State
            self.STAT_RETURN = Gst.StateChangeReturn

            self._mode = mode
            self._is_playing = False
            self._player = Gst.ElementFactory.make("playbin", "player")
            self._player.set_window_handle(self.get_window_handle())

            bus = self._player.get_bus()
            bus.add_signal_watch()
            bus.connect("message::error", self.on_error)
            bus.connect("message::state-changed", self.on_state_changed)
            bus.connect("message::eos", self.on_eos)

    @classmethod
    def get_instance(cls, mode, widget):
        if not cls.__INSTANCE:
            cls.__INSTANCE = GstPlayer(mode, widget)
        return cls.__INSTANCE

    def get_play_mode(self):
        return self._mode

    def play(self, mrl=None):
        self._player.set_state(self.STATE.READY)
        if not mrl:
            return

        self._player.set_property("uri", mrl)

        log(f"Setting the URL for playback: {mrl}")
        ret = self._player.set_state(self.STATE.PLAYING)

        if ret == self.STAT_RETURN.FAILURE:
            msg = f"ERROR: Unable to set the 'PLAYING' state for '{mrl}'."
            log(msg)
            self.emit("error", msg)
        else:
            self.emit("played", 0)
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
        self.emit("error", "Can't Playback!")

    def on_state_changed(self, bus, msg):
        if not msg.src == self._player:
            # Not from the player.
            return

        old_state, new_state, pending = msg.parse_state_changed()
        if new_state is self.STATE.PLAYING:
            log("Starting playback...")
            self.emit("played", 0)
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
                log(f"Video codec: {cod or 'unknown'}")

        nr_audio = self._player.get_property("n-audio")
        for i in range(nr_audio):
            # Retrieve the stream's video tags.
            tags = self._player.emit("get-audio-tags", i)
            if tags:
                _, cod = tags.get_string("audio-codec")
                log(f"Audio codec: {cod or 'unknown'}")


class VlcPlayer(Player):
    """ Simple wrapper for VLC media player.

        Uses python-vlc [https://github.com/oaubert/python-vlc].
    """

    __VLC_INSTANCE = None

    def __init__(self, mode, widget):
        super().__init__(mode, widget)
        try:
            if IS_WIN:
                os.add_dll_directory(r"C:\Program Files\VideoLAN\VLC")

            from app.tools import vlc
            from app.tools.vlc import EventType

            args = f"--quiet {'' if IS_DARWIN else '--no-xlib'}"
            self._player = vlc.Instance(args).media_player_new()
            vlc.libvlc_video_set_key_input(self._player, False)
            vlc.libvlc_video_set_mouse_input(self._player, False)
        except (OSError, AttributeError, NameError) as e:
            log(f"{__class__.__name__}: Load library error: {e}")
            raise ImportError("No VLC is found. Check that it is installed!")
        else:
            self._mode = mode
            self._is_playing = False

            ev_mgr = self._player.event_manager()
            ev_mgr.event_attach(EventType.MediaPlayerVout, self.on_playback_start)
            ev_mgr.event_attach(EventType.MediaPlayerTimeChanged,
                                lambda et: self.emit("position", self._player.get_time()))
            ev_mgr.event_attach(EventType.MediaPlayerEncounteredError, lambda et: self.emit("error", "Can't Playback!"))

            self.init_video_widget(widget)

    @classmethod
    def get_instance(cls, mode, widget):
        if not cls.__VLC_INSTANCE:
            cls.__VLC_INSTANCE = VlcPlayer(mode, widget)
        return cls.__VLC_INSTANCE

    def get_play_mode(self):
        return self._mode

    def play(self, mrl=None):
        if mrl:
            self._player.set_mrl(mrl)
        self._player.play()
        self._is_playing = True

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

    def set_audio_track(self, track):
        self._player.audio_set_track(track)

    def get_audio_track(self):
        return self._player.audio_get_track()

    def set_subtitle_track(self, track):
        self._player.video_set_spu(track)

    def set_aspect_ratio(self, ratio):
        self._player.video_set_aspect_ratio(ratio)

    def on_playback_start(self, event):
        self.emit("played", self._player.get_media().get_duration())
        # Audio tracks.
        a_desc = self._player.audio_get_track_description()
        self.emit("audio-track", [(t[0], t[1].decode(encoding="utf-8", errors="ignore")) for t in a_desc])
        # Subtitle.
        s_desc = self._player.video_get_spu_description()
        self.emit("subtitle-track", [(s[0], s[1].decode(encoding="utf-8", errors="ignore")) for s in s_desc])

    def init_video_widget(self, widget):
        if IS_LINUX:
            self._player.set_xwindow(self.get_window_handle())
        elif IS_DARWIN:
            self._player.set_nsobject(self.get_window_handle())
        else:
            self._player.set_hwnd(self.get_window_handle())


class Recorder:
    __VLC_REC_INSTANCE = None

    _CMD = "sout=#std{{access=file,mux=ts,dst={}.ts}}"
    _TR_CMD = "sout=#transcode{{{}}}:file{{mux=mp4,dst={}.mp4}}"

    def __init__(self, settings):
        try:
            if IS_WIN:
                os.add_dll_directory(r"C:\Program Files\VideoLAN\VLC")

            from app.tools import vlc
            from app.tools.vlc import EventType
        except OSError as e:
            log(f"{__class__.__name__}: Load library error: {e}")
            raise ImportError
        else:
            self._settings = settings
            self._is_record = False
            args = f"--quiet {'' if IS_DARWIN else '--no-xlib'}"
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
        d_now = d_now.replace(" ", "_").replace(":", "-") if IS_WIN else d_now.replace(" ", "_")
        path = f"{path}{name.replace(' ', '_')}_{d_now}"
        cmd = self.get_transcoding_cmd(path) if self._settings.activate_transcoding else self._CMD.format(path)
        media = self._recorder.get_instance().media_new(url, cmd)
        media.get_mrl()

        self._recorder.set_media(media)
        self._is_record = True
        self._recorder.play()
        log(f"Record started {d_now}")

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
        return self._TR_CMD.format(",".join(f"{k}={v}" for k, v in prs.items()), path)


if __name__ == "__main__":
    pass

import sys

from app.commons import run_task, log


class Player:
    __VLC_INSTANCE = None

    def __init__(self, rewind_callback, position_callback, error_callback, playing_callback):
        try:
            from app.tools import vlc
            from app.tools.vlc import EventType
        except OSError as e:
            log("{}: Load library error: {}".format(__class__.__name__, e))
            raise ImportError
        else:
            self._is_playing = False
            args = "--quiet {}".format("" if sys.platform == "darwin" else "--no-xlib")
            self._player = vlc.Instance(args).media_player_new()
            ev_mgr = self._player.event_manager()

            if rewind_callback:
                # TODO look other EventType options
                ev_mgr.event_attach(EventType.MediaPlayerBuffering,
                                    lambda et, p: rewind_callback(p.get_media().get_duration()),
                                    self._player)
            if position_callback:
                ev_mgr.event_attach(EventType.MediaPlayerTimeChanged,
                                    lambda et, p: position_callback(p.get_time()),
                                    self._player)

            if error_callback:
                ev_mgr.event_attach(EventType.MediaPlayerEncounteredError,
                                    lambda et, p: error_callback(),
                                    self._player)
            if playing_callback:
                ev_mgr.event_attach(EventType.MediaPlayerPlaying,
                                    lambda et, p: playing_callback(),
                                    self._player)

    @classmethod
    def get_instance(cls, rewind_callback=None, position_callback=None, error_callback=None, playing_callback=None):
        if not cls.__VLC_INSTANCE:
            cls.__VLC_INSTANCE = Player(rewind_callback, position_callback, error_callback, playing_callback)
        return cls.__VLC_INSTANCE

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


if __name__ == "__main__":
    pass

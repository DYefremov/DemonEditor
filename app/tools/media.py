import ctypes
import sys

from app.commons import run_task
from app.tools import vlc
from app.tools.vlc import EventType


class Player:
    _VLC_INSTANCE = None

    def __init__(self, rewind_callback=None, position_callback=None):
        self._is_playing = False
        self._player = self.get_vlc_instance()
        ev_mgr = self._player.event_manager()

        if rewind_callback:
            # TODO look other EventType options
            ev_mgr.event_attach(EventType.MediaPlayerBuffering,
                                lambda e, p: rewind_callback(p.get_media().get_duration()),
                                self._player)
        if position_callback:
            ev_mgr.event_attach(EventType.MediaPlayerTimeChanged,
                                lambda e, p: position_callback(p.get_time()),
                                self._player)

    @staticmethod
    def get_vlc_instance():
        if Player._VLC_INSTANCE:
            return Player._VLC_INSTANCE
        args = "--quiet {}".format("" if sys.platform == "darwin" else "--no-xlib")
        _VLC_INSTANCE = vlc.Instance(args).media_player_new()
        return _VLC_INSTANCE

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
        g_dll = ctypes.CDLL("libgdk-3.0.dylib")
        get_nsview = g_dll.gdk_quaerz_window_get_nsview
        get_nsview.restype, get_nsview.argtypes = [ctypes.c_void_p], ctypes.c_void_p
        ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
        ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object]
        self._player.set_nsobject(ctypes.pythonapi.PyCapsule_GetPointer(widget.get_window().__gpointer__, None))

    def set_mrl(self, mrl):
        self._player.set_mrl(mrl)

    def is_playing(self):
        return self._is_playing

    def set_full_screen(self, full):
        self._player.set_fullscreen(full)


if __name__ == "__main__":
    pass

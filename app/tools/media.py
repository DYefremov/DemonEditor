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

    def get_vlc_instance(self):
        if Player._VLC_INSTANCE:
            return Player._VLC_INSTANCE

        self._VLC_INSTANCE = vlc.Instance("--no-xlib").media_player_new()

        if sys.platform.startswith("darwin"):
            try:
                view = Player.get_nso()
            except ImportError as e:
                raise e
            else:
                self._VLC_INSTANCE.set_nsobject(view.__c_void_p__())

        return self._VLC_INSTANCE

    @staticmethod
    def get_nso():
        """ This code based on pyobjcvlc.py example
            from  here: https://github.com/oaubert/python-vlc/tree/master/examples
        """
        try:
            from objc import __version__ as __PyObjC__
        except ImportError:
            raise ImportError("No PyObjC is installed!")
        else:
            from Cocoa import NSBackingStoreBuffered, NSBundle, NSScreen, NSMakeRect, NSView, NSWindow

        try:
            from Cocoa import NSWindowStyleMaskClosable, NSWindowStyleMaskMiniaturizable, \
                NSWindowStyleMaskResizable, NSWindowStyleMaskTitled
        except ImportError as e:
            raise e

        NSWindowStyleMaskUsual = NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable \
                                 | NSWindowStyleMaskResizable | NSWindowStyleMaskTitled
        frame = NSScreen.mainScreen().frame()
        w = int(frame.size.width * 0.5)
        h = int(frame.size.height * w / frame.size.width)
        frame = NSMakeRect(frame.origin.x + 10, frame.origin.y + 10, w, h)
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(frame,
                                                                               NSWindowStyleMaskUsual,
                                                                               NSBackingStoreBuffered,
                                                                               False)
        view = NSView.alloc().initWithFrame_(frame)
        window.setContentView_(view)
        window.setContentAspectRatio_(frame.size)
        window.makeKeyAndOrderFront_(None)
        return view

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

    def set_mrl(self, mrl):
        self._player.set_mrl(mrl)

    def is_playing(self):
        return self._is_playing

    def set_full_screen(self, full):
        self._player.set_fullscreen(full)


if __name__ == "__main__":
    pass

from app.commons import run_idle
from app.tools import vlc
from app.ui.uicommons import Gtk, Gdk

MRL = "url"


class Player:
    _VLC_INSTANCE = None

    def __init__(self, url):
        handlers = {"on_play": self.on_play,
                    "on_stop": self.on_stop,
                    "on_drawing_area_realize": self.on_drawing_area_realize,
                    "on_press": self.on_press,
                    "on_key_release": self.on_key_release,
                    "on_state_changed": self.on_state_changed,
                    "on_close_window": self.on_close_window}

        builder = Gtk.Builder()
        builder.add_objects_from_file("player.glade", ("player_main_window",))
        builder.connect_signals(handlers)
        self._main_window = builder.get_object("player_main_window")
        self._main_box = builder.get_object("main_box")
        self._buttonbox = builder.get_object("buttonbox")
        self._frame = builder.get_object("")
        self._drawing_area = builder.get_object("drawing_area")
        self._drawing_area.set_events(Gdk.ModifierType.BUTTON1_MASK)
        self._player = Player.get_vlc_instance().media_player_new()
        self._is_played = False
        self._url = url
        self._full_screen = False

    @staticmethod
    def get_vlc_instance():
        if Player._VLC_INSTANCE:
            return Player._VLC_INSTANCE
        _VLC_INSTANCE = vlc.Instance("--no-xlib")
        return _VLC_INSTANCE

    def on_play(self, item):
        if not self._is_played:
            self._player.play()
            self._is_played = True

    def on_stop(self, item):
        if self._is_played:
            self._player.stop()
            self._is_played = False

    def on_press(self, area, event: Gdk.EventButton):
        if event.button == Gdk.BUTTON_PRIMARY and event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.change_state()

    def on_state_changed(self, window, event):
        if event.new_window_state & Gdk.WindowState.FULLSCREEN:
            if self._main_box in window:
                window.remove(self._main_box)
                self._drawing_area.reparent(self._main_window)
        else:
            if self._drawing_area in self._main_window:
                window.remove(self._drawing_area)
                window.add(self._main_box)
                self._main_box.pack_start(self._drawing_area, True, True, 0)
                self._main_box.reorder_child(self._drawing_area, 0)

    def change_state(self):
        self._full_screen = not self._full_screen
        self._main_window.fullscreen() if self._full_screen else self._main_window.unfullscreen()

    def on_key_release(self, area, key):
        if key.keyval in (Gdk.KEY_F, Gdk.KEY_f):
            self.change_state()

    def on_drawing_area_realize(self, widget):
        win_id = widget.get_window().get_xid()
        if self._player:
            self._is_played = True
            self._player.set_xwindow(win_id)
            self._player.set_mrl(self._url)
            self._player.play()

    @run_idle
    def on_close_window(self, *args):
        if self._player:
            self.on_stop(None)
            self._player.release()
        Gtk.main_quit()

    def show(self):
        self._main_window.show()
        Gtk.main()


if __name__ == "__main__":
    Player(MRL).show()

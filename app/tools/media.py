from app.commons import run_idle
from app.tools import vlc
from app.ui.uicommons import Gtk

MRL = "url"


class Player:
    _VLC_INSTANCE = None

    def __init__(self, url):
        handlers = {"on_play": self.on_play,
                    "on_stop": self.on_stop,
                    "on_drawing_area_realize": self.on_drawing_area_realize,
                    "on_close_window": self.on_close_window}

        builder = Gtk.Builder()
        builder.add_objects_from_file("player.glade", ("player_main_window",))
        builder.connect_signals(handlers)
        self._main_window = builder.get_object("player_main_window")
        self._player = Player.get_vlc_instance().media_player_new()
        self._is_played = False
        self._url = url

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

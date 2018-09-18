from app.tools import vlc


class Player:
    _VLC_INSTANCE = None

    def __init__(self):
        self._is_playing = False
        self._player = self.get_vlc_instance()

    @staticmethod
    def get_vlc_instance():
        if Player._VLC_INSTANCE:
            return Player._VLC_INSTANCE
        _VLC_INSTANCE = vlc.Instance("--no-xlib").media_player_new()
        return _VLC_INSTANCE

    def play(self, mrl=None):
        if not self._is_playing:
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

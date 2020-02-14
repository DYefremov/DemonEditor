from urllib.parse import urlparse

from gi.repository import GLib

from app.connections import HttpRequestType
from app.tools.yt import YouTube
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, get_yt_icon


class LinksTransmitter:
    """ The main class for the "send to" function.

         It used for direct playback of media links by the enigma2 media player.
    """
    __STREAM_PREFIX = "4097:0:1:0:0:0:0:0:0:0:"

    def __init__(self, http_api, app_window):
        handlers = {"on_popup_menu": self.on_popup_menu,
                    "on_status_icon_activate": self.on_status_icon_activate,
                    "on_query_tooltip": self.on_query_tooltip,
                    "on_drag_data_received": self.on_drag_data_received,
                    "on_previous": self.on_previous,
                    "on_next": self.on_next,
                    "on_stop": self.on_stop,
                    "on_clear": self.on_clear,
                    "on_play": self.on_play,
                    "on_exit": self.on_exit}

        self._http_api = http_api
        self._app_window = app_window

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "transmitter.glade")
        builder.connect_signals(handlers)

        self._tray = builder.get_object("status_icon")
        self._main_window = builder.get_object("main_window")
        self._url_entry = builder.get_object("url_entry")
        self._tool_bar = builder.get_object("tool_bar")

        style_provider = Gtk.CssProvider()
        style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._url_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), style_provider,
                                                                    Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def show(self, show):
        self._tray.set_visible(show)
        if not show:
            self.hide()

    def hide(self):
        self._main_window.hide()

    def on_popup_menu(self, menu, button, time):
        menu.popup(None, None, None, None, button, time)

    def on_status_icon_activate(self, window):
        visible = window.get_visible()
        window.hide() if visible else window.show()
        self._app_window.present() if visible else self._app_window.iconify()

    def on_query_tooltip(self, icon, g, x, y, tooltip: Gtk.Tooltip):
        if self._main_window.get_visible() or not self._url_entry.get_text():
            return False

        tooltip.set_text(self._url_entry.get_text())
        return True

    def on_drag_data_received(self, entry, drag_context, x, y, data, info, time):
        url = data.get_text()
        GLib.idle_add(entry.set_text, url)
        gen = self.activate_url(url)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def activate_url(self, url):
        self._url_entry.set_name("GtkEntry")
        result = urlparse(url)

        if result.scheme and result.netloc:
            self._tool_bar.set_sensitive(False)
            yt_id = YouTube.get_yt_id(url)
            yield True

            if yt_id:
                self._url_entry.set_icon_from_pixbuf(Gtk.EntryIconPosition.SECONDARY, get_yt_icon("youtube", 32))
                links, title = YouTube.get_yt_link(yt_id)
                yield True
                if links:
                    url = links[sorted(links, key=lambda x: int(x.rstrip("p")), reverse=True)[0]]
                else:
                    self.on_done(links)
                    return
            else:
                self._url_entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)

            self._http_api.send(HttpRequestType.PLAY, url, self.on_done, self.__STREAM_PREFIX)
            yield True

    def on_done(self, res):
        """ Play callback """
        res = res.get("e2state", None) if res else res
        self._url_entry.set_name("GtkEntry" if res else "digit-entry")
        GLib.idle_add(self._tool_bar.set_sensitive, True)

    def on_previous(self, item):
        self._http_api.send(HttpRequestType.PLAYER_PREV, None, self.on_done)

    def on_next(self, item):
        self._http_api.send(HttpRequestType.PLAYER_NEXT, None, self.on_done)

    def on_play(self, item):
        self._http_api.send(HttpRequestType.PLAYER_PLAY, None, self.on_done)

    def on_stop(self, item):
        self._http_api.send(HttpRequestType.PLAYER_STOP, None, self.on_done)

    def on_clear(self, item):
        """ Remove added links in the playlist. """
        GLib.idle_add(self._tool_bar.set_sensitive, False)
        self._http_api.send(HttpRequestType.PLAYER_LIST, None, self.clear_playlist)

    def clear_playlist(self, res):
        GLib.idle_add(self._tool_bar.set_sensitive, not res)

        for ref in res:
            GLib.idle_add(self._tool_bar.set_sensitive, False)
            self._http_api.send(HttpRequestType.PLAYER_REMOVE,
                                ref.get("e2servicereference", ""),
                                self.on_done,
                                self.__STREAM_PREFIX)

    def on_exit(self, item=None):
        self.show(False)


if __name__ == "__main__":
    pass

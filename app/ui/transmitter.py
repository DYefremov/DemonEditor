from urllib.parse import urlparse
from gi.repository import GLib
from app.connections import HttpRequestType
from app.tools.yt import YouTube
from app.ui.iptv import get_yt_icon
from .uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN


class LinksTransmitter:

    def __init__(self, http_api, app_window):
        handlers = {"on_popup_menu": self.on_popup_menu,
                    "on_status_icon_activate": self.on_status_icon_activate,
                    "on_query_tooltip": self.on_query_tooltip,
                    "on_drag_data_received": self.on_drag_data_received,
                    "on_exit": self.on_exit}

        self._http_api = http_api
        self._app_window = app_window

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_from_file(UI_RESOURCES_PATH + "transmitter.glade")
        builder.connect_signals(handlers)

        self._tray = builder.get_object("status_icon")
        self._main_window = builder.get_object("main_window")
        self._url_entry = builder.get_object("url_entry")

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
        if self._main_window.get_visible():
            return False

        tooltip.set_text("Test")
        return True

    def on_drag_data_received(self, widget, drag_context, x, y, data, info, time):
        gen = self.activate_url(data.get_text())
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def activate_url(self, url):
        result = urlparse(url)
        if result.scheme and result.netloc:
            self._url_entry.set_sensitive(False)
            yt_id = YouTube.get_yt_id(url)
            yield True

            if yt_id:
                self._url_entry.set_icon_from_pixbuf(Gtk.EntryIconPosition.SECONDARY, get_yt_icon("youtube", 32))
                links, title = YouTube.get_yt_link(yt_id)
                yield True
                if links:
                    url = links[sorted(links, key=lambda x: int(x.rstrip("p")), reverse=True)[0]]
            else:
                self._url_entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)

            self._http_api.send(HttpRequestType.PLAY, url, self.on_play)
            yield True

    def on_play(self, res):
        """ Play callback """
        self._url_entry.set_sensitive(True)
        if res:
            print(res)

    def on_exit(self, item=None):
        self.show(False)


if __name__ == "__main__":
    pass

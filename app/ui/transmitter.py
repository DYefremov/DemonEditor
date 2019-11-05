from urllib.parse import urlparse

from app.connections import HttpRequestType
from .uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN


class LinksTransmitter:

    def __init__(self, http_api):
        handlers = {"on_popup_menu": self.on_popup_menu,
                    "on_status_icon_activate": self.on_status_icon_activate,
                    "on_query_tooltip": self.on_query_tooltip,
                    "on_drag_data_received": self.on_drag_data_received,
                    "on_exit": self.on_exit}

        self._http_api = http_api

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
            self._main_window.hide()

    def on_popup_menu(self, menu, button, time):
        menu.popup(None, None, None, None, button, time)

    def on_status_icon_activate(self, window):
        visible = window.get_visible()
        window.hide() if visible else window.show()

    def on_query_tooltip(self, icon, g, x, y, tooltip: Gtk.Tooltip):
        if self._main_window.get_visible():
            return False

        tooltip.set_text("Test")
        return True

    def on_drag_data_received(self, widget, drag_context, x, y, data, info, time):
        self.activate_url(data.get_text())

    def activate_url(self, url):
        result = urlparse(url)
        if result.scheme and result.netloc:
            res = self._http_api.send((HttpRequestType.PLAY, url))
            next(self._http_api)
            print(res)

    def on_exit(self, item=None):
        self.show(False)


if __name__ == "__main__":
    pass

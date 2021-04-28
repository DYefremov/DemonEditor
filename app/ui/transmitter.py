from pathlib import Path
from urllib.parse import urlparse

import gi
from gi.repository import GLib

from app.commons import log
from app.connections import HttpAPI
from app.settings import IS_DARWIN
from app.tools.yt import YouTube
from app.ui.dialogs import get_builder
from app.ui.iptv import get_yt_icon
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH


class LinksTransmitter:
    """ The main media bar class for the "send to" function..

         It used for direct playback of media links by the enigma2 media player.
    """
    __STREAM_PREFIX = "4097:0:1:0:0:0:0:0:0:0:"

    def __init__(self, http_api, app_window, settings):
        handlers = {"on_popup_menu": self.on_popup_menu,
                    "on_status_icon_activate": self.on_status_icon_activate,
                    "on_url_changed": self.on_url_changed,
                    "on_url_activate": self.on_url_activate,
                    "on_drag_data_received": self.on_drag_data_received,
                    "on_previous": self.on_previous,
                    "on_next": self.on_next,
                    "on_stop": self.on_stop,
                    "on_clear": self.on_clear,
                    "on_play": self.on_play}

        self._http_api = http_api
        self._app_window = app_window
        self._is_status_icon = True

        builder = get_builder(UI_RESOURCES_PATH + "transmitter.glade", handlers)

        self._main_window = builder.get_object("main_window")
        self._url_entry = builder.get_object("url_entry")
        self._tool_bar = builder.get_object("tool_bar")
        self._popup_menu = builder.get_object("staus_popup_menu")
        self._restore_menu_item = builder.get_object("restore_menu_item")
        self._status_active = None
        self._status_passive = None
        self._yt = YouTube.get_instance(settings)

        if IS_DARWIN:
            self._tray = builder.get_object("status_icon")
        else:
            try:
                gi.require_version("AppIndicator3", "0.1")
                from gi.repository import AppIndicator3
            except (ImportError, ValueError) as e:
                log("{}: Load library error: {}".format(__class__.__name__, e))
                self._tray = builder.get_object("status_icon")
            else:
                self._is_status_icon = False
                self._status_active = AppIndicator3.IndicatorStatus.ACTIVE
                self._status_passive = AppIndicator3.IndicatorStatus.PASSIVE

            category = AppIndicator3.IndicatorCategory.APPLICATION_STATUS
            path = Path(UI_RESOURCES_PATH + "/icons/hicolor/scalable/apps/demon-editor.svg")
            path = str(path.resolve()) if path.is_file() else "demon-editor"
            self._tray = AppIndicator3.Indicator.new("DemonEditor", path, category)
            self._tray.set_status(self._status_active)
            self._tray.set_secondary_activate_target(builder.get_object("show_menu_item"))
            self._tray.set_menu(self._popup_menu)

        style_provider = Gtk.CssProvider()
        style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._url_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), style_provider,
                                                                    Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def show(self, show):
        if self._is_status_icon:
            self._tray.set_visible(show)
        elif self._status_active:
            self._tray.set_status(self._status_active if show else self._status_passive)
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

    def on_url_changed(self, entry):
        entry.set_name("GtkEntry" if self.is_url(entry.get_text()) else "digit-entry")

    def on_url_activate(self, entry):
        gen = self.activate_url(entry.get_text())
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_drag_data_received(self, entry, drag_context, x, y, data, info, time):
        url = data.get_text()
        GLib.idle_add(entry.set_text, url)
        gen = self.activate_url(url)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def activate_url(self, url):
        self._url_entry.set_name("GtkEntry")
        self._url_entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)

        if self.is_url(url):
            self._tool_bar.set_sensitive(False)
            yt_id = YouTube.get_yt_id(url)
            yield True

            if yt_id:
                self._url_entry.set_icon_from_pixbuf(Gtk.EntryIconPosition.SECONDARY, get_yt_icon("youtube", 32))
                links, title = self._yt.get_yt_link(yt_id, url)
                yield True
                if links:
                    url = links[sorted(links, key=lambda x: int(x.rstrip("p")), reverse=True)[0]]
                else:
                    self.on_done(links)
                    return
            else:
                self._url_entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)

            self._http_api.send(HttpAPI.Request.PLAY, url, self.on_done, self.__STREAM_PREFIX)
            yield True

    def on_done(self, res):
        """ Play callback """
        res = res.get("e2state", None) if res else res
        self._url_entry.set_name("GtkEntry" if res else "digit-entry")
        GLib.idle_add(self._tool_bar.set_sensitive, True)

    def on_previous(self, item):
        self._http_api.send(HttpAPI.Request.PLAYER_PREV, None, self.on_done)

    def on_next(self, item):
        self._http_api.send(HttpAPI.Request.PLAYER_NEXT, None, self.on_done)

    def on_play(self, item):
        self._http_api.send(HttpAPI.Request.PLAYER_PLAY, None, self.on_done)

    def on_stop(self, item):
        self._http_api.send(HttpAPI.Request.PLAYER_STOP, None, self.on_done)

    def on_clear(self, item):
        """ Remove added links in the playlist. """
        GLib.idle_add(self._tool_bar.set_sensitive, False)
        self._http_api.send(HttpAPI.Request.PLAYER_LIST, None, self.clear_playlist)

    def clear_playlist(self, res):
        GLib.idle_add(self._tool_bar.set_sensitive, not res)
        if "error_code" in res:
            log("Error clearing playlist. There may be no http connection.")
            self.on_done(res)
            return

        for ref in res:
            GLib.idle_add(self._tool_bar.set_sensitive, False)
            self._http_api.send(HttpAPI.Request.PLAYER_REMOVE,
                                ref.get("e2servicereference", ""),
                                self.on_done,
                                self.__STREAM_PREFIX)

    @staticmethod
    def is_url(text):
        """ Simple url checking. """
        result = urlparse(text)
        return result.scheme and result.netloc


if __name__ == "__main__":
    pass

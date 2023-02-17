# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2023 Dmitriy Yefremov
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Author: Dmitriy Yefremov
#


import concurrent.futures
import os
import re
import urllib
from urllib.error import HTTPError
from urllib.parse import urlparse, unquote, quote
from urllib.request import Request, urlopen

import requests
from gi.repository import GLib, Gio, GdkPixbuf

from app.commons import run_idle, run_task, log
from app.eparser.ecommons import BqServiceType, Service
from app.eparser.iptv import (NEUTRINO_FAV_ID_FORMAT, StreamType, ENIGMA2_FAV_ID_FORMAT, get_fav_id, MARKER_FORMAT,
                              parse_m3u, PICON_FORMAT)
from app.settings import SettingsType, IS_DARWIN
from app.tools.yt import YouTubeException, YouTube
from app.ui.dialogs import Action, show_dialog, DialogType, get_message, get_builder
from app.ui.main_helper import get_iptv_url, on_popup_menu, get_picon_pixbuf
from app.ui.uicommons import (Gtk, Gdk, UI_RESOURCES_PATH, IPTV_ICON, Column, KeyboardKey, get_yt_icon,
                              IS_GNOME_SESSION, HeaderBar)

_DIGIT_ENTRY_NAME = "digit-entry"
_ENIGMA2_REFERENCE = "{}:{}:{:X}:{:X}:{:X}:{:X}:{:X}:0:0:0"
_PATTERN = re.compile("(?:^[\\s]*$|\\D)")
_UI_PATH = UI_RESOURCES_PATH + "iptv.glade"


def is_data_correct(elems):
    for elem in elems:
        if elem.get_name() == _DIGIT_ENTRY_NAME:
            return False
    return True


def get_stream_type(box):
    active = box.get_active()
    if active == 0:
        return StreamType.DVB_TS.value
    elif active == 1:
        return StreamType.NONE_TS.value
    elif active == 2:
        return StreamType.NONE_REC_1.value
    elif active == 3:
        return StreamType.NONE_REC_2.value
    elif active == 4:
        return StreamType.E_SERVICE_URI.value
    return StreamType.E_SERVICE_HLS.value


class IptvDialog:

    def __init__(self, app, view, bouquet=None, service=None, action=Action.ADD):
        handlers = {"on_response": self.on_response,
                    "on_entry_changed": self.on_entry_changed,
                    "on_url_changed": self.on_url_changed,
                    "on_save": self.on_save,
                    "on_stream_type_changed": self.on_stream_type_changed,
                    "on_yt_quality_changed": self.on_yt_quality_changed,
                    "on_info_bar_close": self.on_info_bar_close}

        self._app = app
        self._action = action
        self._settings = app.app_settings
        self._s_type = self._settings.setting_type
        self._bouquet = bouquet
        self._yt_links = None
        self._yt_dl = None

        builder = get_builder(_UI_PATH, handlers, use_str=True,
                              objects=("iptv_dialog", "stream_type_liststore", "yt_quality_liststore"))

        self._dialog = builder.get_object("iptv_dialog")
        self._dialog.set_transient_for(app.app_window)
        self._name_entry = builder.get_object("name_entry")
        self._description_entry = builder.get_object("description_entry")
        self._url_entry = builder.get_object("url_entry")
        self._reference_entry = builder.get_object("reference_entry")
        self._srv_type_entry = builder.get_object("srv_type_entry")
        self._srv_id_entry = builder.get_object("srv_id_entry")
        self._sid_entry = builder.get_object("sid_entry")
        self._tr_id_entry = builder.get_object("tr_id_entry")
        self._net_id_entry = builder.get_object("net_id_entry")
        self._namespace_entry = builder.get_object("namespace_entry")
        self._stream_type_combobox = builder.get_object("stream_type_combobox")
        self._add_button = builder.get_object("iptv_dialog_add_button")
        self._save_button = builder.get_object("iptv_dialog_save_button")
        self._stream_type_combobox = builder.get_object("stream_type_combobox")
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")
        self._yt_quality_box = builder.get_object("yt_iptv_quality_combobox")
        self._model, self._paths = view.get_selection().get_selected_rows()
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._digit_elems = (self._srv_id_entry, self._srv_type_entry, self._sid_entry, self._tr_id_entry,
                             self._net_id_entry, self._namespace_entry)
        for el in self._digit_elems:
            el.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                           Gtk.STYLE_PROVIDER_PRIORITY_USER)
        if self._s_type is SettingsType.NEUTRINO_MP:
            builder.get_object("iptv_dialog_ts_data_frame").set_visible(False)
            builder.get_object("iptv_type_label").set_visible(False)
            builder.get_object("reference_entry").set_visible(False)
            builder.get_object("iptv_reference_label").set_visible(False)
            self._stream_type_combobox.set_visible(False)
        else:
            self._description_entry.set_visible(False)
            builder.get_object("iptv_description_label").set_visible(False)

        if self._action is Action.ADD:
            self._save_button.set_visible(False)
            self._add_button.set_visible(True)
            if self._s_type is SettingsType.ENIGMA_2:
                self.update_reference_entry()
                self._stream_type_combobox.set_active(1)
        elif self._action is Action.EDIT:
            self._current_srv = service
            self.init_data(self._current_srv)

    def show(self):
        self._dialog.run()

    def on_response(self, dialog, response):
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            self._dialog.destroy()

    def on_save(self, item):
        if self._action is Action.ADD:
            self.on_url_changed(self._url_entry)

        if not is_data_correct(self._digit_elems) or self._url_entry.get_name() == _DIGIT_ENTRY_NAME:
            self.show_info_message(get_message("Error. Verify the data!"), Gtk.MessageType.ERROR)
            return

        if show_dialog(DialogType.QUESTION, self._dialog) in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        self.save_enigma2_data() if self._s_type is SettingsType.ENIGMA_2 else self.save_neutrino_data()
        self._dialog.destroy()

    def init_data(self, srv):
        fav_id = srv.fav_id
        self._name_entry.set_text(srv.service)
        self.init_enigma2_data(fav_id) if self._s_type is SettingsType.ENIGMA_2 else self.init_neutrino_data(fav_id)

    def init_enigma2_data(self, fav_id):
        data, sep, desc = fav_id.partition("#DESCRIPTION")
        self._description_entry.set_text(desc.strip())
        data = data.split(":")
        if len(data) < 11:
            return

        s_type = data[0].strip()
        try:
            stream_type = StreamType(s_type)
            if stream_type is StreamType.DVB_TS:
                self._stream_type_combobox.set_active(0)
            elif stream_type is StreamType.NONE_TS:
                self._stream_type_combobox.set_active(1)
            elif stream_type is StreamType.NONE_REC_1:
                self._stream_type_combobox.set_active(2)
            elif stream_type is StreamType.NONE_REC_2:
                self._stream_type_combobox.set_active(3)
            elif stream_type is StreamType.E_SERVICE_URI:
                self._stream_type_combobox.set_active(4)
            elif stream_type is StreamType.E_SERVICE_HLS:
                self._stream_type_combobox.set_active(5)
        except ValueError:
            self.show_info_message("Unknown stream type {}".format(s_type), Gtk.MessageType.ERROR)

        self._srv_id_entry.set_text(data[1])
        self._srv_type_entry.set_text(str(int(data[2], 16)))
        self._sid_entry.set_text(str(int(data[3], 16)))
        self._tr_id_entry.set_text(str(int(data[4], 16)))
        self._net_id_entry.set_text(str(int(data[5], 16)))
        self._namespace_entry.set_text(str(int(data[6], 16)))
        self._url_entry.set_text(unquote(data[10].strip()))
        self.update_reference_entry()

    def init_neutrino_data(self, fav_id):
        data = fav_id.split("::")
        self._url_entry.set_text(data[0])
        self._description_entry.set_text(data[1])

    def update_reference_entry(self):
        if self._s_type is SettingsType.ENIGMA_2 and is_data_correct(self._digit_elems):
            self.on_url_changed(self._url_entry)
            self._reference_entry.set_text(_ENIGMA2_REFERENCE.format(self.get_type(),
                                                                     self._srv_id_entry.get_text(),
                                                                     int(self._srv_type_entry.get_text()),
                                                                     int(self._sid_entry.get_text()),
                                                                     int(self._tr_id_entry.get_text()),
                                                                     int(self._net_id_entry.get_text()),
                                                                     int(self._namespace_entry.get_text())))

    def get_type(self):
        return get_stream_type(self._stream_type_combobox)

    def on_entry_changed(self, entry):
        if _PATTERN.search(entry.get_text()):
            entry.set_name(_DIGIT_ENTRY_NAME)
        else:
            entry.set_name("GtkEntry")
            self.update_reference_entry()

    def on_url_changed(self, entry):
        url_str = entry.get_text()
        url = urlparse(url_str)
        e_types = (StreamType.E_SERVICE_URI.value, StreamType.E_SERVICE_HLS.value)
        cond = all([url.scheme, url.netloc, url.path]) or self.get_type() in e_types
        entry.set_name("GtkEntry" if cond else _DIGIT_ENTRY_NAME)

        yt_id = YouTube.get_yt_id(url_str)
        if yt_id:
            entry.set_icon_from_pixbuf(Gtk.EntryIconPosition.SECONDARY, get_yt_icon("youtube", 32))
            text = "Found a link to the YouTube resource!\nTry to get a direct link to the video?"
            if show_dialog(DialogType.QUESTION, self._dialog, text=text) == Gtk.ResponseType.OK:
                entry.set_sensitive(False)
                gen = self.set_yt_url(entry, yt_id)
                GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
        elif YouTube.is_yt_video_link(url_str):
            entry.set_icon_from_pixbuf(Gtk.EntryIconPosition.SECONDARY, get_yt_icon("youtube", 32))
        else:
            entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)
            self._yt_quality_box.set_visible(False)

    def set_yt_url(self, entry, video_id):
        try:
            if not self._yt_dl:
                def callback(message, error=True):
                    msg_type = Gtk.MessageType.ERROR if error else Gtk.MessageType.INFO
                    self.show_info_message(message, msg_type)

                self._yt_dl = YouTube.get_instance(self._settings, callback=callback)
                yield True
            links, title = self._yt_dl.get_yt_link(video_id, entry.get_text())
            yield True
        except urllib.error.URLError as e:
            self.show_info_message(get_message("Getting link error:") + (str(e)), Gtk.MessageType.ERROR)
            return
        except YouTubeException as e:
            self.show_info_message((str(e)), Gtk.MessageType.ERROR)
            return
        else:
            if self._action is Action.ADD:
                self._name_entry.set_text(title)

            if links:
                if len(links) > 1:
                    self._yt_quality_box.set_visible(True)
                entry.set_text(links[sorted(links, key=lambda x: int(x.rstrip("p")), reverse=True)[0]])
                self._yt_links = links
            else:
                msg = get_message("Getting link error:") + " No link received for id: {}".format(video_id)
                self.show_info_message(msg, Gtk.MessageType.ERROR)
        finally:
            entry.set_sensitive(True)
        yield True

    def on_stream_type_changed(self, item):
        if self.get_type() in (StreamType.E_SERVICE_URI.value, StreamType.E_SERVICE_HLS.value):
            self.show_info_message("DreamOS only!", Gtk.MessageType.WARNING)
        self.update_reference_entry()

    def on_yt_quality_changed(self, box):
        model = box.get_model()
        active = model.get_value(box.get_active_iter(), 0)
        if self._yt_links and active in self._yt_links:
            self._url_entry.set_text(self._yt_links[active])

    def save_enigma2_data(self):
        name = self._name_entry.get_text().strip()
        fav_id = ENIGMA2_FAV_ID_FORMAT.format(self.get_type(),
                                              self._srv_id_entry.get_text(),
                                              int(self._srv_type_entry.get_text()),
                                              int(self._sid_entry.get_text()),
                                              int(self._tr_id_entry.get_text()),
                                              int(self._net_id_entry.get_text()),
                                              int(self._namespace_entry.get_text()),
                                              quote(self._url_entry.get_text()),
                                              name, name)

        self.update_bouquet_data(name, fav_id)

    def save_neutrino_data(self):
        if self._action is Action.EDIT:
            id_data = self._current_srv.fav_id.split("::")
        else:
            id_data = ["", "", "0", None, None, None, None, "", "", "1"]
        id_data[0] = self._url_entry.get_text()
        id_data[1] = self._description_entry.get_text()
        self.update_bouquet_data(self._name_entry.get_text(), NEUTRINO_FAV_ID_FORMAT.format(*id_data))
        self._dialog.destroy()

    def update_bouquet_data(self, name, fav_id):
        picon_id = f"{self._reference_entry.get_text().replace(':', '_')}.png"

        if self._action is Action.EDIT:
            services = self._app.current_services
            old_srv = services.pop(self._current_srv.fav_id)
            new_service = old_srv._replace(service=name, fav_id=fav_id, picon_id=picon_id)
            services[fav_id] = new_service
            self._app.emit("iptv-service-edited", {self._current_srv.fav_id: (old_srv, new_service)})
        else:
            aggr = [None] * 8
            s_type = BqServiceType.IPTV.name
            srv = (None, None, name, None, None, s_type, None, fav_id, *aggr[0:3])
            itr = self._model.insert_after(self._model.get_iter(self._paths[0]),
                                           srv) if self._paths else self._model.insert(0, srv)
            self._model.set_value(itr, 1, IPTV_ICON)
            self._bouquet.insert(self._model.get_path(itr)[0], fav_id)
            service = Service(None, None, IPTV_ICON, name, *aggr[0:3], s_type, None, picon_id, *aggr, fav_id, None)
            self._app.current_services[fav_id] = service
            self._app.emit("iptv-service-added", (service,))

    @run_idle
    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)


class SearchUnavailableDialog:

    def __init__(self, transient, model, fav_bouquet, iptv_rows, s_type):
        handlers = {"on_response": self.on_response}

        builder = get_builder(UI_RESOURCES_PATH + "iptv.glade", handlers,
                              objects=("search_unavailable_streams_dialog",))

        self._dialog = builder.get_object("search_unavailable_streams_dialog")
        self._dialog.set_transient_for(transient)
        self._model = model
        self._counter_label = builder.get_object("streams_rows_counter_label")
        self._level_bar = builder.get_object("unavailable_streams_level_bar")
        self._bouquet = fav_bouquet
        self._s_type = s_type
        self._iptv_rows = iptv_rows
        self._counter = -1
        self._max_rows = len(self._iptv_rows)
        self._level_bar.set_max_value(self._max_rows)
        self._download_task = True
        self._to_delete = []

        self.update_counter()
        self.do_search()

    @run_task
    def do_search(self):
        import ssl
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self.get_unavailable, row, context): row for row in self._iptv_rows}
            for future in concurrent.futures.as_completed(futures):
                if not self._download_task:
                    executor.shutdown()
                    return
                future.result()
            self._download_task = False
        self.on_close()

    def get_unavailable(self, row, context):
        if not self._download_task:
            return
        try:
            req = Request(get_iptv_url(row, self._s_type))
            self.update_bar()
            urlopen(req, context=context, timeout=2)
        except HTTPError as e:
            if e.code != 403:
                self.append_data(row)
        except Exception:
            self.append_data(row)

    def append_data(self, row):
        self._to_delete.append(self._model.get_iter(row.path))
        self.update_counter()

    @run_idle
    def update_bar(self):
        self._max_rows -= 1
        self._level_bar.set_value(self._max_rows)

    @run_idle
    def update_counter(self):
        self._counter += 1
        self._counter_label.set_text(str(self._counter))

    def show(self):
        response = self._dialog.run()

        return self._to_delete if response not in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT) else False

    def on_response(self, dialog, response):
        if response == Gtk.ResponseType.CANCEL:
            self.on_close()

    @run_idle
    def on_close(self):
        if self._download_task and show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return
        self._download_task = False
        self._dialog.destroy()


class IptvListDialog:
    """ Base class for working with iptv lists. """

    def __init__(self, transient, s_type):
        handlers = {"on_apply": self.on_apply,
                    "on_response": self.on_response,
                    "on_stream_type_default_togged": self.on_stream_type_default_togged,
                    "on_stream_type_changed": self.on_stream_type_changed,
                    "on_default_id_toggled": self.on_default_id_toggled,
                    "on_default_type_toggled": self.on_default_type_toggled,
                    "on_auto_sid_toggled": self.on_auto_sid_toggled,
                    "on_default_tid_toggled": self.on_default_tid_toggled,
                    "on_default_nid_toggled": self.on_default_nid_toggled,
                    "on_default_namespace_toggled": self.on_default_namespace_toggled,
                    "on_reset_to_default": self.on_reset_to_default,
                    "on_entry_changed": self.on_entry_changed,
                    "on_info_bar_close": self.on_info_bar_close}

        self._s_type = s_type

        builder = get_builder(_UI_PATH, handlers, use_str=True,
                              objects=("iptv_list_configuration_dialog", "stream_type_liststore"))

        self._dialog = builder.get_object("iptv_list_configuration_dialog")
        self._dialog.set_transient_for(transient)
        self._data_box = builder.get_object("iptv_list_data_box")
        self._start_values_grid = builder.get_object("start_values_grid")
        self._info_bar = builder.get_object("list_configuration_info_bar")
        self._reference_label = builder.get_object("reference_label")
        self._stream_type_check_button = builder.get_object("stream_type_default_check_button")
        self._id_default_check_button = builder.get_object("id_default_check_button")
        self._type_check_button = builder.get_object("type_default_check_button")
        self._sid_auto_check_button = builder.get_object("sid_auto_check_button")
        self._tid_check_button = builder.get_object("tid_default_check_button")
        self._nid_check_button = builder.get_object("nid_default_check_button")
        self._namespace_check_button = builder.get_object("namespace_default_check_button")
        self._stream_type_combobox = builder.get_object("stream_type_list_combobox")
        self._list_srv_id_entry = builder.get_object("list_srv_id_entry")
        self._list_srv_type_entry = builder.get_object("list_srv_type_entry")
        self._list_sid_entry = builder.get_object("list_sid_entry")
        self._list_tid_entry = builder.get_object("list_tid_entry")
        self._list_nid_entry = builder.get_object("list_nid_entry")
        self._list_namespace_entry = builder.get_object("list_namespace_entry")
        self._apply_button = builder.get_object("list_configuration_apply_button")
        self._cancel_button = builder.get_object("cancel_config_list_button")
        self._ok_button = builder.get_object("list_configuration_ok_button")
        self._ok_button.bind_property("visible", self._apply_button, "visible", 4)
        self._ok_button.bind_property("visible", self._cancel_button, "visible", 4)
        # Style
        style_provider = Gtk.CssProvider()
        style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._default_elems = (self._stream_type_check_button, self._id_default_check_button, self._type_check_button,
                               self._sid_auto_check_button, self._tid_check_button, self._nid_check_button,
                               self._namespace_check_button)
        self._digit_elems = (self._list_srv_id_entry, self._list_srv_type_entry, self._list_sid_entry,
                             self._list_tid_entry, self._list_nid_entry, self._list_namespace_entry)
        for el in self._digit_elems:
            el.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), style_provider,
                                                           Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def show(self):
        self._dialog.run()

    def on_response(self, dialog, response):
        if response == Gtk.ResponseType.APPLY:
            return True

        self._dialog.destroy()

    def on_stream_type_changed(self, box):
        self.update_reference()

    def on_stream_type_default_togged(self, button):
        if button.get_active():
            self._stream_type_combobox.set_active(1)
        self._stream_type_combobox.set_sensitive(not button.get_active())

    def on_default_id_toggled(self, button):
        self.set_default(button, self._list_srv_id_entry, "0")

    def on_default_type_toggled(self, button):
        self.set_default(button, self._list_srv_type_entry, "1")

    def on_auto_sid_toggled(self, button):
        self.set_default(button, self._list_sid_entry, "0")

    def on_default_tid_toggled(self, button):
        self.set_default(button, self._list_tid_entry, "0")

    def on_default_nid_toggled(self, button):
        self.set_default(button, self._list_nid_entry, "0")

    def on_default_namespace_toggled(self, button):
        self.set_default(button, self._list_namespace_entry, "0")

    def set_default(self, button, entry, value):
        if button.get_active():
            entry.set_text(value)
        entry.set_sensitive(not button.get_active())

    @run_idle
    def on_reset_to_default(self, item):
        self._stream_type_combobox.set_active(1)
        self._list_srv_type_entry.set_text("1")
        for el in self._digit_elems[1:]:
            el.set_text("0")
        for el in self._default_elems:
            el.set_active(True)

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    def on_apply(self, item):
        pass

    @run_idle
    def update_reference(self):
        if is_data_correct(self._digit_elems):
            stream_type = get_stream_type(self._stream_type_combobox)
            self._reference_label.set_text(
                _ENIGMA2_REFERENCE.format(stream_type, *[int(elem.get_text()) for elem in self._digit_elems]))

    def on_entry_changed(self, entry):
        if _PATTERN.search(entry.get_text()):
            entry.set_name(_DIGIT_ENTRY_NAME)
        else:
            entry.set_name("GtkEntry")
            self.update_reference()

    def is_default_values(self):
        return any(el.get_text() == "0" for el in self._digit_elems[3:])

    def is_all_data_default(self):
        return all(el.get_active() for el in self._default_elems)


class IptvListConfigurationDialog(IptvListDialog):

    def __init__(self, transient, services, iptv_rows, bouquet, fav_model, s_type):
        super().__init__(transient, s_type)

        self._rows = iptv_rows
        self._bouquet = bouquet
        self._fav_model = fav_model
        self._services = services

    @run_idle
    def on_apply(self, item):
        if not is_data_correct(self._digit_elems):
            show_dialog(DialogType.ERROR, self._dialog, "Error. Verify the data!")
            return

        if self._s_type is SettingsType.ENIGMA_2:
            id_default = self._id_default_check_button.get_active()
            type_default = self._type_check_button.get_active()
            tid_default = self._tid_check_button.get_active()
            sid_auto = self._sid_auto_check_button.get_active()
            nid_default = self._nid_check_button.get_active()
            namespace_default = self._namespace_check_button.get_active()
            all_default = self.is_all_data_default()

            st_type = get_stream_type(self._stream_type_combobox)
            s_id = "0" if id_default else self._list_srv_id_entry.get_text()
            srv_type = int("1" if type_default else self._list_srv_type_entry.get_text())
            sid = "0" if sid_auto else self._list_sid_entry.get_text()
            tid = "0" if tid_default else f"{int(self._list_tid_entry.get_text()):X}"
            nid = "0" if nid_default else f"{int(self._list_nid_entry.get_text()):X}"
            namespace = "0" if namespace_default else f"{int(self._list_namespace_entry.get_text()):X}"
            params = [int(el.get_text()) for el in self._digit_elems[2:]]

            for index, row in enumerate(self._rows):
                fav_id = row[Column.FAV_ID]
                data, sep, desc = fav_id.partition("http")
                data = data.split(":")

                if all_default:
                    data[1], data[2], data[3], data[4], data[5], data[6] = "010000"
                else:
                    data[0], data[1], data[4], data[5], data[6] = st_type, s_id, tid, nid, namespace
                    data[2] = f"{srv_type:X}"

                data[3] = f"{index:X}" if sid_auto else sid
                if sid_auto:
                    params[0] = index
                picon_id = PICON_FORMAT.format(st_type, int(s_id), srv_type, *params)
                data = ":".join(data)
                new_fav_id = f"{data}{sep}{desc}"
                row[Column.FAV_ID] = new_fav_id
                srv = self._services.pop(fav_id, None)

                if srv:
                    self._services[new_fav_id] = srv._replace(fav_id=new_fav_id, picon_id=picon_id)

            self._bouquet.clear()
            list(map(lambda r: self._bouquet.append(r[Column.FAV_ID]), self._fav_model))

            self._info_bar.set_visible(True)
            self._ok_button.set_visible(True)


class M3uImportDialog(IptvListDialog):
    """ Import dialog for *.m3u* playlists. """

    def __init__(self, transient, s_type, m3_path, app):
        super().__init__(transient, s_type)

        self._app = app
        self._picons = app.picons
        self._pic_path = app._settings.profile_picons_path
        self._services = None
        self._url_count = 0
        self._errors_count = 0
        self._max_count = 0
        self._is_download = False
        self._cancellable = Gio.Cancellable()
        self._dialog.set_title(get_message("Playlist import"))
        self._dialog.connect("delete-event", self.on_close)
        self._apply_button.set_label(get_message("Import"))
        # Progress
        self._progress_bar = Gtk.ProgressBar(visible=False, valign="center")
        self._spinner = Gtk.Spinner(active=False)
        self._info_label = Gtk.Label(visible=True, ellipsize="end", max_width_chars=30)
        load_label = Gtk.Label(label=get_message("Loading data..."))
        self._spinner.bind_property("active", self._spinner, "visible")
        self._spinner.bind_property("visible", load_label, "visible")
        self._spinner.bind_property("active", self._start_values_grid, "sensitive", 4)

        progress_box = Gtk.HBox(visible=True, spacing=2)
        progress_box.add(self._progress_bar)
        progress_box.pack_end(self._spinner, False, False, 0)
        progress_box.pack_start(load_label, False, False, 0)
        # Picons
        self._picons_switch = Gtk.Switch(visible=True)
        self._picon_box = Gtk.HBox(visible=True, sensitive=False, spacing=5)
        self._picon_box.pack_end(self._picons_switch, False, False, 0)
        self._picon_box.pack_end(Gtk.Label(visible=True, label=get_message("Download picons")), False, False, 0)
        # Extra box
        extra_box = Gtk.HBox(visible=True, spacing=2, margin_bottom=5, margin_top=5)
        extra_box.set_center_widget(progress_box)
        extra_box.pack_start(self._info_label, False, False, 5)
        extra_box.pack_end(self._picon_box, True, True, 5)

        frame = Gtk.Frame(visible=True, margin_bottom=5)
        frame.add(extra_box)
        self._data_box.add(frame)

        self.get_m3u(m3_path, s_type)

    @run_task
    def get_m3u(self, path, s_type):
        try:
            GLib.idle_add(self._spinner.set_property, "active", True)
            self._services = parse_m3u(path, s_type)
            for s in self._services:
                if s.picon:
                    GLib.idle_add(self._picon_box.set_sensitive, True)
                    break
        finally:
            msg = f"{get_message('Streams detected:')} {len(self._services) if self._services else 0}."
            GLib.idle_add(self._info_label.set_text, msg)
            GLib.idle_add(self._spinner.set_property, "active", False)

    def on_apply(self, item):
        if not is_data_correct(self._digit_elems):
            show_dialog(DialogType.ERROR, self._dialog, "Error. Verify the data!")
            return

        picons = {}
        services = self._services

        if not self.is_all_data_default():
            services = []
            params = [int(el.get_text()) for el in self._digit_elems]
            s_id = params[0]
            s_type = params[1]
            params = params[2:]
            st_type = get_stream_type(self._stream_type_combobox)
            sid_auto = self._sid_auto_check_button.get_active()
            sid = 0 if sid_auto else int(self._list_sid_entry.get_text())

            for i, s in enumerate(self._services, start=params[0]):
                # Skipping markers.
                if not s.data_id:
                    services.append(s)
                    continue

                params[0] = i if sid_auto else sid
                picon_id = PICON_FORMAT.format(st_type, s_id, s_type, *params)
                fav_id = get_fav_id(s.data_id, s.service, self._s_type, params, st_type, s_id, s_type)
                if s.picon:
                    picons[s.picon] = picon_id

                services.append(s._replace(picon=None, picon_id=picon_id, data_id=None, fav_id=fav_id))

        if self._picons_switch.get_active():
            if self.is_default_values():
                show_dialog(DialogType.ERROR, self._dialog,
                            "Set values for TID, NID and Namespace for correct naming of the picons!")
                return

            self.download_picons(picons)
        else:
            GLib.idle_add(self._ok_button.set_visible, True)
            GLib.idle_add(self._info_bar.set_visible, True, priority=GLib.PRIORITY_LOW)

        self._app.append_imported_services(services)

    @run_task
    def download_picons(self, picons):
        self._is_download = True
        os.makedirs(os.path.dirname(self._pic_path), exist_ok=True)
        GLib.idle_add(self._apply_button.set_sensitive, False)
        GLib.idle_add(self._progress_bar.set_visible, True)

        self._errors_count = 0
        self._url_count = len(picons)
        self._max_count = self._url_count
        self._cancellable.reset()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self.download_picon, p, picons.get(p, None)): p for p in filter(None, picons)}
            done, not_done = concurrent.futures.wait(futures, timeout=0)
            while self._is_download and not_done:
                done, not_done = concurrent.futures.wait(not_done, timeout=5)

            for future in not_done:
                future.cancel()
            concurrent.futures.wait(not_done)

            self.update_progress(self._url_count)
            self.on_done()

    def download_picon(self, url, pic_data):
        err_msg = "Picon download error: {}  [{}]"
        timeout = (3, 5)  # connect and read timeouts

        req = requests.get(url, timeout=timeout)
        if req.status_code != 200:
            log(err_msg.format(url, req.reason))
            self.update_progress(1)
        else:
            self.on_picon_load_done(req.content, pic_data)

    @run_idle
    def on_picon_load_done(self, data, user_data):
        try:
            self._info_label.set_text(f"Processing: {user_data}")
            f = Gio.MemoryInputStream.new_from_data(data)
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(f, 220, 132, False, self._cancellable)
            path = f"{self._pic_path}{user_data}"
            pixbuf.savev(path, "png", [], [])
            self._picons[user_data] = get_picon_pixbuf(path)
        except GLib.GError as e:
            self.update_progress(1)
            if e.code != Gio.IOErrorEnum.CANCELLED:
                log(f"Loading picon [{user_data}] data error: {e}")
        else:
            self.update_progress()

    @run_idle
    def update_progress(self, error=0):
        self._errors_count += error
        self._url_count -= 1
        frac = 1 - self._url_count / self._max_count
        self._progress_bar.set_fraction(frac)

    @run_idle
    def on_done(self):
        self._progress_bar.set_visible(False)
        self._progress_bar.set_fraction(0.0)
        self._apply_button.set_sensitive(True)
        self._info_label.set_text(f"Errors: {self._errors_count}.")
        self._is_download = False

        gen = self.update_fav_model()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def update_fav_model(self):
        services = self._app.current_services
        picons = self._app.picons
        model = self._app.fav_view.get_model()
        for r in model:
            s = services.get(r[Column.FAV_ID], None)
            if s:
                model.set_value(r.iter, Column.FAV_PICON, picons.get(s.picon_id, None))
                yield True

        self._info_bar.set_visible(True)
        self._ok_button.set_visible(True)
        yield True

    def on_response(self, dialog, response):
        if response == Gtk.ResponseType.APPLY:
            return True

        if response == Gtk.ResponseType.CANCEL and not self._is_download or not self.on_close():
            self._dialog.destroy()

    def on_close(self, window=None, event=None):
        if self._is_download:
            if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.OK:
                self._is_download = False
                self._cancellable.cancel()
                return False
            return True

        return False


class YtListImportDialog:
    def __init__(self, app):
        handlers = {"on_import": self.on_import,
                    "on_receive": self.on_receive,
                    "on_yt_url_entry_changed": self.on_url_entry_changed,
                    "on_yt_info_bar_close": self.on_info_bar_close,
                    "on_popup_menu": on_popup_menu,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_key_press": self.on_key_press,
                    "on_close": self.on_close}

        self.appender = app.append_imported_services
        self._settings = app.app_settings
        self._s_type = self._settings.setting_type
        self._download_task = False
        self._yt_list_id = None
        self._yt_list_title = None
        self._yt = None

        builder = get_builder(_UI_PATH, handlers, use_str=True,
                              objects=("yt_import_dialog_window", "yt_liststore", "yt_quality_liststore",
                                       "yt_popup_menu", "remove_selection_image", "yt_receive_image",
                                       "yt_import_image"))

        self._dialog = builder.get_object("yt_import_dialog_window")
        self._dialog.set_transient_for(app.app_window)
        self._list_view_scrolled_window = builder.get_object("yt_list_view_scrolled_window")
        self._model = builder.get_object("yt_liststore")
        self._progress_bar = builder.get_object("yt_progress_bar")
        self._info_bar_box = builder.get_object("yt_info_bar_box")
        self._message_label = builder.get_object("yt_info_bar_message_label")
        self._info_bar = builder.get_object("yt_info_bar")
        self._yt_count_label = builder.get_object("yt_count_label")
        self._url_entry = builder.get_object("yt_url_entry")
        self._receive_button = builder.get_object("yt_receive_button")
        self._import_button = builder.get_object("yt_import_button")
        self._quality_box = builder.get_object("yt_quality_combobox")
        self._quality_model = builder.get_object("yt_quality_liststore")
        self._import_button.bind_property("visible", self._quality_box, "visible")
        self._import_button.bind_property("sensitive", self._quality_box, "sensitive")
        self._receive_button.bind_property("sensitive", self._import_button, "sensitive")

        if IS_GNOME_SESSION or IS_DARWIN:
            header_bar = HeaderBar(title="YouTube", subtitle=get_message("Playlist import"))
            self._dialog.set_titlebar(header_bar)
            actions_box = builder.get_object("yt_actions_box")
            import_box = builder.get_object("yt_import_box")
            actions_box.remove(import_box)
            header_bar.pack_end(import_box)
            actions_box.remove(self._receive_button)
            header_bar.pack_start(self._receive_button)
            actions_box.set_visible(False)

        window_size = self._settings.get("yt_import_dialog_size")
        if window_size:
            self._dialog.resize(*window_size)
        # Style
        style_provider = Gtk.CssProvider()
        style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._url_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), style_provider,
                                                                    Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def show(self):
        self._dialog.show()

    @run_task
    def on_import(self, item):
        self.on_info_bar_close()
        self.update_active_elements(False)
        self._download_task = True

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                done_links = {}
                rows = list(filter(lambda r: r[2], self._model))
                if not self._yt:
                    self._yt = YouTube.get_instance(self._settings)

                futures = {executor.submit(self._yt.get_yt_link, r[1], YouTube.VIDEO_LINK.format(r[1]),
                                           True): r for r in rows}
                size = len(futures)
                counter = 0

                for future in concurrent.futures.as_completed(futures):
                    if not self._download_task:
                        executor.shutdown()
                        return

                    done_links[futures[future]] = future.result()
                    counter += 1
                    self.update_progress_bar(counter / size)
        except YouTubeException as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        except Exception as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            if self._download_task:
                self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO)
                self.append_services([done_links[r] for r in rows])
        finally:
            self._download_task = False
            self.update_active_elements(True)

    def on_receive(self, item):
        self.update_active_elements(False)
        self._model.clear()
        self._yt_count_label.set_text("0")
        self.on_info_bar_close()
        self.update_refs_list()

    @run_task
    def update_refs_list(self):
        if self._yt_list_id:
            try:
                if not self._yt:
                    self._yt = YouTube.get_instance(self._settings)
                self._yt_list_title, links = self._yt.get_yt_playlist(self._yt_list_id, self._url_entry.get_text())
            except Exception as e:
                self.show_info_message(str(e), Gtk.MessageType.ERROR)
                return
            else:
                gen = self.update_links(links)
                GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
            finally:
                self.update_active_elements(True)

    def update_links(self, links):
        for link in links:
            yield self._model.append((link[0], link[1], True, None))

        size = len(self._model)
        self._yt_count_label.set_text(str(size))
        self._import_button.set_visible(size)
        yield True

    @run_idle
    def append_services(self, links):
        aggr = [None] * 9
        srvs = []

        if self._yt_list_title:
            title = self._yt_list_title
            fav_id = MARKER_FORMAT.format(0, title, title)
            mk = Service(None, None, None, title, *aggr[0:3], BqServiceType.MARKER.name, *aggr, 0, fav_id, None)
            srvs.append(mk)

        act = self._quality_model.get_value(self._quality_box.get_active_iter(), 0)
        for link in links:
            lnk, title = link or (None, None)
            if not lnk:
                continue
            ln = lnk.get(act) if act in lnk else lnk[sorted(lnk, key=lambda x: int(x.rstrip("p")), reverse=True)[0]]
            fav_id = get_fav_id(ln, title, self._s_type)
            srv = Service(None, None, IPTV_ICON, title, *aggr[0:3], BqServiceType.IPTV.name, *aggr, None, fav_id, None)
            srvs.append(srv)
        self.appender(srvs)

    @run_idle
    def update_active_elements(self, sensitive):
        self._url_entry.set_sensitive(sensitive)
        self._receive_button.set_sensitive(sensitive)

    def on_url_entry_changed(self, entry):
        url_str = entry.get_text()
        yt_id = YouTube.get_yt_list_id(url_str)
        entry.set_name("GtkEntry" if yt_id else _DIGIT_ENTRY_NAME)
        self._receive_button.set_sensitive(bool(yt_id))
        self._import_button.set_sensitive(bool(yt_id))
        self._yt_list_id = yt_id

        if yt_id:
            entry.set_icon_from_pixbuf(Gtk.EntryIconPosition.SECONDARY, get_yt_icon("youtube", 32))
        else:
            entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)

    @run_idle
    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_idle
    def update_progress_bar(self, value):
        self._progress_bar.set_visible(value < 1)
        self._progress_bar.set_fraction(value)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    def on_selected_toggled(self, toggle, path):
        self._model.set_value(self._model.get_iter(path), 2, not toggle.get_active())

    def on_select_all(self, view):
        self.update_selection(view, True)

    def on_unselect_all(self, view):
        self.update_selection(view, False)

    def update_selection(self, view, select):
        view.get_model().foreach(lambda mod, path, itr: mod.set_value(itr, 2, select))

    def on_key_press(self, view, event):
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return
        key = KeyboardKey(key_code)

        if key is KeyboardKey.SPACE:
            path, column = view.get_cursor()
            itr = self._model.get_iter(path)
            selected = self._model.get_value(itr, 2)
            self._model.set_value(itr, 2, not selected)

    def on_close(self, window, event):
        if self._download_task and show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return True

        self._download_task = False
        self._settings.add("yt_import_dialog_size", self._dialog.get_size())


if __name__ == "__main__":
    pass

# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2022 Dmitriy Yefremov
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


""" Module for working with EPG. """
import gzip
import locale
import os
import re
import shutil
import urllib.request
from datetime import datetime
from enum import Enum
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from gi.repository import GLib

from app.commons import run_idle, run_task, run_with_delay
from app.connections import download_data, DownloadType, HttpAPI
from app.eparser.ecommons import BouquetService, BqServiceType
from app.settings import SEP, EpgSource
from app.tools.epg import EPG, ChannelsParser, EpgEvent, XmlTvReader
from app.ui.dialogs import get_message, show_dialog, DialogType, get_builder
from app.ui.tasks import BGTaskWidget
from app.ui.timers import TimerTool
from ..main_helper import on_popup_menu, update_entry_data, scroll_to
from ..uicommons import Gtk, Gdk, UI_RESOURCES_PATH, Column, EPG_ICON, KeyboardKey, IS_GNOME_SESSION, Page


class RefsSource(Enum):
    SERVICES = 0
    XML = 1


class EpgCache(dict):
    def __init__(self, app):
        super().__init__()
        self._current_bq = None
        self._reader = None
        self._canceled = False

        self._settings = app.app_settings
        self._src = self._settings.epg_source
        self._app = app
        self._app.connect("bouquet-changed", self.on_bouquet_changed)
        self._app.connect("profile-changed", self.on_profile_changed)
        self._app.connect("task-canceled", self.on_xml_load_cancel)

        self.init()

    @run_idle
    def init(self):
        if self._src is EpgSource.XML:
            url = self._settings.epg_xml_source
            gz_file = f"{self._settings.profile_data_path}epg{os.sep}epg.gz"
            self._reader = XmlTvReader(gz_file, url)

            def process_data():
                t = BGTaskWidget(self._app, "Processing XMLTV data...", self._reader.parse, )
                self._app.emit("add-background-task", t)

            if os.path.isfile(gz_file):
                # Difference calculation between the current time and file modification.
                dif = datetime.now() - datetime.fromtimestamp(os.path.getmtime(gz_file))
                # We will update daily. -> Temporarily!!!
                if dif.days > 0 and not self._canceled:
                    task = BGTaskWidget(self._app, "Downloading EPG...", self._reader.download, process_data, )
                    self._app.emit("add-background-task", task)
                else:
                    process_data()
            else:
                if not self._canceled:
                    task = BGTaskWidget(self._app, "Downloading EPG...", self._reader.download, process_data, )
                    self._app.emit("add-background-task", task)
        elif self._src is EpgSource.DAT:
            self._reader = EPG.DatReader(f"{self._settings.profile_data_path}epg{os.sep}epg.dat")
            self._reader.download()

        GLib.timeout_add_seconds(self._settings.epg_update_interval, self.update_epg_data, priority=GLib.PRIORITY_LOW)

    def on_bouquet_changed(self, app, bq):
        self._current_bq = bq

    def on_profile_changed(self, app, p):
        self.clear()

    def on_xml_load_cancel(self, app, widget):
        self._canceled = True

    def update_epg_data(self):
        if self._src is EpgSource.HTTP:
            api = self._app.http_api
            bq = self._app.current_bouquet_files.get(self._current_bq, None)

            if bq and api:
                req = quote(f'FROM BOUQUET "userbouquet.{bq}.{self._current_bq.split(":")[-1]}"')
                api.send(HttpAPI.Request.EPG_NOW, f'1:7:1:0:0:0:0:0:0:0:{req}', self.update_http_data)
        elif self._src is EpgSource.XML:
            self.update_xml_data()

        return self._app.display_epg

    def update_http_data(self, epg):
        for e in (EpgTool.get_event(e, False) for e in epg.get("event_list", []) if e.get("e2eventid", "").isdigit()):
            self[e.event_data.get("e2eventservicename", "")] = e

    @run_task
    def update_xml_data(self):
        services = self._app.current_services
        names = {services[s].service for s in self._app.current_bouquets.get(self._current_bq, [])}
        for name, e in self._reader.get_current_events(names).items():
            self[name] = e

    def get_current_event(self, service_name):
        return self.get(service_name, EpgEvent())


class EpgSettingsPopover(Gtk.Popover):

    def __init__(self, app, **kwarg):
        super().__init__(**kwarg)
        self._app = app
        self._app.connect("profile-changed", self.on_profile_changed)

        handlers = {"on_apply": self.on_apply,
                    "on_close": lambda b: self.popdown()}
        builder = get_builder(f"{UI_RESOURCES_PATH}epg{SEP}settings.glade", handlers)
        self.add(builder.get_object("main_box"))

        self._http_src_button = builder.get_object("http_src_button")
        self._xml_src_button = builder.get_object("xml_src_button")
        self._dat_src_button = builder.get_object("dat_src_button")
        self._interval_button = builder.get_object("interval_button")
        self._url_entry = builder.get_object("url_entry")
        self._dat_path_box = builder.get_object("dat_path_box")

        self.init()

    def init(self):
        settings = self._app.app_settings
        src = settings.epg_source
        if src is EpgSource.HTTP:
            self._http_src_button.set_active(True)
        elif src is EpgSource.XML:
            self._xml_src_button.set_active(True)
        else:
            self._dat_src_button.set_active(True)

        self._interval_button.set_value(settings.epg_update_interval)
        self._url_entry.set_text(settings.epg_xml_source)
        self._dat_path_box.set_active_id(settings.epg_dat_path)

    def on_apply(self, button):
        settings = self._app.app_settings
        if self._http_src_button.get_active():
            settings.epg_source = EpgSource.HTTP
        elif self._xml_src_button.get_active():
            settings.epg_source = EpgSource.XML
        else:
            settings.epg_source = EpgSource.DAT

        settings.epg_update_interval = self._interval_button.get_value()
        settings.epg_xml_source = self._url_entry.get_text()
        settings.epg_dat_path = self._dat_path_box.get_active_id()
        self.popdown()

        self._app.change_action_state("display_epg", GLib.Variant.new_boolean(True))

    def on_profile_changed(self, app, p):
        self.init()


class EpgTool(Gtk.Box):
    def __init__(self, app, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._current_bq = None
        self._app = app
        self._app.connect("fav-changed", self.on_service_changed)
        self._app.connect("bouquet-changed", self.on_bouquet_changed)

        handlers = {"on_epg_press": self.on_epg_press,
                    "on_timer_add": self.on_timer_add,
                    "on_epg_filter_changed": self.on_epg_filter_changed,
                    "on_epg_filter_toggled": self.on_epg_filter_toggled,
                    "on_view_query_tooltip": self.on_view_query_tooltip,
                    "on_multi_epg_toggled": self.on_multi_epg_toggled}

        builder = get_builder(f"{UI_RESOURCES_PATH}epg{SEP}tab.glade", handlers)

        self._view = builder.get_object("epg_view")
        self._model = builder.get_object("epg_model")
        self._filter_model = builder.get_object("epg_filter_model")
        self._filter_model.set_visible_func(self.epg_filter_function)
        self._filter_entry = builder.get_object("epg_filter_entry")
        self._multi_epg_button = builder.get_object("multi_epg_button")
        self._event_count_label = builder.get_object("event_count_label")
        self.pack_start(builder.get_object("epg_frame"), True, True, 0)
        # Custom sort function.
        self._view.get_model().set_sort_func(2, self.time_sort_func, 2)

        self.show()

    def on_timer_add(self, action=None, value=None):
        model, paths = self._view.get_selection().get_selected_rows()
        p_count = len(paths)

        if p_count == 1:
            dialog = TimerTool.TimerDialog(self._app.app_window, TimerTool.TimerAction.EVENT, model[paths][-1])
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                gen = self.write_timers_list([dialog.get_request()])
                GLib.idle_add(lambda: next(gen, False))
            dialog.destroy()
        elif p_count > 1:
            if show_dialog(DialogType.QUESTION, self._app.app_window,
                           "Add timers for selected events?") != Gtk.ResponseType.OK:
                return True

            self.add_timers_list((model[p][-1] for p in paths))
        else:
            self._app.show_error_message("No selected item!")

    def add_timers_list(self, paths):
        ref_str = "timeraddbyeventid?sRef={}&eventid={}&justplay=0"
        refs = [ref_str.format(quote(ev.get("e2eventservicereference", "")), ev.get("e2eventid", "")) for ev in paths]

        gen = self.write_timers_list(refs)
        GLib.idle_add(lambda: next(gen, False))

    def write_timers_list(self, refs):
        self._app.wait_dialog.show()
        tasks = list(refs)
        for ref in refs:
            self._app.send_http_request(HttpAPI.Request.TIMER, ref, lambda x: tasks.pop())
            yield True

        while tasks:
            yield True

        self._app.emit("change-page", Page.TIMERS.value)

    def on_epg_press(self, view, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS and len(view.get_model()) > 0:
            self.on_timer_add()

    def on_service_changed(self, app, ref):
        if app.page is Page.EPG:
            if self._multi_epg_button.get_active():
                ref += ":"
                path = next((r.path for r in self._model if r[-1].get("e2eventservicereference", None) == ref), None)
                scroll_to(path, self._view) if path else None
            else:
                self._app.wait_dialog.show()
                self._app.send_http_request(HttpAPI.Request.EPG, quote(ref), self.update_epg_data)

    @run_idle
    def update_epg_data(self, epg):
        self._event_count_label.set_text("0")
        self._model.clear()
        list(map(self._model.append, (self.get_event(e) for e in epg.get("event_list", [])
                                      if e.get("e2eventid", "").isdigit())))
        self._event_count_label.set_text(str(len(self._model)))
        self._app.wait_dialog.hide()

    @staticmethod
    def get_event(event, show_day=True):
        t_str = f"{'%a, ' if show_day else ''}%x, %H:%M"
        s_name = event.get("e2eventservicename", "")
        title = event.get("e2eventtitle", "") or ""
        desc = event.get("e2eventdescription", "") or ""
        desc = desc.strip()

        start = int(event.get("e2eventstart", "0"))
        start_time = datetime.fromtimestamp(start)
        end_time = datetime.fromtimestamp(start + int(event.get("e2eventduration", "0")))
        ev_time = f"{start_time.strftime(t_str)} - {end_time.strftime('%H:%M')}"

        return EpgEvent(s_name, title, ev_time, desc, event)

    def on_epg_filter_changed(self, entry):
        self._filter_model.refilter()

    def on_epg_filter_toggled(self, button):
        if not button.get_active():
            self._filter_entry.set_text("")

    def epg_filter_function(self, model, itr, data):
        txt = self._filter_entry.get_text().upper()
        return next((s for s in model.get(itr, 0, 1, 2, 3) if txt in s.upper()), False)

    def time_sort_func(self, model, iter1, iter2, column):
        """ Custom sort function for time column. """
        event1 = model.get_value(iter1, 4)
        event2 = model.get_value(iter2, 4)

        return int(event1.get("e2eventstart", "0")) - int(event2.get("e2eventstart", "0"))

    def on_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        dst = view.get_dest_row_at_pos(x, y)
        if not dst:
            return False

        path, pos = dst
        model = view.get_model()
        data = model[path][-1]
        desc = data.get("e2eventdescription", "") or ""
        ext_desc = data.get("e2eventdescriptionextended", "") or ""

        tooltip.set_text(ext_desc if ext_desc else desc)
        view.set_tooltip_row(tooltip, path)

        return True

    def on_multi_epg_toggled(self, button):
        self._model.clear()
        self._event_count_label.set_text("0")

        if button.get_active():
            self.get_multi_epg()

    def on_bouquet_changed(self, app, bq):
        self._current_bq = bq
        if app.page is Page.EPG and self._multi_epg_button.get_active():
            self.get_multi_epg()

    def get_multi_epg(self):
        if not self._current_bq:
            return

        self._app.wait_dialog.show()
        bq = self._app.current_bouquet_files.get(self._current_bq, None)
        api = self._app.http_api

        if bq and api:
            tm = datetime.now().timestamp()
            req = quote(f'FROM BOUQUET "userbouquet.{bq}.{self._current_bq.split(":")[-1]}"&time={tm}')
            api.send(HttpAPI.Request.EPG_MULTI, f'1:7:1:0:0:0:0:0:0:0:{req}', self.update_epg_data, timeout=15)


class EpgDialog:

    def __init__(self, app, bouquet, bouquet_name):

        handlers = {"on_close_dialog": self.on_close_dialog,
                    "on_apply": self.on_apply,
                    "on_update": self.on_update,
                    "on_save_to_xml": self.on_save_to_xml,
                    "on_auto_configuration": self.on_auto_configuration,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_filter_changed": self.on_filter_changed,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_popup_menu": on_popup_menu,
                    "on_bouquet_popup_menu": self.on_bouquet_popup_menu,
                    "on_copy_ref": self.on_copy_ref,
                    "on_assign_ref": self.on_assign_ref,
                    "on_reset": self.on_reset,
                    "on_list_reset": self.on_list_reset,
                    "on_drag_begin": self.on_drag_begin,
                    "on_drag_data_get": self.on_drag_data_get,
                    "on_drag_data_received": self.on_drag_data_received,
                    "on_resize": self.on_resize,
                    "on_names_source_changed": self.on_names_source_changed,
                    "on_options_save": self.on_options_save,
                    "on_use_web_source_switch": self.on_use_web_source_switch,
                    "on_enable_filtering_switch": self.on_enable_filtering_switch,
                    "on_update_on_start_switch": self.on_update_on_start_switch,
                    "on_field_icon_press": self.on_field_icon_press,
                    "on_key_press": self.on_key_press,
                    "on_bq_cursor_changed": self.on_bq_cursor_changed}

        self._app = app
        self._services = {}
        self._ex_services = self._app.current_services
        self._ex_fav_model = self._app.fav_view.get_model()
        self._settings = self._app.app_settings
        self._bouquet = bouquet
        self._bouquet_name = bouquet_name
        self._current_ref = []
        self._enable_dat_filter = False
        self._use_web_source = False
        self._update_epg_data_on_start = False
        self._refs_source = RefsSource.SERVICES
        self._download_xml_is_active = False

        builder = get_builder(f"{UI_RESOURCES_PATH}epg{SEP}dialog.glade", handlers)

        self._dialog = builder.get_object("epg_dialog_window")
        self._dialog.set_transient_for(self._app.app_window)
        self._source_view = builder.get_object("source_view")
        self._bouquet_view = builder.get_object("bouquet_view")
        self._bouquet_model = builder.get_object("bouquet_list_store")
        self._services_model = builder.get_object("services_list_store")
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")
        self._assign_ref_popup_item = builder.get_object("bouquet_assign_ref_popup_item")
        self._left_action_box = builder.get_object("left_action_box")
        self._xml_download_progress_bar = builder.get_object("xml_download_progress_bar")
        # Filter
        self._filter_bar = builder.get_object("filter_bar")
        self._filter_entry = builder.get_object("filter_entry")
        self._filter_auto_switch = builder.get_object("filter_auto_switch")
        self._services_filter_model = builder.get_object("services_filter_model")
        self._services_filter_model.set_visible_func(self.services_filter_function)
        # Info
        self._source_count_label = builder.get_object("source_count_label")
        self._source_info_label = builder.get_object("source_info_label")
        self._bouquet_count_label = builder.get_object("bouquet_count_label")
        self._bouquet_epg_count_label = builder.get_object("bouquet_epg_count_label")
        # Options
        self._xml_radiobutton = builder.get_object("xml_radiobutton")
        self._xml_chooser_button = builder.get_object("xml_chooser_button")
        self._names_source_box = builder.get_object("names_source_box")
        self._web_source_box = builder.get_object("web_source_box")
        self._use_web_source_switch = builder.get_object("use_web_source_switch")
        self._url_to_xml_entry = builder.get_object("url_to_xml_entry")
        self._enable_filtering_switch = builder.get_object("enable_filtering_switch")
        self._epg_dat_path_entry = builder.get_object("epg_dat_path_entry")
        self._epg_dat_stb_path_entry = builder.get_object("epg_dat_stb_path_entry")
        self._update_on_start_switch = builder.get_object("update_on_start_switch")
        self._epg_dat_source_box = builder.get_object("epg_dat_source_box")

        if IS_GNOME_SESSION:
            header_bar = Gtk.HeaderBar(visible=True, show_close_button=True, title="EPG",
                                       subtitle=get_message("List configuration"))
            self._dialog.set_titlebar(header_bar)
            builder.get_object("left_action_box").reparent(header_bar)
            right_box = builder.get_object("right_action_box")
            builder.get_object("main_actions_box").remove(right_box)
            header_bar.pack_end(right_box)
            builder.get_object("toolbar_box").set_visible(False)

        self._app.connect("epg-dat-downloaded", self.on_epg_dat_downloaded)

        # Setting the last size of the dialog window
        window_size = self._settings.get("epg_tool_window_size")
        if window_size:
            self._dialog.resize(*window_size)

        self.init_drag_and_drop()
        self.on_update()

    def show(self):
        self._dialog.show()

    def on_close_dialog(self, window, event):
        self._download_xml_is_active = False

    @run_idle
    def on_apply(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self._bouquet.clear()
        list(map(self._bouquet.append, [r[Column.FAV_ID] for r in self._bouquet_model]))
        p_ids = {r[Column.FAV_ID]: r[Column.FAV_POS] for r in self._bouquet_model}
        for index, row in enumerate(self._ex_fav_model):
            fav_id = self._bouquet[index]
            row[Column.FAV_ID] = fav_id
            if row[Column.FAV_TYPE] == BqServiceType.IPTV.name:
                old_fav_id = self._services[fav_id]
                srv = self._ex_services.pop(old_fav_id, None)
                if srv:
                    picon_id = p_ids.get(fav_id) or srv.picon_id
                    self._ex_services[fav_id] = srv._replace(fav_id=fav_id, picon_id=picon_id)
        self._dialog.destroy()

    @run_idle
    def on_update(self, item=None):
        self.clear_data()
        self.init_options()
        if self._update_epg_data_on_start:
            self.download_epg_from_stb()
        else:
            gen = self.init_data()
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def clear_data(self):
        self._services_model.clear()
        self._bouquet_model.clear()
        self._services.clear()
        self._source_info_label.set_text("")
        self._bouquet_epg_count_label.set_text("")
        self.on_info_bar_close()

    def init_data(self):
        gen = self.init_bouquet_data()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

        refs = None
        if self._enable_dat_filter:
            try:
                epg_reader = EPG.DatReader(f"{self._epg_dat_path_entry.get_text()}epg.dat")
                epg_reader.read()
                refs = epg_reader.get_refs()
            except (OSError, ValueError) as e:
                self.show_info_message(f"Read data error: {e}", Gtk.MessageType.ERROR)
                return
            yield True

        if self._refs_source is RefsSource.SERVICES:
            yield from self.init_lamedb_source(refs)
        elif self._refs_source is RefsSource.XML:
            xml_gen = self.init_xml_source(refs)
            try:
                yield from xml_gen
            except ValueError as e:
                self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            self.show_info_message("Unknown names source!", Gtk.MessageType.ERROR)
        yield True

    def init_bouquet_data(self):
        for r in self._ex_fav_model:
            row = [*r[:]]
            fav_id = r[Column.FAV_ID]
            self._services[fav_id] = self._ex_services[fav_id].fav_id
            yield self._bouquet_model.append(row)
        self._bouquet_count_label.set_text(str(len(self._bouquet_model)))
        yield True

    def init_lamedb_source(self, refs):
        srvs = {k[:k.rfind(":")]: v for k, v in self._ex_services.items()}
        s_types = (BqServiceType.MARKER.value, BqServiceType.IPTV.value)
        filtered = filter(None, [srvs.get(ref) for ref in refs]) if refs else filter(
            lambda s: s.service_type not in s_types, self._ex_services.values())

        factor = self._app.DEL_FACTOR / 4
        for index, srv in enumerate(filtered):
            self._services_model.append((srv.service, srv.pos, srv.fav_id, srv.picon_id))
            if index % factor == 0:
                yield True

        self.update_source_count_info()
        yield True

    def init_xml_source(self, refs):
        path = self._epg_dat_path_entry.get_text() if self._use_web_source else self._xml_chooser_button.get_filename()
        if not path:
            self.show_info_message("The path to the xml file is not set!", Gtk.MessageType.ERROR)
            return

        if self._use_web_source:
            #  Downloading gzipped xml file that contains services names with references from the web.
            self._download_xml_is_active = True
            self.update_active_header_elements(False)
            url = self._url_to_xml_entry.get_text()

            try:
                with urllib.request.urlopen(url, timeout=2) as fp:
                    headers = fp.info()
                    content_type = headers.get("Content-Type", "")

                    if content_type != "application/gzip":
                        self._download_xml_is_active = False
                        raise ValueError("{} {} {}".format(get_message("Download XML file error."),
                                                           get_message("Unsupported file type:"),
                                                           content_type))

                    file_name = os.path.basename(url)
                    data_path = self._epg_dat_path_entry.get_text()

                    with open(data_path + file_name, "wb") as tfp:
                        bs = 1024 * 8
                        size = -1
                        read = 0
                        b_num = 0
                        if "content-length" in headers:
                            size = int(headers["Content-Length"])

                        while self._download_xml_is_active:
                            block = fp.read(bs)
                            if not block:
                                break
                            read += len(block)
                            tfp.write(block)
                            b_num += 1
                            self.update_download_progress(b_num * bs / size)
                            yield True

                        path = tfp.name.rstrip(".gz")
            except (HTTPError, URLError) as e:
                raise ValueError(f"{get_message('Download XML file error.')} {e}")
            else:
                try:
                    with open(path, "wb") as f_out:
                        with gzip.open(tfp.name, "rb") as f:
                            shutil.copyfileobj(f, f_out)
                    os.remove(tfp.name)
                except Exception as e:
                    raise ValueError(f"{get_message('Unpacking data error.')} {e}")
            finally:
                self._download_xml_is_active = False
                self.update_active_header_elements(True)

        try:
            s_refs, info = ChannelsParser.get_refs_from_xml(path)
            yield True
        except Exception as e:
            raise ValueError(f"{get_message('XML parsing error:')} {e}")
        else:
            if refs:
                s_refs = filter(lambda x: x.num in refs, s_refs)

            factor = self._app.DEL_FACTOR / 4
            for index, srv in enumerate(s_refs):
                self._services_model.append((srv.name, " ", srv.data, ""))
                if index % factor == 0:
                    yield True

            self.update_source_info(info)
            self.update_source_count_info()
            yield True

    def on_key_press(self, view, event):
        """  Handling  keystrokes  """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return
        key = KeyboardKey(key_code)
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK

        if ctrl and key is KeyboardKey.C:
            self.on_copy_ref()
        elif ctrl and key is KeyboardKey.V:
            self.on_assign_ref()

    def on_bq_cursor_changed(self, view):
        if self._filter_bar.get_visible() and self._filter_auto_switch.get_active():
            path, column = view.get_cursor()
            model = view.get_model()
            if path:
                self._filter_entry.set_text(model[path][Column.FAV_SERVICE] or "")

    @run_idle
    def on_save_to_xml(self, item):
        response = show_dialog(DialogType.CHOOSER, self._dialog, settings=self._settings)
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        services = []
        iptv_types = (BqServiceType.IPTV.value, BqServiceType.MARKER.value)
        for r in self._bouquet_model:
            srv_type = r[Column.FAV_TYPE]
            if srv_type in iptv_types:
                srv = BouquetService(name=r[Column.FAV_SERVICE],
                                     type=BqServiceType(srv_type),
                                     data=r[Column.FAV_ID],
                                     num=r[Column.FAV_NUM])
                services.append(srv)

        ChannelsParser.write_refs_to_xml("{}{}.xml".format(response, self._bouquet_name), services)
        self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO)

    @run_idle
    def on_auto_configuration(self, item):
        """ Simple mapping of services by name. """
        use_cyrillic = locale.getdefaultlocale()[0] in ("ru_RU", "be_BY", "uk_UA", "sr_RS")
        tr = None
        if use_cyrillic:
            # may be not entirely correct
            symbols = (u"АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯІÏҐЎЈЂЉЊЋЏTB",
                       u"ABVGDEEJZIJKLMNOPRSTUFHZCSS_Y_EUAIEGUEDLNCJTV")
            tr = {ord(k): ord(v) for k, v in zip(*symbols)}

        source = {}
        for row in self._services_model:
            name = re.sub("\\W+", "", str(row[0])).upper()
            name = name.translate(tr) if use_cyrillic else name
            source[name] = row

        success_count = 0
        not_founded = {}

        for r in self._bouquet_model:
            if r[Column.FAV_TYPE] != BqServiceType.IPTV.value:
                continue
            name = re.sub("\\W+", "", str(r[Column.FAV_SERVICE])).upper()
            if use_cyrillic:
                name = name.translate(tr)
            ref = source.get(name, None)  # Not [pop], because the list may contain duplicates or similar names!
            if ref:
                self.assign_data(r, ref, True)
                success_count += 1
            else:
                not_founded[name] = r
        # Additional attempt to search in the remaining elements
        for n in not_founded:
            for k in source:
                if k.startswith(n):
                    self.assign_data(not_founded[n], source[k], True)
                    success_count += 1
                    break

        self.update_epg_count()
        self.show_info_message("{} {} {}".format(get_message("Done!"),
                                                 get_message("Count of successfully configured services:"),
                                                 success_count), Gtk.MessageType.INFO)

    def assign_refs(self, model, paths, data):
        [self.assign_data(model[p], data) for p in paths]
        self.update_epg_count()

    def assign_data(self, row, data, show_error=False):
        if row[Column.FAV_TYPE] != BqServiceType.IPTV.value:
            if not show_error:
                self.show_info_message(get_message("Not allowed in this context!"), Gtk.MessageType.ERROR)
            return

        fav_id = row[Column.FAV_ID]
        fav_id_data = fav_id.split(":")
        fav_id_data[3:7] = data[-2].split(":")
        new_fav_id = ":".join(fav_id_data)
        service = self._services.pop(fav_id, None)
        if service:
            self._services[new_fav_id] = service
            row[Column.FAV_ID] = new_fav_id
            row[Column.FAV_LOCKED] = EPG_ICON
            if data[-1]:
                row[Column.FAV_POS] = data[-1]
                p_data = data[-1].split("_")
                if p_data:
                    fav_id_data[2] = p_data[2]
            pos = f"({data[1] if self._refs_source is RefsSource.SERVICES else 'XML'})"
            src = f"{get_message('EPG source')}: {(GLib.markup_escape_text(data[0] or ''))} {pos}"
            row[Column.FAV_TOOLTIP] = f"{get_message('Service reference')}: {':'.join(fav_id_data[:10])}\n{src}"

    def on_filter_toggled(self, button):
        self._filter_bar.set_visible(button.get_active())
        if not button.get_active():
            self._filter_entry.set_text("")

    @run_with_delay(1)
    def on_filter_changed(self, entry):
        self._services_filter_model.refilter()

    def services_filter_function(self, model, itr, data):
        txt = self._filter_entry.get_text().upper()
        return model is None or model == "None" or txt in model.get_value(itr, 0).upper()

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    def on_copy_ref(self, item=None):
        model, paths = self._source_view.get_selection().get_selected_rows()
        self._current_ref.clear()
        if paths:
            self._current_ref.append(model[paths][:])

    def on_assign_ref(self, item=None):
        if self._current_ref:
            model, paths = self._bouquet_view.get_selection().get_selected_rows()
            self.assign_refs(model, paths, self._current_ref.pop())

    @run_idle
    def on_reset(self, item):
        model, paths = self._bouquet_view.get_selection().get_selected_rows()
        if paths:
            row = self._bouquet_model[paths]
            self.reset_row_data(row)
            self.update_epg_count()

    @run_idle
    def on_list_reset(self, item):
        list(map(self.reset_row_data, self._bouquet_model))
        self.update_epg_count()

    def reset_row_data(self, row):
        default_fav_id = self._services.pop(row[Column.FAV_ID], None)
        if default_fav_id:
            self._services[default_fav_id] = default_fav_id
            row[Column.FAV_ID], row[Column.FAV_LOCKED], row[Column.FAV_TOOLTIP] = default_fav_id, None, None

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    @run_idle
    def update_source_info(self, info):
        lines = info.split("\n")
        self._source_info_label.set_text(lines[0] if lines else "")
        self._source_view.set_tooltip_text(info)

    @run_idle
    def update_source_count_info(self):
        source_count = len(self._services_model)
        self._source_count_label.set_text(str(source_count))
        if self._enable_dat_filter and source_count == 0:
            msg = get_message("Current epg.dat file does not contains references for the services of this bouquet!")
            self.show_info_message(msg, Gtk.MessageType.WARNING)

    @run_idle
    def update_epg_count(self):
        count = len(list((filter(None, [r[Column.FAV_LOCKED] for r in self._bouquet_model]))))
        self._bouquet_epg_count_label.set_text(str(count))

    @run_idle
    def update_active_header_elements(self, state):
        self._left_action_box.set_sensitive(state)
        self._xml_download_progress_bar.set_visible(not state)
        self._source_info_label.set_text("" if state else "Downloading XML:")

    @run_idle
    def update_download_progress(self, value):
        self._xml_download_progress_bar.set_fraction(value)

    def on_bouquet_popup_menu(self, menu, event):
        self._assign_ref_popup_item.set_sensitive(self._current_ref)
        on_popup_menu(menu, event)

    # ***************** Drag-and-drop *********************#

    def init_drag_and_drop(self):
        """ Enable drag-and-drop. """
        target = []
        self._source_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.COPY)
        self._source_view.drag_source_add_text_targets()
        self._bouquet_view.enable_model_drag_dest(target, Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._bouquet_view.drag_dest_add_text_targets()

    def on_drag_begin(self, view, context):
        """ Selects a row under the cursor in the view at the dragging beginning. """
        selection = view.get_selection()
        if selection.count_selected_rows() > 1:
            view.do_toggle_cursor_row(view)

    def on_drag_data_get(self, view, drag_context, data, info, time):
        model, paths = view.get_selection().get_selected_rows()
        if paths:
            s_data = model[paths][:]
            if all(s_data[:-1]):
                data.set_text("::::".join(s_data), -1)
            else:
                self.show_info_message(get_message("Source error!"), Gtk.MessageType.ERROR)

    def on_drag_data_received(self, view, drag_context, x, y, data, info, time):
        path, pos = view.get_dest_row_at_pos(x, y)
        model = view.get_model()
        data = data.get_text()
        if data:
            data = data.split("::::")
            self.assign_refs(model, path, data)
        return False

    # ***************** Options *********************#

    def init_options(self):
        epg_dat_path = "{}epg{}".format(self._settings.profile_data_path, SEP)
        self._epg_dat_path_entry.set_text(epg_dat_path)
        default_epg_data_stb_path = "/etc/enigma2"
        epg_options = self._settings.epg_options
        if epg_options:
            self._refs_source = RefsSource.XML if epg_options.get("xml_source", False) else RefsSource.SERVICES
            self._xml_radiobutton.set_active(self._refs_source is RefsSource.XML)
            self._use_web_source = epg_options.get("use_web_source", False)
            self._use_web_source_switch.set_active(self._use_web_source)
            self._url_to_xml_entry.set_text(epg_options.get("url_to_xml", ""))
            self._enable_dat_filter = epg_options.get("enable_filtering", False)
            self._enable_filtering_switch.set_active(self._enable_dat_filter)
            epg_dat_path = epg_options.get("epg_dat_path", epg_dat_path)
            self._epg_dat_path_entry.set_text(epg_dat_path)
            self._epg_dat_stb_path_entry.set_text(epg_options.get("epg_dat_stb_path", default_epg_data_stb_path))
            self._update_epg_data_on_start = epg_options.get("epg_data_update_on_start", False)
            self._update_on_start_switch.set_active(self._update_epg_data_on_start)
            local_xml_path = epg_options.get("local_path_to_xml", None)
            if local_xml_path:
                self._xml_chooser_button.set_filename(local_xml_path)
        os.makedirs(os.path.dirname(self._epg_dat_path_entry.get_text()), exist_ok=True)

    def on_options_save(self, item=None):
        self._settings.epg_options = {"xml_source": self._xml_radiobutton.get_active(),
                                      "use_web_source": self._use_web_source_switch.get_active(),
                                      "local_path_to_xml": self._xml_chooser_button.get_filename(),
                                      "url_to_xml": self._url_to_xml_entry.get_text(),
                                      "enable_filtering": self._enable_filtering_switch.get_active(),
                                      "epg_dat_path": self._epg_dat_path_entry.get_text(),
                                      "epg_dat_stb_path": self._epg_dat_stb_path_entry.get_text(),
                                      "epg_data_update_on_start": self._update_on_start_switch.get_active()}

    def on_resize(self, window):
        if self._settings:
            self._settings.add("epg_tool_window_size", window.get_size())

    def on_names_source_changed(self, button):
        self._refs_source = RefsSource.XML if button.get_active() else RefsSource.SERVICES
        self._names_source_box.set_sensitive(button.get_active())

    def on_enable_filtering_switch(self, switch, state):
        self._epg_dat_source_box.set_sensitive(state)
        self._update_on_start_switch.set_active(False if not state else self._update_epg_data_on_start)

    def on_update_on_start_switch(self, switch, state):
        pass

    def on_use_web_source_switch(self, switch, state):
        self._web_source_box.set_sensitive(state)
        self._xml_chooser_button.set_sensitive(not state)

    def on_field_icon_press(self, entry, icon, event_button):
        update_entry_data(entry, self._dialog, self._settings)

    # ***************** Downloads *********************#

    def on_epg_dat_downloaded(self, app, value):
        gen = self.init_data()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    @run_task
    def download_epg_from_stb(self):
        """ Download the epg.dat file via ftp from the receiver. """
        try:
            download_data(settings=self._settings, download_type=DownloadType.EPG, callback=print)
        except Exception as e:
            GLib.idle_add(self.show_info_message, f"Download epg.dat file error: {e}", Gtk.MessageType.ERROR)
        else:
            GLib.idle_add(self._app.emit, "epg-dat-downloaded", None)


if __name__ == "__main__":
    pass

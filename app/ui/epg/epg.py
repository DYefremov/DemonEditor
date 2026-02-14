# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2025 Dmitriy Yefremov
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
import abc
import gzip
import json
import locale
import os
import re
import shutil
import urllib.request
from datetime import datetime
from enum import Enum
from hashlib import sha1
from itertools import chain
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from gi.repository import GLib

from app.commons import run_idle, run_task, run_with_delay, log
from app.connections import download_data, DownloadType, HttpAPI
from app.eparser.ecommons import BouquetService, BqServiceType
from app.settings import SEP, EpgSource, IS_WIN
from app.tools.epg import EPG, ChannelsParser, EpgEvent, XmlTvReader
from app.ui.dialogs import translate, show_dialog, DialogType, get_builder, get_chooser_dialog
from app.ui.tasks import BGTaskWidget
from app.ui.timers import TimerTool
from ..main_helper import on_popup_menu, update_entry_data, scroll_to, update_toggle_model, update_filter_sat_positions, \
    show_info_bar_message
from ..uicommons import Gtk, Gdk, UI_RESOURCES_PATH, Column, EPG_ICON, KeyboardKey, Page, HeaderBar


class RefsSource(Enum):
    SERVICES = 0
    XML = 1


class StringComparer:
    """ Additional string similarity comparer. """

    class ALG(Enum):
        JARO = "Jaro-Winkler"

    @staticmethod
    def jaro_distance(s1, s2):
        """ Returns [Jaro-Winkler] distance of two strings."""
        if s1 == s2:
            return 1.0

        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0

        match = 0
        max_dist = (max(len(s1), len(s2)) // 2) - 1
        s1_hash = [0] * len(s1)
        s2_hash = [0] * len(s2)

        for i in range(len1):
            for j in range(max(0, i - max_dist), min(len2, i + max_dist + 1)):
                if s1[i] == s2[j] and s2_hash[j] == 0:
                    s1_hash[i] = 1
                    s2_hash[j] = 1
                    match += 1
                    break

        if match == 0:
            return 0.0

        t = 0
        point = 0

        for i in range(len1):
            if s1_hash[i]:
                while s2_hash[point] == 0:
                    point += 1

                if s1[i] != s2[point]:
                    point += 1
                    t += 1
                else:
                    point += 1
            t /= 2

        return (match / len1 + match / len2 + (match - t) / match) / 3.0

    @staticmethod
    def is_similar(s1, s2, alg, max_ch=4, ratio=0.92):
        """ Returns similarity of two strings. """
        if alg is StringComparer.ALG.JARO:
            dist = StringComparer.jaro_distance(s1, s2)
            if dist > 0.7:
                prefix = 0
                for i in range(min(len(s1), len(s2))):
                    if s1[i] == s2[i]:
                        prefix += 1
                    else:
                        break

                prefix = min(max_ch, prefix)  # Maximum of [max_ch] characters are allowed in prefix!
                dist += 0.1 * prefix * (1 - dist)

            return dist > ratio
        else:
            raise ValueError(f"This algorithm [{alg}] is not supported!")


class EpgCache(abc.ABC):
    _CACHE_FILE = "epg-name-cache"
    NAME_CACHE = {}  # service name -> id (tvg-id for *.m3u)

    def __init__(self, app):
        super().__init__()
        self.events = {}

        self._reader = None
        self._canceled = False
        self._is_run = False
        self._current_bq = app.current_bouquet
        self._page = Page.SERVICES

        self._settings = app.app_settings
        self._src = EpgSource.XML
        self._xml_src = None
        self._path = None

        self._app = app
        self._app.connect("bouquet-changed", self.on_bouquet_changed)
        self._app.connect("profile-changed", self.on_profile_changed)
        self._app.connect("epg-settings-changed", self.on_settings_changed)
        self._app.connect("task-canceled", self.on_xml_load_cancel)

        if self._app.app_settings.enable_epg_name_cache:
            self.init_name_cache(self._app.app_settings.default_data_path)

    @property
    def current_reader(self):
        return self._reader

    @property
    def is_run(self):
        return self._is_run

    @property
    def current_gz_file_name(self):
        return self.get_gz_file_name(self._settings.epg_xml_source, self._settings.profile_data_path)

    def on_bouquet_changed(self, app, bq):
        self._current_bq = bq

    def on_profile_changed(self, app, p):
        self._xml_src = self._settings.epg_xml_source
        self.reset()

    def on_settings_changed(self, app, page):
        if page is self._page:
            self.on_profile_changed(app, page)

    def on_xml_load_cancel(self, app, widget):
        self._canceled = True

    @abc.abstractmethod
    def reset(self) -> None:
        pass

    @abc.abstractmethod
    def update_epg_data(self) -> bool:
        pass

    @abc.abstractmethod
    def get_current_event(self, service_name) -> EpgEvent:
        pass

    @abc.abstractmethod
    def get_current_events(self, service_name) -> list:
        pass

    @staticmethod
    def get_gz_file_name(url, path):
        if not url:
            return f"{path}epg{os.sep}epg.gz"

        f_sha1 = sha1(url.encode("utf-8", errors="ignore")).hexdigest()
        return f"{path}epg{os.sep}{f_sha1}_epg.gz"

    @staticmethod
    @run_task
    def update_name_cache(path, values):
        EpgCache.NAME_CACHE.update(values)
        log(f"[{EpgCache.__name__}] Updating name cache...")
        f_name = f"{path}{EpgCache._CACHE_FILE}"
        with open(f_name, "w", encoding="utf-8") as cf:
            log(f"[{EpgCache.__name__}] Dumping name cache... -> [{f_name}]")
            json.dump(EpgCache.NAME_CACHE, cf)

    @staticmethod
    @run_task
    def init_name_cache(path):
        f_name = f"{path}{EpgCache._CACHE_FILE}"
        if not os.path.isfile(f_name):
            return

        log(f"[{EpgCache.__name__}] Name cache init...")
        try:
            with open(f_name, "r", encoding="utf-8") as cf:
                EpgCache.NAME_CACHE.update(json.load(cf))
        except Exception as e:
            log(f"[{EpgCache.__name__}] Name cache init error: {e}")


class FavEpgCache(EpgCache):

    def __init__(self, app):
        super().__init__(app)
        self._app.connect("epg-cache-initialized", self.on_cache_initialized)
        GLib.timeout_add_seconds(self._settings.epg_update_interval, self.init)

    def on_cache_initialized(self, app, cache):
        if cache is not self:
            return

        self._is_run = True
        GLib.timeout_add_seconds(self._settings.epg_update_interval, self.update_epg_data, priority=GLib.PRIORITY_LOW)

    def init(self):
        self._src = self._settings.epg_source
        self._xml_src = self._settings.epg_xml_source
        self._is_run = False
        if self._src is EpgSource.XML:
            url = self._settings.epg_xml_source
            gz_file = self.current_gz_file_name
            self._reader = XmlTvReader(gz_file, url)

            @run_with_delay(2)
            def process_data():
                def process():
                    self._reader.parse()
                    GLib.idle_add(self._app.emit, "epg-cache-initialized", self)

                t = BGTaskWidget(self._app, "Processing XMLTV data...", process, )
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
                if not url:
                    self._is_run = True
                    self._app.show_info_message("The EPG source for the favorites list is not set!",
                                                Gtk.MessageType.WARNING)
                    GLib.idle_add(self._app.emit, "epg-cache-initialized", self)
                else:
                    if not self._canceled:
                        task = BGTaskWidget(self._app, "Downloading EPG...", self._reader.download, process_data, )
                        self._app.emit("add-background-task", task)
        elif self._src is EpgSource.DAT:
            self._reader = EPG.DatReader(f"{self._settings.profile_data_path}epg{os.sep}epg.dat")
            self._reader.download()
        else:
            GLib.idle_add(self._app.emit, "epg-cache-initialized", self)

    def reset(self) -> None:
        self.events.clear()
        if self._is_run:
            self._is_run = False
            GLib.timeout_add_seconds(self._settings.epg_update_interval, self.init)

    def update_epg_data(self):
        if self._src is EpgSource.HTTP:
            api, bq = self._app.http_api, self._app.current_bouquet_files.get(self._current_bq, None)
            if bq and api:
                req = quote(f'FROM BOUQUET "{bq}"')
                api.send(HttpAPI.Request.EPG_NOW, f'1:7:1:0:0:0:0:0:0:0:{req}', self.update_http_data)
        elif self._src is EpgSource.XML:
            self.update_xml_data()

        return self._app.display_epg and self._is_run

    def update_http_data(self, epg):
        for e in (EpgTool.get_event(e, False) for e in epg.get("event_list", []) if e.get("e2eventid", "").isdigit()):
            self.events[e.event_data.get("e2eventservicename", "")] = e

    @run_task
    def update_xml_data(self):
        services = self._app.current_services
        names = {services[s].service for s in self._app.current_bouquets.get(self._current_bq, []) if s in services}
        if self._app.app_settings.enable_epg_name_cache:
            id_names = set(filter(lambda n: n in EpgCache.NAME_CACHE, names))
            names -= id_names
            names.update({EpgCache.NAME_CACHE.get(n) for n in id_names})

        for name, events in self._reader.get_current_events(names).items():
            ev = min(events, key=lambda x: x.start, default=None)
            if ev:
                self.events[name] = ev

    def get_current_event(self, service_name):
        return self.events.get(EpgCache.NAME_CACHE.get(service_name, service_name), EpgEvent())

    def get_current_events(self, service_name):
        return [EpgEvent()]


class TabEpgCache(EpgCache):

    def __init__(self, app, path=None, url=None):
        super().__init__(app)
        self._page = Page.EPG
        self._path = path or self.current_gz_file_name
        self._xml_src = url
        self._task = None

        self._app.connect("epg-cache-initialized", self.on_cache_initialized)

        self.init()

    def on_bouquet_changed(self, app, bq):
        self._current_bq = bq
        self.update_epg_data()

    def init(self):
        self._is_run = True
        self._reader = XmlTvReader(self._path, url=self._xml_src)
        if self._canceled:
            return

        if self._app.display_epg and self._xml_src == self._settings.epg_xml_source:
            ext_cache = self._app.current_epg_cache
            if ext_cache and ext_cache.is_run:
                self._app.emit("epg-cache-initialized", ext_cache)
            return

        self.load_data()

    def load_data(self):
        if os.path.isfile(self._path):
            if self._xml_src:
                # Difference calculation between the current time and file modification.
                dif = datetime.now() - datetime.fromtimestamp(os.path.getmtime(self._path))
                # We will update daily. -> Temporarily!!! Skip download if FAV cache is enabled.
                if dif.days > 0 and not self._app.display_epg:
                    self._task = BGTaskWidget(self._app, "Downloading EPG...", self._reader.download,
                                              self.process_data, )
                    self._app.emit("add-background-task", self._task)
                else:
                    self.process_data()
            else:
                self._task = BGTaskWidget(self._app, "", self.process_data, )
        else:
            if not self._xml_src:
                self._app.emit("epg-cache-initialized", self)
                self._app.show_info_message("Select a local file to load EPG data or add a web source.",
                                            Gtk.MessageType.WARNING)
            else:
                self._task = BGTaskWidget(self._app, "Downloading EPG...", self._reader.download, self.process_data, )
                self._app.emit("add-background-task", self._task)

    def on_cache_initialized(self, app, cache):
        if isinstance(cache, FavEpgCache):
            reader = cache.current_reader
            if reader:
                self._reader.cache.update(reader.cache)
            self._is_run = False
        else:
            if not self._app.display_epg or self._settings.epg_source is not EpgSource.XML or self._xml_src is None:
                self._is_run = False

        self.update_epg_data()

    @run_task
    def process_data(self):
        def process():
            # Skip data parsing data if epg display is enabled and EPG src is XMLTV.
            if not all((self._xml_src, self._app.display_epg, self._settings.epg_source is EpgSource.XML)):
                self._reader.parse()
            self._task = None
            GLib.idle_add(self._app.emit, "epg-cache-initialized", self)

        self._task = BGTaskWidget(self._app, "Processing XMLTV data...", process, )
        GLib.idle_add(self._app.emit, "add-background-task", self._task)

    def reset(self) -> None:
        self._is_run = False
        if self._task:
            self._task.cancel()

        self.init()

    def update_epg_data(self) -> bool:
        services = self._app.current_services
        names = {services[s].service for s in chain.from_iterable(self._app.current_bouquets.values()) if s in services}

        if self._app.app_settings.enable_epg_name_cache:
            id_names = set(filter(lambda n: n in EpgCache.NAME_CACHE, names))
            names -= id_names
            names.update({EpgCache.NAME_CACHE.get(n) for n in id_names})

        for name, events in self._reader.get_current_events(names).items():
            self.events[name] = events

        self._app.emit("epg-cache-updated", self)

        return self._is_run

    def get_current_event(self, service_name) -> EpgEvent:
        pass

    def get_current_events(self, service_name) -> list:
        return self.events.get(EpgCache.NAME_CACHE.get(service_name, service_name), [])


class EpgSettingsPopover(Gtk.Popover):

    def __init__(self, app, **kwarg):
        super().__init__(**kwarg)
        self._app = app
        self._app.connect("profile-changed", self.on_profile_changed)

        handlers = {"on_add_url": self.on_ad_url,
                    "on_remove_url": self.on_remove_url,
                    "on_apply_url": self.on_apply_url,
                    "on_url_entry_focus_out": self.on_url_entry_focus_out,
                    "on_apply": self.on_apply,
                    "on_close": self.on_close}

        builder = get_builder(f"{UI_RESOURCES_PATH}epg{SEP}settings.glade", handlers)
        self.add(builder.get_object("main_box"))

        self._src_selection_box = builder.get_object("source_selection_box")
        self._xml_source_box = builder.get_object("xml_source_box")
        self._download_interval_box = builder.get_object("download_interval_box")
        self._interval_box = builder.get_object("interval_box")
        self._http_src_button = builder.get_object("http_src_button")
        self._xml_src_button = builder.get_object("xml_src_button")
        self._dat_src_button = builder.get_object("dat_src_button")
        self._interval_button = builder.get_object("interval_button")
        self._download_interval_button = builder.get_object("download_interval_button")
        self._url_combo_box = builder.get_object("url_combo_box")
        self._url_entry = builder.get_object("url_entry")
        self._dat_path_box = builder.get_object("dat_path_box")
        self._remove_url_button = builder.get_object("remove_url_button")

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
        self._dat_path_box.set_active_id(settings.epg_dat_path)
        self._url_combo_box.get_model().clear()
        [self._url_combo_box.append(i, i) for i in settings.epg_xml_sources if i]
        self._url_combo_box.set_active_id(settings.epg_xml_source)
        self._remove_url_button.set_sensitive(len(self._url_combo_box.get_model()) > 1)

    def on_ad_url(self, button):
        self._url_entry.set_can_focus(True)
        self._url_entry.grab_focus()

    def on_remove_url(self, button):
        self._url_combo_box.remove(self._url_combo_box.get_active())
        self._url_combo_box.set_active(0)
        self._remove_url_button.set_sensitive(len(self._url_combo_box.get_model()) > 1)

    def on_apply_url(self, button):
        url = self._url_entry.get_text()
        ids = {r[0] for r in self._url_combo_box.get_model()}
        if url in ids:
            self._app.show_error_message("This URL already exists!")
            return True

        self._url_combo_box.append(url, url)
        self._url_combo_box.set_active_id(url)
        self._download_interval_button.grab_focus()
        self._remove_url_button.set_sensitive(len(ids))

    def on_url_entry_focus_out(self, entry, event):
        entry.set_can_focus(False)
        active = self._url_combo_box.get_active_id()
        txt = entry.get_text()
        if active != txt:
            entry.set_text(active or "")

    def on_apply(self, button):
        settings = self._app.app_settings
        if self._http_src_button.get_active():
            src = EpgSource.HTTP
        elif self._xml_src_button.get_active():
            src = EpgSource.XML
        else:
            src = EpgSource.DAT

        xml_src = self._url_combo_box.get_active_id()
        update_interval = self._interval_button.get_value()
        dat_path = self._dat_path_box.get_active_id()

        if any((src != settings.epg_source,
                xml_src != settings.epg_xml_source,
                update_interval != settings.epg_update_interval,
                dat_path != settings.epg_dat_path)):
            self._app.emit("epg-settings-changed", Page.SERVICES)

        settings.epg_update_interval = update_interval
        settings.epg_source = src
        settings.epg_xml_source = xml_src
        settings.epg_xml_sources = [r[0] for r in self._url_combo_box.get_model()]
        settings.epg_dat_path = dat_path
        self.popdown()

    def on_close(self, button):
        self.init()
        self.popdown()

    def on_profile_changed(self, app, p):
        self.init()


class TabEpgSettingsPopover(EpgSettingsPopover):

    def init(self):
        self._xml_src_button.set_active(True)
        self._http_src_button.set_visible(False)
        self._src_selection_box.set_visible(False)
        self._interval_box.set_visible(False)
        self._xml_source_box.set_margin_top(5)

        settings = self._app.app_settings
        self._interval_button.set_value(settings.epg_update_interval)
        self._url_combo_box.get_model().clear()
        [self._url_combo_box.append(i, i) for i in settings.epg_xml_sources if i]
        self._url_combo_box.set_active_id(settings.epg_xml_source)

    def on_apply(self, button):
        settings = self._app.app_settings
        xml_src = self._url_combo_box.get_active_id()

        if xml_src != settings.epg_xml_source:
            settings.epg_xml_source = xml_src
            self._app.emit("epg-settings-changed", Page.EPG)

        settings.epg_xml_sources = [r[0] for r in self._url_combo_box.get_model()]
        self.popdown()


class EpgTool(Gtk.Box):
    # Batch size to data load in one pass.
    LOAD_FACTOR = 100

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)

        self._epg_cache = None
        self._src = EpgSource.HTTP
        self._current_bq = app.current_bouquet

        self._app = app
        self._app.connect("data-open", self.on_data_open)
        self._app.connect("data-extract", self.on_data_extract)
        self._app.connect("fav-changed", self.on_service_changed)
        self._app.connect("profile-changed", self.on_profile_changed)
        self._app.connect("bouquet-changed", self.on_bouquet_changed)
        self._app.connect("epg-cache-updated", self.on_epg_cache_updated)
        self._app.connect("epg-display-changed", self.on_epg_display_changed)
        self._app.connect("filter-toggled", self.on_filter_toggled)

        handlers = {"on_epg_filter_changed": self.on_epg_filter_changed,
                    "on_epg_filter_toggled": self.on_epg_filter_toggled,
                    "on_view_query_tooltip": self.on_view_query_tooltip,
                    "on_multi_epg_toggled": self.on_multi_epg_toggled,
                    "on_xmltv_toggled": self.on_xmltv_toggled,
                    "on_epg_press": self.on_epg_press,
                    "on_timer_add": self.on_timer_add}

        builder = get_builder(f"{UI_RESOURCES_PATH}epg{SEP}tab.glade", handlers)

        self._view = builder.get_object("epg_view")
        self._model = builder.get_object("epg_model")
        self._filter_model = builder.get_object("epg_filter_model")
        self._filter_model.set_visible_func(self.epg_filter_function)
        self._filter_button = builder.get_object("epg_filter_button")
        self._filter_entry = builder.get_object("epg_filter_entry")
        self._multi_epg_button = builder.get_object("multi_epg_button")
        self._src_xmltv_button = builder.get_object("src_xmltv_button")
        self._epg_options_button = builder.get_object("epg_options_button")
        self._epg_options_button.connect("realize", lambda b: b.set_popover(TabEpgSettingsPopover(self._app)))
        self._event_count_label = builder.get_object("event_count_label")
        self._cache_info_label = builder.get_object("cache_info_label")
        self.set_cache_info(0, 0)
        self.pack_start(builder.get_object("epg_frame"), True, True, 0)
        # Custom data functions.
        renderer = builder.get_object("epg_start_renderer")
        column = builder.get_object("epg_start_column")
        column.set_cell_data_func(renderer, self.start_data_func)
        renderer = builder.get_object("epg_end_renderer")
        column = builder.get_object("epg_end_column")
        column.set_cell_data_func(renderer, self.end_data_func)
        renderer = builder.get_object("epg_length_renderer")
        column = builder.get_object("epg_length_column")
        column.set_cell_data_func(renderer, self.duration_data_func)
        # Time formats.
        self._time_fmt = "%a %x - %H:%M"
        self._duration_fmt = f"%{'' if IS_WIN else '-'}Hh %Mm"

        self.show()

    def on_data_open(self, app, page):
        if page is not Page.EPG:
            return

        response = get_chooser_dialog(self._app.app_window, self._app.app_settings, "XMLTV", ("*.xml",))
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        self.open_data(response)

    def on_data_extract(self, app, page):
        if page is not Page.EPG:
            return

        f_filter = Gtk.FileFilter()
        f_filter.set_name("*.zip, *.gz, *.xz")
        f_filter.add_mime_type("application/zip")
        f_filter.add_mime_type("application/gzip")
        f_filter.add_mime_type("application/x-xz")

        response = get_chooser_dialog(self._app.app_window, self._app.app_settings,
                                      "*.zip, *.gz, *.xz files", ("*.zip", "*.gz", "*.xz"), "Open archive", f_filter)
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return
        self.open_data(response)

    def open_data(self, path):
        if next(self.clear(), False):
            if not self._epg_cache:
                self._epg_cache = TabEpgCache(self._app, path)
            else:
                if self._epg_cache.is_run:
                    self._app.show_error_message("Data loading in progress!")
                    return

                self._epg_cache._path = path
                self._epg_cache._xml_src = None
                self._epg_cache.reset()
            GLib.idle_add(self._src_xmltv_button.set_active, True)

    def on_service_changed(self, app, srv):
        if app.page is not Page.EPG:
            return

        if self._src is EpgSource.HTTP:
            ref = app.get_service_ref_data(srv)
            if not ref:
                return

            if self._multi_epg_button.get_active():
                ref += ":"
                path = next((r.path for r in self._model if r[-1].get("e2eventservicereference", None) == ref), None)
                scroll_to(path, self._view) if path else None
            else:
                self._app.wait_dialog.show()
                self._app.send_http_request(HttpAPI.Request.EPG, quote(ref), self.update_http_epg_data)
        else:
            if self._epg_cache.is_run:
                self._app.show_error_message("Data loading in progress!")
                return

            if self._multi_epg_button.get_active():
                name =  srv.service
                if self._app.app_settings.enable_epg_name_cache:
                    name = EpgCache.NAME_CACHE.get(name, name)

                path = next((r.path for r in self._model if r[-1].get("e2eventservicename", None) == name), None)
                scroll_to(path, self._view) if path else None
            else:
                self._app.wait_dialog.show()
                self.update_xmltv_epg_data([srv.service])

    def on_profile_changed(self, app, prf):
        gen = self.update_epg_data()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_bouquet_changed(self, app, bq):
        self._current_bq = bq
        if app.page is Page.EPG and self._multi_epg_button.get_active():
            self.get_multi_epg()

    def on_epg_cache_updated(self, app, cache):
        self.set_cache_info(len(cache.events), len(list(chain.from_iterable(cache.events.values()))))

    def set_cache_info(self, s_count, ev_count):
        self._cache_info_label.set_text(f"{translate('Services')}: {s_count}  {translate('Events')}: {ev_count}")

    def on_epg_display_changed(self, app, display):
        self._epg_options_button.set_visible(not display and self._src is EpgSource.XML)

    def update_http_epg_data(self, epg=None):
        if epg:
            events = (self.get_event(e) for e in epg.get("event_list", []) if e.get("e2eventid", "").isdigit())
        else:
            events = ()
        gen = self.update_epg_data(events)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def update_xmltv_epg_data(self, names):
        gen = self.update_epg_data(chain.from_iterable(self._epg_cache.get_current_events(n) for n in names))
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def update_epg_data(self, events=()):
        c_gen = self.clear()
        yield from c_gen
        for index, e in enumerate(events):
            if index % self.LOAD_FACTOR == 0:
                self._event_count_label.set_text(str(len(self._model)))
                yield True
            self._model.append(e)
        self._event_count_label.set_text(str(len(self._model)))
        self._app.wait_dialog.hide()
        yield True

    def clear(self):
        if len(self._model) < self.LOAD_FACTOR * 20:
            self._model.clear()
        else:
            # Init new models.
            column_types = (self._model.get_column_type(i) for i in range(self._model.get_n_columns()))
            self._model = Gtk.ListStore(*column_types)
            self._filter_model = self._model.filter_new()
            self._filter_model.set_visible_func(self.epg_filter_function)
            self._view.set_model(Gtk.TreeModelSort(model=self._filter_model))
        self._event_count_label.set_text("0")
        yield True

    @staticmethod
    def get_event(event, show_day=True):
        s_name = event.get("e2eventservicename", "")
        title = event.get("e2eventtitle", "") or ""
        desc = event.get("e2eventdescription", "") or ""
        desc = desc.strip()
        start, duration = int(event.get("e2eventstart", "0")), int(event.get("e2eventduration", "0"))

        return EpgEvent(s_name, title, start, start + duration, duration, desc, event)

    def start_data_func(self, column, renderer, model, itr, data):
        value = datetime.fromtimestamp(model.get_value(itr, Column.EPG_START))
        renderer.set_property("text", value.strftime(self._time_fmt))

    def end_data_func(self, column, renderer, model, itr, data):
        value = datetime.fromtimestamp(model.get_value(itr, Column.EPG_END))
        renderer.set_property("text", value.strftime(self._time_fmt))

    def duration_data_func(self, column, renderer, model, itr, data):
        value = datetime.utcfromtimestamp(model.get_value(itr, Column.EPG_LENGTH))
        renderer.set_property("text", value.strftime(self._duration_fmt))

    @run_with_delay(2)
    def on_epg_filter_changed(self, entry):
        self._filter_model.refilter()

    def on_epg_filter_toggled(self, button):
        if not button.get_active():
            self._filter_entry.set_text("")

    def epg_filter_function(self, model, itr, data):
        txt = self._filter_entry.get_text().upper()
        return next((s for s in model.get(itr,
                                          Column.EPG_SERVICE,
                                          Column.EPG_TITLE,
                                          Column.EPG_DESC) if s and txt in s.upper()), False)

    def on_filter_toggled(self, app, value):
        if self._app.page is Page.EPG:
            active = not self._filter_button.get_active()
            self._filter_button.set_active(active)
            if active:
                self._filter_entry.grab_focus()

    def on_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        dst = view.get_dest_row_at_pos(x, y)
        if not dst:
            return False

        path, pos = dst
        model = view.get_model()
        data = model[path][-1]
        if not data:
            return False

        desc = data.get("e2eventdescription", "") or ""
        ext_desc = data.get("e2eventdescriptionextended", "") or ""
        if not any((desc, ext_desc)):
            return False

        tooltip.set_text(ext_desc if ext_desc else desc)
        view.set_tooltip_row(tooltip, path)

        return True

    def on_multi_epg_toggled(self, button):
        if button.get_active():
            self.get_multi_epg()
        else:
            next(self.clear(), False)

    def on_xmltv_toggled(self, button):
        if button.get_active():
            self._src = EpgSource.XML
            if self._epg_cache is None:
                settings = self._app.app_settings
                xml_src = self._app.app_settings.epg_xml_source if settings.epg_source is EpgSource.XML else None
                self._epg_cache = TabEpgCache(self._app, url=xml_src)
        else:
            self._src = EpgSource.HTTP
            self.update_http_epg_data()

        self._epg_options_button.set_visible(not self._app.display_epg and self._src is EpgSource.XML)

    def get_multi_epg(self):
        if not self._current_bq:
            return

        self._app.wait_dialog.show()

        if self._src is EpgSource.HTTP:
            bq, api = self._app.current_bouquet_files.get(self._current_bq, None), self._app.http_api
            if bq and api:
                tm = datetime.now().timestamp()
                req = quote(f'FROM BOUQUET "{bq}"&time={tm}')
                api.send(HttpAPI.Request.EPG_MULTI, f'1:7:1:0:0:0:0:0:0:0:{req}', self.update_http_epg_data, timeout=15)
        else:
            srvs = self._app.current_services
            bq_names = (srvs[s].service for s in self._app.current_bouquets.get(self._current_bq, []) if s in srvs)
            self.update_xmltv_epg_data(bq_names)

    # ****************** Timers ***************** #

    def on_epg_press(self, view, event):
        if self._src_xmltv_button.get_active():
            return True

        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS and len(view.get_model()) > 0:
            self.on_timer_add()

    def on_timer_add(self, action=None, value=None):
        model, paths = self._view.get_selection().get_selected_rows()
        p_count = len(paths)

        if p_count == 1:
            dialog = TimerTool.TimerDialog(self._app.app_window, TimerTool.TimerAction.EVENT, model[paths][-1] or {})
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


class EpgDialog:

    def __init__(self, app, bouquet_name):

        handlers = {"on_close_dialog": self.on_close_dialog,
                    "on_apply": self.on_apply,
                    "on_update": self.on_update,
                    "on_save_to_xml": self.on_save_to_xml,
                    "on_auto_configuration": self.on_auto_configuration,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_filter_satellite_toggled": self.on_filter_satellite_toggled,
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
                    "on_bq_cursor_changed": self.on_bq_cursor_changed,
                    "on_source_view_query_tooltip": self.on_source_view_query_tooltip,
                    "on_paned_size_allocate": lambda p, a: p.set_position(0.5 * a.width)}

        self._app = app
        self._ex_services = self._app.current_services
        self._ex_fav_model = self._app.fav_view.get_model()
        self._settings = self._app.app_settings
        self._bouquet_name = bouquet_name
        self._current_ref = []
        self._enable_dat_filter = False
        self._use_web_source = False
        self._update_epg_data_on_start = False
        self._refs_source = RefsSource.SERVICES
        self._download_xml_is_active = False
        self._sat_positions = None

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
        self._src_load_spinner = builder.get_object("src_load_spinner")
        self._auto_config_button = builder.get_object("auto_config_button")
        self._enable_deep_comparing_switch = builder.get_object("enable_deep_comparing_switch")
        # Filter
        self._filter_bar = builder.get_object("filter_bar")
        self._filter_entry = builder.get_object("filter_entry")
        self._filter_auto_button = builder.get_object("filter_auto_button")
        self._services_filter_model = builder.get_object("services_filter_model")
        self._services_filter_model.set_visible_func(self.services_filter_function)
        self._sat_pos_filter_model = builder.get_object("sat_pos_filter_model")
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

        if self._settings.use_header_bar:
            header_bar = HeaderBar(title="EPG", subtitle=translate("List configuration"))
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
        if show_dialog(DialogType.QUESTION, self._dialog) != Gtk.ResponseType.OK:
            return

        p = re.compile(r"\d+")
        updated = {}

        for i, row in enumerate(self._bouquet_model):
            if row[Column.FAV_LOCKED]:
                fav_id = self._ex_fav_model[row.path][Column.FAV_ID]
                srv = self._ex_services.pop(fav_id, None)
                if srv:
                    new_fav_id, picon_id = row[Column.FAV_ID], row[Column.FAV_POS]
                    if picon_id:
                        picon_id = re.sub(p, re.search(p, srv.picon_id).group(), picon_id, count=1)
                    else:
                        picon_id = srv.picon_id
                    new = srv._replace(fav_id=new_fav_id, data_id=new_fav_id.strip(), picon_id=picon_id)
                    self._ex_services[new_fav_id] = new
                    updated[fav_id] = (srv, new)

        if updated:
            self._app.emit("iptv-service-edited", updated)

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

        self._src_load_spinner.start()

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

        self._src_load_spinner.stop()
        yield True

    def init_bouquet_data(self):
        for r in self._ex_fav_model:
            row = [*r[:]]
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
            self._services_model.append((srv.service, srv.pos, srv.fav_id, srv.picon_id, srv.picon_id))
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
                        raise ValueError("{} {} {}".format(translate("Download XML file error."),
                                                           translate("Unsupported file type:"),
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
                raise ValueError(f"{translate('Download XML file error.')} {e}")
            else:
                try:
                    with open(path, "wb") as f_out:
                        with gzip.open(tfp.name, "rb") as f:
                            shutil.copyfileobj(f, f_out)
                    os.remove(tfp.name)
                except Exception as e:
                    raise ValueError(f"{translate('Unpacking data error.')} {e}")
            finally:
                self._download_xml_is_active = False
                self.update_active_header_elements(True)

        try:
            s_refs, info = ChannelsParser.get_refs_from_xml(path)
            yield True
        except Exception as e:
            raise ValueError(f"{translate('XML parsing error:')} {e}")
        else:
            refs = refs or {}
            factor = self._app.DEL_FACTOR / 4

            for index, srv in enumerate(s_refs):
                ref_data = srv.data.split(":")
                ref = ":".join(ref_data[3:6])
                if ref in refs:
                    continue

                data = ":".join(ref_data[3:7])
                pos, ch_id = srv.num
                pos = pos or " "
                self._services_model.append((srv.name, pos, data, "_".join(ref_data).rstrip("_"), ch_id))

                if index % factor == 0:
                    yield True

            self.update_source_info(info)
            self.update_source_count_info()
            yield True

    def on_key_press(self, view, event):
        """  Handling  keystrokes  """
        key = KeyboardKey(event.hardware_keycode)
        if key is KeyboardKey.UNDEFINED:
            return

        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK

        if ctrl and key is KeyboardKey.C:
            self.on_copy_ref()
        elif ctrl and key is KeyboardKey.V:
            self.on_assign_ref()

    def on_bq_cursor_changed(self, view):
        if self._filter_bar.get_visible() and self._filter_auto_button.get_active():
            path, column = view.get_cursor()
            model = view.get_model()
            if path:
                self._filter_entry.set_text(model[path][Column.FAV_SERVICE] or "")

    def on_source_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        result = view.get_dest_row_at_pos(x, y)
        if not result:
            return False

        path, pos = result
        ch_id = view.get_model()[path][-1]
        if not ch_id:
            return False

        if self._refs_source is RefsSource.XML:
            text = f"ID = {ch_id}"
        else:
            text = f"{translate('Service reference')}: {ch_id.rstrip('.png')}"

        tooltip.set_text(text)
        view.set_tooltip_row(tooltip, path)
        return True

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

        ChannelsParser.write_refs_to_xml(f"{response}{self._bouquet_name}.xml", services)
        self.show_info_message(translate("Done!"), Gtk.MessageType.INFO)

    @run_idle
    def on_auto_configuration(self, item):
        gen = self.auto_configuration()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def auto_configuration(self):
        """ Simple mapping of services by name. """
        self._auto_config_button.set_sensitive(False)
        use_cyrillic = locale.getdefaultlocale()[0] in ("ru_RU", "be_BY", "uk_UA", "sr_RS")
        tr = None
        if use_cyrillic:
            # may be not entirely correct
            symbols = (u"АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯІÏҐЎЈЂЉЊЋЏTB",
                       u"ABVGDEEJZIJKLMNOPRSTUFHZCSS_Y_EUAIEGUEDLNCJTV")
            tr = {ord(k): ord(v) for k, v in zip(*symbols)}

        source = {}
        for row in self._source_view.get_model():
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
                self._bouquet_epg_count_label.set_text(str(success_count))
                yield True
            else:
                not_founded[name] = r

        # Additional attempt to search in the remaining elements
        use_deep = self._enable_deep_comparing_switch.get_active()
        for n in not_founded:
            for k in source:
                if StringComparer.is_similar(k, n, StringComparer.ALG.JARO) if use_deep else k.startswith(n):
                    self.assign_data(not_founded[n], source[k], True)
                    success_count += 1
                    self._bouquet_epg_count_label.set_text(str(success_count))
                    break
                yield True

        self._auto_config_button.set_sensitive(True)
        self.update_epg_count()
        self.show_info_message("{} {} {}".format(translate("Done!"),
                                                 translate("Count of successfully configured services:"),
                                                 success_count), Gtk.MessageType.INFO)
        yield True

    def assign_refs(self, model, paths, data):
        [self.assign_data(model[p], data) for p in paths]
        self.update_epg_count()

    def assign_data(self, row, data, show_error=False):
        if row[Column.FAV_TYPE] != BqServiceType.IPTV.value:
            if not show_error:
                self.show_info_message(translate("Not allowed in this context!"), Gtk.MessageType.ERROR)
            return

        fav_id = row[Column.FAV_ID]
        fav_id_data = fav_id.split(":")
        fav_id_data[3:7] = data[-3].split(":")[3:7]

        if data[-2]:
            row[Column.FAV_POS] = data[-2]
            p_data = data[-2].split("_")
            if p_data:
                fav_id_data[2] = p_data[2]

        new_fav_id = ":".join(fav_id_data)
        row[Column.FAV_ID] = new_fav_id
        row[Column.FAV_LOCKED] = EPG_ICON

        pos = f"({data[1] if self._refs_source is RefsSource.SERVICES else 'XML'})"
        src = f"{translate('EPG source')}: {(GLib.markup_escape_text(data[0] or ''))} {pos}"
        row[Column.FAV_TOOLTIP] = f"{translate('Service reference')}: {':'.join(fav_id_data[:10])}\n{src}"

    def on_filter_toggled(self, button):
        self._filter_bar.set_visible(button.get_active())
        if button.get_active():
            self._sat_positions = {r[1] for r in self._services_model}
            update_filter_sat_positions(self._sat_pos_filter_model, self._sat_positions)
        else:
            self._sat_positions = None
            self._filter_entry.set_text("") if self._filter_entry.get_text() else self.on_filter_changed()

    def on_filter_satellite_toggled(self, toggle, path):
        update_toggle_model(self._sat_pos_filter_model, path, toggle)
        self._sat_positions.clear()
        self._sat_positions.update({r[0] for r in self._sat_pos_filter_model if r[1]})
        self.on_filter_changed()

    @run_with_delay(2)
    def on_filter_changed(self, entry=None):
        self._services_filter_model.refilter()

    def services_filter_function(self, model, itr, data):
        txt = self._filter_entry.get_text().upper()
        pos = model.get_value(itr, 1)
        pos = self._sat_positions is None or pos in self._sat_positions
        return model is None or model == "None" or (txt in model.get_value(itr, 0).upper() and pos)

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
        row[Column.FAV_LOCKED], row[Column.FAV_TOOLTIP], row[Column.FAV_POS] = None, None, None

    @run_idle
    def show_info_message(self, text, message_type):
        show_info_bar_message(self._info_bar, self._message_label, text, message_type)

    @run_idle
    def update_source_info(self, info):
        lines = info.split("\n")
        self._source_info_label.set_text(lines[0] if lines else "")

    @run_idle
    def update_source_count_info(self):
        source_count = len(self._services_model)
        self._source_count_label.set_text(str(source_count))
        if self._enable_dat_filter and source_count == 0:
            msg = translate("Current epg.dat file does not contains references for the services of this bouquet!")
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
                self.show_info_message(translate("Source error!"), Gtk.MessageType.ERROR)

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
            self._enable_deep_comparing_switch.set_active(epg_options.get("enable_deep_comparing", False))
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
                                      "enable_deep_comparing": self._enable_deep_comparing_switch.get_active(),
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

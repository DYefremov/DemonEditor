# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2024 Dmitriy Yefremov
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


import os
import re
import sys
from collections import Counter
from contextlib import suppress
from datetime import datetime
from functools import lru_cache
from html import escape
from itertools import chain
from urllib.parse import urlparse, unquote

from gi.repository import GLib, Gio, GObject

from app.commons import run_idle, log, run_task, run_with_delay, init_logger, DefaultDict
from app.connections import (HttpAPI, download_data, DownloadType, upload_data, STC_XML_FILE)
from app.eparser import get_blacklist, write_blacklist, write_bouquet
from app.eparser import get_services, get_bouquets, write_bouquets, write_services, Bouquets, Bouquet, Service
from app.eparser.ecommons import CAS, Flag, BouquetService
from app.eparser.enigma.bouquets import BqServiceType
from app.eparser.iptv import export_to_m3u, StreamType
from app.eparser.neutrino.bouquets import BqType
from app.settings import (SettingsType, Settings, SettingsException, SettingsReadException, IS_DARWIN, IS_LINUX,
                          PlayStreamsMode, PlaybackMode, USE_HEADER_BAR)
from app.tools.media import Recorder
from app.ui.control import ControlTool
from app.ui.epg.epg import FavEpgCache, EpgSettingsPopover, EpgDialog, EpgTool
from app.ui.ftp import FtpClientBox
from app.ui.logs import LogsClient
from app.ui.playback import PlayerBox
from app.ui.recordings import RecordingsTool
from app.ui.telnet import TelnetClient
from app.ui.timers import TimerTool
from app.ui.transmitter import LinksTransmitter
from .backup import BackupDialog, backup_data, clear_data_path, restore_data
from .dialogs import show_dialog, DialogType, get_chooser_dialog, WaitDialog, translate, get_builder
from .imports import ImportDialog, import_bouquet
from .iptv import (IptvDialog, SearchUnavailableDialog, IptvListConfigurationDialog, YtListImportDialog,
                   M3uImportDialog, ExportM3uDialog)
from .main_helper import *
from .picons import PiconManager
from .search import SearchProvider
from .service_details_dialog import ServiceDetailsDialog, Action
from .settings_dialog import SettingsDialog
from .uicommons import (Gtk, Gdk, UI_RESOURCES_PATH, LOCKED_ICON, HIDE_ICON, IPTV_ICON, MOVE_KEYS, KeyboardKey, Column,
                        MOD_MASK, APP_FONT, Page, HeaderBar)
from .xml.dialogs import ServicesUpdateDialog
from .xml.edit import SatellitesTool


class Application(Gtk.Application):
    """ Main application class. """
    SERVICE_MODEL = "services_list_store"
    FAV_MODEL = "fav_list_store"
    BQ_MODEL = "bouquets_tree_store"
    ALT_MODEL = "alt_list_store"
    IPTV_MODEL = "iptv_list_store"
    DRAG_SEP = "::::"

    MARKER_TYPES = {BqServiceType.MARKER.name, BqServiceType.SPACE.name, BqServiceType.ALT.name}

    DEL_FACTOR = 100  # Batch size to delete in one pass.
    FAV_FACTOR = DEL_FACTOR * 5

    _TV_TYPES = ("TV", "TV (HD)", "TV (UHD)", "TV (H264)")

    BG_TASK_LIMIT = 5

    _URL_PATTERN = re.compile(r"((https?)+.*?(?=https?|$))")

    # Dynamically active elements depending on the selected view
    _SERVICE_ELEMENTS = ("services_to_fav_end_move_popup_item", "services_to_fav_move_popup_item",
                         "services_create_bouquet_popup_item", "services_copy_popup_item", "services_edit_popup_item",
                         "services_add_new_popup_item", "services_picon_popup_item", "services_remove_popup_item")

    _FAV_ELEMENTS = ("fav_cut_popup_item", "fav_paste_popup_item", "fav_locate_popup_item", "fav_iptv_popup_item",
                     "fav_insert_marker_popup_item", "fav_insert_space_popup_item", "fav_edit_sub_menu_popup_item",
                     "fav_edit_popup_item", "fav_picon_popup_item", "fav_copy_popup_item", "fav_add_alt_popup_item",
                     "fav_epg_configuration_popup_item", "fav_mark_dup_popup_item", "fav_remove_dup_popup_item",
                     "fav_reference_popup_item")

    _BOUQUET_ELEMENTS = ("bouquets_new_popup_item", "bouquets_edit_popup_item", "bouquets_cut_popup_item",
                         "bouquets_copy_popup_item", "bouquets_paste_popup_item", "new_header_button",
                         "bouquet_import_popup_item", "import_m3u_header_button", "export_to_m3u_header_button")

    _COMMONS_ELEMENTS = ("bouquets_remove_popup_item", "fav_remove_popup_item", "import_bq_menu_button")

    _FAV_ENIGMA_ELEMENTS = ("fav_insert_marker_popup_item", "fav_epg_configuration_popup_item")

    _FAV_IPTV_ELEMENTS = ("fav_iptv_popup_item", "iptv_menu_button")

    DATA_SAVE_PAGES = {Page.SERVICES, Page.SATELLITE}
    DATA_OPEN_PAGES = {Page.SERVICES, Page.SATELLITE, Page.PICONS, Page.EPG}
    DATA_EXTRACT_PAGES = {Page.SERVICES, Page.EPG}
    DATA_SEND_PAGES = {Page.SERVICES, Page.SATELLITE, Page.PICONS, Page.FTP}
    DATA_RECEIVE_PAGES_enabled = {Page.SERVICES, Page.SATELLITE, Page.PICONS, Page.RECORDINGS, Page.FTP}

    def __init__(self, **kwargs):
        super().__init__(flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE, **kwargs)
        # Adding command line options
        self.add_main_option("log", ord("l"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "", None)
        self.add_main_option("record", ord("r"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "", None)
        self.add_main_option("debug", ord("d"), GLib.OptionFlags.NONE, GLib.OptionArg.STRING, "", None)

        handlers = {"on_close_app": self.on_close_app,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_profile_changed": self.on_profile_changed,
                    "on_tree_view_key_press": self.on_tree_view_key_press,
                    "on_tree_view_key_release": self.on_tree_view_key_release,
                    "on_bouquets_selection": self.on_bouquets_selection,
                    "on_fav_selection": self.on_fav_selection,
                    "on_alt_selection": self.on_alt_selection,
                    "on_services_selection": self.on_services_selection,
                    "on_fav_cut": self.on_fav_cut,
                    "on_bouquets_cut": self.on_bouquets_cut,
                    "on_services_copy": self.on_services_copy,
                    "on_iptv_services_copy": self.on_iptv_services_copy,
                    "on_fav_copy": self.on_fav_copy,
                    "on_bouquets_copy": self.on_bouquets_copy,
                    "on_reference_copy": self.on_reference_copy,
                    "on_reference_assign": self.on_reference_assign,
                    "on_fav_paste": self.on_fav_paste,
                    "on_bouquets_paste": self.on_bouquets_paste,
                    "on_rename_for_bouquet": self.on_rename_for_bouquet,
                    "on_set_default_name_for_bouquet": self.on_set_default_name_for_bouquet,
                    "on_services_add_new": self.on_services_add_new,
                    "on_delete": self.on_delete,
                    "on_edit": self.on_edit,
                    "on_to_fav_copy": self.on_to_fav_copy,
                    "on_to_fav_end_copy": self.on_to_fav_end_copy,
                    "on_fav_sort": self.on_fav_sort,
                    "on_bq_view_query_tooltip": self.on_bq_view_query_tooltip,
                    "on_fav_view_query_tooltip": self.on_fav_view_query_tooltip,
                    "on_services_view_query_tooltip": self.on_services_view_query_tooltip,
                    "on_iptv_view_query_tooltip": self.on_iptv_view_query_tooltip,
                    "on_view_drag_begin": self.on_view_drag_begin,
                    "on_view_drag_end": self.on_view_drag_end,
                    "on_view_drag_data_get": self.on_view_drag_data_get,
                    "on_services_view_drag_drop": self.on_services_view_drag_drop,
                    "on_services_view_drag_data_received": self.on_services_view_drag_data_received,
                    "on_view_drag_data_received": self.on_view_drag_data_received,
                    "on_bq_view_drag_data_received": self.on_bq_view_drag_data_received,
                    "on_alt_view_drag_data_received": self.on_alt_view_drag_data_received,
                    "on_view_press": self.on_view_press,
                    "on_view_release": self.on_view_release,
                    "on_view_popup_menu": self.on_view_popup_menu,
                    "on_view_focus": self.on_view_focus,
                    "on_model_changed": self.on_model_changed,
                    "on_import_yt_list": self.on_import_yt_list,
                    "on_import_m3u": self.on_import_m3u,
                    "on_bouquet_export": self.on_bouquet_export,
                    "on_export_to_m3u": self.on_export_to_m3u,
                    "on_export_all_iptv_to_m3u": self.on_export_all_iptv_to_m3u,
                    "on_import_bouquet": self.on_import_bouquet,
                    "on_insert_marker": self.on_insert_marker,
                    "on_insert_space": self.on_insert_space,
                    "on_fav_press": self.on_fav_press,
                    "on_locate_in_services": self.on_locate_in_services,
                    "on_mark_duplicates": self.on_mark_duplicates,
                    "on_remove_duplicates": self.on_remove_duplicates,
                    "on_services_mark_not_in_bouquets": self.on_services_mark_not_in_bouquets,
                    "on_services_clear_marked": self.on_services_clear_marked,
                    "on_services_clear_new_marked": self.on_services_clear_new_marked,
                    "on_filter_changed": self.on_filter_changed,
                    "on_iptv_filter_changed": self.on_iptv_filter_changed,
                    "on_filter_type_toggled": self.on_filter_type_toggled,
                    "on_services_filter_toggled": self.on_services_filter_toggled,
                    "on_iptv_services_filter_toggled": self.on_iptv_services_filter_toggled,
                    "on_filter_satellite_toggled": self.on_filter_satellite_toggled,
                    "on_filter_bouquet_toggled": self.on_filter_bouquet_toggled,
                    "on_filter_in_bq_toggled": self.on_filter_in_bq_toggled,
                    "on_assign_picon_file": self.on_assign_picon_file,
                    "on_assign_picon": self.on_assign_picon,
                    "on_remove_picon": self.on_remove_picon,
                    "on_remove_unused_picons": self.on_remove_unused_picons,
                    "on_iptv": self.on_iptv,
                    "on_epg_list_configuration": self.on_epg_list_configuration,
                    "on_iptv_list_configuration": self.on_iptv_list_configuration,
                    "on_play_stream": self.on_play_stream,
                    "on_play_current": self.on_play_current,
                    "on_main_window_state": self.on_main_window_state,
                    "on_record": self.on_record,
                    "on_remove_all_unavailable": self.on_remove_all_unavailable,
                    "on_new_bouquet": self.on_new_bouquet,
                    "on_new_sub_bouquet": self.on_new_sub_bouquet,
                    "on_create_bouquet_for_current_satellite": self.on_create_bouquet_for_current_satellite,
                    "on_create_bouquet_for_each_satellite": self.on_create_bouquet_for_each_satellite,
                    "on_create_bouquet_for_current_package": self.on_create_bouquet_for_current_package,
                    "on_create_bouquet_for_each_package": self.on_create_bouquet_for_each_package,
                    "on_create_bouquet_for_current_type": self.on_create_bouquet_for_current_type,
                    "on_create_bouquet_for_each_type": self.on_create_bouquet_for_each_type,
                    "on_add_alternatives": self.on_add_alternatives,
                    "on_satellites_realize": self.on_satellites_realize,
                    "on_picons_realize": self.on_picons_realize,
                    "on_epg_realize": self.on_epg_realize,
                    "on_timers_realize": self.on_timers_realize,
                    "on_recordings_realize": self.on_recordings_realize,
                    "on_control_realize": self.on_control_realize,
                    "on_ftp_realize": self.on_ftp_realize,
                    "on_telnet_realize": self.on_telnet_realize,
                    "on_visible_page": self.on_visible_page,
                    "on_iptv_toggled": self.on_iptv_toggled,
                    "on_data_paned_realize": self.init_main_paned_position}

        self._settings = Settings.get_instance()
        self._s_type = self._settings.setting_type
        self._is_enigma = self._s_type is SettingsType.ENIGMA_2
        self._is_send_data_enabled = False
        self._is_receive_data_enabled = True
        self._is_data_open_enabled = True
        self._is_data_extract_enabled = False
        self._is_data_save_enabled = False
        # Used for copy/paste. When adding the previous data will not be deleted.
        # Clearing only after the insertion!
        self._rows_buffer = []
        self._bouquets_buffer = []
        self._services = {}
        self._bouquets = {}
        self._bq_file = {}
        self._alt_file = set()
        self._alt_counter = 1
        self._data_hash = 0
        self._filter_cache = {}
        self._iptv_filter_cache = {}
        self._in_bouquets = set()
        # For bouquets with different names of services in bouquet and main list
        self._extra_bouquets = {}
        self._blacklist = set()
        self._current_bq_name = None
        self._bq_selected = ""  # Current selected bouquet
        self._select_enabled = True  # Multiple selection
        # Picons
        self._picons_buffer = []
        self._picons = DefaultDict(self.get_picon)
        # Current satellite positions in the services list
        self._sat_positions = set()
        self._service_types = set()
        self._bq_names = set()
        self._services_models = {self.SERVICE_MODEL, self.IPTV_MODEL}
        # Tools
        self._links_transmitter = None
        self._satellite_tool = None
        self._picon_manager = None
        self._epg_tool = None
        self._timers_tool = None
        self._recordings_tool = None
        self._control_tool = None
        self._ftp_client = None
        # Record
        self._recorder = None
        # HTTP API
        self._http_api = None
        self._fav_click_mode = None
        # Appearance
        self._current_font = APP_FONT
        self._picons_size = self._settings.list_picon_size
        self._use_colors = False
        self._NEW_COLOR = None  # Color for new services in the main list
        self._EXTRA_COLOR = None  # Color for services with a extra name for the bouquet
        # Current page.
        self._page = Page.INFO
        self._fav_pages = {Page.SERVICES, Page.PICONS, Page.EPG, Page.TIMERS}
        self._no_download_pages = {Page.TIMERS, Page.CONTROL}
        # Signals.
        GObject.signal_new("profile-changed", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("bouquet-changed", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("fav-changed", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("fav-clicked", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("srv-clicked", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("iptv-clicked", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("page-changed", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("change-page", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("layout-changed", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("play-recording", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("play-current", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("data-load-done", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("filter-toggled", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("picon-assign", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("services-update", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("iptv-service-edited", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("iptv-service-added", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("data-open", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("data-extract", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("data-receive", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("data-send", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("data-save", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("data-save-as", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("add-background-task", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("task-done", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("task-cancel", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("task-canceled", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,)),
        GObject.signal_new("list-font-changed", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("clipboard-changed", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("epg-dat-downloaded", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("epg-settings-changed", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("epg-cache-initialized", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("epg-cache-updated", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("epg-display-changed", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))

        builder = get_builder(UI_RESOURCES_PATH + "main.glade", handlers)
        self._main_window = builder.get_object("main_window")
        self._stack = builder.get_object("stack")
        self._services_stack = builder.get_object("services_stack")
        self._fav_paned = builder.get_object("fav_paned")
        self._bq_frame = builder.get_object("bq_frame")
        self._fav_frame = builder.get_object("fav_frame")
        self._services_view = builder.get_object("services_tree_view")
        self._iptv_services_view = builder.get_object("iptv_services_view")
        self._fav_view = builder.get_object("fav_tree_view")
        self._bouquets_view = builder.get_object("bouquets_tree_view")
        self._fav_model = builder.get_object("fav_list_store")
        self._services_model = builder.get_object("services_list_store")
        self._bouquets_model = builder.get_object("bouquets_tree_store")
        self._bq_name_label = builder.get_object("bq_name_label")
        self._iptv_model = builder.get_object("iptv_list_store")
        self._iptv_menu_button = builder.get_object("iptv_menu_button")
        # Setting custom sort function for position column.
        self._services_view.get_model().set_sort_func(Column.SRV_POS, self.position_sort_func, Column.SRV_POS)
        # App info
        self._app_info_box = builder.get_object("app_info_box")
        self._app_info_box.bind_property("visible", builder.get_object("data_paned"), "visible", 4)
        # Info bar.
        self._info_bar = builder.get_object("info_bar")
        self._info_label = builder.get_object("info_label")
        # Status bar.
        self._status_bar_box = builder.get_object("status_bar_box")
        self._profile_combo_box = builder.get_object("profile_combo_box")
        self._receiver_info_box = builder.get_object("receiver_info_box")
        self._receiver_info_label = builder.get_object("receiver_info_label")
        self._current_ip_label = builder.get_object("current_ip_label")
        self._signal_box = builder.get_object("signal_box")
        self._service_name_label = builder.get_object("service_name_label")
        self._service_epg_label = builder.get_object("service_epg_label")
        self._signal_level_bar = builder.get_object("signal_level_bar")
        self._http_status_image = builder.get_object("http_status_image")
        self._cas_label = builder.get_object("cas_label")
        self._fav_count_label = builder.get_object("fav_count_label")
        self._bouquets_count_label = builder.get_object("bouquets_count_label")
        self._tv_count_label = builder.get_object("tv_count_label")
        self._radio_count_label = builder.get_object("radio_count_label")
        self._data_count_label = builder.get_object("data_count_label")
        self._iptv_count_label = builder.get_object("iptv_count_label")
        self._services_load_spinner = builder.get_object("services_load_spinner")
        self._iptv_services_load_spinner = builder.get_object("iptv_services_load_spinner")
        self._save_tool_button = builder.get_object("save_tool_button")
        self.bind_property("is-data-save-enabled", self._save_tool_button, "visible")
        self._receiver_info_box.bind_property("visible", self._http_status_image, "visible", 4)
        self._receiver_info_box.bind_property("visible", self._signal_box, "visible")
        self._task_box = builder.get_object("task_box")
        # Alternatives
        self._alt_view = builder.get_object("alt_tree_view")
        self._alt_model = builder.get_object("alt_list_store")
        self._alt_revealer = builder.get_object("alt_revealer")
        self._alt_revealer.bind_property("visible", self._alt_revealer, "reveal-child")
        # Force Ctrl press event for view. Multiple selections in lists only with Space key(as in file managers)!!!
        self._services_view.connect("key-press-event", self.force_ctrl)
        self._iptv_services_view.connect("key-press-event", self.force_ctrl)
        self._fav_view.connect("key-press-event", self.force_ctrl)
        # Clipboard
        self._clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        ref_item = builder.get_object("fav_assign_ref_popup_item")
        self.bind_property("is_enigma", ref_item, "visible")
        # We use a custom event for observe clipboard state.
        # "owner-change" -> https://gitlab.gnome.org/GNOME/gtk/-/issues/1757
        self.connect("clipboard-changed", lambda a, o: ref_item.set_sensitive(o))
        # Wait dialog
        self._wait_dialog = WaitDialog(self._main_window)
        # Filter
        self._services_model_filter = builder.get_object("services_model_filter")
        self._services_model_filter.set_visible_func(self.services_filter_function)
        self._iptv_services_model_filter = builder.get_object("iptv_services_model_filter")
        self._iptv_services_model_filter.set_visible_func(self.iptv_services_filter_function)
        self._filter_services_button = builder.get_object("filter_services_button")
        self._filter_entry = builder.get_object("filter_entry")
        self._iptv_filter_entry = builder.get_object("iptv_filter_entry")
        self._filter_box = builder.get_object("filter_box")
        self._iptv_filter_box = builder.get_object("iptv_filter_box")
        self._filter_types_model = builder.get_object("filter_types_list_store")
        self._filter_sat_pos_model = builder.get_object("filter_sat_pos_list_store")
        self._filter_bouquet_model = builder.get_object("filter_bouquet_list_store")
        self._filter_only_free_button = builder.get_object("filter_only_free_button")
        self._filter_not_in_bq_button = builder.get_object("filter_not_in_bq_button")
        self._services_load_spinner.bind_property("active", self._filter_services_button, "sensitive", 4)
        self._filter_iptv_services_button = builder.get_object("filter_iptv_services_button")
        # Search.
        services_search_provider = SearchProvider(self._services_view,
                                                  builder.get_object("services_search_entry"),
                                                  builder.get_object("srv_search_down_button"),
                                                  builder.get_object("srv_search_up_button"),
                                                  (Column.SRV_SERVICE, Column.SRV_PACKAGE))
        self._srv_search_button = builder.get_object("srv_search_button")
        self._srv_search_button.bind_property("active", builder.get_object("srv_search_box"), "visible")
        self._srv_search_button.connect("toggled", services_search_provider.on_search_toggled)
        fav_search_provider = SearchProvider(self._fav_view,
                                             builder.get_object("fav_search_entry"),
                                             builder.get_object("fav_search_down_button"),
                                             builder.get_object("fav_search_up_button"),
                                             (Column.FAV_SERVICE, Column.FAV_TYPE, Column.FAV_POS))
        self._fav_search_button = builder.get_object("fav_search_button")
        self._fav_search_button.bind_property("active", builder.get_object("fav_search_box"), "visible")
        self._fav_search_button.connect("toggled", fav_search_provider.on_search_toggled)
        iptv_search_provider = SearchProvider(self._iptv_services_view,
                                              builder.get_object("iptv_search_entry"),
                                              builder.get_object("iptv_search_down_button"),
                                              builder.get_object("iptv_search_up_button"),
                                              (Column.IPTV_SERVICE,))
        self._iptv_search_button = builder.get_object("iptv_search_button")
        self._iptv_search_button.bind_property("active", builder.get_object("iptv_search_box"), "visible")
        self._iptv_search_button.connect("toggled", iptv_search_provider.on_search_toggled)
        # Playback.
        self._player_box = PlayerBox(self)
        self._player_box.bind_property("visible", self._profile_combo_box, "visible", 4)
        self._player_box.connect("show", self.on_playback_show)
        self._player_box.connect("playback-close", self.on_playback_close)
        self._player_box.connect("playback-full-screen", self.on_playback_full_screen)
        self._data_paned = builder.get_object("data_paned")
        self._data_paned.bind_property("visible", self._status_bar_box, "visible")
        self._main_paned = builder.get_object("main_paned")
        # Record.
        self._record_image = builder.get_object("record_button_image")
        # Dynamically active elements depending on the selected view.
        d_elements = (self._SERVICE_ELEMENTS, self._BOUQUET_ELEMENTS, self._COMMONS_ELEMENTS, self._FAV_ELEMENTS,
                      self._FAV_ENIGMA_ELEMENTS, self._FAV_IPTV_ELEMENTS)
        self._tool_elements = {k: builder.get_object(k) for k in set(chain.from_iterable(d_elements))}
        # Lock, Hide.
        self._bouquet_lock_hide_box = builder.get_object("bouquet_lock_hide_box")
        self._bouquets_view.bind_property("is-focus", self._bouquet_lock_hide_box, "sensitive")
        self.bind_property("is-enigma", builder.get_object("enigma_lock_hide_box"), "visible")
        # Clear "New" menu item
        self.bind_property("is-enigma", builder.get_object("services_clear_new_flag_item"), "visible")
        # Sub-bouquets menu item.
        self.bind_property("is-enigma", builder.get_object("bouquets_new_sub_popup_item"), "visible")
        # Stack page widgets.
        self._stack_services_frame = builder.get_object("services_frame")
        self._stack_satellite_box = builder.get_object("satellite_box")
        self._stack_picon_box = builder.get_object("picon_box")
        self._stack_epg_box = builder.get_object("epg_box")
        self._stack_timers_box = builder.get_object("timers_box")
        self._stack_recordings_box = builder.get_object("recordings_box")
        self._stack_ftp_box = builder.get_object("ftp_box")
        self._stack_control_box = builder.get_object("control_box")
        self.connect("change-page", self.on_page_change)
        self.connect("page-changed", self.on_page_changed)
        # Extra tools.
        self._telnet_box = builder.get_object("telnet_box")
        self._logs_box = builder.get_object("logs_box")
        self._logs_box.pack_start(LogsClient(self), True, True, 0)
        self._bottom_paned = builder.get_object("bottom_paned")
        self.connect("services-update", self.on_services_update)
        # Open-Send-Receive.
        self.connect("data-open", self.on_data_open)
        self.connect("data-extract", self.on_data_extract)
        self.connect("data-receive", self.on_download)
        self.connect("data-send", self.on_upload)
        # Data save.
        self.connect("data-save", self.on_data_save)
        self.connect("data-save-as", self.on_data_save_as)
        # Background tasks.
        self.connect("add-background-task", self.on_bg_task_add)
        self.connect("task-done", self.on_task_done)
        self.connect("task-cancel", self.on_task_cancel)
        # Font.
        self.connect("list-font-changed", self.on_list_font_changed)
        # Header bar.
        profile_box = builder.get_object("profile_combo_box")
        toolbar_box = builder.get_object("toolbar_main_box")
        if self._settings.use_header_bar:
            header_bar = HeaderBar()
            if IS_LINUX:
                header_bar.pack_start(builder.get_object("file_header_button"))

            header_bar.pack_start(profile_box)
            header_bar.pack_start(toolbar_box)
            header_bar.set_custom_title(builder.get_object("stack_switcher"))
            self._player_box.bind_property("visible", builder.get_object("main_popover_menu_box"), "visible", 4)
            self._player_box.bind_property("visible", builder.get_object("close_player_menu_button"), "visible")
            self._main_window.set_titlebar(header_bar)
        else:
            tool_bar = Gtk.Box(visible=True, spacing=6, margin=6, valign=Gtk.Align.CENTER)
            tool_bar.add(profile_box)
            tool_bar.add(toolbar_box)
            tool_bar.set_center_widget(builder.get_object("stack_switcher"))
            main_header_box = Gtk.Box(visible=True, spacing=6)
            main_header_box.get_style_context().add_class(Gtk.STYLE_CLASS_PRIMARY_TOOLBAR)
            main_header_box.pack_start(tool_bar, True, True, 0)
            main_box = builder.get_object("main_window_box")
            main_box.add(main_header_box)
            main_box.reorder_child(main_header_box, 0)
            self._data_paned.bind_property("visible", main_header_box, "visible")
        self._player_box.bind_property("visible", profile_box, "visible", 4)
        self._player_box.bind_property("visible", toolbar_box, "visible", 4)
        # Picons.
        self._picon_renderer = builder.get_object("picon_renderer")
        self._picon_column = builder.get_object("picon_column")
        self._picon_column.set_cell_data_func(self._picon_renderer, self.picon_data_func)
        self._fav_picon_renderer = builder.get_object("fav_picon_renderer")
        self._fav_picon_column = builder.get_object("fav_picon_column")
        self._fav_picon_column.set_cell_data_func(self._fav_picon_renderer, self.fav_picon_data_func)
        self._iptv_picon_renderer = builder.get_object("iptv_picon_renderer")
        self._iptv_picon_column = builder.get_object("iptv_picon_column")
        self._iptv_picon_column.set_cell_data_func(self._iptv_picon_renderer, self.iptv_picon_data_func)
        self._picon_column.set_visible(self._settings.display_picons)
        self._fav_picon_column.set_visible(self._settings.display_picons)
        self._iptv_picon_column.set_visible(self._settings.display_picons)
        # IPTV tab.
        self._iptv_button = builder.get_object("iptv_button")
        self._dvb_button = builder.get_object("dvb_button")
        iptv_type_column = builder.get_object("iptv_type_column")
        iptv_type_column.set_cell_data_func(builder.get_object("iptv_type_renderer"), self.iptv_type_data_func)
        iptv_button = builder.get_object("iptv_button")
        iptv_button.bind_property("active", self._filter_services_button, "visible", 4)
        iptv_button.bind_property("active", self._srv_search_button, "visible", 4)
        iptv_button.bind_property("active", builder.get_object("enigma_hide_button"), "visible", 4)
        iptv_button.bind_property("active", builder.get_object("enigma_locked_button"), "visible", 4)
        iptv_button.bind_property("active", self._filter_iptv_services_button, "visible")
        iptv_button.bind_property("active", self._iptv_search_button, "visible")
        iptv_button.bind_property("active", builder.get_object("iptv_export_to_m3u_button"), "visible")
        self._iptv_services_load_spinner.bind_property("active", self._filter_iptv_services_button, "sensitive", 4)
        self._iptv_services_load_spinner.bind_property("active", self._profile_combo_box, "sensitive", 4)
        self._iptv_services_load_spinner.bind_property("active", self._dvb_button, "sensitive", 4)
        self._services_load_spinner.bind_property("active", self._iptv_button, "sensitive", 4)
        self.connect("profile-changed", self.init_iptv)
        self.connect("iptv-service-added", self.on_iptv_service_added)
        self.connect("iptv-service-edited", self.on_iptv_service_edited)
        # EPG.
        self._display_epg = False
        self._epg_cache = None
        fav_service_column = builder.get_object("fav_service_column")
        fav_service_column.set_cell_data_func(builder.get_object("fav_service_renderer"), self.fav_service_data_func)
        self._epg_menu_button = builder.get_object("epg_menu_button")
        self._epg_menu_button.connect("realize", lambda b: b.set_popover(EpgSettingsPopover(self)))
        self.bind_property("is_enigma", self._epg_menu_button, "sensitive")
        self._epg_start_time_fmt = "%a, %H:%M"
        self._epg_end_time_fmt = "%H:%M"
        self.connect("epg-display-changed", self.on_epg_display_changed)
        # Hiding for Neutrino.
        self.bind_property("is_enigma", builder.get_object("services_button_box"), "visible")
        # Setting the last size of the window if it was saved.
        main_window_size = self._settings.get("window_size")
        if main_window_size:
            self._main_window.resize(*main_window_size)
        # Layout.
        self.init_layout()
        # Style.
        style_provider = Gtk.CssProvider()
        style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._status_bar_box.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), style_provider,
                                                                         Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.init_app_menu()
        self.init_actions()
        self.set_accels()

        self.init_drag_and_drop()
        self.init_appearance()
        self.filter_set_default()

    def do_activate(self):
        self._main_window.set_application(self)
        self._main_window.set_wmclass("DemonEditor", "DemonEditor")
        self._main_window.present()

        self.init_profiles()
        gen = self.init_http_api()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def do_shutdown(self):
        """  Performs shutdown tasks """
        if self._settings.load_last_config:
            self._settings.add("last_config", {"last_profile": self._settings.current_profile,
                                               "last_bouquet": self._current_bq_name})
        self._settings.save()  # storing current settings

        if self._http_api:
            self._http_api.close()

        Gtk.Application.do_shutdown(self)

    def do_command_line(self, command_line):
        """ Processing command line parameters. """
        options = command_line.get_options_dict()
        options = options.end().unpack()

        if "log" in options:
            init_logger()

        if "record" in options:
            log("Starting record of current stream...")
            log("Not implemented yet!")

        if "debug" in options:
            d_op = options.get("debug", "off")
            if d_op == "on":
                self._settings.debug_mode = True
            elif d_op == "off":
                self._settings.debug_mode = False
            else:
                msg = "No valid [on, off] arguments for -d found!"
                log(msg) if "log" in options else print(msg)
                return 1

            log(f"Debug mode is {d_op}.")
            self._settings.save()

        self.activate()
        return 0

    def init_app_menu(self):
        builder = get_builder(UI_RESOURCES_PATH + "app_menu.ui", tag="attribute")
        if not USE_HEADER_BAR:
            if IS_DARWIN:
                if not self.get_app_menu():
                    self.set_app_menu(builder.get_object("mac_app_menu"))
                self.set_menubar(builder.get_object("mac_menu_bar"))
            else:
                self.set_menubar(builder.get_object("menu_bar"))
        else:
            tools_menu = builder.get_object("tools_menu")
            tools_button = Gtk.MenuButton(visible=True, menu_model=tools_menu, direction=Gtk.ArrowType.NONE)
            tools_button.set_tooltip_text(translate("Tools"))
            tools_button.set_image(Gtk.Image.new_from_icon_name("applications-utilities-symbolic", Gtk.IconSize.BUTTON))

            view_menu = builder.get_object("view_menu")
            view_button = Gtk.MenuButton(visible=True, menu_model=view_menu, direction=Gtk.ArrowType.NONE)
            view_button.set_tooltip_text(translate("View"))

            box = Gtk.ButtonBox(visible=True, layout_style="expand")
            box.add(tools_button)
            box.add(view_button)
            self._main_window.get_titlebar().pack_end(box)
        # IPTV menu.
        self._iptv_menu_button.set_menu_model(builder.get_object("iptv_menu"))
        iptv_elem = self._tool_elements.get("fav_iptv_popup_item")
        for h in (self.on_iptv, self.on_import_yt_list, self.on_import_m3u, self.on_epg_list_configuration,
                  self.on_iptv_list_configuration, self.on_remove_all_unavailable):
            iptv_elem.bind_property("sensitive", self.set_action(h.__name__, h, False), "enabled")

        if self._settings.extensions_support:
            self.init_extensions(builder)

    def init_extensions(self, builder):
        import pkgutil
        from importlib.util import module_from_spec
        from app.ui.extensions.management import ExtensionManager
        # Extensions (Plugins) section.
        ext_section = builder.get_object(f"{'mac_' if IS_DARWIN else ''}extension_section")
        self.set_action("on_extension_manager", lambda a, v: ExtensionManager(self).show())
        ext_section.append_item(Gio.MenuItem.new(translate("Extension Manager"), "app.on_extension_manager"))

        ext_path = f"{self._settings.default_data_path}tools{os.sep}extensions"
        ext_paths = [f"{os.path.dirname(__file__)}{os.sep}extensions", ext_path, "extensions"]
        extensions = {}
        switchable = []
        default = []

        def ac(a, v):
            c = extensions[a.get_name()]
            e = c(self)
            e.exec()

        def sw(a, v):
            c = extensions[a.get_name()]
            a.set_state(v)
            e = c(self)
            e.exec() if v else e.stop()

        for importer, name, is_package in pkgutil.iter_modules(ext_paths):
            if is_package:
                spec = importer.find_spec(name)
                if spec is None:
                    log(f"Extension init error: Module {name} not found.")
                    continue

                m = module_from_spec(spec)
                spec.loader.exec_module(m)
                cls_name = name.capitalize()
                if hasattr(m, cls_name):
                    cls = getattr(m, cls_name)
                    if cls.EMBEDDED:
                        cls(self)
                        continue

                    action_name = f"on_{name}_extension"
                    item = Gio.MenuItem.new(cls.LABEL, f"app.{action_name}")
                    extensions[action_name] = cls

                    if cls.SWITCHABLE:
                        switchable.append(item)
                        self.set_state_action(action_name, sw, False)
                    else:
                        default.append(item)
                        self.set_action(action_name, ac)

        switchable.sort(key=lambda i: i.get_attribute_value("label"), reverse=True)
        default.sort(key=lambda i: i.get_attribute_value("label"), reverse=True)
        [ext_section.append_item(item) for item in switchable]
        [ext_section.append_item(item) for item in default]

    def init_actions(self):
        # Main actions.
        self.set_action("preferences", self.on_settings)
        self.set_action("about", self.on_about_app)
        self.set_action("quit", self.on_close_app)
        # Import.
        self.set_action("on_import_bouquet", self.on_import_bouquet)
        self.set_action("on_import_bouquets", self.on_import_bouquets)
        self.set_action("on_new_configuration", self.on_new_configuration)
        self.set_action("on_import_from_web", self.on_import_from_web)
        # Tools.
        self.set_action("on_backup_tool_show", self.on_backup_tool_show)
        self.set_state_action("on_telnet_show", self.on_telnet_show, False)
        self.set_state_action("on_logs_show", self.on_logs_show, False)
        # Filter.
        filter_action = Gio.SimpleAction.new("filter", None)
        filter_action.connect("activate", lambda a, v: self.emit("filter-toggled", None))
        self._main_window.add_action(filter_action)  # For "win.*" actions!
        self.connect("filter-toggled", self.on_services_filter_toggled)
        self.connect("filter-toggled", self.on_iptv_services_filter_toggled)
        # Lock, Hide.
        self.set_action("on_hide", self.on_hide)
        self.set_action("on_locked", self.on_locked)
        # Open and download/upload data.
        self.set_action("open_data", lambda a, v: self.open_data())
        self.set_action("upload_all", lambda a, v: self.emit("data-send", self._page))
        self.set_action("upload_bouquets", lambda a, v: self.on_upload_data(DownloadType.BOUQUETS))
        sa = self.set_action("on_data_save", lambda a, v: self.emit("data-save", self._page), False)
        self.bind_property("is-data-save-enabled", sa, "enabled")
        sa = self.set_action("on_data_save_as", lambda a, v: self.emit("data-save-as", self._page), False)
        self.bind_property("is-data-save-enabled", sa, "enabled")
        sa = self.set_action("on_receive", self.on_receive)
        self.bind_property("is-receive-data-enabled", sa, "enabled")
        sa = self.set_action("on_send", self.on_send, False)
        self.bind_property("is-send-data-enabled", sa, "enabled")
        sa = self.set_action("on_data_open", lambda a, v: self.emit("data-open", self._page))
        self.bind_property("is-data-open-enabled", sa, "enabled")
        sa = self.set_action("on_archive_open", lambda a, v: self.emit("data-extract", self._page))
        self.bind_property("is-data-extract-enabled", sa, "enabled")
        # Edit.
        self.set_action("on_edit", self.on_edit)
        # View actions.
        sa = self.set_state_action("show_bouquets", self.on_page_show, self._settings.get("show_bouquets", True))
        sa.connect("change-state", lambda a, v: self._stack_services_frame.set_visible(v))
        sa = self.set_state_action("show_satellites", self.on_page_show, self._settings.get("show_satellites", True))
        sa.connect("change-state", lambda a, v: self._stack_satellite_box.set_visible(v))
        sa = self.set_state_action("show_picons", self.on_page_show, self._settings.get("show_picons", True))
        sa.connect("change-state", lambda a, v: self._stack_picon_box.set_visible(v))
        sa = self.set_state_action("show_epg", self.on_page_show, self._settings.get("show_epg", True))
        sa.connect("change-state", lambda a, v: self._stack_epg_box.set_visible(v))
        self.bind_property("is-enigma", sa, "enabled")
        sa = self.set_state_action("show_timers", self.on_page_show, self._settings.get("show_timers", True))
        sa.connect("change-state", lambda a, v: self._stack_timers_box.set_visible(v))
        self.bind_property("is-enigma", sa, "enabled")
        sa = self.set_state_action("show_recordings", self.on_page_show, self._settings.get("show_recordings", True))
        sa.connect("change-state", lambda a, v: self._stack_recordings_box.set_visible(v))
        self.bind_property("is-enigma", sa, "enabled")
        sa = self.set_state_action("show_ftp", self.on_page_show, self._settings.get("show_ftp", True))
        sa.connect("change-state", lambda a, v: self._stack_ftp_box.set_visible(v))
        sa = self.set_state_action("show_control", self.on_page_show, self._settings.get("show_control", True))
        sa.connect("change-state", lambda a, v: self._stack_control_box.set_visible(v))
        self.bind_property("is-enigma", sa, "enabled")
        # Display picons.
        self.set_state_action("display_picons", self.set_display_picons, self._settings.display_picons)
        # Display EPG.
        sa = self.set_state_action("display_epg", self.set_display_epg, self._settings.display_epg)
        self.change_action_state("display_epg", GLib.Variant.new_boolean(self._settings.display_epg))
        self.bind_property("is-enigma", sa, "enabled")
        # Alternate layout.
        sa = self.set_state_action("set_alternate_layout", self.set_use_alt_layout, self._settings.alternate_layout)
        sa.connect("change-state", self.on_layout_change)
        # Header bar for macOS.
        sa = self.set_state_action("set_alternate_title", self.set_use_alt_title, self._settings.use_header_bar)
        sa.set_enabled(not IS_LINUX)
        # Menu bar and playback.
        self.set_action("on_playback_close", self._player_box.on_close)
        if not USE_HEADER_BAR:
            # We are working with the "hidden-when" submenu attribute. See 'app_menu_.ui' file.
            hide_bar_action = Gio.SimpleAction.new("hide_menu_bar", None)
            self._player_box.bind_property("visible", hide_bar_action, "enabled", 4)
            self.add_action(hide_bar_action)
            hide_media_bar = Gio.SimpleAction.new("hide_media_bar", None)
            hide_media_bar.set_enabled(False)
            self._player_box.bind_property("visible", hide_media_bar, "enabled")
            self.add_action(hide_media_bar)

    def set_action(self, name, fun, enabled=True):
        ac = Gio.SimpleAction.new(name, None)
        ac.connect("activate", fun)
        ac.set_enabled(enabled)
        self.add_action(ac)

        return ac

    def set_state_action(self, name, fun, enabled=True):
        action = Gio.SimpleAction.new_stateful(name, None, GLib.Variant.new_boolean(enabled))
        action.connect("change-state", fun)
        self.add_action(action)

        return action

    def set_accels(self):
        """ Setting accelerators for the actions. """
        self.set_accels_for_action("app.on_data_save", ["<primary>s"])
        self.set_accels_for_action("app.on_download_data", ["<primary>d"])
        self.set_accels_for_action("app.upload_all", ["<primary>u"])
        self.set_accels_for_action("app.upload_bouquets", ["<primary>b"])
        self.set_accels_for_action("app.open_data", ["<primary>o"])
        self.set_accels_for_action("app.on_hide", ["<primary>h"])
        self.set_accels_for_action("app.on_locked", ["<primary>l"])
        self.set_accels_for_action("app.quit", ["<primary>q"])
        self.set_accels_for_action("app.on_edit", ["<primary>e"])
        self.set_accels_for_action("app.on_telnet_show", ["<primary>t"])
        self.set_accels_for_action("app.on_logs_show", ["<shift><primary>l"])
        self.set_accels_for_action("win.filter", ["<shift><primary>f"])

    def init_profiles(self):
        self.update_profiles()
        if self._settings.load_last_config:
            config = self._settings.get("last_config") or {}
            if config.get("last_bouquet", None):
                self.connect("data-load-done", self.open_last_bouquet)
            last_profile = config.get("last_profile", None)
            self._profile_combo_box.set_active_id(last_profile)
            if last_profile == self._settings.default_profile:
                self.open_data()
        else:
            self._profile_combo_box.set_active_id(self._settings.current_profile)

    def init_drag_and_drop(self):
        """ Enable drag-and-drop. """
        target = []
        bq_target = []

        self._services_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.COPY)
        self._iptv_services_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.COPY)
        self._services_view.enable_model_drag_dest([], Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._fav_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target,
                                                Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE | Gdk.DragAction.COPY)
        self._fav_view.enable_model_drag_dest(target, Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._bouquets_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, bq_target,
                                                     Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._bouquets_view.enable_model_drag_dest(bq_target, Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._alt_view.enable_model_drag_dest(bq_target, Gdk.DragAction.DEFAULT | Gdk.DragAction.COPY)
        self._alt_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.MOVE)

        self._fav_view.drag_source_set_target_list(None)
        self._fav_view.drag_dest_add_text_targets()
        self._fav_view.drag_source_add_text_targets()
        self._fav_view.drag_dest_add_uri_targets()

        self._services_view.drag_source_set_target_list(None)
        self._services_view.drag_source_add_text_targets()
        self._services_view.drag_dest_add_text_targets()
        self._services_view.drag_dest_add_uri_targets()

        self._iptv_services_view.drag_source_set_target_list(None)
        self._iptv_services_view.drag_source_add_text_targets()

        self._bouquets_view.drag_dest_set_target_list(None)
        self._bouquets_view.drag_source_set_target_list(None)
        self._bouquets_view.drag_dest_add_text_targets()
        self._bouquets_view.drag_source_add_text_targets()

        self._alt_view.drag_source_set_target_list(None)
        self._alt_view.drag_source_add_text_targets()
        self._alt_view.drag_dest_add_text_targets()

        self._app_info_box.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self._app_info_box.drag_dest_add_text_targets()
        # For multiple selection.
        self._services_view.get_selection().set_select_function(self.view_selection_func)
        self._iptv_services_view.get_selection().set_select_function(self.view_selection_func)
        self._fav_view.get_selection().set_select_function(self.view_selection_func)
        self._bouquets_view.get_selection().set_select_function(self.view_selection_func)

    def init_appearance(self, update=False):
        """ Appearance initialisation.

            If update=False - first call on program start, else - after options changes!
        """
        if self._current_font != self._settings.list_font:
            self._current_font = self._settings.list_font
            self.emit("list-font-changed", self._current_font)

        if self._picons_size != self._settings.list_picon_size:
            self._picons_size = self._settings.list_picon_size
            self._picons.clear()
            self.refresh_models()

        self._picon_renderer.set_fixed_size(self._picons_size, self._picons_size * 0.65)
        self._fav_picon_renderer.set_fixed_size(self._picons_size, self._picons_size * 0.65)
        self._iptv_picon_renderer.set_fixed_size(self._picons_size, self._picons_size * 0.65)

        if self._s_type is SettingsType.ENIGMA_2:
            self._use_colors = self._settings.use_colors

            if self._use_colors:
                new_rgb = Gdk.RGBA()
                extra_rgb = Gdk.RGBA()
                new_rgb = new_rgb if new_rgb.parse(self._settings.new_color) else None
                extra_rgb = extra_rgb if extra_rgb.parse(self._settings.extra_color) else None
                if update:
                    gen = self.update_background_colors(new_rgb, extra_rgb)
                    GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
                else:
                    self._NEW_COLOR = new_rgb
                    self._EXTRA_COLOR = extra_rgb

    def init_layout(self):
        """ Initializes an alternate layout, if enabled. """
        if self._settings.alternate_layout:
            self._main_paned.pack2(self._player_box, True, True)
            self.reverse_main_elements(True)
        else:
            self._main_paned.remove(self._data_paned)
            self._main_paned.pack1(self._player_box, True, True)
            self._main_paned.pack2(self._data_paned, True, True)

    def init_bq_position(self):
        self._fav_paned.remove(self._fav_frame)
        self._fav_paned.remove(self._bq_frame)

        if self._settings.alternate_layout:
            self._fav_paned.pack1(self._bq_frame, True, False)
            self._fav_paned.pack2(self._fav_frame, True, False)
        else:
            self._fav_paned.pack1(self._fav_frame, True, False)
            self._fav_paned.pack2(self._bq_frame, True, False)

    def init_main_paned_position(self, paned):
        """ Initializes starting positions of main paned widgets. """
        width = paned.get_allocated_width()
        main_position = self._settings.get("data_paned_position", width * 0.5)
        fav_position = self._settings.get("fav_paned_position", width * 0.25)
        paned.set_position(main_position)
        self._fav_paned.set_position(fav_position)

    def init_new_services_models(self):
        """ Initializes new models for main services view. """
        column_types = (self._services_model.get_column_type(i) for i in range(self._services_model.get_n_columns()))
        self._services_model = Gtk.ListStore(*column_types)
        self._services_model.set_name(self.SERVICE_MODEL)
        self._services_model_filter = self._services_model.filter_new()
        self._services_model_filter.set_visible_func(self.services_filter_function)
        self._services_view.set_model(Gtk.TreeModelSort(model=self._services_model_filter))

    def init_new_iptv_models(self):
        """ Initializes new models for IPTV services view. """
        column_types = (self._iptv_model.get_column_type(i) for i in range(self._iptv_model.get_n_columns()))
        self._iptv_model = Gtk.ListStore(*column_types)
        self._iptv_model.set_name(self.IPTV_MODEL)
        self._iptv_services_model_filter = self._iptv_model.filter_new()
        self._iptv_services_model_filter.set_visible_func(self.iptv_services_filter_function)
        self._iptv_services_view.set_model(Gtk.TreeModelSort(model=self._iptv_services_model_filter))

    def init_iptv(self, app, profile):
        """ Initializes IPTV after profile change. """
        self._dvb_button.set_active(True)
        # We will recreate the models every time. At the moment it looks the best.
        self._iptv_count_label.set_text("0")
        self.init_new_iptv_models()

    def update_background_colors(self, new_color, extra_color):
        if extra_color != self._EXTRA_COLOR:
            for row in self._fav_model:
                if row[Column.FAV_BACKGROUND]:
                    row[Column.FAV_BACKGROUND] = extra_color
                    yield True

        if new_color != self._NEW_COLOR:
            for row in self._services_model:
                if row[Column.SRV_BACKGROUND]:
                    row[Column.SRV_BACKGROUND] = new_color
                    yield True

        self._NEW_COLOR = new_color
        self._EXTRA_COLOR = extra_color
        yield True

    def on_list_font_changed(self, app, font):
        """ Modifies the font of the main views when changed in the settings. """
        from gi.repository import Pango
        font_desc = Pango.FontDescription.from_string(font)
        views = (self._services_view, self._iptv_services_view, self._fav_view, self._bouquets_view)
        list(map(lambda v: v.modify_font(font_desc), views))

    @staticmethod
    def force_ctrl(view, event):
        """ Function for force ctrl press event for view """
        if not event.state & Gdk.ModifierType.SHIFT_MASK:
            event.state |= MOD_MASK

    def on_close_app(self, *args):
        """ Performing operations before closing the application. """
        # Saving the current size of the application window.
        if not self._main_window.is_maximized():
            self._settings.add("window_size", self._main_window.get_size())
        # Saving the state of the main paned widgets.
        self._settings.add("data_paned_position", self._data_paned.get_position())
        self._settings.add("fav_paned_position", self._fav_paned.get_position())

        if self.is_data_loading():
            msg = f"{translate('Data loading in progress!')}\n\n\t{translate('Are you sure?')}"
            if show_dialog(DialogType.QUESTION, self._main_window, msg) != Gtk.ResponseType.OK:
                return True

        if self._recorder:
            if self._recorder.is_record():
                msg = f"{translate('Recording in progress!')}\n\n\t{translate('Are you sure?')}"
                if show_dialog(DialogType.QUESTION, self._main_window, msg) != Gtk.ResponseType.OK:
                    return True
            self._recorder.release()

        if not self.is_data_saved():
            gen = self.save_data(lambda: GLib.idle_add(self.quit))
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
            return True
        else:
            GLib.idle_add(self.quit)

    def on_main_window_state(self, window, event):
        if event.new_window_state & Gdk.WindowState.FULLSCREEN or event.new_window_state & Gdk.WindowState.MAXIMIZED:
            # Saving the current size of the application window.
            self._settings.add("window_size", self._main_window.get_size())

    @run_idle
    def on_about_app(self, action, value=None):
        show_dialog(DialogType.ABOUT, self._main_window)

    @run_idle
    def move_items(self, key):
        """ Move items in fav or bouquets tree view """
        if self._services_view.is_focus():
            return
        move_items(key, self._fav_view if self._fav_view.is_focus() else self._bouquets_view)

    # ************** Pages initialization *************** #

    def on_satellites_realize(self, box):
        if not self._satellite_tool:
            self._satellite_tool = SatellitesTool(self, self._settings)
            box.pack_start(self._satellite_tool, True, True, 0)

    def on_picons_realize(self, box):
        if not self._picon_manager:
            ids = {}
            if self._s_type is SettingsType.ENIGMA_2:
                for r in self._services_model:
                    data = r[Column.SRV_PICON_ID].split("_")
                    ids[f"{data[3]}:{data[5]}:{data[6]}"] = r[Column.SRV_PICON_ID]

            self._picon_manager = PiconManager(self, self._settings, ids, self._sat_positions)
            box.pack_start(self._picon_manager, True, True, 0)

    def on_epg_realize(self, box):
        if not self._epg_tool:
            self._epg_tool = EpgTool(self)
            box.pack_start(self._epg_tool, True, True, 0)

    def on_timers_realize(self, box):
        if not self._timers_tool:
            self._timers_tool = TimerTool(self, self._http_api)
            box.pack_start(self._timers_tool, True, True, 0)

    def on_recordings_realize(self, box):
        if not self._recordings_tool:
            self._recordings_tool = RecordingsTool(self)
            box.pack_start(self._recordings_tool, True, True, 0)
            self._player_box.connect("play", self._recordings_tool.on_playback)
            self._player_box.connect("playback-close", self._recordings_tool.on_playback_close)

    def on_ftp_realize(self, box):
        if not self._ftp_client:
            self._ftp_client = FtpClientBox(self, self._settings)
            box.pack_start(self._ftp_client, True, True, 0)

    def on_control_realize(self, box):
        if not self._control_tool:
            self._control_tool = ControlTool(self, self._settings)
            box.pack_start(self._control_tool, True, True, 0)

    def on_telnet_realize(self, box):
        box.pack_start(TelnetClient(self), True, True, 0)

    def on_visible_page(self, stack, param):
        self._page = Page(stack.get_visible_child_name())
        self._fav_paned.set_visible(self._page in self._fav_pages)
        self.is_data_save_enabled = self._page in self.DATA_SAVE_PAGES
        self.is_data_open_enabled = self._page in self.DATA_OPEN_PAGES
        self.is_data_extract_enabled = self._page in self.DATA_EXTRACT_PAGES
        self.is_send_data_enabled = self._page in self.DATA_SEND_PAGES
        self.is_receive_data_enabled = self._page in self.DATA_RECEIVE_PAGES_enabled
        self.emit("page-changed", self._page)

    def on_iptv_toggled(self, button):
        is_iptv = button.get_active()
        self._services_stack.set_visible_child_name("iptv" if is_iptv else "dvb")
        # We add data only if the model is empty.
        if is_iptv and not len(self._iptv_model):
            gen = self.append_iptv_data()
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_page_show(self, action, value):
        action.set_state(value)
        self._settings.add(action.get_name(), bool(value))

    def on_page_change(self, app, page_name):
        self._stack.set_visible_child_name(page_name)

    def on_page_changed(self, app, page):
        if not self._settings.load_last_config and not len(self._bouquets_model):
            self.open_data()

    def set_use_alt_layout(self, action, value):
        action.set_state(value)
        self._settings.alternate_layout = bool(value)

    def set_use_alt_title(self, action, value):
        action.set_state(value)
        value = bool(value)
        self._settings.use_header_bar = bool(value)

        msg = translate("Restart the program to apply all changes.")
        if value:
            warn = "It can cause some problems."
            msg = f"{translate('EXPERIMENTAL!')} {warn} {msg}"
        self.show_info_message(msg, Gtk.MessageType.WARNING)

    @run_idle
    def on_layout_change(self, action, value):
        is_alt = bool(value)
        self.reverse_main_elements(is_alt)
        if self._settings.play_streams_mode is PlayStreamsMode.BUILT_IN:
            msg = translate("Layout of elements has been changed!")
            msg = f"{msg} {translate('Restart the program to apply all changes.')}"
            self.show_info_message(msg, Gtk.MessageType.WARNING)

        self.emit("layout-changed", is_alt)

    def reverse_main_elements(self, alt_layout):
        self._data_paned.remove(self._stack)
        self._data_paned.remove(self._fav_paned)
        self._data_paned.pack1(self._fav_paned if alt_layout else self._stack, True, False)
        self._data_paned.pack2(self._stack if alt_layout else self._fav_paned, True, False)

        self.init_bq_position()

    # ****************** Custom data functions ***************** #

    def iptv_type_data_func(self, column, renderer, model, itr, data):
        fav_id = model.get_value(itr, Column.IPTV_FAV_ID)
        f_data = fav_id.split(":", maxsplit=1)
        renderer.set_property("text", f"{StreamType(f_data[0].strip() if f_data else '0').name}")

    def iptv_picon_data_func(self, column, renderer, model, itr, data):
        picon_id, name = model.get_value(itr, Column.IPTV_PICON_ID), model.get_value(itr, Column.IPTV_SERVICE)
        renderer.set_property("pixbuf", self.get_picon_pixbuf(picon_id, name))

    def picon_data_func(self, column, renderer, model, itr, data):
        picon = self._picons.get(model.get_value(itr, Column.SRV_PICON_ID))
        if not picon:
            picon = self._picons.get(get_picon_file_name(model.get_value(itr, Column.SRV_SERVICE)))
        renderer.set_property("pixbuf", picon)

    def fav_picon_data_func(self, column, renderer, model, itr, data):
        srv = self._services.get(model.get_value(itr, Column.FAV_ID), None)
        if not srv or not srv.service:
            return True

        picon = self.get_picon_pixbuf(srv.picon_id, srv.service)
        # Alternatives.
        if srv.service_type == BqServiceType.ALT.name:
            alt_servs = srv.transponder
            if alt_servs:
                alt_srv = self._services.get(alt_servs[0].data, None)
                if alt_srv:
                    picon = self._picons.get(alt_srv.picon_id, None) if srv else None

        renderer.set_property("pixbuf", picon)

    def get_picon_pixbuf(self, picon_id, srv_name):
        """ Returns a picon pixbuf by id or service name.

            Used for models with IPTV services.
        """
        picon = self._picons.get(picon_id)
        # Trying to get a satellite service piсon.
        if not picon and picon_id:
            picon = self._picons.get(picon_id.replace(picon_id[:picon_id.find("_")], "1", 1))
        # Getting picon by service name.
        if not picon:
            picon = self._picons.get(get_picon_file_name(srv_name))

        return picon

    def fav_service_data_func(self, column, renderer, model, itr, data):
        if self._display_epg and self._s_type is SettingsType.ENIGMA_2:
            srv_name = model.get_value(itr, Column.FAV_SERVICE)
            if model.get_value(itr, Column.FAV_TYPE) in self.MARKER_TYPES:
                return True

            event = self._epg_cache.get_current_event(srv_name)
            if event:
                if event.start:
                    start = datetime.fromtimestamp(event.start).strftime(self._epg_start_time_fmt)
                    end = datetime.fromtimestamp(event.end).strftime(self._epg_end_time_fmt)
                    sep = "-"
                else:
                    start, end, sep = "", "", ""
                # https://docs.gtk.org/Pango/pango_markup.html
                renderer.set_property("markup", (f'{escape(srv_name)}\n\n'
                                                 f'<span size="small" weight="bold">{escape(event.title)}</span>\n'
                                                 f'<span size="small" style="italic">{start} {sep} {end}</span>'))
                return False
        return True

    def view_selection_func(self, *args):
        """ Used to control selection via drag and drop in views [via _select_enabled field].

            Prevents deselection when the mouse is clicked.
        """
        return self._select_enabled

    # ***************** Copy - Cut - Paste ********************* #

    def on_services_copy(self, view):
        self.on_copy(view, target=ViewTarget.FAV)

    def on_iptv_services_copy(self, view):
        self.on_copy(view, target=ViewTarget.IPTV)

    def on_fav_copy(self, view):
        self.on_copy(view, target=ViewTarget.SERVICES)

    def on_bouquets_copy(self, view):
        self.on_copy(view, target=ViewTarget.BOUQUET)

    def on_copy(self, view, target):
        if not self._settings.unlimited_copy_buffer:
            self._bouquets_buffer.clear() if target is ViewTarget.BOUQUET else self._rows_buffer.clear()

        model, paths = view.get_selection().get_selected_rows()

        if target is ViewTarget.FAV:
            self._rows_buffer.extend((0, *model.get(model.get_iter(path), Column.SRV_CODED, Column.SRV_SERVICE,
                                                    Column.SRV_LOCKED, Column.SRV_HIDE, Column.SRV_TYPE, Column.SRV_POS,
                                                    Column.SRV_FAV_ID, Column.SRV_PICON), None, None) for path in paths)
        elif target is ViewTarget.SERVICES:
            self._rows_buffer.extend(model[path][:] for path in paths)
        elif target is ViewTarget.IPTV:
            self._rows_buffer.extend(((0, None, row[Column.IPTV_SERVICE], None, None, BqServiceType.IPTV.name, None,
                                       row[Column.IPTV_FAV_ID], row[Column.IPTV_PICON], None, None) for row in
                                      (model[path][:] for path in paths)))
        elif target is ViewTarget.BOUQUET:
            to_copy = list(map(model.get_iter, filter(lambda p: p.get_depth() == 2, paths)))
            if to_copy:
                self._bouquets_buffer.extend([model[i][:] for i in to_copy])

    def on_reference_copy(self, view):
        """ Copying picon id to clipboard. """
        copy_reference(view, self)

    def on_fav_cut(self, view):
        self.on_cut(view, ViewTarget.FAV)

    def on_bouquets_cut(self, view):
        self.on_cut(view, ViewTarget.BOUQUET)

    def on_cut(self, view, target=None):
        if not self._settings.unlimited_copy_buffer:
            self._bouquets_buffer.clear() if target is ViewTarget.BOUQUET else self._rows_buffer.clear()

        if target is ViewTarget.FAV:
            for row in tuple(self.on_delete(view)):
                self._rows_buffer.append(row)
        elif target is ViewTarget.BOUQUET:
            model, paths = view.get_selection().get_selected_rows()
            to_cut = list(map(model.get_iter, filter(lambda p: p.get_depth() == 2, paths)))
            if to_cut:
                self._bouquets_buffer.extend([model[i][:] for i in to_cut])
                list(map(model.remove, to_cut))

    def on_fav_paste(self, view):
        self.on_paste(view, ViewTarget.FAV)

    def on_bouquets_paste(self, view):
        self.on_paste(view, ViewTarget.BOUQUET)

    def on_paste(self, view, target):
        selection = view.get_selection()

        if target is ViewTarget.FAV:
            self.fav_paste(selection)
        elif target is ViewTarget.BOUQUET:
            self.bouquet_paste(selection)
        self.on_view_focus(view)

    def fav_paste(self, selection):
        dest_index = 0
        bq_selected = self.check_bouquet_selection()
        if not bq_selected:
            return

        fav_bouquet = self._bouquets[bq_selected]
        model, paths = selection.get_selected_rows()

        if paths:
            dest_index = int(paths[0][0])

        for row in self._rows_buffer:
            dest_index += 1
            model.insert(dest_index, row)
            fav_bouquet.insert(dest_index, row[Column.FAV_ID])

        if model.get_name() == self.FAV_MODEL:
            self.update_fav_num_column(model)

        self._rows_buffer.clear()

    def bouquet_paste(self, selection):
        model, paths = selection.get_selected_rows()
        if len(paths) > 1:
            self.show_error_message("Please, select only one item!")
            return

        path = paths[0]
        dest_iter = model.get_iter(path)

        if path.get_depth() == 1:
            list(map(lambda r: model.append(dest_iter, r), self._bouquets_buffer))
            self._bouquets_view.expand_all()
        else:
            p_iter = model.iter_parent(dest_iter)
            dest_index = path.get_indices()[1] + 1
            for index, row in enumerate(self._bouquets_buffer):
                model.insert(p_iter, dest_index + index, row)
        self._bouquets_buffer.clear()
        self.update_bouquets_type()

    def on_services_update(self, app, services):
        """ Updates services in the main model. """
        for r in self._fav_model:
            fav_id = r[Column.FAV_ID]
            if fav_id in services:
                service = services[fav_id]
                r[Column.FAV_SERVICE] = service.service

        for r in self._services_model:
            fav_id = r[Column.SRV_FAV_ID]
            if fav_id in services:
                service = services[fav_id]
                r[Column.SRV_SERVICE] = service.service

    # ***************** Deletion ********************* #

    def on_delete(self, view):
        """ Delete selected items from view

            returns deleted rows list!
        """
        if self.is_data_loading():
            show_dialog(DialogType.ERROR, self._main_window, translate("Data loading in progress!"))
            return

        selection = view.get_selection()
        model, paths = selection.get_selected_rows()
        if not paths:
            self.show_error_message("No selected item!")
            return

        model_name = get_base_model(model).get_name()
        itrs = [model.get_iter(path) for path in paths]
        rows = [model[in_itr][:] for in_itr in itrs]

        if len(itrs) > self.DEL_FACTOR:
            self._wait_dialog.show("Deleting data...")

        priority = GLib.PRIORITY_LOW

        if model_name == self.FAV_MODEL:
            gen = self.remove_favs(itrs, model)
        elif model_name == self.BQ_MODEL:
            gen = self.delete_bouquets(itrs, model)
            priority = GLib.PRIORITY_DEFAULT
        elif model_name == self.SERVICE_MODEL:
            gen = self.delete_services(itrs, model, rows, self._services_model)
        elif model_name == self.IPTV_MODEL:
            gen = self.delete_services(itrs, model, rows, self._iptv_model, Column.IPTV_FAV_ID)
        elif model_name == self.ALT_MODEL:
            gen = self.delete_alts(itrs, model, rows)

        GLib.idle_add(lambda: next(gen, False), priority=priority)
        self.on_view_focus(view)

        return rows

    def remove_favs(self, itrs, model):
        """ Deleting bouquet services. """
        if self._bq_selected:
            fav_bouquet = self._bouquets.get(self._bq_selected, None)
            if fav_bouquet:
                for index, itr in enumerate(itrs):
                    del fav_bouquet[int(model.get_path(itr)[0])]
                    self._fav_model.remove(itr)
                    if index % self.DEL_FACTOR == 0:
                        yield True
                self.update_fav_num_column(model)

        self.on_model_changed(self._fav_model)
        self._wait_dialog.hide()
        yield True

    def delete_services(self, itrs, model, rows, srv_model, fav_column=Column.SRV_FAV_ID):
        """ Deleting services. """
        for index, s_itr in enumerate(get_base_itrs(itrs, model)):
            srv_model.remove(s_itr)
            if index % self.DEL_FACTOR == 0:
                yield True

        srv_ids_to_delete = set()
        for row in rows:
            # There are channels with the same parameters except for the name.
            # None because it can have duplicates! Need fix
            fav_id = row[fav_column]
            for bq in self._bouquets:
                services = self._bouquets[bq]
                if services:
                    with suppress(ValueError):
                        services.remove(fav_id)
                        srv_ids_to_delete.add(fav_id)
            self._services.pop(fav_id, None)

        for f_itr in filter(lambda r: r[Column.FAV_ID] in srv_ids_to_delete, self._fav_model):
            self._fav_model.remove(f_itr.iter)

        self.update_fav_num_column(self._fav_model)
        self.refresh_counters(srv_model)
        self._wait_dialog.hide()
        yield True

    @run_with_delay(1)
    def refresh_counters(self, srv_model):
        self.on_model_changed(srv_model)
        self.update_sat_positions()

    def delete_bouquets(self, itrs, model):
        """ Deleting bouquets """
        if len(itrs) == 1 and len(model.get_path(itrs[0])) < 2:
            self.show_error_message("This item is not allowed to be removed!")
            return

        for itr in itrs:
            if len(model.get_path(itr)) < 2:
                continue

            self._fav_model.clear()
            yield True
            b_row = self._bouquets_model[itr][:]
            self._bouquets.pop(f"{b_row[Column.BQ_NAME]}:{b_row[Column.BQ_TYPE]}", None)
            self._bouquets_model.remove(itr)

        self._bq_selected = ""
        self._bq_name_label.set_text(self._bq_selected)
        self.on_model_changed(model)
        self._wait_dialog.hide()
        yield True

    # ***************** Bouquets ********************* #

    def get_bouquet_file_name(self, bouquet):
        bouquet_file_name = "{}userbouquet.{}.{}".format(self._settings.get(self._s_type).get("data_dir_path"),
                                                         *bouquet.split(":"))
        return bouquet_file_name

    def on_new_bouquet(self, view, sub=False):
        """ Creates a new item in the bouquets tree """
        model, paths = view.get_selection().get_selected_rows()

        if paths:
            itr = model.get_iter(paths[0])
            if not model.iter_parent(itr) and sub:
                self.show_error_message("Not allowed in this context!")
                return

            bq_type = model.get_value(itr, Column.BQ_TYPE)
            bq_name = gen_bouquet_name(self._bouquets, "bouquet", bq_type)

            response = show_dialog(DialogType.INPUT, self._main_window, bq_name)
            if response == Gtk.ResponseType.CANCEL:
                return

            bq = response, None, None, bq_type
            key = f"{response}:{bq_type}"

            while key in self._bouquets:
                self.show_error_message(translate("A bouquet with that name exists!"))
                response = show_dialog(DialogType.INPUT, self._main_window, bq_name)
                if response == Gtk.ResponseType.CANCEL:
                    return

                key = f"{response}:{bq_type}"
                bq = response, None, None, bq_type

            self._current_bq_name = response

            if not model.iter_parent(itr):  # root parent
                scroll_to(model.get_path(model.insert(itr, Column.BQ_NAME, bq)), view, paths)
            else:
                p_itr = model.iter_parent(itr)
                if sub:
                    if model.iter_parent(p_itr):
                        self.show_error_message("Not allowed in this context!")
                        return
                    else:
                        if len(self._fav_model):
                            msg = "This bouquet already contains data.\n\nThey may be lost when saved!"
                            if show_dialog(DialogType.QUESTION, self._main_window, msg) != Gtk.ResponseType.OK:
                                return

                        scroll_to(model.get_path(model.append(itr, bq)), view, paths)
                else:
                    it = model.insert(p_itr, int(model.get_path(itr)[1]) + 1, bq) if p_itr else model.append(itr, bq)
                    scroll_to(model.get_path(it), view, paths)
            self._bouquets[key] = []

    def on_new_sub_bouquet(self, item=None):
        self.on_new_bouquet(self._bouquets_view, True)

    def on_edit(self, *args):
        """ Edit header bar button """
        if self._services_view.is_focus():
            self.on_service_edit(self._services_view)
        elif self._iptv_services_view.is_focus():
            self.on_service_edit(self._iptv_services_view)
        elif self._fav_view.is_focus():
            self.on_service_edit(self._fav_view)
        elif self._bouquets_view.is_focus():
            self.on_rename(self._bouquets_view)

    def on_to_fav_copy(self, view):
        """ Copy items from main to beginning of fav list """
        selection = self.get_selection(view)
        if selection:
            self.receive_selection(view=self._fav_view, drop_info=None, data=selection)
            scroll_to(0, self._fav_view)

    def on_to_fav_end_copy(self, view):
        """  Copy items from main to end of fav list """
        selection = self.get_selection(view)
        if selection:
            pos = Gtk.TreeViewDropPosition.AFTER
            path = Gtk.TreePath.new()
            mod_len = len(self._fav_model)
            info = None
            if mod_len > 0:
                path.append_index(mod_len - 1)
                info = (path, pos)
            self.receive_selection(view=self._fav_view, drop_info=info, data=selection)
            if mod_len > 0:
                scroll_to(mod_len, self._fav_view)

    @run_with_delay(1)
    def update_fav_num_column(self, model):
        """ Iterate through model and updates values for Num column """
        gen = self.update_num_column(model)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def update_num_column(self, model):
        num = 0
        for row in model:
            is_marker = row[Column.FAV_TYPE] in self.MARKER_TYPES
            if not is_marker:
                num += 1
            row[Column.FAV_NUM] = 0 if is_marker else num

        self.on_model_changed(model)
        yield True

    def update_bouquet_list(self):
        """ Update bouquet after move items """
        if self._bq_selected:
            fav_bouquet = self._bouquets[self._bq_selected]
            fav_bouquet.clear()
            for row in self._fav_model:
                fav_bouquet.append(row[Column.FAV_ID])

    # ** Bouquet details sort [sorting model not used!] ** #

    def on_fav_sort(self, column):
        """ Bouquet details (FAV) list sorting by clicking on column header. """
        if not len(self._fav_model):
            return

        bq = self._bouquets.get(self._bq_selected, None)
        if not bq:
            return

        msg = "Are you sure you want to change the order\n\t of services in this bouquet?"
        if show_dialog(DialogType.QUESTION, self._main_window, msg) != Gtk.ResponseType.OK:
            return

        c_num = Column.FAV_NUM
        c_name = column.get_name()

        if c_name == "fav_service_column":
            c_num = Column.FAV_SERVICE
        elif c_name == "fav_type_column":
            c_num = Column.FAV_TYPE
        elif c_name == "fav_pos_column":
            c_num = Column.FAV_POS

        order = column.get_sort_order()
        if not column.get_sort_indicator():
            self.reset_view_sort_indication(self._fav_view)
            column.set_sort_indicator(True)
        else:
            order = not order
            column.set_sort_order(not column.get_sort_order())

        model, paths = self._fav_view.get_selection().get_selected_rows()

        if len(paths) < 2 and len(bq) > self.FAV_FACTOR or len(paths) > self.FAV_FACTOR:
            self._wait_dialog.show(translate("Sorting data..."))
        GLib.idle_add(self.sort_fav, c_num, bq, paths, order, 0 if c_num == Column.FAV_NUM else "")

    def sort_fav(self, c_num, bq, paths, rev=False, nv=""):
        """ Sorting function for the bouquet details list.

            @param c_num: column number
            @param bq: current bouquet
            @param paths: selected paths
            @param rev: sort reverse.
            @param nv: default value for the None items.
            If the number of selected items is more than one, then only these items will be sorted!
        """
        rows = self._fav_model if len(paths) < 2 else [self._fav_model[p] for p in paths]
        index = int(str(rows[0].path))
        columns = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        for s_row, row in zip(sorted(map(
                lambda r: r[:], rows),
                key=lambda r: r[c_num] or nv if c_num != Column.FAV_POS else get_pos_num(r[c_num]),
                reverse=rev), rows):
            self._fav_model.set(row.iter, columns, s_row)
            bq[index] = s_row[Column.FAV_ID]
            index += 1

        self._wait_dialog.hide()
        self._fav_view.grab_focus()

    def reset_view_sort_indication(self, view):
        for column in view.get_columns():
            column.set_sort_indicator(False)
            column.set_sort_order(Gtk.SortType.ASCENDING)

    def position_sort_func(self, model, iter1, iter2, column):
        """ Custom sort function for position column. """
        return get_pos_num(model.get_value(iter1, column)) - get_pos_num(model.get_value(iter2, column))

    # ********************* Hints ************************* #

    def on_bq_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        if not self._main_window.is_active():
            return False

        result = view.get_dest_row_at_pos(x, y)
        if not result:
            return False

        path, pos = result
        model = view.get_model()

        row = model[path][:]
        name, b_type = row[Column.BQ_NAME], row[Column.BQ_TYPE]
        b_id = f"{name}:{b_type}"
        bq = self._bouquets.get(b_id, None)
        if bq is None:
            return False

        counter = Counter(s.service_type for s in filter(None, (self._services.get(f_id, None) for f_id in bq)))
        services_txt = "\n".join(f"{k}: {v}" for k, v in counter.items())
        n_msg, s_msg, f_msg = translate("Name"), translate("Services"), translate("File")
        f = f"\n\n{f_msg}: {self._bq_file.get(b_id, '')}" if self._s_type is SettingsType.ENIGMA_2 else ""
        tooltip.set_text(f"{n_msg}: {name}\n{s_msg}:\n{services_txt}{f}")
        view.set_tooltip_row(tooltip, path)

        return True

    def on_fav_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        """  Sets detailed info about service in the tooltip [fav view]. """
        if not self._main_window.is_active():
            return False

        result = view.get_dest_row_at_pos(x, y)
        if not result or not self._settings.show_bq_hints:
            return False

        return self.get_tooltip(view, result, tooltip)

    def on_services_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        """  Sets short info about service in the tooltip [main services view]. """
        if not self._main_window.is_active():
            return False

        result = view.get_dest_row_at_pos(x, y)
        if not result or not self._settings.show_srv_hints:
            return False

        return self.get_tooltip(view, result, tooltip, target=ViewTarget.SERVICES)

    def on_iptv_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        if not self._main_window.is_active():
            return False

        result = view.get_dest_row_at_pos(x, y)
        if not result or not self._settings.show_srv_hints:
            return False

        path, pos = result
        srv = self._services.get(view.get_model()[path][Column.IPTV_FAV_ID], None)
        if srv and srv.picon_id:
            tooltip.set_icon(self.get_tooltip_picon(srv))
            fav_id = srv.fav_id
            names = (b[:b.rindex(":")] for b, ids in self._bouquets.items() if fav_id in ids)
            text = f"{translate('Name')}: {srv.service}\n{translate('Bouquets')}: {', '.join(names)}"
            tooltip.set_text(text)
            view.set_tooltip_row(tooltip, path)
            return True
        return False

    def get_tooltip(self, view, dst_row, tooltip, target=ViewTarget.FAV):
        path, pos = dst_row
        model = view.get_model()

        target_column = Column.FAV_ID if target is ViewTarget.FAV else Column.SRV_FAV_ID
        srv = self._services.get(model[path][target_column], None)
        if srv and srv.picon_id:
            tooltip.set_icon(self.get_tooltip_picon(srv))
            txt = self.get_hint_for_fav_list(srv) if target is ViewTarget.FAV else self.get_hint_for_srv_list(srv)
            tooltip.set_text(txt)
            view.set_tooltip_row(tooltip, path)
            return True
        return False

    def get_hint_for_fav_list(self, srv):
        """ Returns detailed info about service as formatted string for using as hint. """
        header, ref = self.get_hint_header_info(srv)

        if srv.service_type == BqServiceType.IPTV.name:
            return f"{header}{ref}"

        pol = ", {}: {},".format(translate("Pol"), srv.pol) if srv.pol else ","
        fec = "{}: {}".format("FEC", srv.fec) if srv.fec else ","
        ht = "{}{}: {}\n{}: {}\n{}: {}\n{}: {}{} {}, {}\n{}"
        return ht.format(header,
                         translate("Package"), srv.package,
                         translate("System"), srv.system,
                         translate("Freq"), srv.freq,
                         translate("Rate"), srv.rate, pol, fec,
                         self.get_ssid_info(srv),
                         ref)

    def get_hint_for_srv_list(self, srv):
        """ Returns short info about service as formatted string for using as hint. """
        header, ref = self.get_hint_header_info(srv)
        return f"{header}{self.get_ssid_info(srv)}\n{ref}"

    def get_hint_header_info(self, srv):
        header = f"{translate('Name')}: {srv.service}\n{translate('Type')}: {srv.service_type}\n"
        ref = f"{translate('Service reference')}: {get_service_reference(srv)}"
        return header, ref

    def get_ssid_info(self, srv):
        """ Returns SID representation in hex and dec formats. """
        sid = srv.ssid or "0"
        try:
            dec = "{0:04d}".format(int(sid, 16))
        except ValueError as e:
            log(f"SID value conversion error: {e}")
        else:
            return f"SID: 0x{sid.upper()} ({dec})"

        return f"SID: 0x{sid.upper()}"

    # ***************** Drag-and-drop ********************* #

    def on_view_drag_begin(self, view, context):
        """ Sets its own icon for dragging.

            We have to use "connect_after" (after="yes" in xml) to override what the default handler did.
            https://lazka.github.io/pgi-docs/Gtk-3.0/classes/Widget.html#Gtk.Widget.signals.drag_begin
        """
        top_model, paths = view.get_selection().get_selected_rows()
        if len(paths) < 1:
            return

        name, model = get_model_data(view)
        name_column, type_column = Column.SRV_SERVICE, Column.SRV_TYPE
        if name == self.FAV_MODEL:
            name_column, type_column = Column.FAV_SERVICE, Column.FAV_TYPE
        elif name == self.BQ_MODEL:
            name_column, type_column = Column.BQ_NAME, Column.BQ_TYPE
        elif name == self.ALT_MODEL:
            name_column, type_column = Column.ALT_SERVICE, Column.ALT_TYPE
        elif name == self.IPTV_MODEL:
            name_column, type_column = Column.IPTV_SERVICE, Column.IPTV_TYPE
        # https://stackoverflow.com/a/52248549
        Gtk.drag_set_icon_pixbuf(context, self.get_drag_icon_pixbuf(top_model, paths, name_column, type_column), 0, 0)
        return True

    def on_view_drag_end(self, view, context):
        self._select_enabled = True
        view.get_selection().unselect_all()

    def get_drag_icon_pixbuf(self, model, paths, text_column, type_column):
        """ Creates and returns Pixbuf for a dragging icon. """
        import cairo

        window = Gtk.OffscreenWindow()
        window.get_style_context().add_class(Gtk.STYLE_CLASS_DND)
        frame = Gtk.Frame()
        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        padding = 10

        for index, row in enumerate([model[p] for p in paths]):
            if index == 25:
                list_box.add(Gtk.Arrow(Gtk.ArrowType.DOWN))
                break

            h_box = Gtk.HBox()
            h_box.set_spacing(10)
            h_box.get_style_context().add_class(Gtk.STYLE_CLASS_LIST_ROW)
            label = Gtk.Label(row[text_column])
            label.set_alignment(0, 0)
            label.set_padding(padding, 2)
            h_box.add(label)
            label = Gtk.Label(row[type_column])
            label.set_halign(Gtk.Align.END)
            label.set_padding(padding, 2)
            h_box.add(label)
            list_box.add(h_box)

        if len(paths) > 1:
            list_box.add(Gtk.Separator())
            h_box = Gtk.HBox()
            h_box.set_spacing(2)
            img = Gtk.Image.new_from_icon_name("document-properties", 0)
            h_box.add(img)
            h_box.add(Gtk.Label(len(paths)))
            h_box.set_halign(Gtk.Align.START)
            h_box.set_margin_left(10)
            h_box.set_margin_bottom(5)
            h_box.set_margin_top(2)
            list_box.add(h_box)

        frame.add(list_box)
        frame.show_all()
        window.add(frame)
        window.show()
        alloc = frame.get_allocation()
        w, h = alloc.width, alloc.height
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        frame.draw(cairo.Context(surf))
        pix = Gdk.pixbuf_get_from_surface(surf, 0, 0, w, h)
        window.destroy()

        return pix

    def on_view_drag_data_get(self, view, drag_context, data, info, time):
        selection = self.get_selection(view)
        if selection:
            data.set_text(selection, -1)

    def on_services_view_drag_drop(self, view, drag_context, x, y, time):
        view.stop_emission_by_name("drag_drop")
        # https://stackoverflow.com/q/7661016  [Some data was dropped, get the data!]
        targets = drag_context.list_targets()
        view.drag_get_data(drag_context, targets[-1] if targets else Gdk.atom_intern("text/plain", False), time)

    def on_services_view_drag_data_received(self, view, drag_context, x, y, data, info, time):
        #  Needs for the GtkTreeView when using models [filter, sort]
        #  that don't support the GtkTreeDragDest interface.
        view.stop_emission_by_name("drag_data_received")
        self.on_view_drag_data_received(view, drag_context, x, y, data, info, time)

    def on_view_drag_data_received(self, view, drag_context, x, y, data, info, time):
        txt = data.get_text()
        uris = data.get_uris()
        name, model = get_model_data(view)

        if txt:
            if txt.startswith("file://") and name == self.SERVICE_MODEL:
                self.on_import_data(urlparse(unquote(txt)).path.strip())
            elif name == self.FAV_MODEL:
                self.receive_selection(view=view, drop_info=view.get_dest_row_at_pos(x, y), data=txt)

        if uris:
            if len(uris) == 2:
                self.picons_buffer = self.on_assign_picon_file(view, urlparse(unquote(uris[0])).path,
                                                               urlparse(unquote(uris[1])).path + os.sep)
            elif IS_DARWIN and len(uris) == 1:
                src, sep, dest = uris[0].partition(self.DRAG_SEP)
                src_path = urlparse(unquote(src)).path
                if dest:
                    dest_path = urlparse(unquote(dest)).path + os.sep
                    self.picons_buffer = self.on_assign_picon_file(view, src_path, dest_path)

            drag_context.finish(True, False, time)

    def on_bq_view_drag_data_received(self, view, drag_context, x, y, data, info, time):
        model_name, model = get_model_data(view)
        drop_info = view.get_dest_row_at_pos(x, y)
        data = data.get_text()
        if not data:
            return

        if data.startswith("file://"):
            self.on_import_bouquet(None, file_path=urlparse(unquote(data)).path.strip())
            return

        itr_str, sep, source = data.partition(self.DRAG_SEP)
        if source != self.BQ_MODEL:
            return

        if drop_info:
            path, position = drop_info
            itrs = [model.get_iter_from_string(itr) for itr in itr_str.split(",")]
            top_iter = model.get_iter(path)
            parent_itr = model.iter_parent(top_iter)  # parent
            to_del = []
            if parent_itr:
                p_path = model.get_path(parent_itr)[0]
                for itr in itrs:
                    p_itr = model.iter_parent(itr)
                    if not p_itr:
                        break

                    if all((IS_LINUX, p_itr, model.get_path(p_itr)[0] == p_path)):
                        model.move_after(itr, top_iter)
                        top_iter = itr
                    else:
                        model.insert(parent_itr, model.get_path(top_iter)[1], model[itr][:])
                        to_del.append(itr)
            elif not model.iter_has_child(top_iter) or not IS_LINUX:
                for itr in itrs:
                    model.append(top_iter, model[itr][:])
                    to_del.append(itr)
                view.expand_all()

            list(map(model.remove, to_del))
            self.update_bouquets_type()
            drag_context.finish(True, False, time)

    def get_selection(self, view):
        """ Creates a string from the iterators of the selected rows """
        model, paths = view.get_selection().get_selected_rows()
        model = get_base_model(model)

        if len(paths) > 0:
            itrs = [model.get_iter(path) for path in paths]
            return f"{','.join([model.get_string_from_iter(itr) for itr in itrs])}::::{model.get_name()}"

    def receive_selection(self, *, view, drop_info, data):
        """  Update fav view  after data received  """
        try:
            itr_str, sep, source = data.partition(self.DRAG_SEP)
            if source == self.BQ_MODEL:
                return

            bq_selected = self.check_bouquet_selection()
            if not bq_selected:
                return

            model = get_base_model(view.get_model())
            dst_index = -1

            if drop_info:
                path, position = drop_info
                dst_index = path.get_indices()[0]

            fav_bouquet = self._bouquets[bq_selected]
            itrs = itr_str.split(",")

            if source == self.SERVICE_MODEL:
                ext_model = self._services_view.get_model()
                self.receive_data_to_fav(dst_index, fav_bouquet, itrs, model, ext_model, Column.SRV_FAV_ID)
            elif source == self.FAV_MODEL:
                in_itrs = [model.get_iter_from_string(itr) for itr in itrs]
                in_rows = [model[in_itr][:] for in_itr in in_itrs]
                for row in in_rows:
                    model.insert(dst_index, row)
                    fav_bouquet.insert(dst_index, row[Column.FAV_ID])
                    dst_index += 1
                for in_itr in in_itrs:
                    del fav_bouquet[int(model.get_path(in_itr)[0])]
                    model.remove(in_itr)
            elif source == self.IPTV_MODEL:
                ext_model = self._iptv_services_view.get_model()
                self.receive_data_to_fav(dst_index, fav_bouquet, itrs, model, ext_model, Column.IPTV_FAV_ID)
            self.update_fav_num_column(model)
        except ValueError as e:
            self.show_error_message(str(e))

    def receive_data_to_fav(self, dst_index, fav_bouquet, itrs, model, ext_model, fav_column):
        """ Adds data obtained via drag and drop to the favorites model. """
        ext_itrs = [ext_model.get_iter_from_string(itr) for itr in itrs]
        ext_rows = [ext_model[ext_itr][:] for ext_itr in ext_itrs]
        for ext_row in ext_rows:
            dst_index += 1
            fav_id = ext_row[fav_column]
            ch = self._services[fav_id]
            model.insert(dst_index, (0, ch.coded, ch.service, ch.locked, ch.hide, ch.service_type, ch.pos,
                                     ch.fav_id, self._picons.get(ch.picon_id, None), None, None))
            fav_bouquet.insert(dst_index, ch.fav_id)

    def on_view_press(self, view, event):
        """ Handles a mouse click (press) to view. """
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_PRIMARY:
            target = view.get_path_at_pos(event.x, event.y)
            # Idea taken from here: https://kevinmehall.net/2010/pygtk_multi_select_drag_drop
            mask = not (event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK))
            if target and mask and view.get_selection().path_is_selected(target[0]):
                self._select_enabled = False

            name, model = get_model_data(view)
            self.delete_views_selection(name)
        elif event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS and event.button == Gdk.BUTTON_PRIMARY:
            if self._settings.main_list_playback and self._fav_click_mode is not PlaybackMode.DISABLED:
                if view is self._services_view:
                    self.emit("srv-clicked", self._fav_click_mode)
                elif view is self._iptv_services_view:
                    self.emit("iptv-clicked", self._fav_click_mode)

    def on_view_release(self, view, event):
        """ Handles a mouse click (release) to view. """
        # Enable selection.
        self._select_enabled = True

    def delete_views_selection(self, name):
        if name == self.SERVICE_MODEL:
            self.delete_selection(self._fav_view)
        elif name == self.FAV_MODEL:
            self.delete_selection(self._services_view, self._iptv_services_view)
        elif name == self.BQ_MODEL:
            self.delete_selection(self._services_view, self._fav_view, self._iptv_services_view)
        elif name == self.IPTV_MODEL:
            self.delete_selection(self._fav_view)

    def on_view_popup_menu(self, menu, event):
        """ Shows popup menu for any view """
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
            name = Gtk.Buildable.get_name(menu)
            if name == "services_popup_menu":
                self.delete_selection(self._fav_view, self._bouquets_view)
                self.on_view_focus(self._services_view)
            elif name == "fav_popup_menu":
                self.delete_selection(self._services_view, self._bouquets_view)
                self.on_view_focus(self._fav_view)
            elif name == "bouquets_popup_menu":
                self.delete_selection(self._services_view, self._fav_view)
                self.on_view_focus(self._bouquets_view)

            menu.popup(None, None, None, None, event.button, event.time)
            return True

    # ***************** Send/Receive data ********************* #

    def on_receive(self, action=None, value=None):
        if self._page not in self._no_download_pages:
            self.change_action_state("on_logs_show", GLib.Variant.new_boolean(True))
            self.emit("data-receive", self._page)
        else:
            self.show_error_message("Not allowed in this context!")

    def on_send(self, action=None, value=None):
        if self._page not in self._no_download_pages:
            self.change_action_state("on_logs_show", GLib.Variant.new_boolean(True))
            self.emit("data-send", self._page)
        else:
            self.show_error_message("Not allowed in this context!")

    def on_download(self, app, page):
        if page is Page.INFO:
            self.on_download_data()
        elif page is Page.SERVICES:
            self.on_download_data(DownloadType.SERVICES)

    def on_upload(self, app, page):
        if page is Page.INFO:
            self.on_upload_data()
        elif page is Page.SERVICES:
            self.on_upload_data(DownloadType.SERVICES)

    def on_bg_task_add(self, app, task):
        if len(self._task_box) <= self.BG_TASK_LIMIT:
            self._task_box.add(task)
        else:
            self.show_error_message("Task limit (> 5) exceeded!")

    def on_task_done(self, app, task):
        self._task_box.remove(task)
        task.destroy()

    def on_task_cancel(self, app, task):
        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.OK:
            task.cancel()
            self.on_task_done(app, task)

    @run_task
    def on_download_data(self, download_type=DownloadType.ALL):
        backup, backup_src, data_path = self._settings.backup_before_downloading, None, None
        try:
            if backup and download_type is not DownloadType.SATELLITES:
                data_path = self._settings.profile_data_path
                backup_path = self._settings.profile_backup_path or self._settings.default_backup_path
                backup_src = backup_data(data_path, backup_path, download_type is DownloadType.ALL)

            download_data(settings=self._settings, download_type=download_type)
        except Exception as e:
            msg = "Downloading data error: {}"
            log(msg.format(e), debug=self._settings.debug_mode, fmt_message=msg)
            self.show_error_message(str(e))
            if all((backup, data_path)):
                restore_data(backup_src, data_path)
        else:
            if download_type is DownloadType.SATELLITES:
                self._satellite_tool.load_satellites_list()
            else:
                GLib.idle_add(self.open_data)

    def on_upload_data(self, download_type=DownloadType.ALL):
        if not self.is_data_saved():
            gen = self.save_data(lambda: self.upload_data(download_type))
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
        else:
            self.upload_data(download_type)

    @run_task
    def upload_data(self, download_type):
        opts = self._settings
        multiple = len(self._settings.hosts) > 1
        for host in self._settings.hosts:
            if multiple:
                log(f"##### Uploading data on [{host}] #####")
            try:
                upload_data(settings=opts, download_type=download_type, ext_host=host)
            except Exception as e:
                msg = "Uploading data error: {}"
                log(msg.format(e), debug=self._settings.debug_mode, fmt_message=msg)
                if host == self._settings.host:
                    self.show_error_message(str(e))
        log(f"##### Done! #####")

    def on_data_open(self, app, page):
        """ Opening data via "File/Open". """
        if page is Page.SERVICES or page is Page.INFO:
            response = show_dialog(DialogType.CHOOSER, self._main_window, settings=self._settings, title="Open folder")
            if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
                return
            self.open_data(response)

    def on_data_extract(self, app, page):
        """ Opening the data archive via "File/Extract...". """
        if page is Page.SERVICES:
            file_filter = None
            if IS_DARWIN:
                file_filter = Gtk.FileFilter()
                file_filter.set_name("*.zip, *.gz")
                file_filter.add_mime_type("application/zip")
                file_filter.add_mime_type("application/gzip")

            response = get_chooser_dialog(self._main_window, self._settings,
                                          "*.zip, *.gz files", ("*.zip", "*.gz"), "Open archive", file_filter)
            if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
                return
            self.open_data(response)

    def open_data(self, data_path=None, callback=None):
        """ Opening data and fill views. """
        if self.is_data_loading():
            self.show_error_message("Data loading in progress!")
            return

        if data_path and os.path.isfile(data_path):
            self.open_compressed_data(data_path)
        else:
            gen = self.update_data(data_path, callback)
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def open_compressed_data(self, data_path):
        """ Opening archived data.  """
        arch_path = self.get_archive_path(data_path)
        if arch_path:
            gen = self.update_data(f"{arch_path.name}{os.sep}", callback=arch_path.cleanup)
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def get_archive_path(self, data_path):
        """ Returns the temp dir path for the extracted data, or None if the archive format is not supported. """
        import zipfile
        import tarfile
        import tempfile

        tmp_path = tempfile.TemporaryDirectory()
        tmp_path_name = tmp_path.name

        if zipfile.is_zipfile(data_path):
            with zipfile.ZipFile(data_path) as zip_file:
                for zip_info in zip_file.infolist():
                    if not zip_info.filename.endswith(os.sep):
                        f_name = os.path.basename(zip_info.filename)
                        if f_name:
                            zip_info.filename = f_name
                            zip_file.extract(zip_info, path=tmp_path_name)
        elif tarfile.is_tarfile(data_path):
            with tarfile.open(data_path) as tar:
                for mb in tar.getmembers():
                    if mb.isfile():
                        mb.name = os.path.basename(mb.name)
                        tar.extract(mb, path=tmp_path_name)
        else:
            tmp_path.cleanup()
            log(f"Error getting the path for the archive. Unsupported file format: {data_path}")
            self.show_error_message("Unsupported format!")
            return

        return tmp_path

    def update_data(self, data_path, callback=None):
        self._profile_combo_box.set_sensitive(False)
        self._alt_revealer.set_visible(False)
        self._filter_services_button.set_active(False)
        self._wait_dialog.show()

        yield from self.clear_current_data()
        # Reset of sorting
        self._services_view.get_model().reset_default_sort_func()
        self.reset_view_sort_indication(self._services_view)
        self.reset_view_sort_indication(self._fav_view)

        try:
            current_profile = self._profile_combo_box.get_active_text()
            if not current_profile:
                self.show_error_message("No profile selected!")
                return

            if current_profile != self._settings.current_profile:
                self.init_profiles()

            data_path = self._settings.profile_data_path if data_path is None else data_path
            local_path = self._settings.profile_data_path
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            if data_path != local_path:
                from shutil import copyfile

                for f in STC_XML_FILE:
                    xml_src = data_path + f
                    if os.path.isfile(xml_src):
                        copyfile(xml_src, local_path + f)

            prf = self._s_type
            black_list = get_blacklist(data_path)
            bouquets = get_bouquets(data_path, prf)
            yield True
            services = get_services(data_path, prf, self.get_format_version() if prf is SettingsType.ENIGMA_2 else 0)
            yield True
        except FileNotFoundError as e:
            msg = translate("Please, download files from receiver or setup your path for read data!")
            self.show_error_message(getattr(e, "message", str(e)) + "\n\n" + msg)
            return
        except SyntaxError as e:
            self.show_error_message(str(e))
            return
        except Exception as e:
            msg = "Reading data error: {}"
            log(msg.format(e), debug=self._settings.debug_mode, fmt_message=msg)
            self.show_error_message("{}\n{}".format(translate("Reading data error!"), e))
            return
        else:
            self.append_blacklist(black_list)
            yield from self.append_data(bouquets, services)
            if callback:
                callback()
            yield True
            self._data_hash = self.get_data_hash()
            yield True
            if self._filter_box.get_visible():
                self.on_filter_changed()
            yield True
        finally:
            self._profile_combo_box.set_sensitive(True)
            self._wait_dialog.hide()
            self.emit("data-load-done", self._settings.current_profile)

    def append_data(self, bouquets, services):
        if self._app_info_box.get_visible():
            yield from self.show_app_info(False)
        self.append_bouquets(bouquets)
        yield from self.append_services(services)
        self.update_sat_positions()
        yield True

    def show_app_info(self, visible):
        self._app_info_box.set_visible(visible)
        if visible:
            self._app_info_box.grab_focus()
        else:
            if self._services_view.get_realized():
                self._services_view.grab_focus()
        yield True

    def append_blacklist(self, black_list):
        if black_list:
            self._blacklist.update(black_list)

    def append_bouquets(self, bqs):
        if len(self._bouquets_model):
            self.add_to_bouquets(bqs)
        else:
            allow_markers = self.bq_has_markers(bqs)

            for bouquet in bqs:
                parent = self._bouquets_model.append(None, [bouquet.name, None, None, bouquet.type])
                for bq in bouquet.bouquets:
                    # Markers!
                    if bq.type == BqType.MARKER.value and allow_markers:
                        self.append_bouquet(bq, parent)
                    else:
                        self.append_bouquet(bq, parent)

    def bq_has_markers(self, bqs):
        """" Checks if there are markers in the list of bouquets. """
        msg = "Detected markers in the bouquet list!\nThis feature is not fully supported.\n\n\t Add them to the list?"
        for bq in bqs:
            for b in bq.bouquets:
                if b.type == BqType.MARKER.value:
                    return show_dialog(DialogType.QUESTION, self._main_window, msg) == Gtk.ResponseType.OK
        return True

    def add_to_bouquets(self, bqs):
        for bouquets in bqs:
            for row in self._bouquets_model:
                if row[Column.BQ_TYPE] == bouquets.type:
                    for bq in bouquets.bouquets:
                        self.append_bouquet(bq, row.iter)

    def append_bouquet(self, bq, parent):
        name, bq_type, locked, hidden = bq.name, bq.type, bq.locked, HIDE_ICON if bq.hidden else None
        # Parental control state.
        if self._s_type is SettingsType.ENIGMA_2:
            locked = LOCKED_ICON if bq.locked in self._blacklist else None
        else:
            locked = LOCKED_ICON if bq.locked else None

        bouquet = self._bouquets_model.append(parent, [name, locked, hidden, bq_type])
        bq_id = f"{name}:{bq_type}"
        services = []
        extra_services = {}  # for services with different names in bouquet and main list
        agr = [None] * 7
        for srv in bq.services:
            fav_id = srv.data
            # IPTV and MARKER services
            s_type = srv.type
            if s_type in (BqServiceType.MARKER, BqServiceType.IPTV, BqServiceType.SPACE):
                icon = None
                picon_id = None
                data_id = srv.num
                locked = None

                if s_type is BqServiceType.IPTV:
                    icon = IPTV_ICON
                    fav_id_data = fav_id.lstrip().split(":")
                    if len(fav_id_data) > 10:
                        data_id = ":".join(fav_id_data[:11])
                        picon_id = "{}_{}_{}_{}_{}_{}_{}_{}_{}_{}.png".format(*fav_id_data[:10])
                        locked = LOCKED_ICON if data_id in self._blacklist else None
                srv = Service(None, None, icon, srv.name, locked, None, None, s_type.name,
                              self._picons.get(picon_id, None), picon_id, *agr, data_id, fav_id, None)
                self._services[fav_id] = srv
            elif s_type is BqServiceType.ALT:
                self._alt_file.add(f"{srv.data}:{bq_type}")
                srv = Service(None, None, None, srv.name, locked, None, None, s_type.name,
                              None, None, *agr, srv.data, fav_id, srv.num)
                self._services[fav_id] = srv
            elif s_type is BqServiceType.BOUQUET:
                # Sub bouquets!
                self.append_bouquet(srv.data, bouquet)
            elif srv.name:
                extra_services[fav_id] = srv.name
            services.append(fav_id)

        self._bouquets[bq_id] = services
        self._bq_file[bq_id] = bq.file
        if extra_services:
            self._extra_bouquets[bq_id] = extra_services

    @run_idle
    def open_last_bouquet(self, app, profile):
        """ Loads the last opened bouquet. """
        self.disconnect_by_func(self.open_last_bouquet)  # -> We run it only once.
        config = self._settings.get("last_config") or {}
        last_bouquet = config.get("last_bouquet", None)

        for r in self._bouquets_model:
            for i in r.iterchildren():
                if i[Column.BQ_NAME] == last_bouquet:
                    self._bouquets_view.expand_row(self._bouquets_model.get_path(r.iter), Column.BQ_NAME)
                    self._bouquets_view.set_cursor(i.path)
                    self._bouquets_view.row_activated(i.path, self._bouquets_view.get_column(Column.BQ_NAME))
                    break

    def append_services(self, services):
        to_add = []
        for srv in services:
            if srv.fav_id not in self._services:
                to_add.append(srv)
            #  Adding channels to dict with fav_id as keys.
            self._services[srv.fav_id] = srv
        self.update_services_counts(len(self._services.values()))
        self._wait_dialog.hide()
        self._services_load_spinner.start()
        factor = self.DEL_FACTOR / 4

        for index, srv in enumerate(to_add):
            background = self.get_new_background(srv.flags_cas)
            s = srv + (None, background)
            self._services_model.append(s)
            if index % factor == 0:
                yield True

        self._services_load_spinner.stop()
        yield True

    def append_iptv_data(self, services=None):
        self._iptv_services_load_spinner.start()
        services = services or self._services.values()

        for index, s in enumerate(filter(lambda x: x.service_type == BqServiceType.IPTV.name, services), start=1):
            ref, url = get_iptv_data(s.fav_id)
            self._iptv_model.append((s.service, None, None, ref, url, s.fav_id, s.picon_id, None))
            if index % self.DEL_FACTOR == 0:
                self._iptv_count_label.set_text(str(index))
                yield True

        self._iptv_count_label.set_text(str(len(self._iptv_model)))
        self._iptv_services_load_spinner.stop()
        yield True

    def get_new_background(self, flags):
        if self._use_colors and flags:
            f_flags = list(filter(lambda x: x.startswith("f:"), flags.split(",")))
            if f_flags and Flag.is_new(Flag.parse(f_flags[0])):
                return self._NEW_COLOR

    def clear_current_data(self):
        """ Clearing current data from lists """
        self._bouquets_model.clear()
        yield True
        self._fav_model.clear()
        yield True

        if len(self._services_model) < self.DEL_FACTOR * 30:
            for index, itr in enumerate([row.iter for row in self._services_model]):
                self._services_model.remove(itr)
                if index % self.DEL_FACTOR == 0:
                    yield True
        else:
            # With a large amount of data,
            # it is more optimal to recreate the models.
            self.init_new_services_models()
            yield True

        self._blacklist.clear()
        self._services.clear()
        self._rows_buffer.clear()
        self._picons.clear()
        self._alt_file.clear()
        self._alt_counter = 1
        self._bouquets.clear()
        self._bq_file.clear()
        self._extra_bouquets.clear()
        self._current_bq_name = None
        self._bq_name_label.set_text("")
        self.init_sat_positions()
        self.update_services_counts()
        self._wait_dialog.set_text(None)
        yield True

    def on_data_save(self, app, page):
        if page is Page.SERVICES:
            self.on_services_save()

    def on_data_save_as(self, app, page):
        if page is Page.SERVICES:
            self.on_services_save_as()

    def on_services_save(self):
        if len(self._bouquets_model) == 0:
            self.show_error_message("No data to save!")
            return

        if show_dialog(DialogType.QUESTION, self._main_window) != Gtk.ResponseType.OK:
            return

        gen = self.save_data()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_services_save_as(self):
        if len(self._bouquets_model) == 0:
            self.show_error_message("No data to save!")
            return

        response = show_dialog(DialogType.CHOOSER, self._main_window, settings=self._settings,
                               buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK),
                               create_dir=True)
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        if os.listdir(response):
            msg = "{}\n\n\t\t{}".format(translate("The selected folder already contains files!"),
                                        translate("Are you sure?"))
            if show_dialog(DialogType.QUESTION, self._main_window, msg) != Gtk.ResponseType.OK:
                return

        gen = self.save_data(lambda: show_dialog(DialogType.INFO, self._main_window, "Done!"), response)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def save_data(self, callback=None, ext_path=None):
        self._save_tool_button.set_sensitive(False)
        profile = self._s_type
        path = ext_path or self._settings.profile_data_path
        backup_path = self._settings.profile_backup_path
        # Backup data or clearing data path
        backup_data(path, backup_path) if not ext_path and self._settings.backup_before_save else clear_data_path(path)
        yield True

        bouquets = []

        def parse_bouquets(model, b_path, itr):
            bqs = None
            if model.iter_has_child(itr):
                bqs = [self.get_bouquet(model.iter_nth_child(itr, n), model) for n in range(model.iter_n_children(itr))]
            if len(b_path) == 1:
                bouquets.append(Bouquets(*model.get(itr, Column.BQ_NAME, Column.BQ_TYPE), bqs if bqs else []))

        # Getting bouquets
        self._bouquets_view.get_model().foreach(parse_bouquets)
        write_bouquets(path, bouquets, profile, self._settings.force_bq_names, self._blacklist)
        yield True
        # Getting services
        services_model = get_base_model(self._services_view.get_model())
        services = [Service(*row[: Column.SRV_TOOLTIP]) for row in services_model]
        write_services(path, services, profile, self.get_format_version() if profile is SettingsType.ENIGMA_2 else 0)
        yield True

        if profile is SettingsType.ENIGMA_2:
            # Blacklist.
            write_blacklist(path, self._blacklist)

        self._save_tool_button.set_sensitive(True)
        yield True
        self._data_hash = self.get_data_hash()
        yield True
        if callback:
            callback()

    def get_bouquet(self, itr, model):
        """ Constructs and returns Bouquet class instance. """
        bq_name, locked, hidden, bq_type = model[itr][:]
        bq_id = f"{bq_name}:{bq_type}"
        bq_file = self._bq_file.get(bq_id, None)
        favs = self._bouquets.get(bq_id, [])
        ex_s = self._extra_bouquets.get(bq_id, None)
        bq_s = list(filter(None, [self._services.get(f_id, None) for f_id in favs]))
        # Sub bouquets.
        if model.iter_has_child(itr):
            s_bs = [self.get_bouquet(model.iter_nth_child(itr, n), model) for n in range(model.iter_n_children(itr))]
            return Bouquet(bq_name, BqType.BOUQUET.value, s_bs, locked, hidden, bq_file)

        if self._s_type is SettingsType.ENIGMA_2:
            bq_s = self.get_enigma_bq_services(bq_s, ex_s)

        return Bouquet(bq_name, bq_type, bq_s, locked, hidden, bq_file)

    def get_enigma_bq_services(self, services, ext_services):
        """ Preparing a list of services for the Enigma2 bouquet. """
        s_list = []
        for srv in services:
            if srv.service_type == BqServiceType.ALT.name:
                # Alternatives to service in a bouquet.
                alts = list(map(lambda s: s._replace(service=None),
                                filter(None, [self._services.get(s.data, None) for s in srv.transponder or []])))
                s_list.append(srv._replace(transponder=alts))
            else:
                # Extra names for service in bouquet.
                s_list.append(srv._replace(service=ext_services.get(srv.fav_id, None) if ext_services else None))
        return s_list

    def on_new_configuration(self, action, value=None):
        """ Creates new empty configuration """
        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return

        gen = self.create_new_configuration(self._s_type)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def create_new_configuration(self, profile):
        if self._app_info_box.get_visible():
            yield from self.show_app_info(False)

        c_gen = self.clear_current_data()
        yield from c_gen

        if profile is SettingsType.ENIGMA_2:
            parent = self._bouquets_model.append(None, ["Bouquets (TV)", None, None, BqType.TV.value])
            f_name = f"userbouquet.favourites.{BqType.TV.value}"
            self.append_bouquet(Bouquet("Favourites (TV)", BqType.TV.value, [], None, None, f_name), parent)
            parent = self._bouquets_model.append(None, ["Bouquets (Radio)", None, None, BqType.RADIO.value])
            f_name = f"userbouquet.favourites.{BqType.RADIO.value}"
            self.append_bouquet(Bouquet("Favourites (Radio)", BqType.RADIO.value, [], None, None, f_name), parent)
        elif profile is SettingsType.NEUTRINO_MP:
            self._bouquets_model.append(None, ["Providers", None, None, BqType.BOUQUET.value])
            self._bouquets_model.append(None, ["FAV", None, None, BqType.TV.value])
            self._bouquets_model.append(None, ["WEBTV", None, None, BqType.WEBTV.value])

        self._data_hash = self.get_data_hash()
        yield True

    def on_fav_selection(self, model, path, column):
        row = model[path][:]
        fav_id = row[Column.FAV_ID]
        srv = self._services.get(fav_id, None)

        if row[Column.FAV_TYPE] == BqServiceType.ALT.name:
            self._alt_model.clear()
            if srv:
                for i, s in enumerate(srv[-1] or [], start=1):
                    s = self._services.get(s.data, None)
                    if s:
                        pic = self._picons.get(s.picon_id, None)
                        itr = model.get_string_from_iter(model.get_iter(path))
                        self._alt_model.append((i, pic, s.service, s.service_type, s.pos, s.fav_id, fav_id, itr))
                self._alt_revealer.set_visible(True)
        else:
            self._alt_revealer.set_visible(False)
            self.on_info_bar_close()

            if self._page is Page.EPG and srv.service_type not in self.MARKER_TYPES:
                self.emit("fav-changed", srv)

    def on_services_selection(self, model, path, column):
        self.update_service_bar(model, path)

    def update_service_bar(self, model, path):
        def_val = "Unknown"
        cas = model.get_value(model.get_iter(path), Column.SRV_CAS_FLAGS)
        if not cas:
            return
        cvs = list(filter(lambda val: val.startswith("C:") and len(val) > 3, cas.split(",")))
        self._cas_label.set_text(", ".join(map(str, sorted(set(CAS.get(v[:4].upper(), def_val) for v in cvs)))))

    def on_bouquets_selection(self, model, path, column):
        self.reset_view_sort_indication(self._fav_view)
        self._alt_revealer.set_visible(False)
        self._current_bq_name = model[path][0] if len(path) > 1 else None
        self._bq_name_label.set_text(self._current_bq_name if self._current_bq_name else "")
        itr = model.get_iter(path)

        if self._current_bq_name:
            ch_row = model[itr][:]
            self._bq_selected = f"{ch_row[Column.BQ_NAME]}:{ch_row[Column.BQ_TYPE]}"
        else:
            self._bq_selected = ""

        if self._bouquets_view.row_expanded(path):
            self._bouquets_view.collapse_row(path)
        else:
            self._bouquets_view.expand_row(path, column)

        if len(path) > 1:
            gen = self.update_bouquet_services(model, path)
            GLib.idle_add(lambda: next(gen, False))
            if not model.iter_has_child(itr):
                self.emit("bouquet-changed", self._bq_selected)

    def update_bouquet_services(self, model, path, bq_key=None):
        """ Updates list of bouquet services """
        tree_iter = None
        if path:
            tree_iter = model.get_iter(path)

        key = bq_key if bq_key else "{}:{}".format(*model.get(tree_iter, Column.BQ_NAME, Column.BQ_TYPE))
        services = self._bouquets.get(key, [])
        ex_services = self._extra_bouquets.get(key, None)

        if len(services) > self.FAV_FACTOR * 20:
            self._bouquets_view.set_sensitive(False)
            yield True

        self._fav_view.set_model(None)
        self._fav_model.clear()

        num = 0
        for srv_id in services:
            srv = self._services.get(srv_id, None)
            ex_srv_name = None
            if ex_services:
                ex_srv_name = ex_services.get(srv_id)
            if srv:
                background = self._EXTRA_COLOR if self._use_colors and ex_srv_name else None

                srv_type = srv.service_type
                is_marker = srv_type in self.MARKER_TYPES
                if not is_marker:
                    num += 1

                self._fav_model.append((0 if is_marker else num, srv.coded, ex_srv_name if ex_srv_name else srv.service,
                                        srv.locked, srv.hide, srv_type, srv.pos, srv.fav_id,
                                        None, None, background))

        yield True
        self._fav_view.set_model(self._fav_model)
        self.on_model_changed(self._fav_model)
        self._bouquets_view.set_sensitive(True)
        self._bouquets_view.grab_focus()
        yield True

    def check_bouquet_selection(self):
        """ Checks and returns bouquet if selected """
        if not self._bq_selected:
            self.show_error_message("Error. No bouquet is selected!")
            return

        if self._s_type is SettingsType.NEUTRINO_MP and self._bq_selected.endswith(BqType.WEBTV.value):
            self.show_error_message("Operation not allowed in this context!")
            return

        return self._bq_selected

    @run_idle
    def update_bouquets_type(self):
        """ Update bouquets type in the model and dict """
        for row in get_base_model(self._bouquets_view.get_model()):
            bqs_rows = row.iterchildren()
            if bqs_rows:
                bq_type = row[-1]
                for b_row in bqs_rows:
                    bq_id = f"{b_row[Column.BQ_NAME]}:{b_row[Column.BQ_TYPE]}"
                    bq = self._bouquets.get(bq_id, None)
                    if bq:
                        b_row[Column.BQ_TYPE] = bq_type
                        self._bouquets[f"{b_row[Column.BQ_NAME]}:{b_row[Column.BQ_TYPE]}"] = bq

    def delete_selection(self, view, *args):
        """ Used for clear selection on given view(s). """
        for v in [view, *args]:
            v.get_selection().unselect_all()

    def on_settings(self, action, value=None):
        dialog = SettingsDialog(self._main_window, self._settings)
        dialog.show()
        if dialog.is_updated():
            gen = self.update_settings()
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def update_settings(self):
        s_type = self._settings.setting_type

        if s_type != self._s_type:
            yield from self.show_app_info(True)
            self._s_type = s_type
            c_gen = self.clear_current_data()
            yield from c_gen

        self.init_appearance(True)
        self.init_profiles()
        yield True
        gen = self.init_http_api()
        yield from gen

    def on_profile_changed(self, entry):
        active = self._profile_combo_box.get_active_text()
        if not active:
            return

        changed = self._settings.current_profile != active

        if active in self._settings.profiles:
            self.set_profile(active)

        gen = self.init_http_api()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

        if self._ftp_client:
            self._ftp_client.init_ftp()

        if changed:
            self.open_data()
            if self._settings.display_epg:
                self.change_action_state("display_epg", GLib.Variant.new_boolean(self._settings.display_epg))
            self.emit("profile-changed", None)

    def set_profile(self, active):
        self._settings.current_profile = active
        self._s_type = self._settings.setting_type
        self.update_profile_label()
        is_enigma = self._s_type is SettingsType.ENIGMA_2
        self.set_property("is-enigma", is_enigma)
        self.update_elements_visibility(is_enigma)

    def update_profiles(self):
        self._profile_combo_box.remove_all()
        for p in self._settings.profiles:
            self._profile_combo_box.append(p, p)

    @run_idle
    def update_elements_visibility(self, is_enigma=False):
        self._stack_services_frame.set_visible(self._settings.get("show_bouquets", True))
        self._stack_satellite_box.set_visible(self._settings.get("show_satellites", True))
        self._stack_picon_box.set_visible(self._settings.get("show_picons", True))
        self._stack_ftp_box.set_visible(self._settings.get("show_ftp", True))
        self._stack_epg_box.set_visible(is_enigma and self._settings.get("show_epg", True))
        self._stack_timers_box.set_visible(is_enigma and self._settings.get("show_timers", True))
        self._stack_recordings_box.set_visible(is_enigma and self._settings.get("show_recordings", True))
        self._stack_control_box.set_visible(is_enigma and self._settings.get("show_control", True))
        self._iptv_button.set_active(False)

    def on_tree_view_key_press(self, view, event):
        """  Handling  keystrokes on press """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK
        if key is KeyboardKey.F:
            if ctrl:
                self.activate_search_state(view)
            return True

        ctrl = event.state & MOD_MASK
        model_name, model = get_model_data(view)

        if ctrl and key is KeyboardKey.INSERT:
            # Move items from app to fav list
            if model_name in self._services_models:
                self.on_to_fav_copy(view)
            elif model_name == self.BQ_MODEL:
                self.on_new_bouquet(view)
        elif ctrl and key is KeyboardKey.BACK_SPACE and model_name in self._services_models:
            self.on_to_fav_end_copy(view)
        elif ctrl and key in MOVE_KEYS:
            self.move_items(key)
        elif ctrl and key is KeyboardKey.C:
            if model_name == self.SERVICE_MODEL:
                self.on_copy(view, ViewTarget.FAV)
            elif model_name == self.FAV_MODEL:
                self.on_copy(view, ViewTarget.SERVICES)
            elif model_name == self.IPTV_MODEL:
                self.on_copy(view, ViewTarget.IPTV)
            else:
                self.on_copy(view, ViewTarget.BOUQUET)
        elif ctrl and key is KeyboardKey.X:
            if model_name == self.FAV_MODEL:
                self.on_cut(view, ViewTarget.FAV)
            elif model_name == self.BQ_MODEL:
                self.on_cut(view, ViewTarget.BOUQUET)
        elif ctrl and key is KeyboardKey.V:
            if model_name == self.FAV_MODEL:
                self.on_paste(view, ViewTarget.FAV)
            elif model_name == self.BQ_MODEL:
                self.on_paste(view, ViewTarget.BOUQUET)
        elif key is KeyboardKey.DELETE:
            self.on_delete(view)
        elif ctrl and key is KeyboardKey.R or key is KeyboardKey.F2:
            if event.state & Gdk.ModifierType.MOD1_MASK:  # ALT
                self.on_rename_for_bouquet()
            else:
                self.on_rename(view)

    def on_tree_view_key_release(self, view, event):
        """  Handling  keystrokes on release """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK
        model_name, model = get_model_data(view)

        if key is KeyboardKey.LEFT or key is KeyboardKey.RIGHT:
            view.do_unselect_all(view)
        elif ctrl and model_name == self.FAV_MODEL:
            if key is KeyboardKey.P:
                self.emit("fav-clicked", PlaybackMode.STREAM)
            if key is KeyboardKey.W:
                self.emit("fav-clicked", PlaybackMode.ZAP_PLAY)
            if key is KeyboardKey.Z:
                self.emit("fav-clicked", PlaybackMode.ZAP)
            elif key is KeyboardKey.CTRL_L or key is KeyboardKey.CTRL_R:
                self.update_fav_num_column(model)
                self.update_bouquet_list()

    def on_view_focus(self, view, focus_event=None):
        # Preventing focus lack for some cases.
        if not focus_event and not view.is_focus():
            view.grab_focus()
            return True

        model_name, model = get_model_data(view)
        not_empty = len(model) > 0 if model else False
        is_service = model_name == self.SERVICE_MODEL

        if model_name == self.BQ_MODEL:
            for elem in self._tool_elements:
                self._tool_elements[elem].set_sensitive(False)
            for elem in self._BOUQUET_ELEMENTS:
                self._tool_elements[elem].set_sensitive(not_empty)
                if elem == "bouquets_paste_popup_item":
                    self._tool_elements[elem].set_sensitive(not_empty and self._bouquets_buffer)
        else:
            for elem in self._FAV_ELEMENTS:
                if elem in ("paste_tool_button", "fav_paste_popup_item"):
                    self._tool_elements[elem].set_sensitive(not is_service and self._rows_buffer)
                elif elem in self._FAV_ENIGMA_ELEMENTS:
                    self._tool_elements[elem].set_sensitive(self._bq_selected and not is_service)
                else:
                    self._tool_elements[elem].set_sensitive(not_empty and not is_service)
            for elem in self._SERVICE_ELEMENTS:
                self._tool_elements[elem].set_sensitive(not_empty and is_service)
            for elem in self._BOUQUET_ELEMENTS:
                self._tool_elements[elem].set_sensitive(False)

        for elem in self._FAV_IPTV_ELEMENTS:
            is_iptv = self._bq_selected and not is_service
            if self._s_type is SettingsType.NEUTRINO_MP:
                is_iptv = is_iptv and BqType(self._bq_selected.split(":")[1]) is BqType.WEBTV
            self._tool_elements[elem].set_sensitive(is_iptv)
        for elem in self._COMMONS_ELEMENTS:
            self._tool_elements[elem].set_sensitive(not_empty)

        if self._s_type is not SettingsType.ENIGMA_2:
            for elem in self._FAV_ENIGMA_ELEMENTS:
                self._tool_elements[elem].set_sensitive(False)

    def on_hide(self, action=None, value=None):
        self.set_service_flags(Flag.HIDE)

    def on_locked(self, action=None, value=None):
        self.set_service_flags(Flag.LOCK)

    def set_service_flags(self, flag):
        if self._bouquets_view.is_focus() and self._bq_selected:
            model, paths = self._bouquets_view.get_selection().get_selected_rows()
            for p in paths:
                itr = model.get_iter(p)
                if not model.iter_has_child(itr):
                    value = model.get_value(itr, 1 if flag is Flag.LOCK else 2)
                    value = None if value else LOCKED_ICON if flag is Flag.LOCK else HIDE_ICON
                    model.set_value(itr, 1 if flag is Flag.LOCK else 2, value)

            if self._s_type is SettingsType.ENIGMA_2:
                msg = translate("After uploading the changes you may need to completely reboot the receiver!")
                self.show_info_message(f"{translate('EXPERIMENTAL!')} {msg}", Gtk.MessageType.WARNING)
        else:
            if self._s_type is SettingsType.ENIGMA_2:
                set_flags(flag, self._services_view, self._fav_view, self._services, self._blacklist)

    def on_model_changed(self, model, path=None, itr=None):
        model_name = model.get_name()

        if model_name == self.FAV_MODEL:
            self._fav_count_label.set_text(str(len(model)))
        elif model_name == self.SERVICE_MODEL:
            self.update_services_counts(len(model))
        elif model_name == self.IPTV_MODEL:
            self._iptv_count_label.set_text(str(len(model)))
        elif model_name == self.BQ_MODEL:
            self._bouquets_count_label.set_text(str(len(self._bouquets.keys())))

    @lru_cache(maxsize=1)
    def update_services_counts(self, size=0):
        """ Updates counters for services. May be temporary! """
        tv_count = 0
        radio_count = 0
        data_count = 0

        for ch in self._services.values():
            ch_type = ch.service_type
            if ch_type in self._TV_TYPES:
                tv_count += 1
            elif ch_type == "Radio":
                radio_count += 1
            elif ch_type == "Data":
                data_count += 1

        self._tv_count_label.set_text(str(tv_count))
        self._radio_count_label.set_text(str(radio_count))
        self._data_count_label.set_text(str(data_count))

    def on_insert_marker(self, view, m_type=BqServiceType.MARKER):
        """ Inserts marker into bouquet services list. """
        insert_marker(view, self._bouquets, self._bq_selected, self._services, self._main_window, m_type)
        self.update_fav_num_column(self._fav_model)

    def on_insert_space(self, view):
        self.on_insert_marker(view, BqServiceType.SPACE)

    def on_fav_press(self, menu, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            if self._fav_click_mode is PlaybackMode.DISABLED:
                return

            self.emit("fav-clicked", self._fav_click_mode)
        else:
            return self.on_view_popup_menu(menu, event)

    # ***************** IPTV *********************#

    def on_iptv(self, action, value=None):
        response = IptvDialog(self, self._fav_view, self._bouquets.get(self._bq_selected, None), Action.ADD).show()
        if response != Gtk.ResponseType.CANCEL:
            self.update_fav_num_column(self._fav_model)

    def on_iptv_service_added(self, app, services):
        if len(self._iptv_model) or self._iptv_button.get_active():
            gen = self.append_iptv_data(services)
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_iptv_service_edit(self, fav_id, view):
        service = self._services.get(fav_id, None)
        if service:
            IptvDialog(self, view, service=service, action=Action.EDIT).show()
        else:
            log(f"Error. Service with id '{fav_id}' not found!")

    @run_idle
    def on_iptv_service_edited(self, app, services: dict):
        for srvs in self._bouquets.values():
            for i, s in enumerate(srvs):
                if s in services:
                    old, new = services[s]
                    srvs[i] = new.fav_id

        for r in self._fav_model:
            fav_id = r[Column.FAV_ID]
            if fav_id in services:
                old, new = services[fav_id]
                name, new_fav_id = new.service, new.fav_id
                r[Column.FAV_SERVICE] = name
                r[Column.FAV_ID] = new_fav_id

        for r in self._iptv_model:
            fav_id = r[Column.IPTV_FAV_ID]
            if fav_id in services:
                old, new = services[fav_id]
                name, new_fav_id = new.service, new.fav_id
                ref, url = get_iptv_data(new_fav_id)
                r[Column.IPTV_SERVICE] = name
                r[Column.IPTV_PICON_ID] = new.picon_id
                r[Column.IPTV_REF] = ref
                r[Column.IPTV_URL] = url
                r[Column.IPTV_FAV_ID] = new_fav_id

    @run_idle
    def on_iptv_list_configuration(self, action, value=None):
        if self._s_type is SettingsType.NEUTRINO_MP:
            self.show_error_message("Neutrino at the moment not supported!")
            return

        iptv_rows = list(filter(lambda r: r[Column.FAV_TYPE] == BqServiceType.IPTV.value, self._fav_model))
        if not iptv_rows:
            self.show_error_message("This list does not contains IPTV streams!")
            return

        if not self._bq_selected:
            return

        bq = self._bouquets.get(self._bq_selected, [])
        IptvListConfigurationDialog(self._main_window, self._services, iptv_rows, bq,
                                    self._fav_model, self._s_type).show()

    @run_idle
    def on_remove_all_unavailable(self, action, value=None):
        iptv_rows = list(filter(lambda r: r[Column.FAV_TYPE] == BqServiceType.IPTV.value, self._fav_model))
        if not iptv_rows:
            self.show_error_message("This list does not contains IPTV streams!")
            return

        if not self._bq_selected:
            return

        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return

        fav_bqt = self._bouquets.get(self._bq_selected, None)
        response = SearchUnavailableDialog(self._main_window, self._fav_model, fav_bqt, iptv_rows, self._s_type).show()
        if response:
            gen = self.remove_favs(response, self._fav_model)
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_reference_assign(self, view):
        """ Assigns DVB reference to the selected IPTV services. """
        model, paths = view.get_selection().get_selected_rows()
        iptv_paths = [p for p in paths if model[p][Column.FAV_TYPE] == BqServiceType.IPTV.value]
        if not iptv_paths:
            self.show_error_message("No IPTV services selected!")
            return

        ref = self._clipboard.wait_for_text()
        if ref and re.match(r"\d+_\d+_\w+_\w+_\w+_\w+_\w+_0_0_0", ref):
            [self.assign_reference(model, p, ref) for p in iptv_paths]
            self._clipboard.clear()
        else:
            log(f"Error parsing reference [{ref}].")

        self.emit("clipboard-changed", self._clipboard.wait_is_text_available())

    def assign_reference(self, model, path, ref):
        ref_data = ref.split("_")
        row = model[path]
        fav_id = row[Column.FAV_ID]
        fav_id_data = fav_id.split(":")
        fav_id_data[2:7] = ref_data[2:7]
        new_fav_id = ":".join(fav_id_data)
        new_data_id = ":".join(fav_id_data[:11]).strip()
        old_srv = self._services.pop(fav_id, None)
        if old_srv:
            picon_id_data = old_srv.picon_id.split("_")
            picon_id_data[2:7] = ref_data[2:7]
            new_service = old_srv._replace(data_id=new_data_id, fav_id=new_fav_id, picon_id="_".join(picon_id_data))
            self._services[new_fav_id] = new_service
            self.emit("iptv-service-edited", {fav_id: (old_srv, new_service)})

    # ****************** EPG  ********************** #

    def set_display_epg(self, action, value):
        action.set_state(value)
        set_display = bool(value)
        self._settings.display_epg = set_display
        self._epg_menu_button.set_visible(set_display)
        self._display_epg = set_display
        self.emit("epg-display-changed", set_display)

    def on_epg_display_changed(self, app, display):
        if display:
            if self._epg_cache is None:
                self._epg_cache = FavEpgCache(self)
            else:
                self._epg_cache.reset()

    def on_epg_list_configuration(self, action, value=None):
        if self._s_type is not SettingsType.ENIGMA_2:
            self.show_error_message("Only Enigma2 is supported!")
            return

        if not any(r[Column.FAV_TYPE] == BqServiceType.IPTV.value for r in self._fav_model):
            self.show_error_message("This list does not contains IPTV streams!")
            return

        EpgDialog(self, self._current_bq_name).show()

    # ***************** Import ******************** #

    def on_import_yt_list(self, action, value=None):
        """ Import playlist from YouTube. """
        if not self._bq_selected:
            return

        YtListImportDialog(self).show()

    def on_import_m3u(self, action, value=None):
        """ Imports iptv from m3u files. """
        response = get_chooser_dialog(self._main_window, self._settings, "*.m3u* files", ("*.m3u", "*.m3u8"))
        if response == Gtk.ResponseType.CANCEL:
            return

        if not str(response).endswith(("m3u", "m3u8")):
            self.show_error_message("No m3u file is selected!")
            return

        M3uImportDialog(self._main_window, self._s_type, response, self).show()

    def append_imported_services(self, services):
        bq_services = self._bouquets.get(self._bq_selected)
        self._fav_model.clear()
        for srv in services:
            self._services[srv.fav_id] = srv
            bq_services.append(srv.fav_id)

        gen = self.update_bouquet_services(self._fav_model, None, self._bq_selected)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
        self.emit("iptv-service-added", services)

    def on_import_data(self, path):
        if self.is_data_loading():
            self.show_error_message("Data loading in progress!")
            return

        msg = "Combine with the current data?"
        if len(self._services_model) > 0 and show_dialog(DialogType.QUESTION, self._main_window,
                                                         msg) == Gtk.ResponseType.OK:
            self.import_data(path, force=True)
        else:
            if os.path.isdir(path) and not path.endswith(os.sep):
                path += os.sep
            self.open_data(path)

    def on_import_bouquet(self, action, value=None, file_path=None):
        model, paths = self._bouquets_view.get_selection().get_selected_rows()
        if not paths:
            self.show_error_message("No selected item!")
            return

        appender = self.append_bouquet if self._s_type is SettingsType.ENIGMA_2 else self.append_bouquets
        import_bouquet(self, model, paths[0], appender, file_path)

    def on_import_bouquets(self, action, value=None):
        response = show_dialog(DialogType.CHOOSER, self._main_window, settings=self._settings)
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        self.import_data(response)

    def import_data(self, path, force=None, callback=None):
        if os.path.isdir(path) and not path.endswith(os.sep):
            path += os.sep
        elif os.path.isfile(path):
            arch_path = self.get_archive_path(path)
            if not arch_path:
                return

            path = arch_path.name + os.sep
            callback = arch_path.cleanup

        def append(b, s):
            gen = self.append_imported_data(b, s, callback)
            GLib.idle_add(lambda: next(gen, False))

        dialog = ImportDialog(self, path, append)
        dialog.import_bouquets_data() if force else dialog.show()

    def append_imported_data(self, bouquets, services, callback=None):
        try:
            self._wait_dialog.show()
            yield from self.append_data(bouquets, services)
        finally:
            log("Importing data done!")
            if callback:
                callback()
            self._wait_dialog.hide()

    def on_import_from_web(self, action, value=None):
        if self._s_type is not SettingsType.ENIGMA_2:
            self.show_error_message("Not allowed in this context!")
            return
        ServicesUpdateDialog(self).show()

    @run_idle
    def on_import_data_from_web(self, services, bouquets=None):
        msg = "Combine with the current data?"

        def clb():
            self.show_info_message("Done!")

        if len(self._services_model) > 0 and show_dialog(DialogType.QUESTION, self._main_window,
                                                         msg) == Gtk.ResponseType.OK:
            gen = self.append_imported_data(bouquets or [], services, clb)
        else:
            gen = self.import_data_from_web(services, bouquets, clb)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def import_data_from_web(self, services, bouquets, callback=None):
        self._wait_dialog.show()
        yield from self.create_new_configuration(self._s_type)
        yield from self.append_imported_data(bouquets or [], services, callback)
        self._wait_dialog.hide()

    # ***************** Export  ******************** #

    def on_bouquet_export(self, item=None):
        """ Exports single bouquet to file. """
        bq_selected = self.check_bouquet_selection()
        if not bq_selected:
            return

        model, paths = self._bouquets_view.get_selection().get_selected_rows()
        if len(paths) > 1:
            self.show_error_message("Please, select only one bouquet!")
            return

        response = show_dialog(DialogType.CHOOSER, self._main_window, settings=self._settings,
                               buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        try:
            itr = model.get_iter(paths)
            bq = self.get_bouquet(itr, model)
            if self._s_type is SettingsType.NEUTRINO_MP:
                bq = Bouquets(*model.get(itr, Column.BQ_NAME, Column.BQ_TYPE), [bq])
                response += bq.name
            write_bouquet(response, bq, self._s_type)
        except OSError as e:
            self.show_error_message(str(e))
        else:
            show_dialog(DialogType.INFO, self._main_window, "Done!")

    @run_idle
    def on_export_to_m3u(self, item=None):
        """ Exports bouquets to a *.m3u file. """
        if self.is_data_loading():
            return self.show_error_message("Data loading in progress!")

        model, paths = self._bouquets_view.get_selection().get_selected_rows()
        sb = (f"{i[0]}:{i[1]}" for i in (model.get(model.get_iter(p), Column.BQ_NAME, Column.BQ_TYPE) for p in paths))
        bouquets = {b: self._bouquets[b] for b in sb if b in self._bouquets}
        if not bouquets:
            self.show_error_message("Error. No bouquets selected!")
            return

        ExportM3uDialog(self, bouquets).run()

    def on_export_all_iptv_to_m3u(self, action, value=None):
        if self.is_data_loading():
            return self.show_error_message("Data loading in progress!")

        self.save_bouquet_to_m3u((BouquetService(r[Column.IPTV_SERVICE], BqServiceType.IPTV, r[Column.IPTV_FAV_ID], i)
                                  for i, r in enumerate(self._iptv_model)), name="IPTV")

    def save_bouquet_to_m3u(self, bq_services, url=None, name=None):
        """ Saves bouquet services to *.m3u file. """
        response = show_dialog(DialogType.CHOOSER, self._main_window, settings=self._settings,
                               buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        try:
            bq = Bouquet(name or self._current_bq_name, None, bq_services, None, None)
            export_to_m3u(response, bq, self._s_type, url)
        except Exception as e:
            self.show_error_message(str(e))
        else:
            show_dialog(DialogType.INFO, self._main_window, "Done!")

    # ***************** Backup  ******************** #

    def on_backup_tool_show(self, action, value=None):
        """ Shows backup tool dialog """
        BackupDialog(self._main_window, self._settings, self.open_data).show()

    # ***************** Extra tools  ******************** #

    def on_telnet_show(self, action, value=False):
        action.set_state(value)
        self._telnet_box.set_visible(value)
        self.update_tools_visibility()

    def on_logs_show(self, action, value=False):
        action.set_state(value)
        self._logs_box.set_visible(value)
        self.update_tools_visibility()

    @run_idle
    def update_tools_visibility(self):
        self._bottom_paned.set_visible(self._telnet_box.get_visible() or self._logs_box.get_visible())

    # ************************* Streams ***************************** #

    def on_play_stream(self, item=None):
        self.emit("fav-clicked", PlaybackMode.STREAM)

    def on_play_current(self, item=None):
        """  starts playback of the current channel. """
        self.emit("play-current", None)

    def on_playback_full_screen(self, box, state):
        self._data_paned.set_visible(state)
        self._main_window.unfullscreen() if state else self._main_window.fullscreen()
        if not USE_HEADER_BAR:
            self._main_window.set_show_menubar(state)

    def on_playback_show(self, box):
        if self._page is not Page.RECORDINGS and self._settings.play_streams_mode is PlayStreamsMode.BUILT_IN:
            self._stack.set_visible(False)
            self._fav_paned.set_orientation(Gtk.Orientation.VERTICAL)

    @run_idle
    def on_playback_close(self, box, state):
        self._fav_view.set_sensitive(True)
        self._stack.set_visible(True)
        self.on_info_bar_close()
        self._fav_paned.set_orientation(Gtk.Orientation.HORIZONTAL)

    def on_record(self, button):
        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return True

        if not self._recorder:
            try:
                self._recorder = Recorder.get_instance(self._settings)
            except (ImportError, NameError, AttributeError):
                self.show_error_message("No VLC is found. Check that it is installed!")
                return

        is_record = self._recorder.is_record()

        if is_record:
            self._recorder.stop()
        else:
            if self._s_type is SettingsType.ENIGMA_2:
                self._http_api.send(HttpAPI.Request.STREAM_CURRENT, "", self.record)
            elif self._s_type is SettingsType.NEUTRINO_MP:
                self._http_api.send(HttpAPI.Request.N_ZAP, "",
                                    lambda rf: self._http_api.send(HttpAPI.Request.N_STREAM,
                                                                   rf.get("data", ""), self.record))
            else:
                log("Error [on record]: Settings type is not supported!")

    def record(self, data):
        url = self.get_url_from_m3u(data)
        if url:
            self._recorder.record(url, self._service_name_label.get_text())
            GLib.timeout_add_seconds(1, self.update_record_button, priority=GLib.PRIORITY_LOW)

    def update_record_button(self):
        is_rec = self._recorder.is_record()
        if not is_rec:
            self._record_image.set_opacity(1.0)
        else:
            self._record_image.set_opacity(0 if self._record_image.get_opacity() else 1.0)
        return is_rec

    # ************************ HTTP API **************************** #

    def init_http_api(self):
        self._fav_click_mode = PlaybackMode(self._settings.fav_click_mode)
        api_enable = self._settings.http_api_support
        GLib.idle_add(self._http_status_image.set_visible, api_enable and not self._receiver_info_box.get_visible())

        if not api_enable:
            GLib.idle_add(self._receiver_info_box.set_visible, False)
            if self._http_api:
                self._http_api.close()
                yield True
                self._http_api = None
            self.init_send_to(False)
            return

        current_profile = self._profile_combo_box.get_active_text()
        if current_profile in self._settings.profiles:
            self._settings.current_profile = current_profile

        if not self._http_api:
            self._http_api = HttpAPI(self._settings)
            if self._s_type is SettingsType.ENIGMA_2:
                GLib.timeout_add_seconds(3, self.update_info,
                                         HttpAPI.Request.INFO,
                                         self.update_receiver_info,
                                         priority=GLib.PRIORITY_LOW)
            else:
                GLib.timeout_add_seconds(3, self.update_info,
                                         HttpAPI.Request.N_INFO,
                                         self.update_neutrino_receiver_info,
                                         priority=GLib.PRIORITY_LOW)
        else:
            self._http_api.init()

        self.init_send_to(api_enable and self._settings.enable_send_to)
        yield True

    @run_idle
    def init_send_to(self, enable):
        if enable and not self._links_transmitter:
            self._links_transmitter = LinksTransmitter(self._http_api, self._main_window, self._settings)
        elif self._links_transmitter:
            self._links_transmitter.show(enable)

    def get_url_from_m3u(self, data):
        error_code = data.get("error_code", 0)
        if error_code:
            log(f"HTTP connection error [{error_code}].")
            self.show_error_message("No connection to the receiver!")
            return

        m3u = data.get("m3u", None)
        if m3u:
            urls = re.findall(self._URL_PATTERN, m3u)
            if urls:
                if len(urls) > 1:
                    # Retrieving direct link for IPTV service.
                    url, sep, name = urls[1][0].partition(":")
                    return unquote(url)
                else:
                    return urls[0][0]

    def save_stream_to_m3u(self, url):
        if self._page not in self._fav_pages:
            self.show_error_message("Not allowed in this context!")
            return

        path, column = self._fav_view.get_cursor()
        s_name = self._fav_model.get_value(self._fav_model.get_iter(path), Column.FAV_SERVICE) if path else "stream"

        try:
            response = show_dialog(DialogType.CHOOSER, self._main_window, settings=self._settings)
            if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
                return

            with open(f"{response}{s_name}.m3u", "w", encoding="utf-8") as file:
                file.writelines(f"#EXTM3U\n#EXTVLCOPT--http-reconnect=true\n#EXTINF:-1,{s_name}\n{url}\n")
        except IOError as e:
            self.show_error_message(str(e))
        else:
            show_dialog(DialogType.INFO, self._main_window, "Done!")
        finally:
            GLib.idle_add(self._fav_view.set_sensitive, True)

    def get_service_ref(self, path, show_error=True):
        row = self._fav_model[path][:]
        srv_type, fav_id = row[Column.FAV_TYPE], row[Column.FAV_ID]

        if srv_type in self.MARKER_TYPES and show_error:
            self.show_error_message("Not allowed in this context!")
            return

        srv = self._services.get(fav_id, None)
        if srv:
            if srv_type == BqServiceType.IPTV.name:
                return srv.fav_id.strip()
            elif srv.picon_id:
                return self.get_service_ref_data(srv)

    def get_service_ref_data(self, srv):
        ref = srv.picon_id.rstrip(".png").replace("_", ":") if srv.picon_id else ""
        if self._s_type is SettingsType.ENIGMA_2:
            return ref
        elif self._s_type is SettingsType.NEUTRINO_MP:
            # It may require some correction for cable and terrestrial channels!
            try:
                pos, freq = int(get_pos_num(srv.pos)) * 10, int(srv.freq)
                tid, nid, sid = int(ref[: -8], 16), int(ref[-8: -4], 16), int(srv.ssid, 16)
            except ValueError:
                log(f"Error getting reference for: {srv}")
            else:
                return format((pos + freq * 4 << 48 | tid << 32 | nid << 16 | sid), "x")

    def update_info(self, req, cb):
        """ Updating current info over HTTP API. """
        if not self._http_api:
            GLib.idle_add(self._http_status_image.set_visible, False)
            GLib.idle_add(self._receiver_info_box.set_visible, False)
            return False

        self._http_api.send(req, None, cb)
        return True

    def send_http_request(self, req_type, ref, callback=log, ref_prefix=""):
        """ Sends requests via HTTP API.

            Returns request status (sent or no).
        """
        if not self._http_api:
            self.show_error_message("HTTP API is not activated. Check your settings!")
            self._wait_dialog.hide()
        elif self._http_status_image.get_visible():
            self.show_error_message("No connection to the receiver!")
            self._wait_dialog.hide()
        else:
            self._http_api.send(req_type, ref, callback)
            return True
        return False

    # ************** Enigma2 HTTP API section ********************** #

    def update_receiver_info(self, info):
        error_code = info.get("error_code", 0) if info else 0
        GLib.idle_add(self._receiver_info_box.set_visible, error_code == 0, priority=GLib.PRIORITY_LOW)
        if error_code < 0:
            if self._page is Page.CONTROL:
                GLib.idle_add(self._control_tool.update_signal, None)
            return
        elif error_code == 412:
            self._http_api.init()
            return

        srv_name = info.get("e2servicename", None) if info else None
        if srv_name:
            image = info.get("e2distroversion", "")
            image_ver = info.get("e2imageversion", "")
            model = info.get("e2model", "")
            info_text = f"{model} Image: {image} {image_ver}"
            GLib.idle_add(self._receiver_info_label.set_text, info_text, priority=GLib.PRIORITY_LOW)
            service_name = srv_name or ""
            GLib.idle_add(self._service_name_label.set_text, service_name, priority=GLib.PRIORITY_LOW)
            if service_name:
                self.update_service_info()

        GLib.idle_add(self._signal_box.set_visible, bool(srv_name), priority=GLib.PRIORITY_LOW)

    def update_service_info(self):
        if self._http_api:
            self._http_api.send(HttpAPI.Request.SIGNAL, None, self.update_signal)
            self._http_api.send(HttpAPI.Request.CURRENT, None, self.update_status)

    def update_signal(self, sig):
        if self._page is Page.CONTROL:
            self._control_tool.update_signal(sig)

        self.set_signal(sig.get("e2snr", "0 %") if sig else "0 %")

    @lru_cache(maxsize=2)
    def set_signal(self, val):
        val = val.strip().rstrip("%") or 0
        try:
            val = int(val)
            self._signal_level_bar.set_value(val)
        except ValueError:
            pass  # NOP
        finally:
            GLib.idle_add(self._signal_level_bar.set_visible, val != 0 and val != "N/A")

    @run_idle
    def update_status(self, evn):
        if evn:
            s_duration = int(evn.get("e2eventstart", 0) or 0)
            self._service_epg_label.set_visible(s_duration > 0)
            if not s_duration:
                return

            s_time = datetime.fromtimestamp(s_duration)
            end_time = datetime.fromtimestamp(s_duration + int(evn.get("e2eventduration", "0") or "0"))
            title = evn.get("e2eventtitle", "")
            dsc = f"{title} {s_time.hour}:{s_time.minute} - {end_time.hour}:{end_time.minute}"
            self._service_epg_label.set_text(dsc)
            self._service_epg_label.set_tooltip_text(evn.get("e2eventdescription", ""))

    # ************** Neutrino HTTP API section ********************* #

    def update_neutrino_receiver_info(self, info):
        error_code = info.get("error_code", 0) if info else 0
        GLib.idle_add(self._receiver_info_box.set_visible, error_code == 0, priority=GLib.PRIORITY_LOW)
        if error_code < 0:
            return
        elif error_code == 412:
            self._http_api.init()
            return

        GLib.idle_add(self._receiver_info_label.set_text, info.get("info", ""), priority=GLib.PRIORITY_LOW)

        if self._http_api:
            self._http_api.send(HttpAPI.Request.SIGNAL, None, self.update_neutrino_signal)

    def update_neutrino_signal(self, sig):
        data = sig.get("data", None)
        if data:
            self.set_neutrino_signal(data)

    @lru_cache(maxsize=2)
    def set_neutrino_signal(self, sig):
        s_data = sig.split()
        has_data = len(s_data) == 6
        if has_data:
            try:
                self._signal_level_bar.set_value(int(s_data[3]))
            except ValueError:
                pass  # NOP

        GLib.idle_add(self._signal_level_bar.set_visible, has_data)
        GLib.idle_add(self._signal_box.set_visible, has_data, priority=GLib.PRIORITY_LOW)

    # ***************** Filter and search ********************* #

    def on_services_filter_toggled(self, app=None, value=None):
        if self._page is not Page.SERVICES:
            return True

        if self.is_data_loading() or self._iptv_button.get_active():
            return True

        active = not self._filter_box.get_visible()
        self._filter_services_button.set_active(active)
        if active:
            self._filter_entry.grab_focus()
        elif len(self._services_model) != len(self._services_model_filter):
            self.on_filter_changed()
        self.filter_set_default()
        self._filter_box.set_visible(active)

    def on_iptv_services_filter_toggled(self, app=None, value=None):
        if self._page is not Page.SERVICES or not self._iptv_button.get_active():
            return True

        active = not self._iptv_filter_box.get_visible()
        if active:
            self._iptv_filter_entry.grab_focus()
        elif len(self._iptv_model) != len(self._iptv_services_model_filter):
            self.on_iptv_filter_changed()
        self._iptv_filter_box.set_visible(active)
        # Defaults.
        self.iptv_filter_set_default()

    @run_idle
    def filter_set_default(self):
        """ Setting defaults for filter elements. """
        self._filter_entry.set_text("")
        self._filter_only_free_button.set_active(False)
        self._filter_not_in_bq_button.set_active(False)
        self._filter_types_model.foreach(lambda m, p, i: m.set_value(i, 1, True))
        self._service_types.update({r[0] for r in self._filter_types_model})
        self.update_sat_positions()

    @run_idle
    def iptv_filter_set_default(self):
        """ Setting defaults for IPTV filter elements. """
        self._iptv_filter_entry.set_text("")
        first = self._filter_bouquet_model[self._filter_bouquet_model.get_iter_first()][:]
        self._filter_bouquet_model.clear()
        self._filter_bouquet_model.append((first[0], True))
        self._bq_names.clear()
        self._bq_names.update((b[:b.rindex(":")] for b in self._bouquets))
        list(map(lambda b: self._filter_bouquet_model.append((b, True)), self._bq_names))

    def init_sat_positions(self):
        self._sat_positions.clear()
        first = self._filter_sat_pos_model[0][:]
        self._filter_sat_pos_model.clear()
        self._filter_sat_pos_model.append(first)

    def update_sat_positions(self):
        """ Updates positions values for the filtering function. """
        self._sat_positions.clear()

        if self._s_type is SettingsType.ENIGMA_2:
            terrestrial = False
            cable = False

            for srv in self._services.values():
                tr_type = srv.transponder_type
                if tr_type == "s" and srv.pos:
                    self._sat_positions.add(srv.pos)
                elif tr_type == "t" or tr_type == "a":
                    terrestrial = True
                elif tr_type == "c":
                    cable = True

            if terrestrial:
                self._sat_positions.add("T")
            if cable:
                self._sat_positions.add("C")
        elif self._s_type is SettingsType.NEUTRINO_MP:
            list(map(lambda s: self._sat_positions.add(s.pos), filter(lambda s: s.pos, self._services.values())))

        update_filter_sat_positions(self._filter_sat_pos_model, self._sat_positions)

    @run_with_delay(1)
    def on_filter_changed(self, item=None):
        self._services_load_spinner.start()
        self.update_filter_cache()
        self.update_filter_state()

    @run_with_delay(1)
    def on_iptv_filter_changed(self, item=None):
        self.update_iptv_filter_cache()
        self.update_iptv_filter_state()

    def update_filter_state(self):
        factor = self.DEL_FACTOR * 2
        refresh = len(self._services_model_filter) > factor and self._filter_services_button.get_active()
        gen = self.refilter(self._services_view, self._services_model, factor, refresh)
        GLib.idle_add(lambda: next(gen, False))

    def update_iptv_filter_state(self):
        factor = self.DEL_FACTOR * 2
        refresh = len(self._iptv_services_model_filter) > factor and self._filter_iptv_services_button.get_active()
        gen = self.refilter(self._iptv_services_view, self._iptv_model, factor, refresh)
        GLib.idle_add(lambda: next(gen, False))

    def refilter(self, view, model, factor=100, refresh=False):
        main_model = view.get_model()
        view.set_model(None) if refresh else None

        for i, r in enumerate(model.emit("row-changed", r.path, r.iter) for r in model):
            if i % factor == 0:
                yield True

        view.set_model(main_model)
        GLib.idle_add(self._services_load_spinner.stop)

    def update_filter_cache(self):
        self._filter_cache.clear()
        if not self._filter_box.is_visible():
            return

        txt = self._filter_entry.get_text().upper()
        for r in self._services_model:
            fav_id = r[Column.SRV_FAV_ID]
            free = not r[Column.SRV_CODED] if self._filter_only_free_button.get_active() else True
            self._filter_cache[fav_id] = all((free, fav_id not in self._in_bouquets,
                                              r[Column.SRV_TYPE] in self._service_types,
                                              r[Column.SRV_POS] in self._sat_positions,
                                              txt in "".join((r[Column.SRV_SERVICE],
                                                              r[Column.SRV_PACKAGE],
                                                              r[Column.SRV_TYPE],
                                                              r[Column.SRV_SSID],
                                                              r[Column.SRV_FREQ])).upper()))

    def update_iptv_filter_cache(self):
        self._iptv_filter_cache.clear()
        if not self._iptv_filter_box.is_visible():
            return

        ids = {}
        for k, v in self._bouquets.items():
            for f_id in v:
                ids[f_id] = k[:k.rindex(":")]

        selected_bqs = {r[0] for r in self._filter_bouquet_model if r[1]}
        txt = self._iptv_filter_entry.get_text().upper()
        for r in self._iptv_model:
            fav_id = r[Column.IPTV_FAV_ID]
            self._iptv_filter_cache[fav_id] = all((txt in r[Column.IPTV_SERVICE].upper(),
                                                   ids.get(fav_id, "") in selected_bqs))

    def services_filter_function(self, model, itr, data):
        return self._filter_cache.get(model.get_value(itr, Column.SRV_FAV_ID), True)

    def iptv_services_filter_function(self, model, itr, data):
        return self._iptv_filter_cache.get(model.get_value(itr, Column.IPTV_FAV_ID), True)

    def on_filter_type_toggled(self, toggle, path):
        self.update_filter_toggle_model(self._filter_types_model, toggle, path, self._service_types)

    def on_filter_satellite_toggled(self, toggle, path):
        self.update_filter_toggle_model(self._filter_sat_pos_model, toggle, path, self._sat_positions)

    def on_filter_bouquet_toggled(self, toggle, path):
        self.update_filter_toggle_model(self._filter_bouquet_model, toggle, path, self._bq_names)

    @run_idle
    def on_filter_in_bq_toggled(self, button):
        if button.get_active():
            self._in_bouquets.update(chain.from_iterable(self._bouquets.values()))
        else:
            self._in_bouquets.clear()

        if self._filter_services_button.get_active():
            self.on_filter_changed()

    def update_filter_toggle_model(self, model, toggle, path, values_set):
        update_toggle_model(model, path, toggle)
        values_set.clear()
        values_set.update({r[0] for r in model if r[1]})
        self.on_iptv_filter_changed() if self._iptv_button.get_active() else self.on_filter_changed()

    def activate_search_state(self, view):
        if view is self._services_view:
            self._srv_search_button.set_active(True)
        elif view is self._iptv_services_view:
            self._iptv_search_button.set_active(True)
        elif view is self._fav_view:
            self._fav_search_button.set_active(True)

    # ***************** Editing *********************#

    def on_service_edit(self, view):
        if self.is_data_loading():
            return self.show_error_message("Data loading in progress!")

        model, paths = view.get_selection().get_selected_rows()
        if is_only_one_item_selected(paths, self):
            model_name = get_base_model(model).get_name()
            if model_name == self.FAV_MODEL:
                srv_type = model.get_value(model.get_iter(paths), Column.FAV_TYPE)
                if srv_type == BqServiceType.ALT.name:
                    return self.show_error_message("Operation not allowed in this context!")

                if srv_type in self.MARKER_TYPES:
                    return self.on_rename(view)
                elif srv_type == BqServiceType.IPTV.name:
                    return self.on_iptv_service_edit(model[paths][Column.FAV_ID], view)

                self._dvb_button.set_active(True)
                self.on_locate_in_services(view)

            if model_name == self.IPTV_MODEL:
                self.on_iptv_service_edit(model[paths][Column.IPTV_FAV_ID], view)
            else:
                ServiceDetailsDialog(self, self._NEW_COLOR).show()

    def on_services_add_new(self, item):
        ServiceDetailsDialog(self, action=Action.ADD).show()

    def on_bouquets_edit(self, view):
        """ Renaming bouquets. """
        if not self._bq_selected and self._s_type is SettingsType.NEUTRINO_MP:
            self.show_error_message("This item is not allowed to edit!")
            return

        model, paths = view.get_selection().get_selected_rows()

        if paths:
            itr = model.get_iter(paths[0])
            bq_name, bq_type = model.get(itr, Column.BQ_NAME, Column.BQ_TYPE)
            response = show_dialog(DialogType.INPUT, self._main_window, bq_name)
            if response == Gtk.ResponseType.CANCEL:
                return

            bq = f"{response}:{bq_type}"
            if bq in self._bouquets:
                self.show_error_message(translate("A bouquet with that name exists!"))
                return

            model.set_value(itr, Column.BQ_NAME, response)
            if not model.iter_parent(itr):
                return

            old_bq_name = f"{bq_name}:{bq_type}"
            self._bouquets[bq] = self._bouquets.pop(old_bq_name)
            self._bq_file[bq] = self._bq_file.pop(old_bq_name, None)
            self._current_bq_name = response
            self._bq_name_label.set_text(self._current_bq_name)
            self._bq_selected = bq
            # Services with extra names for the bouquet.
            ext_bq = self._extra_bouquets.get(old_bq_name, None)
            if ext_bq:
                self._extra_bouquets[bq] = ext_bq

    def on_rename(self, view):
        name, model = get_model_data(view)
        if name == self.BQ_MODEL:
            self.on_bouquets_edit(view)
        elif name == self.FAV_MODEL:
            rename(view, self._main_window, ViewTarget.FAV, service_view=self._services_view,
                   services=self._services)
        elif name == self.SERVICE_MODEL:
            rename(view, self._main_window, ViewTarget.SERVICES, fav_view=self._fav_view, services=self._services)

    def on_rename_for_bouquet(self, item=None):
        path, column = self._fav_view.get_cursor()
        if not self._fav_view.is_focus() or path is None:
            return

        data = self._fav_model[path][:]
        cur_name, srv_type, fav_id = data[Column.FAV_SERVICE], data[Column.FAV_TYPE], data[Column.FAV_ID]

        if srv_type == BqServiceType.IPTV.name or srv_type == BqServiceType.MARKER.name:
            self.show_error_message("Not allowed in this context!")
            return

        response = show_dialog(DialogType.INPUT, self._main_window, cur_name)
        if response == Gtk.ResponseType.CANCEL:
            return

        srv = self._services.get(fav_id, None)
        ex_bq = self._extra_bouquets.get(self._bq_selected, None)

        if srv.service == response and ex_bq:
            ex_bq.pop(fav_id, None)
            if not ex_bq:
                self._extra_bouquets.pop(self._bq_selected, None)
        else:
            if ex_bq:
                ex_bq[fav_id] = response
            else:
                self._extra_bouquets[self._bq_selected] = {fav_id: response}

        self._fav_model.set(self._fav_model.get_iter(path), {Column.FAV_SERVICE: response, Column.FAV_TOOLTIP: None,
                                                             Column.FAV_BACKGROUND: self._EXTRA_COLOR})

    def on_set_default_name_for_bouquet(self, item):
        selection = get_selection(self._fav_view, self._main_window)
        if not selection:
            return

        model, paths = selection
        fav_id = model[paths][Column.FAV_ID]
        srv = self._services.get(fav_id, None)
        ex_bq = self._extra_bouquets.get(self._bq_selected, None)

        if not ex_bq:
            self.show_error_message("No changes required!")
            return
        else:
            if not ex_bq.pop(fav_id, None):
                self.show_error_message("No changes required!")
                return
            if not ex_bq:
                self._extra_bouquets.pop(self._bq_selected, None)

        model.set(model.get_iter(paths), {Column.FAV_SERVICE: srv.service, Column.FAV_TOOLTIP: None,
                                          Column.FAV_BACKGROUND: None})

    def on_locate_in_services(self, view):
        is_iptv = self._iptv_button.get_active()
        locate_view = self._iptv_services_view if is_iptv else self._services_view
        column = Column.IPTV_FAV_ID if is_iptv else Column.SRV_FAV_ID
        locate_in_services(view, locate_view, column, self._main_window)

    def on_mark_duplicates(self, item):
        """ Marks services with duplicate [names] in the fav list.  """
        from collections import Counter

        dup = Counter(r[Column.FAV_SERVICE] for r in self._fav_model if r[Column.FAV_TYPE] not in self.MARKER_TYPES)
        dup = {k for k, v in dup.items() if v > 1}

        for r in self._fav_model:
            if r[Column.FAV_SERVICE] in dup:
                r[Column.FAV_BACKGROUND] = self._NEW_COLOR

    def on_remove_duplicates(self, item):
        exist = set()
        to_remove = []
        for r in self._fav_model:
            fav_id = r[Column.FAV_ID]
            if fav_id in exist:
                to_remove.append(r.iter)
            else:
                exist.add(fav_id)

        count = len(to_remove)
        if count:
            if show_dialog(DialogType.QUESTION, self._main_window) != Gtk.ResponseType.OK:
                return
            gen = self.remove_favs(to_remove, self._fav_model)
            GLib.idle_add(lambda: next(gen, False))
            self.show_info_message(f"{translate('Done!')} {translate('Removed')}: {count}")
        else:
            self.show_info_message(f"{translate('Done!')} {translate('Found')}: {count}")

    def on_services_mark_not_in_bouquets(self, item):
        if self.is_data_loading():
            self.show_error_message("Data loading in progress!")
            return

        gen = self.mark_not_in_bouquets()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def mark_not_in_bouquets(self):
        self._services_load_spinner.start()
        ids = set(chain.from_iterable(self._bouquets.values()))

        for index, row in enumerate(self._services_model):
            fav_id = row[Column.SRV_FAV_ID]
            if fav_id not in ids:
                row[Column.SRV_BACKGROUND] = self._EXTRA_COLOR

            if index % self.FAV_FACTOR == 0:
                yield True

        self._services_load_spinner.stop()
        yield True

    def on_services_clear_marked(self, item):
        if self.is_data_loading():
            self.show_error_message("Data loading in progress!")
            return

        gen = self.clear_marked()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def clear_marked(self):
        self._services_load_spinner.start()
        for index, row in enumerate(self._services_model):
            row[Column.SRV_BACKGROUND] = self.get_new_background(row[Column.SRV_CAS_FLAGS])
            if index % self.FAV_FACTOR == 0:
                yield True

        self._services_load_spinner.stop()
        yield True

    def on_services_clear_new_marked(self, item):
        if self.is_data_loading():
            self.show_error_message("Data loading in progress!")
            return

        model, paths = self._services_view.get_selection().get_selected_rows()
        if not paths:
            self.show_error_message("No selected item!")
            return

        gen = self.clear_new_marked(model, paths)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def clear_new_marked(self, model, paths):
        self._services_load_spinner.start()

        paths = get_base_paths(paths, model)
        model = get_base_model(model)
        for index, p in enumerate(paths):
            flags = model[p][Column.SRV_CAS_FLAGS]
            if flags:
                flags_data = flags.split(",")
                for i, f in enumerate(flags_data):
                    if f.startswith("f:"):
                        flag = Flag.parse(f)
                        if Flag.is_new(flag):
                            flag -= Flag.NEW.value
                            if flag:
                                flags_data[i] = f"f:{flag:02d}"
                            else:
                                flags_data.remove(f)

                            flags = ",".join(flags_data)
                            model[p][Column.SRV_BACKGROUND] = None
                            model[p][Column.SRV_CAS_FLAGS] = flags
                            fav_id = model[p][Column.SRV_FAV_ID]
                            srv = self._services.get(fav_id, None)
                            if srv:
                                self._services[fav_id] = srv._replace(flags_cas=flags)
                            break

            if index % self.FAV_FACTOR == 0:
                yield True

        self.show_info_message("Done!", Gtk.MessageType.INFO)
        self._services_load_spinner.stop()
        yield True

    # ***************** Picons ********************* #

    @run_idle
    def set_display_picons(self, action, value):
        action.set_state(value)
        set_display = bool(value)
        self._settings.display_picons = set_display
        self._picon_column.set_visible(set_display)
        self._fav_picon_column.set_visible(set_display)
        self._iptv_picon_column.set_visible(set_display)
        self.refresh_models()

    @run_idle
    def refresh_models(self):
        model = self._services_view.get_model()
        self._services_view.set_model(None)
        self._services_view.set_model(model)
        self._fav_view.set_model(None)
        self._fav_view.set_model(self._fav_model)
        model = self._iptv_services_view.get_model()
        self._iptv_services_view.set_model(None)
        self._iptv_services_view.set_model(model)

    @run_idle
    def update_picons(self):
        self._picons.clear()
        self._fav_model.foreach(lambda m, p, i: m.set_value(i, Column.FAV_PICON, None))

    def get_picon(self, p_id):
        return get_picon_pixbuf(f"{self._settings.profile_picons_path}{p_id}", self._picons_size)

    def get_tooltip_picon(self, srv):
        size, path, picon_id = self._settings.tooltip_logo_size, self._settings.profile_picons_path, srv.picon_id
        pix = get_picon_pixbuf(f"{path}{picon_id}", size=size)
        if not pix:
            picon_id = picon_id.replace(picon_id[:picon_id.find("_")], "1", 1)
            pix = get_picon_pixbuf(f"{path}{picon_id}", size=size)
        if not pix:
            pix = get_picon_pixbuf(f"{path}{get_picon_file_name(srv.service)}", size=size)
        return pix

    def on_assign_picon(self, view, src_path=None, dst_path=None):
        self._stack.set_visible_child_name(Page.PICONS.value)
        self.emit("picon-assign", self.get_target_view(view))

    def on_assign_picon_file(self, view, src_path=None, dst_path=None):
        return assign_picons(self.get_target_view(view), self._services_view, self._fav_view, self._main_window,
                             self._picons, self._settings, self._services, src_path, dst_path)

    def on_remove_picon(self, view):
        remove_picon(self.get_target_view(view), self._services_view, self._fav_view, self._picons, self._settings)

    def on_remove_unused_picons(self, item):
        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return

        remove_all_unused_picons(self._settings, self._services.values())

    def get_target_view(self, view):
        return ViewTarget.SERVICES if Gtk.Buildable.get_name(view) == "services_tree_view" else ViewTarget.FAV

    # ***************** Bouquets ********************* #

    def on_create_bouquet_for_current_satellite(self, item):
        self.create_bouquets(BqGenType.SAT)

    def on_create_bouquet_for_each_satellite(self, item):
        self.create_bouquets(BqGenType.EACH_SAT)

    def on_create_bouquet_for_current_package(self, item):
        self.create_bouquets(BqGenType.PACKAGE)

    def on_create_bouquet_for_each_package(self, item):
        self.create_bouquets(BqGenType.EACH_PACKAGE)

    def on_create_bouquet_for_current_type(self, item):
        self.create_bouquets(BqGenType.TYPE)

    def on_create_bouquet_for_each_type(self, item):
        self.create_bouquets(BqGenType.EACH_TYPE)

    def create_bouquets(self, g_type):
        if self.is_data_loading():
            self.show_error_message("Data loading in progress!")
            return

        if not len(self._bouquets_model):
            self.show_error_message("No bouquets config is loaded. Load or create a new config!")
            return

        gen_bouquets(self, g_type)

    # ***************** Alternatives ********************* #

    def on_add_alternatives(self, item):
        """ Adding alternatives. """
        model, paths = self._fav_view.get_selection().get_selected_rows()
        if not paths:
            return

        if len(paths) > 1:
            self.show_error_message("Please, select only one item!")
            return

        row = model[paths][:]
        s_types = {BqServiceType.MARKER.name, BqServiceType.SPACE.name, BqServiceType.ALT.name, BqServiceType.IPTV.name}
        if row[Column.FAV_TYPE] in s_types:
            self.show_error_message("Operation not allowed in this context!")
            return

        srv = self._services.get(row[Column.FAV_ID], None)
        bq = self._bouquets.get(self._bq_selected, None)
        if not srv or not bq:
            return

        bq_name, sep, bq_type = self._bq_selected.partition(":")
        fav_id = srv.fav_id

        key = f"de{self._alt_counter:02d}:{bq_type}"
        #  Generating file name for alternative
        while key in self._alt_file:
            self._alt_counter += 1
            key = f"de{self._alt_counter:02d}:{bq_type}"

        alt_name = f"de{self._alt_counter:02d}"
        alt_id = f"alternatives_{self._bq_selected}_{fav_id}"
        if alt_id in bq:
            self.show_error_message("A similar service is already in this list!")
            return

        dt, it = BqServiceType.DEFAULT, BqServiceType.IPTV
        bq_srv = BouquetService(None, dt if srv.service_type != it.name else it, fav_id, 0)
        s_type = BqServiceType.ALT.name
        a_srv = srv._replace(service_type=s_type, pos=None, data_id=alt_name, fav_id=alt_id, transponder=(bq_srv,))
        try:
            index = bq.index(fav_id)
        except ValueError as e:
            log(f"[on_add_alternatives] error: {e}")
        else:
            bq[index] = alt_id
            self._services[alt_id] = a_srv
            self._alt_file.add(key)
            data = {Column.FAV_CODED: srv.coded, Column.FAV_SERVICE: srv.service, Column.FAV_LOCKED: srv.locked,
                    Column.FAV_HIDE: srv.hide, Column.FAV_TYPE: s_type, Column.FAV_POS: None,
                    Column.FAV_ID: alt_id, Column.FAV_PICON: self._picons.get(srv.picon_id, None)}
            model.set(model.get_iter(paths), data)
            self._fav_view.row_activated(paths[0], self._fav_view.get_column(Column.FAV_NUM))

    def delete_alts(self, itrs, model, rows):
        """ Deleting alternatives. """
        list(map(model.remove, itrs))
        row = rows[0]
        alt_id = row[Column.ALT_ID]

        if not len(model):
            bq = self._bouquets.get(self._bq_selected, None)
            if not bq:
                return

            fav_id, itr = row[Column.ALT_FAV_ID], row[Column.ALT_ITER]
            bq[bq.index(alt_id)] = fav_id
            self._services.pop(alt_id, None)
            srv = self._services.get(fav_id, None)
            if srv:
                itr = self._fav_model.get_iter_from_string(itr)
                data = {Column.FAV_CODED: srv.coded, Column.FAV_SERVICE: srv.service, Column.FAV_LOCKED: srv.locked,
                        Column.FAV_HIDE: srv.hide, Column.FAV_TYPE: srv.service_type, Column.FAV_POS: srv.pos,
                        Column.FAV_ID: srv.fav_id, Column.FAV_PICON: self._picons.get(srv.picon_id, None)}
                self._fav_model.set(itr, data)
                self._alt_revealer.set_visible(False)
        else:
            srv = self._services.get(alt_id, None)
            if srv:
                alt_services = srv.transponder or ()
                alt_services = tuple(s for s in alt_services if s.data not in {row[Column.ALT_FAV_ID] for row in rows})
                self._services[alt_id] = srv._replace(transponder=alt_services)

        yield True

    def on_alt_view_drag_data_received(self, view, drag_context, x, y, data, info, time):
        srv = self._services.get(self._alt_model.get_value(self._alt_model.get_iter_first(), Column.ALT_ID), None)
        if not srv:
            return True

        txt = data.get_text()
        if txt:
            itr_str, sep, source = txt.partition(self.DRAG_SEP)
            if source == self.SERVICE_MODEL:
                model, id_col, t_col = self._services_view.get_model(), Column.SRV_FAV_ID, Column.SRV_TYPE
            elif source == self.FAV_MODEL:
                model, id_col, t_col = self._fav_view.get_model(), Column.FAV_ID, Column.FAV_TYPE
            elif source == self.ALT_MODEL:
                return self.on_alt_move(itr_str, view.get_dest_row_at_pos(x, y), srv)
            else:
                return True

            return self.on_alt_received(itr_str, model, id_col, t_col, srv)

    def on_alt_received(self, itr_str, model, id_col, t_col, srv):
        itrs = tuple(model.get_iter_from_string(itr) for itr in itr_str.split(","))
        types = {BqServiceType.MARKER.name, BqServiceType.SPACE.name, BqServiceType.ALT.name}
        ids = tuple(model.get_value(itr, id_col) for itr in itrs if model.get_value(itr, t_col) not in types)
        srvs = tuple(self._services.get(f_id, None) for f_id in ids)
        dt, it = BqServiceType.DEFAULT, BqServiceType.IPTV
        a_srvs = tuple(BouquetService(None, dt if s.service_type != it.name else it, s.fav_id, 0) for s in srvs)
        alt_services = srv.transponder + a_srvs
        self._services[srv.fav_id] = srv._replace(transponder=alt_services)

        a_row = self._alt_model[self._alt_model.get_iter_first()][:]
        alt_id, a_itr = a_row[Column.ALT_ID], a_row[Column.ALT_ITER]

        for i, srv in enumerate(srvs, start=len(self._alt_model) + 1):
            pic = self._picons.get(srv.picon_id, None)
            self._alt_model.append((i, pic, srv.service, srv.service_type, srv.pos, srv.fav_id, alt_id, a_itr))

        return True

    def on_alt_move(self, s_iters, info, srv):
        """ Move alternatives in the list. """
        di = -1
        if info:
            path, position = info
            di = path.get_indices()[0]

        itrs = tuple(self._alt_model.get_iter_from_string(itr) for itr in s_iters.split(","))
        [self._alt_model.insert(i, r) for i, r in enumerate((self._alt_model[in_itr][:] for in_itr in itrs), start=di)]
        list(map(self._alt_model.remove, itrs))

        d_type, i_type = BqServiceType.DEFAULT, BqServiceType.IPTV
        alt_srvs = []
        for i, r in enumerate(self._alt_model, start=1):
            r[Column.ALT_NUM] = i
            s_type = d_type if r[Column.ALT_TYPE] != i_type.name else i_type
            alt_srvs.append(BouquetService(None, s_type, r[Column.ALT_FAV_ID], i))

        self._services[srv.fav_id] = srv._replace(transponder=tuple(alt_srvs))
        a_iter = self._alt_model.get_iter_first()
        srv = self._services.get(self._alt_model.get_value(a_iter, Column.ALT_FAV_ID), None)
        if srv:
            fav_iter = self._fav_model.get_iter_from_string(self._alt_model.get_value(a_iter, Column.ALT_ITER))
            self._fav_model.set_value(fav_iter, Column.FAV_PICON, self._picons.get(srv.picon_id, None))

        return True

    def on_alt_selection(self, model, path, column):
        if self._page is Page.EPG:
            row = model[path][:]
            srv = self._services.get(row[Column.ALT_FAV_ID], None)
            if srv and srv.transponder or row[Column.ALT_TYPE] == BqServiceType.IPTV.name:
                self.emit("fav-changed", srv)

    # ***************** Profile label ********************* #

    @run_idle
    def update_profile_label(self):
        label, sep, ip = self._current_ip_label.get_text().partition(":")
        self._current_ip_label.set_text(f"{label}: {self._settings.host}")

        profile_name = self._profile_combo_box.get_active_text()
        msg = translate("Profile:")

        if self._s_type is SettingsType.ENIGMA_2:
            title = f"DemonEditor [{msg} {profile_name} - Enigma2 v.{self.get_format_version()}]"
            self._main_window.set_title(title)
        elif self._s_type is SettingsType.NEUTRINO_MP:
            self._main_window.set_title(f"DemonEditor [{msg} {profile_name} - Neutrino-MP]")

    def get_format_version(self):
        return 5 if self._settings.v5_support else 4

    def show_error_message(self, message):
        self.show_info_message(message, Gtk.MessageType.ERROR)

    @run_idle
    def show_info_message(self, text, message_type=Gtk.MessageType.INFO):
        show_info_bar_message(self._info_bar, self._info_label, text, message_type)

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    def is_data_loading(self):
        is_services_loading = self._services_load_spinner.get_property("active")
        return is_services_loading or self._iptv_services_load_spinner.get_property("active")

    def is_data_saved(self):
        if self._data_hash != 0 and self._data_hash != self.get_data_hash():
            msg = "There are unsaved changes.\n\n\t Save them now?"
            resp = show_dialog(DialogType.QUESTION, self._main_window, msg, action_type=Gtk.ButtonsType.YES_NO)
            return resp != Gtk.ResponseType.YES
        return True

    def get_data_hash(self):
        """ Returns the sum of all data hash. """
        return sum(map(hash, map(frozenset, (self._services.items(),
                                             self._bouquets.keys(),
                                             map(tuple, self._bouquets.values())))))

    # ******************* Properties ***********************#

    @property
    def fav_view(self):
        return self._fav_view

    @property
    def services_view(self):
        return self._services_view

    @property
    def iptv_services_view(self):
        return self._iptv_services_view

    @property
    def bouquets_view(self):
        return self._bouquets_view

    @property
    def filter_entry(self):
        return self._filter_entry

    @property
    def current_services(self):
        return self._services

    @property
    def current_bouquet(self):
        return self._bq_selected

    @property
    def current_bouquets(self):
        return self._bouquets

    @property
    def current_bouquet_files(self):
        return self._bq_file

    @property
    def picons(self):
        return self._picons

    @property
    def picons_buffer(self):
        """ Returns a copy and clears the current buffer. """
        buf = list(self._picons_buffer)
        self._picons_buffer.clear()
        return buf

    @picons_buffer.setter
    def picons_buffer(self, value):
        self._picons_buffer.extend(value)

    @property
    def app_window(self):
        return self._main_window

    @property
    def app_settings(self):
        return self._settings

    @property
    def wait_dialog(self):
        return self._wait_dialog

    @property
    def http_api(self):
        return self._http_api

    @GObject.Property(type=bool, default=True)
    def is_enigma(self):
        return self._is_enigma

    @is_enigma.setter
    def is_enigma(self, value):
        self._is_enigma = value

    @GObject.Property(type=bool, default=False)
    def is_send_data_enabled(self):
        return self._is_send_data_enabled

    @is_send_data_enabled.setter
    def is_send_data_enabled(self, value):
        self._is_send_data_enabled = value

    @GObject.Property(type=bool, default=True)
    def is_receive_data_enabled(self):
        return self._is_receive_data_enabled

    @is_receive_data_enabled.setter
    def is_receive_data_enabled(self, value):
        self._is_receive_data_enabled = value

    @GObject.Property(type=bool, default=False)
    def is_data_save_enabled(self):
        return self._is_data_save_enabled

    @is_data_save_enabled.setter
    def is_data_save_enabled(self, value):
        self._is_data_save_enabled = value

    @GObject.Property(type=bool, default=True)
    def is_data_open_enabled(self):
        return self._is_data_open_enabled

    @is_data_open_enabled.setter
    def is_data_open_enabled(self, value):
        self._is_data_open_enabled = value

    @GObject.Property(type=bool, default=True)
    def is_data_extract_enabled(self):
        return self._is_data_extract_enabled

    @is_data_extract_enabled.setter
    def is_data_extract_enabled(self, value):
        self._is_data_extract_enabled = value

    @property
    def page(self):
        return self._page

    @property
    def display_epg(self):
        return self._display_epg

    @property
    def current_epg_cache(self):
        return self._epg_cache


def start_app():
    try:
        Settings.get_instance()
    except SettingsReadException as e:
        msg = f"{translate('Error reading or writing program settings!')}\n {e}"
        show_dialog(DialogType.INFO, transient=Gtk.Dialog(), text=msg)
    except SettingsException as e:
        msg = f"{e}\n\n{translate('It is recommended to load the default settings!')}"
        dlg = Gtk.Dialog()
        if show_dialog(DialogType.QUESTION, dlg, msg) != Gtk.ResponseType.OK:
            return True

        Settings.reset_to_default()
        show_dialog(DialogType.INFO, transient=dlg, text=translate("All setting were reset. Restart the program!"))
    else:
        app = Application()
        app.run(sys.argv)


if __name__ == "__main__":
    pass

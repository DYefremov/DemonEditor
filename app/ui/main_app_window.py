import os
import sys
from contextlib import suppress
from datetime import datetime
from functools import lru_cache
from itertools import chain
from urllib.parse import urlparse, unquote

from gi.repository import GLib, Gio

from app.commons import run_idle, log, run_task, run_with_delay, init_logger
from app.connections import (HttpAPI, download_data, DownloadType, upload_data, test_http, TestException,
                             HttpApiException, STC_XML_FILE)
from app.eparser import get_blacklist, write_blacklist
from app.eparser import get_services, get_bouquets, write_bouquets, write_services, Bouquets, Bouquet, Service
from app.eparser.ecommons import CAS, Flag, BouquetService
from app.eparser.enigma.bouquets import BqServiceType
from app.eparser.iptv import export_to_m3u
from app.eparser.neutrino.bouquets import BqType
from app.settings import SettingsType, Settings, SettingsException, PlayStreamsMode, SettingsReadException
from app.tools.media import Player, Recorder, HttpPlayer
from app.ui.epg_dialog import EpgDialog
from app.ui.transmitter import LinksTransmitter
from .backup import BackupDialog, backup_data, clear_data_path
from .dialogs import show_dialog, DialogType, get_chooser_dialog, WaitDialog, get_message
from .download_dialog import DownloadDialog
from .imports import ImportDialog, import_bouquet
from .iptv import IptvDialog, SearchUnavailableDialog, IptvListConfigurationDialog, YtListImportDialog, M3uImportDialog
from .main_helper import (insert_marker, move_items, rename, ViewTarget, set_flags, locate_in_services,
                          scroll_to, get_base_model, update_picons_data, copy_picon_reference, assign_picons,
                          remove_picon, is_only_one_item_selected, gen_bouquets, BqGenType, get_iptv_url, append_picons,
                          get_selection, get_model_data, remove_all_unused_picons, get_picon_pixbuf, get_base_itrs)
from .picons_manager import PiconsDialog
from .satellites_dialog import show_satellites_dialog, ServicesUpdateDialog
from .search import SearchProvider
from .service_details_dialog import ServiceDetailsDialog, Action
from .settings_dialog import show_settings_dialog
from .uicommons import (Gtk, Gdk, UI_RESOURCES_PATH, LOCKED_ICON, HIDE_ICON, IPTV_ICON, MOVE_KEYS, KeyboardKey, Column,
                        FavClickMode, MOD_MASK)


class Application(Gtk.Application):
    SERVICE_MODEL_NAME = "services_list_store"
    FAV_MODEL_NAME = "fav_list_store"
    BQ_MODEL_NAME = "bouquets_tree_store"
    ALT_MODEL_NAME = "alt_list_store"
    DRAG_SEP = "::::"

    DEL_FACTOR = 50  # Batch size to delete in one pass.
    FAV_FACTOR = DEL_FACTOR * 2

    _TV_TYPES = ("TV", "TV (HD)", "TV (UHD)", "TV (H264)")

    # Dynamically active elements depending on the selected view
    _SERVICE_ELEMENTS = ("services_to_fav_end_move_popup_item", "services_to_fav_move_popup_item",
                         "services_create_bouquet_popup_item", "services_copy_popup_item", "services_edit_popup_item",
                         "services_add_new_popup_item", "services_picon_popup_item", "services_remove_popup_item")

    _FAV_ELEMENTS = ("fav_cut_popup_item", "fav_paste_popup_item", "fav_locate_popup_item", "fav_iptv_popup_item",
                     "fav_insert_marker_popup_item", "fav_insert_space_popup_item", "fav_edit_sub_menu_popup_item",
                     "fav_edit_popup_item", "fav_picon_popup_item", "fav_copy_popup_item",
                     "fav_epg_configuration_popup_item", "fav_add_alt_popup_item")

    _BOUQUET_ELEMENTS = ("bouquets_new_popup_item", "bouquets_edit_popup_item", "bouquets_cut_popup_item",
                         "bouquets_copy_popup_item", "bouquets_paste_popup_item", "bouquet_import_popup_item",
                         "add_bouquet_tool_button")

    _COMMONS_ELEMENTS = ("bouquets_remove_popup_item", "fav_remove_popup_item")

    _FAV_ENIGMA_ELEMENTS = ("fav_insert_marker_popup_item", "fav_epg_configuration_popup_item")

    _FAV_IPTV_ELEMENTS = ("fav_iptv_popup_item",)

    _LOCK_HIDE_ELEMENTS = ()

    def __init__(self, **kwargs):
        super().__init__(flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE, **kwargs)
        # Adding command line options
        self.add_main_option("log", ord("l"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "", None)
        self.add_main_option("record", ord("r"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "", None)
        self.add_main_option("telnet", ord("t"), GLib.OptionFlags.NONE, GLib.OptionArg.STRING, "", None)
        self.add_main_option("debug", ord("d"), GLib.OptionFlags.NONE, GLib.OptionArg.STRING, "", None)

        self._handlers = {"on_close_app": self.on_close_app,
                          "on_about_app": self.on_about_app,
                          "on_settings": self.on_settings,
                          "on_profile_changed": self.on_profile_changed,
                          "on_download": self.on_download,
                          "on_data_open": self.on_data_open,
                          "on_new_configuration": self.on_new_configuration,
                          "on_tree_view_key_press": self.on_tree_view_key_press,
                          "on_tree_view_key_release": self.on_tree_view_key_release,
                          "on_bouquets_selection": self.on_bouquets_selection,
                          "on_satellite_editor_show": self.on_satellite_editor_show,
                          "on_fav_selection": self.on_fav_selection,
                          "on_alt_selection": self.on_alt_selection,
                          "on_services_selection": self.on_services_selection,
                          "on_fav_cut": self.on_fav_cut,
                          "on_bouquets_cut": self.on_bouquets_cut,
                          "on_services_copy": self.on_services_copy,
                          "on_fav_copy": self.on_fav_copy,
                          "on_bouquets_copy": self.on_bouquets_copy,
                          "on_fav_paste": self.on_fav_paste,
                          "on_bouquets_paste": self.on_bouquets_paste,
                          "on_rename_for_bouquet": self.on_rename_for_bouquet,
                          "on_set_default_name_for_bouquet": self.on_set_default_name_for_bouquet,
                          "on_services_add_new": self.on_services_add_new,
                          "on_edit": self.on_edit,
                          "on_delete": self.on_delete,
                          "on_to_fav_copy": self.on_to_fav_copy,
                          "on_to_fav_end_copy": self.on_to_fav_end_copy,
                          "on_fav_sort": self.on_fav_sort,
                          "on_fav_view_query_tooltip": self.on_fav_view_query_tooltip,
                          "on_services_view_query_tooltip": self.on_services_view_query_tooltip,
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
                          "on_export_to_m3u": self.on_export_to_m3u,
                          "on_import_bouquet": self.on_import_bouquet,
                          "on_import_bouquets": self.on_import_bouquets,
                          "on_backup_tool_show": self.on_backup_tool_show,
                          "on_insert_marker": self.on_insert_marker,
                          "on_insert_space": self.on_insert_space,
                          "on_fav_press": self.on_fav_press,
                          "on_locate_in_services": self.on_locate_in_services,
                          "on_picons_manager_show": self.on_picons_manager_show,
                          "on_filter_changed": self.on_filter_changed,
                          "on_assign_picon": self.on_assign_picon,
                          "on_remove_picon": self.on_remove_picon,
                          "on_reference_picon": self.on_reference_picon,
                          "on_remove_unused_picons": self.on_remove_unused_picons,
                          "on_search_down": self.on_search_down,
                          "on_search_up": self.on_search_up,
                          "on_search": self.on_search,
                          "on_iptv": self.on_iptv,
                          "on_epg_list_configuration": self.on_epg_list_configuration,
                          "on_iptv_list_configuration": self.on_iptv_list_configuration,
                          "on_play_stream": self.on_play_stream,
                          "on_watch": self.on_watch,
                          "on_player_play": self.on_player_play,
                          "on_player_stop": self.on_player_stop,
                          "on_player_previous": self.on_player_previous,
                          "on_player_next": self.on_player_next,
                          "on_player_rewind": self.on_player_rewind,
                          "on_player_close": self.on_player_close,
                          "on_player_press": self.on_player_press,
                          "on_full_screen": self.on_full_screen,
                          "on_drawing_area_realize": self.on_drawing_area_realize,
                          "on_player_drawing_area_draw": self.on_player_drawing_area_draw,
                          "on_ftp_realize": self.on_ftp_realize,
                          "on_record": self.on_record,
                          "on_remove_all_unavailable": self.on_remove_all_unavailable,
                          "on_new_bouquet": self.on_new_bouquet,
                          "on_create_bouquet_for_current_satellite": self.on_create_bouquet_for_current_satellite,
                          "on_create_bouquet_for_each_satellite": self.on_create_bouquet_for_each_satellite,
                          "on_create_bouquet_for_current_package": self.on_create_bouquet_for_current_package,
                          "on_create_bouquet_for_each_package": self.on_create_bouquet_for_each_package,
                          "on_create_bouquet_for_current_type": self.on_create_bouquet_for_current_type,
                          "on_create_bouquet_for_each_type": self.on_create_bouquet_for_each_type,
                          "on_add_alternatives": self.on_add_alternatives}

        self._settings = Settings.get_instance()
        self._s_type = self._settings.setting_type
        # Used for copy/paste. When adding the previous data will not be deleted.
        # Clearing only after the insertion!
        self._rows_buffer = []
        self._bouquets_buffer = []
        self._picons_buffer = []
        self._services = {}
        self._bouquets = {}
        self._bq_file = {}
        self._alt_file = set()
        self._alt_counter = 1
        self._data_hash = 0
        # For bouquets with different names of services in bouquet and main list
        self._extra_bouquets = {}
        self._picons = {}
        self._blacklist = set()
        self._current_bq_name = None
        self._bq_selected = ""  # Current selected bouquet
        self._select_enabled = True  # Multiple selection
        # Current satellite positions in the services list
        self._sat_positions = []
        self._marker_types = {BqServiceType.MARKER.name, BqServiceType.SPACE.name}
        # Player
        self._player = None
        self._full_screen = False
        self._current_mrl = None
        # Record
        self._recorder = None
        # http api
        self._http_api = None
        self._fav_click_mode = None
        self._links_transmitter = None
        self._control_box = None
        self._ftp_client = None
        # Colors
        self._use_colors = False
        self._NEW_COLOR = None  # Color for new services in the main list
        self._EXTRA_COLOR = None  # Color for services with a extra name for the bouquet

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "main_window.glade")
        builder.connect_signals(self._handlers)
        self._main_window = builder.get_object("main_window")
        main_window_size = self._settings.get("window_size")
        # Setting the last size of the window if it was saved
        if main_window_size:
            self._main_window.resize(*main_window_size)
        self._services_view = builder.get_object("services_tree_view")
        self._fav_view = builder.get_object("fav_tree_view")
        self._bouquets_view = builder.get_object("bouquets_tree_view")
        self._fav_model = builder.get_object("fav_list_store")
        self._services_model = builder.get_object("services_list_store")
        self._bouquets_model = builder.get_object("bouquets_tree_store")
        self._main_data_box = builder.get_object("main_data_box")
        self._status_bar_box = builder.get_object("status_bar_box")
        self._services_main_box = builder.get_object("services_main_box")
        self._bouquets_main_box = builder.get_object("bouquets_main_box")
        self._header_bar = builder.get_object("header_bar")
        self._bq_name_label = builder.get_object("bq_name_label")
        tool_bar = builder.get_object("top_toolbar")
        self._main_data_box.bind_property("visible", tool_bar, "visible")
        self._telnet_tool_button = builder.get_object("telnet_tool_button")
        # App info
        self._app_info_box = builder.get_object("app_info_box")
        self._app_info_box.bind_property("visible", builder.get_object("main_paned"), "visible", 4)
        self._app_info_box.bind_property("visible", builder.get_object("toolbar_extra_box"), "visible", 4)
        self._app_info_box.bind_property("visible", builder.get_object("toolbar_tools_box"), "visible", 4)
        self._app_info_box.bind_property("visible", builder.get_object("save_tool_button"), "visible", 4)
        self._app_info_box.bind_property("visible", builder.get_object("add_bouquet_tool_button"), "visible", 4)
        # Status bar
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
        self._signal_level_bar.bind_property("visible", builder.get_object("play_current_service_button"), "visible")
        self._signal_level_bar.bind_property("visible", builder.get_object("record_button"), "visible")
        self._receiver_info_box.bind_property("visible", self._http_status_image, "visible", 4)
        self._receiver_info_box.bind_property("visible", self._signal_box, "visible")
        # Alternatives
        self._alt_view = builder.get_object("alt_tree_view")
        self._alt_model = builder.get_object("alt_list_store")
        self._alt_revealer = builder.get_object("alt_revealer")
        self._alt_revealer.bind_property("visible", self._alt_revealer, "reveal-child")
        # Control
        self._control_button = builder.get_object("control_button")
        self._receiver_info_box.bind_property("visible", self._control_button, "visible")
        self._control_revealer = builder.get_object("control_revealer")
        # FTP client
        self._ftp_button = builder.get_object("ftp_button")
        self._ftp_revealer = builder.get_object("ftp_revealer")
        self._ftp_button.bind_property("active", self._ftp_revealer, "visible")
        # Force Ctrl press event for view. Multiple selections in lists only with Space key(as in file managers)!!!
        self._services_view.connect("key-press-event", self.force_ctrl)
        self._fav_view.connect("key-press-event", self.force_ctrl)
        # Clipboard
        self._clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        # Wait dialog
        self._wait_dialog = WaitDialog(self._main_window)
        # Filter
        self._services_model_filter = builder.get_object("services_model_filter")
        self._services_model_filter.set_visible_func(self.services_filter_function)
        self._filter_entry = builder.get_object("filter_entry")
        self._filter_bar = builder.get_object("filter_bar")
        self._filter_types_box = builder.get_object("filter_types_box")
        self._filter_sat_positions_box = builder.get_object("filter_sat_positions_box")
        self._filter_types_model = builder.get_object("filter_types_list_store")
        self._filter_sat_positions_model = builder.get_object("filter_sat_positions_list_store")
        self._filter_only_free_button = builder.get_object("filter_only_free_button")
        self._filter_bar.bind_property("search-mode-enabled", self._filter_bar, "visible")
        # Player
        self._player_box = builder.get_object("player_box")
        self._player_scale = builder.get_object("player_scale")
        self._player_full_time_label = builder.get_object("player_full_time_label")
        self._player_current_time_label = builder.get_object("player_current_time_label")
        self._player_rewind_box = builder.get_object("player_rewind_box")
        self._player_drawing_area = builder.get_object("player_drawing_area")
        self._player_tool_bar = builder.get_object("player_tool_bar")
        self._player_prev_button = builder.get_object("player_prev_button")
        self._player_next_button = builder.get_object("player_next_button")
        self._player_box.bind_property("visible", tool_bar, "visible", 4)
        self._player_box.bind_property("visible", self._services_main_box, "visible", 4)
        self._player_box.bind_property("visible", self._bouquets_main_box, "visible", 4)
        self._player_box.bind_property("visible", builder.get_object("fav_pos_column"), "visible", 4)
        self._player_box.bind_property("visible", builder.get_object("fav_pos_column"), "visible", 4)
        self._player_box.bind_property("visible", self._profile_combo_box, "sensitive", 4)
        self._fav_view.bind_property("sensitive", self._player_prev_button, "sensitive")
        self._fav_view.bind_property("sensitive", self._player_next_button, "sensitive")
        # Record
        self._record_image = builder.get_object("record_button_image")
        # Enabling events for the drawing area
        self._player_drawing_area.set_events(Gdk.ModifierType.BUTTON1_MASK)
        self._player_frame = builder.get_object("player_frame")
        # Search
        self._search_bar = builder.get_object("search_bar")
        self._search_bar.bind_property("search-mode-enabled", self._search_bar, "visible")
        self._search_entry = builder.get_object("search_entry")
        self._search_provider = SearchProvider((self._services_view, self._fav_view, self._bouquets_view),
                                               builder.get_object("search_down_button"),
                                               builder.get_object("search_up_button"))
        # Dynamically active elements depending on the selected view
        d_elements = (self._SERVICE_ELEMENTS, self._BOUQUET_ELEMENTS, self._COMMONS_ELEMENTS, self._FAV_ELEMENTS,
                      self._FAV_ENIGMA_ELEMENTS, self._FAV_IPTV_ELEMENTS, self._LOCK_HIDE_ELEMENTS)
        self._tool_elements = {k: builder.get_object(k) for k in set(chain.from_iterable(d_elements))}
        # Style
        style_provider = Gtk.CssProvider()
        style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._status_bar_box.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), style_provider,
                                                                         Gtk.STYLE_PROVIDER_PRIORITY_USER)
        # Layout
        if self._settings.is_darwin and self._settings.alternate_layout:
            self._main_paned = builder.get_object("main_data_paned")
            self._fav_paned = builder.get_object("fav_bouquets_paned")
            self._fav_box = self._fav_paned.get_child1()
            self._bouquets_box = self._fav_paned.get_child2()
            self._left_ar_bq_button = builder.get_object("left_arrow_bq_button")
            self._left_ar_bq_button.bind_property("visible", builder.get_object("right_arrow_bq_button"), "visible", 4)
            self._left_ar_bq_button.set_visible(True)
            self.init_layout(builder)

    def init_layout(self, builder):
        """ Initializes an alternate layout, if enabled. """
        top_box = builder.get_object("top_box")
        top_toolbar = builder.get_object("top_toolbar")
        top_toolbar.set_margin_left(0)
        top_toolbar.set_margin_right(10)

        extra_box = builder.get_object("toolbar_extra_tools_box")
        extra_box.set_margin_left(10)
        extra_box.set_margin_right(0)
        extra_box.reorder_child(self._ftp_button, 0)
        extra_box.reorder_child(builder.get_object("add_bouquet_tool_button"), 2)

        top_box.set_child_packing(extra_box, False, True, 0, Gtk.PackType.START)
        top_box.set_child_packing(top_toolbar, False, True, 0, Gtk.PackType.END)
        top_box.reorder_child(extra_box, 0)
        top_box.reorder_child(top_toolbar, 1)

        center_box = builder.get_object("center_box")
        center_box.reorder_child(self._ftp_revealer, 0)
        center_box.reorder_child(self._control_revealer, 1)
        center_box.reorder_child(builder.get_object("main_box"), 2)

        services_box = self._main_paned.get_child1()
        self._main_paned.remove(services_box)
        self._main_paned.remove(self._fav_paned)
        self._main_paned.pack1(self._fav_paned, True, True)
        self._main_paned.pack2(services_box, True, True)

        self._left_ar_bq_button.set_visible(not self._settings.bq_details_first)
        self.init_bq_position()

    def init_bq_position(self):
        self._fav_paned.remove(self._fav_box)
        self._fav_paned.remove(self._bouquets_box)

        if self._settings.bq_details_first:
            self._fav_paned.pack1(self._fav_box, False, False)
            self._fav_paned.pack2(self._bouquets_box, False, False)
        else:
            self._fav_paned.pack1(self._bouquets_box, False, False)
            self._fav_paned.pack2(self._fav_box, False, False)

    def do_startup(self):
        Gtk.Application.do_startup(self)

        self.init_keys()
        self.set_accels()

        builder = Gtk.Builder()
        builder.set_translation_domain("demon-editor")
        builder.add_from_file(UI_RESOURCES_PATH + "app_menu_bar.ui")
        self.set_menubar(builder.get_object("menu_bar"))
        self.set_app_menu(builder.get_object("app-menu"))

        if self._settings.get("telnet"):
            self.init_telnet(builder)

        self.update_profile_label()
        self.init_drag_and_drop()
        self.init_colors()

        if self._settings.load_last_config:
            config = self._settings.get("last_config") or {}
            self.init_profiles(config.get("last_profile", None))
            last_bouquet = config.get("last_bouquet", None)
            self.open_data(callback=lambda: self.open_bouquet(last_bouquet))
        else:
            self.init_profiles()
        gen = self.init_http_api()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def init_telnet(self, builder):
        t_section = builder.get_object("telnet_section")
        t_section.append_item(Gio.MenuItem.new("Telnet", "app.on_telnet_client_show"))
        ac = Gio.SimpleAction.new("on_telnet_client_show", None)
        ac.connect("activate", self.on_telnet_client_show)
        self.add_action(ac)
        self.set_accels_for_action("app.on_telnet_client_show", ["<primary>t"])
        self._telnet_tool_button.set_visible(True)

    def init_keys(self):
        main_handlers = ("on_new_configuration", "on_data_open", "on_download", "on_settings",
                         "on_close_app", "on_import_bouquet", "on_import_bouquets", "on_satellite_editor_show",
                         "on_picons_manager_show", "on_backup_tool_show", "on_about_app")
        iptv_handlers = ("on_iptv", "on_import_yt_list", "on_import_m3u", "on_export_to_m3u",
                         "on_epg_list_configuration", "on_iptv_list_configuration", "on_remove_all_unavailable")

        list(map(lambda x: self.set_action(x, self._handlers.get(x)), main_handlers))
        # Import
        action = self.set_action("on_import_bouquet", self._handlers.get("on_import_bouquet"), False)
        self._tool_elements.get("bouquet_import_popup_item").bind_property("sensitive", action, "enabled")
        # IPTV
        iptv_elem = self._tool_elements.get("fav_iptv_popup_item")
        for h in iptv_handlers:
            action = self.set_action(h, self._handlers.get(h), False)
            iptv_elem.bind_property("sensitive", action, "enabled")
        # Search, Filter
        search_action = Gio.SimpleAction.new_stateful("search", None, GLib.Variant.new_boolean(False))
        search_action.connect("change-state", self.on_search_toggled)
        search_action.set_enabled(False)
        self._app_info_box.bind_property("visible", search_action, "enabled", 4)
        self._main_window.add_action(search_action)  # For "win.*" actions!
        filter_action = Gio.SimpleAction.new_stateful("filter", None, GLib.Variant.new_boolean(False))
        filter_action.connect("change-state", self.on_filter_toggled)
        filter_action.set_enabled(False)
        self._app_info_box.bind_property("visible", filter_action, "enabled", 4)
        self._main_window.add_action(filter_action)
        # Lock, Hide
        self._app_info_box.bind_property("visible", self.set_action("on_hide", self.on_hide, False), "enabled", 4)
        self._app_info_box.bind_property("visible", self.set_action("on_locked", self.on_locked, False), "enabled", 4)
        # Open and download/upload data
        self.set_action("open_data", lambda a, v: self.open_data())
        self.set_action("on_download_data", self.on_download_data)
        self.set_action("upload_all", lambda a, v: self.on_upload_data(DownloadType.ALL))
        self.set_action("upload_bouquets", lambda a, v: self.on_upload_data(DownloadType.BOUQUETS))
        self.set_action("on_archive_open", self.on_archive_open)
        self.set_action("on_import_from_web", self.on_import_from_web)
        # Edit
        self.set_action("on_edit", self.on_edit)
        # Save
        self._app_info_box.bind_property("visible", self.set_action("on_data_save", self.on_data_save, False),
                                         "enabled", 4)
        # Control
        remote_action = Gio.SimpleAction.new_stateful("on_remote", None, GLib.Variant.new_boolean(False))
        remote_action.connect("change-state", self.on_control)
        self.add_action(remote_action)
        # Layout
        self.set_action("on_switch_fav_position", self.on_switch_fav_position)

    def set_action(self, name, fun, enabled=True):
        ac = Gio.SimpleAction.new(name, None)
        ac.connect("activate", fun)
        ac.set_enabled(enabled)
        self.add_action(ac)
        return ac

    def set_accels(self):
        """ Setting accelerators for the actions. """
        self.set_accels_for_action("app.on_data_save", ["<primary>s"])
        self.set_accels_for_action("app.on_download_data", ["<primary>d"])
        self.set_accels_for_action("app.upload_all", ["<primary>u"])
        self.set_accels_for_action("app.upload_bouquets", ["<primary>b"])
        self.set_accels_for_action("app.open_data", ["<primary>o"])
        self.set_accels_for_action("app.on_hide", ["<primary>h"])
        self.set_accels_for_action("app.on_locked", ["<primary>l"])
        self.set_accels_for_action("app.on_close_app", ["<primary>q"])
        self.set_accels_for_action("app.on_edit", ["<primary>e"])
        self.set_accels_for_action("win.search", ["<primary>f"])
        self.set_accels_for_action("win.filter", ["<shift><primary>f"])

    def do_activate(self):
        self._main_window.set_application(self)
        self._main_window.set_wmclass("DemonEditor", "DemonEditor")
        self._main_window.present()

    def do_shutdown(self):
        """  Performs shutdown tasks """
        if self._settings.load_last_config:
            self._settings.add("last_config", {"last_profile": self._settings.current_profile,
                                               "last_bouquet": self._current_bq_name})
        self._settings.save()  # storing current settings

        if self._player:
            self._player.release()

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

        if "telnet" in options:
            t_op = options.get("telnet", "off")
            if t_op == "on":
                self._settings.add("telnet", True)
            elif t_op == "off":
                self._settings.add("telnet", False)
            else:
                log("No valid [on, off] arguments for -t found!")
                return 1
            log("Telnet support is {}. Restart the program to apply the settings!".format(t_op))
            self._settings.save()

        if "debug" in options:
            d_op = options.get("debug", "off")
            if d_op == "on":
                self._settings.debug_mode = True
            elif d_op == "off":
                self._settings.debug_mode = False
            else:
                log("No valid [on, off] arguments for -d found!")
                return 1
            log("Debug mode is {}.".format(d_op))
            self._settings.save()

        self.activate()
        return 0

    def init_profiles(self, profile=None):
        self.update_profiles()
        self._profile_combo_box.set_active_id(profile if profile else self._settings.current_profile)
        if profile:
            self.set_profile(profile)

    def init_drag_and_drop(self):
        """ Enable drag-and-drop. """
        target = []
        bq_target = []

        self._services_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.COPY)
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
        self._services_view.drag_dest_add_uri_targets()

        self._bouquets_view.drag_dest_set_target_list(None)
        self._bouquets_view.drag_source_set_target_list(None)
        self._bouquets_view.drag_dest_add_text_targets()
        self._bouquets_view.drag_source_add_text_targets()
        self._bouquets_view.drag_dest_add_uri_targets()

        self._alt_view.drag_source_set_target_list(None)
        self._alt_view.drag_source_add_text_targets()
        self._alt_view.drag_dest_add_text_targets()

        self._app_info_box.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        if self._settings.is_darwin:
            self._app_info_box.drag_dest_add_uri_targets()
        else:
            self._app_info_box.drag_dest_add_text_targets()
            self._services_view.drag_dest_add_text_targets()
        # For multiple selection.
        self._services_view.get_selection().set_select_function(lambda *args: self._select_enabled)
        self._fav_view.get_selection().set_select_function(lambda *args: self._select_enabled)
        self._bouquets_view.get_selection().set_select_function(lambda *args: self._select_enabled)

    def init_colors(self, update=False):
        """ Initialisation of background colors for the services.

            If update=False - first call on program start, else - after options changes!
        """
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

    def force_ctrl(self, view, event):
        """ Function for force ctrl press event for view """
        event.state |= MOD_MASK

    def on_close_app(self, *args):
        """ Performing operations before closing the application. """
        # Saving the current size of the application window.
        self._settings.add("window_size", self._main_window.get_size())

        if self._recorder:
            if self._recorder.is_record():
                msg = "{}\n\n\t{}".format(get_message("Recording in progress!"), get_message("Are you sure?"))
                if show_dialog(DialogType.QUESTION, self._main_window, msg) == Gtk.ResponseType.CANCEL:
                    return True
            self._recorder.release()

        if not self.is_data_saved():
            gen = self.save_data(lambda: GLib.idle_add(self.quit))
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
            return True
        else:
            GLib.idle_add(self.quit)

    @run_idle
    def on_about_app(self, action, value=None):
        show_dialog(DialogType.ABOUT, self._main_window)

    @run_idle
    def move_items(self, key):
        """ Move items in fav or bouquets tree view """
        if self._services_view.is_focus():
            return
        move_items(key, self._fav_view if self._fav_view.is_focus() else self._bouquets_view)

    def on_switch_fav_position(self, action, value=None):
        visible = self._left_ar_bq_button.get_visible()
        self._settings.bq_details_first = visible
        self._left_ar_bq_button.set_visible(not visible)
        self.init_bq_position()

    # ***************** Copy - Cut - Paste *********************#

    def on_services_copy(self, view):
        self.on_copy(view, target=ViewTarget.FAV)

    def on_fav_copy(self, view):
        self.on_copy(view, target=ViewTarget.SERVICES)

    def on_bouquets_copy(self, view):
        self.on_copy(view, target=ViewTarget.BOUQUET)

    def on_copy(self, view, target):
        model, paths = view.get_selection().get_selected_rows()

        if target is ViewTarget.FAV:
            self._rows_buffer.extend((0, *model.get(model.get_iter(path), Column.SRV_CODED, Column.SRV_SERVICE,
                                                    Column.SRV_LOCKED, Column.SRV_HIDE, Column.SRV_TYPE, Column.SRV_POS,
                                                    Column.SRV_FAV_ID, Column.SRV_PICON), None, None) for path in paths)
        elif target is ViewTarget.SERVICES:
            self._rows_buffer.extend(model[path][:] for path in paths)
        elif target is ViewTarget.BOUQUET:
            to_copy = list(map(model.get_iter, filter(lambda p: p.get_depth() == 2, paths)))
            if to_copy:
                self._bouquets_buffer.extend([model[i][:] for i in to_copy])

    def on_fav_cut(self, view):
        self.on_cut(view, ViewTarget.FAV)

    def on_bouquets_cut(self, view):
        self.on_cut(view, ViewTarget.BOUQUET)

    def on_cut(self, view, target=None):
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

        if model.get_name() == self.FAV_MODEL_NAME:
            self.update_fav_num_column(model)

        self._rows_buffer.clear()

    def bouquet_paste(self, selection):
        model, paths = selection.get_selected_rows()
        if len(paths) > 1:
            self.show_error_dialog("Please, select only one item!")
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

    # ***************** Deletion *********************#

    def on_delete(self, view):
        """ Delete selected items from view

            returns deleted rows list!
        """
        selection = view.get_selection()
        model, paths = selection.get_selected_rows()
        model_name = get_base_model(model).get_name()
        itrs = [model.get_iter(path) for path in paths]
        rows = [model[in_itr][:] for in_itr in itrs]

        if len(itrs) > self.DEL_FACTOR:
            self._wait_dialog.show("Deleting data...")

        priority = GLib.PRIORITY_LOW

        if model_name == self.FAV_MODEL_NAME:
            gen = self.remove_favs(itrs, model)
        elif model_name == self.BQ_MODEL_NAME:
            gen = self.delete_bouquets(itrs, model)
            priority = GLib.PRIORITY_DEFAULT
        elif model_name == self.SERVICE_MODEL_NAME:
            gen = self.delete_services(itrs, model, rows)
        elif model_name == self.ALT_MODEL_NAME:
            gen = self.delete_alts(itrs, model, rows)

        GLib.idle_add(lambda: next(gen, False), priority=priority)
        self.on_view_focus(view)

        return rows

    def remove_favs(self, itrs, model):
        """ Deleting bouquet services """
        if self._bq_selected:
            fav_bouquet = self._bouquets.get(self._bq_selected, None)
            if fav_bouquet:
                for index, itr in enumerate(itrs):
                    del fav_bouquet[int(model.get_path(itr)[0])]
                    self._fav_model.remove(itr)
                    if index % self.DEL_FACTOR == 0:
                        yield True
                self.update_fav_num_column(model)

        self._wait_dialog.hide()
        yield True

    def delete_services(self, itrs, model, rows):
        """ Deleting services """
        for index, s_itr in enumerate(get_base_itrs(itrs, model)):
            self._services_model.remove(s_itr)
            if index % self.DEL_FACTOR == 0:
                yield True

        srv_ids_to_delete = set()
        for row in rows:
            # There are channels with the same parameters except for the name.
            # None because it can have duplicates! Need fix
            fav_id = row[Column.SRV_FAV_ID]
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
        self.update_sat_positions()
        self._wait_dialog.hide()
        yield True

    def delete_bouquets(self, itrs, model):
        """ Deleting bouquets """
        if len(itrs) == 1 and len(model.get_path(itrs[0])) < 2:
            self.show_error_dialog("This item is not allowed to be removed!")
            return

        for itr in itrs:
            if len(model.get_path(itr)) < 2:
                continue

            self._fav_model.clear()
            yield True
            b_row = self._bouquets_model[itr][:]
            self._bouquets.pop("{}:{}".format(b_row[Column.BQ_NAME], b_row[Column.BQ_TYPE]), None)
            self._bouquets_model.remove(itr)

        self._bq_selected = ""
        self._bq_name_label.set_text(self._bq_selected)
        self._wait_dialog.hide()
        yield True

    # ***************** ####### *********************#

    def get_bouquet_file_name(self, bouquet):
        bouquet_file_name = "{}userbouquet.{}.{}".format(self._settings.get(self._s_type).get("data_dir_path"),
                                                         *bouquet.split(":"))
        return bouquet_file_name

    def on_new_bouquet(self, view):
        """ Creates a new item in the bouquets tree """
        model, paths = view.get_selection().get_selected_rows()

        if paths:
            itr = model.get_iter(paths[0])
            bq_type = model.get_value(itr, 3)
            bq_name = "bouquet"
            count = 0
            key = "{}:{}".format(bq_name, bq_type)
            #  Generating name of new bouquet
            while key in self._bouquets:
                count += 1
                bq_name = "bouquet{}".format(count)
                key = "{}:{}".format(bq_name, bq_type)

            response = show_dialog(DialogType.INPUT, self._main_window, bq_name)
            if response == Gtk.ResponseType.CANCEL:
                return

            bq = response, None, None, bq_type
            key = "{}:{}".format(response, bq_type)

            while key in self._bouquets:
                self.show_error_dialog(get_message("A bouquet with that name exists!"))
                response = show_dialog(DialogType.INPUT, self._main_window, bq_name)
                if response == Gtk.ResponseType.CANCEL:
                    return

                key = "{}:{}".format(response, bq_type)
                bq = response, None, None, bq_type

            self._current_bq_name = response

            if model.iter_n_children(itr):  # parent
                ch_itr = model.insert(itr, 0, bq)
                scroll_to(model.get_path(ch_itr), view, paths)
            else:
                p_itr = model.iter_parent(itr)
                it = model.insert(p_itr, int(model.get_path(itr)[1]) + 1, bq) if p_itr else model.append(itr, bq)
                scroll_to(model.get_path(it), view, paths)
            self._bouquets[key] = []

    def on_edit(self, *args):
        """ Edit header bar button """
        if self._services_view.is_focus():
            self.on_service_edit(self._services_view)
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
            is_marker = row[Column.FAV_TYPE] in self._marker_types
            if not is_marker:
                num += 1
            row[Column.FAV_NUM] = 0 if is_marker else num
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
            self._wait_dialog.show(get_message("Sorting data..."))
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

        for s_row, row in zip(sorted(map(lambda r: r[:], rows), key=lambda r: r[c_num] or nv, reverse=rev), rows):
            self._fav_model.set(row.iter, columns, s_row)
            bq[index] = s_row[Column.FAV_ID]
            index += 1

        self._wait_dialog.hide()
        self._fav_view.grab_focus()

    def reset_view_sort_indication(self, view):
        for column in view.get_columns():
            column.set_sort_indicator(False)
            column.set_sort_order(Gtk.SortType.ASCENDING)

    # ********************* Hints *************************#

    def on_fav_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        """  Sets detailed info about service in the tooltip [fav view]. """
        result = view.get_dest_row_at_pos(x, y)
        if not result or not self._settings.show_bq_hints:
            return False

        return self.get_tooltip(view, result, tooltip)

    def on_services_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        """  Sets short info about service in the tooltip [main services view]. """
        result = view.get_dest_row_at_pos(x, y)
        if not result or not self._settings.show_srv_hints:
            return False

        return self.get_tooltip(view, result, tooltip, target=ViewTarget.SERVICES)

    def get_tooltip(self, view, dest_row, tooltip, target=ViewTarget.FAV):
        path, pos = dest_row
        model = view.get_model()

        target_column = Column.FAV_ID if target is ViewTarget.FAV else Column.SRV_FAV_ID
        srv = self._services.get(model[path][target_column], None)
        if srv and srv.picon_id:
            tooltip.set_icon(get_picon_pixbuf(self._settings.picons_local_path + srv.picon_id, size=96))
            tooltip.set_text(
                self.get_hint_for_bq_list(srv) if target is ViewTarget.FAV else self.get_hint_for_srv_list(srv))
            view.set_tooltip_row(tooltip, path)
            return True
        return False

    def get_hint_for_bq_list(self, srv):
        """ Returns detailed info about service as formatted string for using as hint. """
        header, ref = self.get_hint_header_info(srv)

        if srv.service_type == "IPTV":
            return "{}{}".format(header, ref)

        pol = ", {}: {},".format(get_message("Pol"), srv.pol) if srv.pol else ","
        fec = "{}: {}".format("FEC", srv.fec) if srv.fec else ","
        ht = "{}{}: {}\n{}: {}\n{}: {}\n{}: {}{} {}, {}\n{}"
        return ht.format(header,
                         get_message("Package"), srv.package,
                         get_message("System"), srv.system,
                         get_message("Freq"), srv.freq,
                         get_message("Rate"), srv.rate, pol, fec, self.get_ssid_info(srv),
                         ref)

    def get_hint_for_srv_list(self, srv):
        """ Returns short info about service as formatted string for using as hint. """
        header, ref = self.get_hint_header_info(srv)
        return "{}{}\n{}".format(header, self.get_ssid_info(srv), ref)

    def get_hint_header_info(self, srv):
        header = "{}: {}\n{}: {}\n".format(get_message("Name"), srv.service, get_message("Type"), srv.service_type)
        ref = "{}: {}".format(get_message("Service reference"), srv.picon_id.rstrip(".png"))
        return header, ref

    def get_ssid_info(self, srv):
        """ Returns SID representation in hex and dec formats. """
        sid = srv.ssid or "0"
        try:
            dec = "{0:04d}".format(int(sid, 16))
        except ValueError as e:
            log("SID value conversion error: {}".format(e))
        else:
            return "SID: 0x{} ({})".format(sid.upper(), dec)

        return "SID: 0x{}".format(sid.upper())

    # ***************** Drag-and-drop *********************#

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
        if name == self.FAV_MODEL_NAME:
            name_column, type_column = Column.FAV_SERVICE, Column.FAV_TYPE
        elif name == self.BQ_MODEL_NAME:
            name_column, type_column = Column.BQ_NAME, Column.BQ_TYPE
        elif name == self.ALT_MODEL_NAME:
            name_column, type_column = Column.ALT_SERVICE, Column.ALT_TYPE
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
        view.drag_get_data(drag_context, targets[-1] if targets else Gdk.atom_intern("text/uri-list", False), time)

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
            if txt.startswith("file://") and name == self.SERVICE_MODEL_NAME:
                self.on_import_data(urlparse(unquote(txt)).path.strip())
            elif name == self.FAV_MODEL_NAME:
                self.receive_selection(view=view, drop_info=view.get_dest_row_at_pos(x, y), data=txt)

        if uris:
            src, sep, dest = uris[0].partition("::::")
            src_path = urlparse(unquote(src)).path
            if dest:
                dest_path = urlparse(unquote(dest)).path + "/"
                self.picons_buffer = self.on_assign_picon(view, src_path, dest_path)
            elif name == self.SERVICE_MODEL_NAME:
                self.on_import_data(src_path)
            drag_context.finish(True, False, time)

    def on_bq_view_drag_data_received(self, view, drag_context, x, y, data, info, time):
        model_name, model = get_model_data(view)
        drop_info = view.get_dest_row_at_pos(x, y)

        uris = data.get_uris()
        if uris:
            self.on_import_bouquet(None, file_path=urlparse(unquote(uris[0])).path.strip())
            return

        data = data.get_text()
        if not data:
            return

        if data.startswith("file://"):
            self.on_import_bouquet(None, file_path=urlparse(unquote(data)).path.strip())
            return

        itr_str, sep, source = data.partition(self.DRAG_SEP)
        if source != self.BQ_MODEL_NAME:
            return

        if drop_info:
            path, position = drop_info
            itrs = [model.get_iter_from_string(itr) for itr in itr_str.split(",")]
            top_iter = model.get_iter(path)
            parent_itr = model.iter_parent(top_iter)  # parent
            to_del = []
            is_darwin = self._settings.is_darwin

            if parent_itr:
                p_path = model.get_path(parent_itr)[0]
                for itr in itrs:
                    p_itr = model.iter_parent(itr)
                    if not p_itr:
                        break

                    if all((not is_darwin, p_itr, model.get_path(p_itr)[0] == p_path)):
                        model.move_after(itr, top_iter)
                        top_iter = itr
                    else:
                        model.insert(parent_itr, model.get_path(top_iter)[1], model[itr][:])
                        to_del.append(itr)
            elif not model.iter_has_child(top_iter) or is_darwin:
                for itr in itrs:
                    model.append(top_iter, model[itr][:])
                    to_del.append(itr)
                view.expand_all()

            list(map(model.remove, to_del))
            self.update_bouquets_type()

    def get_selection(self, view):
        """ Creates a string from the iterators of the selected rows """
        model, paths = view.get_selection().get_selected_rows()
        model = get_base_model(model)

        if len(paths) > 0:
            itrs = [model.get_iter(path) for path in paths]
            return "{}::::{}".format(",".join([model.get_string_from_iter(itr) for itr in itrs]), model.get_name())

    def receive_selection(self, *, view, drop_info, data):
        """  Update fav view  after data received  """
        try:
            itr_str, sep, source = data.partition(self.DRAG_SEP)
            if source == self.BQ_MODEL_NAME:
                return

            bq_selected = self.check_bouquet_selection()
            if not bq_selected:
                return

            model = get_base_model(view.get_model())
            dest_index = -1

            if drop_info:
                path, position = drop_info
                dest_index = path.get_indices()[0]

            fav_bouquet = self._bouquets[bq_selected]
            itrs = itr_str.split(",")

            if source == self.SERVICE_MODEL_NAME:
                ext_model = self._services_view.get_model()
                ext_itrs = [ext_model.get_iter_from_string(itr) for itr in itrs]
                ext_rows = [ext_model[ext_itr][:] for ext_itr in ext_itrs]

                for ext_row in ext_rows:
                    dest_index += 1
                    fav_id = ext_row[Column.SRV_FAV_ID]
                    ch = self._services[fav_id]
                    model.insert(dest_index, (0, ch.coded, ch.service, ch.locked, ch.hide, ch.service_type, ch.pos,
                                              ch.fav_id, self._picons.get(ch.picon_id, None), None, None))
                    fav_bouquet.insert(dest_index, ch.fav_id)
            elif source == self.FAV_MODEL_NAME:
                in_itrs = [model.get_iter_from_string(itr) for itr in itrs]
                in_rows = [model[in_itr][:] for in_itr in in_itrs]
                for row in in_rows:
                    model.insert(dest_index, row)
                    fav_bouquet.insert(dest_index, row[Column.FAV_ID])
                    dest_index += 1
                for in_itr in in_itrs:
                    del fav_bouquet[int(model.get_path(in_itr)[0])]
                    model.remove(in_itr)
            self.update_fav_num_column(model)
        except ValueError as e:
            self.show_error_dialog(str(e))

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

    def on_view_release(self, view, event):
        """ Handles a mouse click (release) to view. """
        # Enable selection.
        self._select_enabled = True

    def delete_views_selection(self, name):
        if name == self.SERVICE_MODEL_NAME:
            self.delete_selection(self._fav_view)
        elif name == self.FAV_MODEL_NAME:
            self.delete_selection(self._services_view)
        elif name == self.BQ_MODEL_NAME:
            self.delete_selection(self._services_view, self._fav_view)

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

            menu.popup_at_pointer(None)
            return True

    def on_satellite_editor_show(self, action, value=None):
        """ Shows satellites editor dialog """
        show_satellites_dialog(self._main_window, self._settings)

    def on_download(self, action=None, value=None):
        dialog = DownloadDialog(self._main_window, self._settings, self.open_data, self.update_settings)

        if not self.is_data_saved():
            gen = self.save_data(dialog.show)
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
        else:
            dialog.show()

    @run_task
    def on_download_data(self, *args):
        try:
            download_data(settings=self._settings,
                          download_type=DownloadType.ALL,
                          callback=lambda x: print(x, end=""))
        except Exception as e:
            msg = "Downloading data error: {}"
            log(msg.format(e), debug=self._settings.debug_mode, fmt_message=msg)
            self.show_error_dialog(str(e))
        else:
            GLib.idle_add(self.open_data)

    def on_upload_data(self, download_type):
        if not self.is_data_saved():
            gen = self.save_data(lambda: self.on_upload_data(download_type))
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
        else:
            self.upload_data(download_type)

    @run_task
    def upload_data(self, download_type):
        try:
            profile = self._s_type
            opts = self._settings
            use_http = profile is SettingsType.ENIGMA_2

            if profile is SettingsType.ENIGMA_2:
                host, port, user, password = opts.host, opts.http_port, opts.user, opts.password
                try:
                    test_http(host, port, user, password, use_ssl=opts.http_use_ssl, skip_message=True)
                except (TestException, HttpApiException):
                    use_http = False

            upload_data(settings=opts,
                        download_type=download_type,
                        remove_unused=True,
                        callback=lambda x: print(x, end=""),
                        use_http=use_http)
        except Exception as e:
            msg = "Uploading data error: {}"
            log(msg.format(e), debug=self._settings.debug_mode, fmt_message=msg)
            self.show_error_dialog(str(e))

    def on_data_open(self, action=None, value=None):
        """ Opening data via "File/Open". """
        response = show_dialog(DialogType.CHOOSER, self._main_window, settings=self._settings, title="Open folder")
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return
        self.open_data(response)

    def on_archive_open(self, action=None, value=None):
        """ Opening the data archive via "File/Open archive". """
        file_filter = Gtk.FileFilter()
        file_filter.set_name("*.zip, *.gz")
        file_filter.add_mime_type("application/zip")
        file_filter.add_mime_type("application/gzip")

        response = show_dialog(DialogType.CHOOSER, self._main_window,
                               action_type=Gtk.FileChooserAction.OPEN,
                               file_filter=file_filter,
                               settings=self._settings,
                               title="Open archive")
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return
        self.open_data(response)

    def open_data(self, data_path=None, callback=None):
        """ Opening data and fill views. """
        if data_path and os.path.isfile(data_path):
            self.open_compressed_data(data_path)
        else:
            gen = self.update_data(data_path, callback)
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def open_compressed_data(self, data_path):
        """ Opening archived data.  """
        arch_path = self.get_archive_path(data_path)
        if arch_path:
            gen = self.update_data("{}{}".format(arch_path.name, os.sep), callback=arch_path.cleanup)
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
                        try:
                            f_name = zip_info.filename.encode("cp437").decode("utf-8")
                        except (UnicodeEncodeError, UnicodeDecodeError) as e:
                            log("Filename [{}] error in zip archive: {}".format(zip_info.filename, e))
                        else:
                            zip_info.filename = os.path.basename(f_name)
                            zip_file.extract(zip_info, path=tmp_path_name)
        elif tarfile.is_tarfile(data_path):
            with tarfile.open(data_path) as tar:
                for mb in tar.getmembers():
                    if mb.isfile():
                        mb.name = os.path.basename(mb.name)
                        tar.extract(mb, path=tmp_path_name)
        else:
            tmp_path.cleanup()
            log("Error getting the path for the archive. Unsupported file format: {}".format(data_path))
            self.show_error_dialog("Unsupported format!")
            return

        return tmp_path

    def update_data(self, data_path, callback=None):
        self._profile_combo_box.set_sensitive(False)
        self._alt_revealer.set_visible(False)
        self._wait_dialog.show()

        yield from self.clear_current_data()
        # Reset of sorting
        self._services_view.get_model().reset_default_sort_func()
        self.reset_view_sort_indication(self._services_view)
        self.reset_view_sort_indication(self._fav_view)

        try:
            current_profile = self._profile_combo_box.get_active_text()
            if not current_profile:
                self.show_error_dialog("No profile selected!")
                return

            if current_profile != self._settings.current_profile:
                self.init_profiles(self._settings.current_profile)

            data_path = self._settings.data_local_path if data_path is None else data_path
            local_path = self._settings.data_local_path
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
            update_picons_data(self._settings.picons_local_path, self._picons)
            yield True
        except FileNotFoundError as e:
            msg = get_message("Please, download files from receiver or setup your path for read data!")
            self.show_error_dialog(getattr(e, "message", str(e)) + "\n\n" + msg)
            return
        except SyntaxError as e:
            self.show_error_dialog(str(e))
            return
        except Exception as e:
            msg = "Reading data error: {}"
            log(msg.format(e), debug=self._settings.debug_mode, fmt_message=msg)
            self.show_error_dialog("{}\n{}".format(get_message("Reading data error!"), e))
            return
        else:
            self.append_blacklist(black_list)
            yield from self.append_data(bouquets, services)
        finally:
            self._wait_dialog.hide()
            self._profile_combo_box.set_sensitive(True)
            if callback:
                callback()
            yield True
            self.on_view_focus(self._services_view)
            yield True
            self._data_hash = self.get_data_hash()
            yield True

    def append_data(self, bouquets, services):
        if self._app_info_box.get_visible():
            yield from self.show_app_info(False)
        self.append_bouquets(bouquets)
        yield from self.append_services(services)
        self.update_sat_positions()
        yield True

    def show_app_info(self, visible):
        self._app_info_box.set_visible(visible)
        self._app_info_box.grab_focus() if visible else self._services_view.grab_focus()
        yield True

    def append_blacklist(self, black_list):
        if black_list:
            self._blacklist.update(black_list)

    def append_bouquets(self, bqs):
        if len(self._bouquets_model):
            self.add_to_bouquets(bqs)
        else:
            for bouquet in bqs:
                parent = self._bouquets_model.append(None, [bouquet.name, None, None, bouquet.type])
                for bq in bouquet.bouquets:
                    self.append_bouquet(bq, parent)

    def add_to_bouquets(self, bqs):
        for bouquets in bqs:
            for row in self._bouquets_model:
                if row[Column.BQ_TYPE] == bouquets.type:
                    for bq in bouquets.bouquets:
                        self.append_bouquet(bq, row.iter)

    def append_bouquet(self, bq, parent):
        name, bq_type, locked, hidden = bq.name, bq.type, bq.locked, bq.hidden
        self._bouquets_model.append(parent, [name, locked, hidden, bq_type])
        bq_id = "{}:{}".format(name, bq_type)
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
                self._alt_file.add("{}:{}".format(srv.data, bq_type))
                srv = Service(None, None, None, srv.name, locked, None, None, s_type.name,
                              None, None, *agr, srv.data, fav_id, srv.num)
                self._services[fav_id] = srv
            elif srv.name:
                extra_services[fav_id] = srv.name
            services.append(fav_id)

        self._bouquets[bq_id] = services
        self._bq_file[bq_id] = bq.file
        if extra_services:
            self._extra_bouquets[bq_id] = extra_services

    @run_idle
    def open_bouquet(self, name):
        """ Find and open bouquet by name """
        for r in self._bouquets_model:
            for i in r.iterchildren():
                if i[Column.BQ_NAME] == name:
                    self._bouquets_view.expand_row(self._bouquets_model.get_path(r.iter), Column.BQ_NAME)
                    self._bouquets_view.set_cursor(i.path)
                    self._bouquets_view.row_activated(i.path, self._bouquets_view.get_column(Column.BQ_NAME))
                    break

    def append_services(self, services):
        for srv in services:
            #  Adding channels to dict with fav_id as keys.
            self._services[srv.fav_id] = srv
        self.update_services_counts(len(self._services.values()))
        factor = self.DEL_FACTOR * 2

        for index, srv in enumerate(services):
            tooltip, background = None, None
            if self._use_colors:
                flags = srv.flags_cas
                if flags:
                    f_flags = list(filter(lambda x: x.startswith("f:"), flags.split(",")))
                    if f_flags and Flag.is_new(int(f_flags[0][2:])):
                        background = self._NEW_COLOR

            s = srv._replace(picon=self._picons.get(srv.picon_id, None)) + (tooltip, background)
            self._services_model.append(s)
            if index % factor == 0:
                yield True
        yield True

    def clear_current_data(self):
        """ Clearing current data from lists """
        if len(self._services_model) > self.DEL_FACTOR * 100:
            self._wait_dialog.set_text("Deleting data...")

        self._bouquets_model.clear()
        yield True
        self._fav_model.clear()
        yield True
        s_model = self._services_view.get_model()
        self._services_view.set_model(None)
        yield True
        for index, itr in enumerate([row.iter for row in self._services_model]):
            self._services_model.remove(itr)
            if index % self.DEL_FACTOR == 0:
                yield True
        yield True
        self._services_view.set_model(s_model)
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

    def on_data_save(self, *args):
        if self._app_info_box.get_visible():
            return

        if len(self._bouquets_model) == 0:
            self.show_error_dialog("No data to save!")
            return

        if show_dialog(DialogType.QUESTION, self._main_window) != Gtk.ResponseType.OK:
            return

        gen = self.save_data()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def save_data(self, callback=None):
        profile = self._s_type
        path = self._settings.data_local_path
        backup_path = self._settings.backup_local_path
        # Backup data or clearing data path
        backup_data(path, backup_path) if self._settings.backup_before_save else clear_data_path(path)
        yield True

        bouquets = []

        def parse_bouquets(model, b_path, itr):
            bqs = None
            if model.iter_has_child(itr):
                bqs = []
                num_of_children = model.iter_n_children(itr)
                for num in range(num_of_children):
                    bq_itr = model.iter_nth_child(itr, num)
                    bq_name, locked, hidden, bq_type = model.get(bq_itr, Column.BQ_NAME, Column.BQ_LOCKED,
                                                                 Column.BQ_HIDDEN, Column.BQ_TYPE)
                    bq_id = "{}:{}".format(bq_name, bq_type)
                    favs = self._bouquets[bq_id]
                    ex_s = self._extra_bouquets.get(bq_id, None)
                    bq_s = list(filter(None, [self._services.get(f_id, None) for f_id in favs]))

                    if profile is SettingsType.ENIGMA_2:
                        bq_s = self.get_enigma_bq_services(bq_s, ex_s)

                    bq = Bouquet(bq_name, bq_type, bq_s, locked, hidden, self._bq_file.get(bq_id, None))
                    bqs.append(bq)
            if len(b_path) == 1:
                bouquets.append(Bouquets(*model.get(itr, Column.BQ_NAME, Column.BQ_TYPE), bqs if bqs else []))

        # Getting bouquets
        self._bouquets_view.get_model().foreach(parse_bouquets)
        write_bouquets(path, bouquets, profile, self._settings.force_bq_names)
        yield True
        # Getting services
        services_model = get_base_model(self._services_view.get_model())
        services = [Service(*row[: Column.SRV_TOOLTIP]) for row in services_model]
        write_services(path, services, profile, self.get_format_version() if profile is SettingsType.ENIGMA_2 else 0)
        yield True

        if profile is SettingsType.ENIGMA_2:
            # blacklist
            write_blacklist(path, self._blacklist)
        yield True
        self._data_hash = self.get_data_hash()
        yield True
        if callback:
            callback()

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
            self.append_bouquet(Bouquet("Favourites (TV)", BqType.TV.value, [], None, None, "favourites"), parent)
            parent = self._bouquets_model.append(None, ["Bouquets (Radio)", None, None, BqType.RADIO.value])
            self.append_bouquet(Bouquet("Favourites (Radio)", BqType.RADIO.value, [], None, None, "favourites"), parent)
        elif profile is SettingsType.NEUTRINO_MP:
            self._bouquets_model.append(None, ["Providers", None, None, BqType.BOUQUET.value])
            self._bouquets_model.append(None, ["FAV", None, None, BqType.TV.value])
            self._bouquets_model.append(None, ["WEBTV", None, None, BqType.WEBTV.value])

        self._data_hash = self.get_data_hash()
        yield True

    def on_fav_selection(self, model, path, column):
        row = model[path][:]
        if row[Column.FAV_TYPE] == BqServiceType.ALT.name:
            self._alt_model.clear()
            a_id = row[Column.FAV_ID]
            srv = self._services.get(a_id, None)
            if srv:
                for i, s in enumerate(srv[-1] or [], start=1):
                    srv = self._services.get(s.data, None)
                    if srv:
                        pic = self._picons.get(srv.picon_id, None)
                        itr = model.get_string_from_iter(model.get_iter(path))
                        self._alt_model.append((i, pic, srv.service, srv.service_type, srv.pos, srv.fav_id, a_id, itr))
                self._alt_revealer.set_visible(True)
        else:
            self._alt_revealer.set_visible(False)

            if self._control_box and self._control_box.update_epg:
                ref = self.get_service_ref(path)
                if not ref:
                    return
                self._control_box.on_service_changed(ref)

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
        self._current_bq_name = model[path][0] if len(path) > 1 else None
        self._bq_name_label.set_text(self._current_bq_name if self._current_bq_name else "")

        if self._current_bq_name:
            ch_row = model[model.get_iter(path)][:]
            self._bq_selected = "{}:{}".format(ch_row[Column.BQ_NAME], ch_row[Column.BQ_TYPE])
        else:
            self._bq_selected = ""

        if self._bouquets_view.row_expanded(path):
            self._bouquets_view.collapse_row(path)
        else:
            self._bouquets_view.expand_row(path, column)

        if len(path) > 1:
            gen = self.update_bouquet_services(model, path)
            GLib.idle_add(lambda: next(gen, False))

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
                is_marker = srv_type in self._marker_types
                if not is_marker:
                    num += 1

                picon = self._picons.get(srv.picon_id, None)
                # Alternatives
                if srv.service_type == BqServiceType.ALT.name:
                    alt_servs = srv.transponder
                    if alt_servs:
                        alt_srv = self._services.get(alt_servs[0].data, None)
                        picon = self._picons.get(alt_srv.picon_id, None) if srv else None

                self._fav_model.append((0 if is_marker else num, srv.coded, ex_srv_name if ex_srv_name else srv.service,
                                        srv.locked, srv.hide, srv_type, srv.pos, srv.fav_id,
                                        picon, None, background))

        yield True
        self._fav_view.set_model(self._fav_model)
        self._bouquets_view.set_sensitive(True)
        self._bouquets_view.grab_focus()
        yield True

    def check_bouquet_selection(self):
        """ Checks and returns bouquet if selected """
        if not self._bq_selected:
            self.show_error_dialog("Error. No bouquet is selected!")
            return

        if self._s_type is SettingsType.NEUTRINO_MP and self._bq_selected.endswith(BqType.WEBTV.value):
            self.show_error_dialog("Operation not allowed in this context!")
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
                    bq_id = "{}:{}".format(b_row[Column.BQ_NAME], b_row[Column.BQ_TYPE])
                    bq = self._bouquets.get(bq_id, None)
                    if bq:
                        b_row[Column.BQ_TYPE] = bq_type
                        self._bouquets["{}:{}".format(b_row[Column.BQ_NAME], b_row[Column.BQ_TYPE])] = bq

    def delete_selection(self, view, *args):
        """ Used for clear selection on given view(s) """
        for v in [view, *args]:
            v.get_selection().unselect_all()

    def on_settings(self, action, value=None):
        response = show_settings_dialog(self._main_window, self._settings)
        if response != Gtk.ResponseType.CANCEL:
            gen = self.update_settings()
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def update_settings(self):
        s_type = self._settings.setting_type

        if s_type != self._s_type:
            yield from self.show_app_info(True)
            self._s_type = s_type
            c_gen = self.clear_current_data()
            yield from c_gen

        self.init_colors(True)
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

        if self._ftp_button.get_active() and self._ftp_client:
            self._ftp_client.init_ftp()

        if self._app_info_box.get_visible():
            return

        if changed:
            self.open_data()

    def set_profile(self, active):
        self._settings.current_profile = active
        self._s_type = self._settings.setting_type
        self.update_profile_label()

    def update_profiles(self):
        self._profile_combo_box.remove_all()
        for p in self._settings.profiles:
            self._profile_combo_box.append(p, p)

    def on_tree_view_key_press(self, view, event):
        """  Handling  keystrokes on press """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        if key is KeyboardKey.F:
            return True

        ctrl = event.state & MOD_MASK
        model_name, model = get_model_data(view)

        if ctrl and key in MOVE_KEYS:
            self.move_items(key)
        elif ctrl and key is KeyboardKey.C:
            if model_name == self.SERVICE_MODEL_NAME:
                self.on_copy(view, ViewTarget.FAV)
            elif model_name == self.FAV_MODEL_NAME:
                self.on_copy(view, ViewTarget.SERVICES)
            else:
                self.on_copy(view, ViewTarget.BOUQUET)
        elif ctrl and key is KeyboardKey.X:
            if model_name == self.FAV_MODEL_NAME:
                self.on_cut(view, ViewTarget.FAV)
            elif model_name == self.BQ_MODEL_NAME:
                self.on_cut(view, ViewTarget.BOUQUET)
        elif ctrl and key is KeyboardKey.V:
            if model_name == self.FAV_MODEL_NAME:
                self.on_paste(view, ViewTarget.FAV)
            elif model_name == self.BQ_MODEL_NAME:
                self.on_paste(view, ViewTarget.BOUQUET)
        elif key is KeyboardKey.DELETE:
            self.on_delete(view)

    def on_tree_view_key_release(self, view, event):
        """  Handling  keystrokes on release """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK
        model_name, model = get_model_data(view)

        if ctrl and key is KeyboardKey.INSERT:
            # Move items from app to fav list
            if model_name == self.SERVICE_MODEL_NAME:
                self.on_to_fav_copy(view)
            elif model_name == self.BQ_MODEL_NAME:
                self.on_new_bouquet(view)
        elif ctrl and key is KeyboardKey.BACK_SPACE and model_name == self.SERVICE_MODEL_NAME:
            self.on_to_fav_end_copy(view)
        elif ctrl and key is KeyboardKey.R or key is KeyboardKey.F2:
            self.on_rename(view)
        elif key is KeyboardKey.LEFT or key is KeyboardKey.RIGHT:
            view.do_unselect_all(view)
        elif ctrl and model_name == self.FAV_MODEL_NAME:
            if key is KeyboardKey.P:
                self.on_play_stream()
            if key is KeyboardKey.W:
                self.on_zap(self.on_watch)
            if key is KeyboardKey.Z:
                self.on_zap()
            elif key is KeyboardKey.CTRL_L or key is KeyboardKey.CTRL_R:
                self.update_fav_num_column(model)
                self.update_bouquet_list()

    def on_view_focus(self, view, focus_event=None):
        model_name, model = get_model_data(view)
        not_empty = len(model) > 0  # if  > 0 model has items
        is_service = model_name == self.SERVICE_MODEL_NAME

        if model_name == self.BQ_MODEL_NAME:
            for elem in self._tool_elements:
                self._tool_elements[elem].set_sensitive(False)
            for elem in self._BOUQUET_ELEMENTS:
                self._tool_elements[elem].set_sensitive(not_empty)
                if elem == "bouquets_paste_popup_item":
                    self._tool_elements[elem].set_sensitive(not_empty and self._bouquets_buffer)
            if self._s_type is SettingsType.NEUTRINO_MP:
                for elem in self._LOCK_HIDE_ELEMENTS:
                    self._tool_elements[elem].set_sensitive(not_empty)
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
            for elem in self._LOCK_HIDE_ELEMENTS:
                self._tool_elements[elem].set_sensitive(not_empty and self._s_type is SettingsType.ENIGMA_2)

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
        if self._s_type is SettingsType.ENIGMA_2:
            set_flags(flag, self._services_view, self._fav_view, self._services, self._blacklist)
        elif self._s_type is SettingsType.NEUTRINO_MP and self._bq_selected:
            model, paths = self._bouquets_view.get_selection().get_selected_rows()
            itr = model.get_iter(paths[0])
            value = model.get_value(itr, 1 if flag is Flag.LOCK else 2)
            value = None if value else LOCKED_ICON if flag is Flag.LOCK else HIDE_ICON
            model.set_value(itr, 1 if flag is Flag.LOCK else 2, value)

    @run_idle
    def on_model_changed(self, model, path, itr=None):
        model_name = model.get_name()

        if model_name == self.FAV_MODEL_NAME:
            self._fav_count_label.set_text(str(len(model)))
        elif model_name == self.SERVICE_MODEL_NAME:
            self.update_services_counts(len(model))
        elif model_name == self.BQ_MODEL_NAME:
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
            if self._fav_click_mode is FavClickMode.DISABLED:
                return

            self._fav_view.set_sensitive(False)

            if self._fav_click_mode is FavClickMode.STREAM:
                self.on_play_stream()
            elif self._fav_click_mode is FavClickMode.ZAP_PLAY:
                self.on_zap(self.on_watch)
            elif self._fav_click_mode is FavClickMode.ZAP:
                self.on_zap()
            elif self._fav_click_mode is FavClickMode.PLAY:
                self.on_stream()
        else:
            return self.on_view_popup_menu(menu, event)

    # ***************** IPTV *********************#

    def on_iptv(self, action, value=None):
        response = IptvDialog(self._main_window,
                              self._fav_view,
                              self._services,
                              self._bouquets.get(self._bq_selected, None),
                              self._settings,
                              Action.ADD).show()
        if response != Gtk.ResponseType.CANCEL:
            self.update_fav_num_column(self._fav_model)

    @run_idle
    def on_iptv_list_configuration(self, action, value=None):
        if self._s_type is SettingsType.NEUTRINO_MP:
            self.show_error_dialog("Neutrino at the moment not supported!")
            return

        iptv_rows = list(filter(lambda r: r[Column.FAV_TYPE] == BqServiceType.IPTV.value, self._fav_model))
        if not iptv_rows:
            self.show_error_dialog("This list does not contains IPTV streams!")
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
            self.show_error_dialog("This list does not contains IPTV streams!")
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

    # ****************** EPG  **********************#

    def on_epg_list_configuration(self, action, value=None):
        if self._s_type is not SettingsType.ENIGMA_2:
            self.show_error_dialog("Only Enigma2 is supported!")
            return

        if not any(r[Column.FAV_TYPE] == BqServiceType.IPTV.value for r in self._fav_model):
            self.show_error_dialog("This list does not contains IPTV streams!")
            return

        bq = self._bouquets.get(self._bq_selected)
        EpgDialog(self._main_window, self._settings, self._services, bq, self._fav_model, self._current_bq_name).show()

    # ***************** Import  ********************#

    def on_import_yt_list(self, action, value=None):
        """ Import playlist from YouTube """
        if not self._bq_selected:
            return

        YtListImportDialog(self._main_window, self._settings, self.append_imported_services).show()

    def on_import_m3u(self, action, value=None):
        """ Imports iptv from m3u files. """
        response = get_chooser_dialog(self._main_window, self._settings, "*.m3u* files", ("*.m3u", "*.m3u8"))
        if response == Gtk.ResponseType.CANCEL:
            return

        if not str(response).endswith(("m3u", "m3u8")):
            self.show_error_dialog("No m3u file is selected!")
            return

        if self._bq_selected:
            M3uImportDialog(self._main_window, self._s_type, response, self).show()

    def append_imported_services(self, services):
        bq_services = self._bouquets.get(self._bq_selected)
        self._fav_model.clear()
        for srv in services:
            self._services[srv.fav_id] = srv
            bq_services.append(srv.fav_id)

        gen = self.update_bouquet_services(self._fav_model, None, self._bq_selected)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    @run_idle
    def on_export_to_m3u(self, action, value=None):
        i_types = (BqServiceType.IPTV.value, BqServiceType.MARKER.value)
        bq_services = [BouquetService(r[Column.FAV_SERVICE],
                                      BqServiceType(r[Column.FAV_TYPE]),
                                      r[Column.FAV_ID],
                                      r[Column.FAV_NUM]) for r in self._fav_model if r[Column.FAV_TYPE] in i_types]

        if not any(s.type is BqServiceType.IPTV for s in bq_services):
            self.show_error_dialog("This list does not contains IPTV streams!")
            return

        response = show_dialog(DialogType.CHOOSER, self._main_window, settings=self._settings)
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        try:
            bq = Bouquet(self._current_bq_name, None, bq_services, None, None)
            export_to_m3u(response, bq, self._s_type)
        except Exception as e:
            self.show_error_dialog(str(e))
        else:
            show_dialog(DialogType.INFO, self._main_window, "Done!")

    def on_import_data(self, path):
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
            self.show_error_dialog("No selected item!")
            return

        appender = self.append_bouquet if self._s_type is SettingsType.ENIGMA_2 else self.append_bouquets
        import_bouquet(self._main_window, model, paths[0], self._settings, self._services, appender, file_path)

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

        dialog = ImportDialog(self._main_window, path, self._settings, self._services.keys(), append)
        dialog.import_data() if force else dialog.show()

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
            self.show_error_dialog("Not allowed in this context!")
            return
        ServicesUpdateDialog(self._main_window, self._settings, self.on_import_data_from_web).show()

    @run_idle
    def on_import_data_from_web(self, services):
        msg = "Combine with the current data?"
        if len(self._services_model) > 0 and show_dialog(DialogType.QUESTION, self._main_window,
                                                         msg) == Gtk.ResponseType.OK:
            gen = self.append_imported_data([], services)
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
        else:
            gen = self.import_data_from_web(services)
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def import_data_from_web(self, services):
        self._wait_dialog.show()
        if self._app_info_box.get_visible():
            yield from self.create_new_configuration(self._s_type)
        yield from self.append_services(services)
        self.update_sat_positions()
        yield True
        self._wait_dialog.hide()

    # ***************** Backup  ********************#

    def on_backup_tool_show(self, action, value=None):
        """ Shows backup tool dialog """
        BackupDialog(self._main_window, self._settings, self.open_data).show()

    # ***************** Telnet *********************#

    def on_telnet_client_show(self, action, value=None):
        from app.ui.telnet import TelnetDialog
        TelnetDialog(self._main_window, self._settings).show()

    # ***************** Player *********************#

    def on_play_stream(self, item=None):
        self.on_player_play()

    @run_idle
    def on_player_play(self, item=None):
        path, column = self._fav_view.get_cursor()
        if path:
            row = self._fav_model[path][:]
            if row[Column.FAV_TYPE] != BqServiceType.IPTV.name:
                self.show_error_dialog("Not allowed in this context!")
                self.set_playback_elms_active()
                return

            url = get_iptv_url(row, self._s_type)
            self.update_player_buttons()
            if not url:
                self.show_error_dialog("No reference is present!")
                self.set_playback_elms_active()
                return
            self.play(url)

    def play(self, url):
        mode = self._settings.play_streams_mode
        if mode is PlayStreamsMode.M3U:
            self.save_stream_to_m3u(url)
            return

        if mode is PlayStreamsMode.VLC:
            try:
                if self._player and self._player.get_play_mode() is not mode:
                    self._player.release()
                    self._player = None
                if not self._player:
                    self._player = HttpPlayer.get_instance(self._settings)
            except ImportError:
                self.show_error_dialog("No VLC is found. Check that it is installed!")
            else:
                self._player.play(url)
            finally:
                self.set_playback_elms_active()
        else:
            if not self._player_box.get_visible():
                self.set_player_area_size(self._player_box)
                self._current_mrl = url
            self._player_box.set_visible(True)

            if self._player and self._player.get_play_mode() is PlayStreamsMode.BUILT_IN:
                GLib.idle_add(self._player.play, url, priority=GLib.PRIORITY_LOW)
            elif self._player:
                self.show_error_dialog("Play mode has been changed!\nRestart the program to apply the settings.")
                self.set_playback_elms_active()

    def on_player_stop(self, item=None):
        if self._player:
            self._player.stop()

    def on_player_previous(self, item):
        if self._fav_view.do_move_cursor(self._fav_view, Gtk.MovementStep.DISPLAY_LINES, -1):
            self.set_player_action()

    def on_player_next(self, item):
        if self._fav_view.do_move_cursor(self._fav_view, Gtk.MovementStep.DISPLAY_LINES, 1):
            self.set_player_action()

    @run_with_delay(1)
    def set_player_action(self):
        if self._fav_click_mode is FavClickMode.PLAY:
            self.on_stream()
        elif self._fav_click_mode is FavClickMode.ZAP_PLAY:
            self.on_zap(self.on_watch)
        elif self._fav_click_mode is FavClickMode.STREAM:
            self.on_play_stream()

    def on_player_rewind(self, scale, scroll_type, value):
        self._player.set_time(int(value))

    def update_player_buttons(self):
        if self._player:
            path, column = self._fav_view.get_cursor()
            current_index = path[0]
            self._player_prev_button.set_sensitive(current_index != 0)
            self._player_next_button.set_sensitive(len(self._fav_model) != current_index + 1)

    def on_player_close(self, item=None):
        if self._player:
            self._player.stop()

        self.set_playback_elms_active()
        GLib.idle_add(self._player_box.set_visible, False, priority=GLib.PRIORITY_LOW)

    @lru_cache(maxsize=1)
    def on_player_duration_changed(self, duration):
        self._player_scale.set_value(0)
        self._player_scale.get_adjustment().set_upper(duration)
        GLib.idle_add(self._player_rewind_box.set_visible, duration > 0, priority=GLib.PRIORITY_LOW)
        GLib.idle_add(self._player_current_time_label.set_text, "0", priority=GLib.PRIORITY_LOW)
        GLib.idle_add(self._player_full_time_label.set_text, self.get_time_str(duration), priority=GLib.PRIORITY_LOW)

    def on_player_time_changed(self, t):
        if not self._full_screen and self._player_rewind_box.get_visible():
            GLib.idle_add(self._player_current_time_label.set_text, self.get_time_str(t), priority=GLib.PRIORITY_LOW)

    def on_player_error(self):
        self.set_playback_elms_active()
        self.show_error_dialog("Can't Playback!")

    @run_idle
    def set_playback_elms_active(self):
        self._fav_view.set_sensitive(True)
        self._fav_view.do_grab_focus(self._fav_view)

    def get_time_str(self, duration):
        """ Returns a string representation of time from duration in milliseconds """
        m, s = divmod(duration // 1000, 60)
        h, m = divmod(m, 60)
        return "{}{:02d}:{:02d}".format(str(h) + ":" if h else "", m, s)

    def on_drawing_area_realize(self, widget):
        self.set_player_area_size(widget)

        if not self._player:
            try:
                self._player = Player.get_instance(rewind_callback=self.on_player_duration_changed,
                                                   position_callback=self.on_player_time_changed,
                                                   error_callback=self.on_player_error,
                                                   playing_callback=self.set_playback_elms_active)
            except (ImportError, NameError, AttributeError):
                self.show_error_dialog("No VLC is found. Check that it is installed!")
                return True
            else:
                if self._settings.is_darwin:
                    self._player.set_nso(widget)
                else:
                    self._player.set_xwindow(widget.get_window().get_xid())
                self._player.play(self._current_mrl)
            finally:
                self.set_playback_elms_active()

    def set_player_area_size(self, widget):
        w, h = self._main_window.get_size()
        widget.set_size_request(w * 0.6, -1)

    def on_player_drawing_area_draw(self, widget, cr):
        """ Used for black background drawing in the player drawing area.

            Required for Gtk >= 3.20.
            More info: https://developer.gnome.org/gtk3/stable/ch32s10.html,
            https://developer.gnome.org/gtk3/stable/GtkStyleContext.html#gtk-render-background
        """
        context = widget.get_style_context()
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        Gtk.render_background(context, cr, 0, 0, width, height)
        r, g, b, a = 0, 0, 0, 1  # black color
        cr.set_source_rgba(r, g, b, a)
        cr.rectangle(0, 0, width, height)
        cr.fill()

    def on_player_press(self, area, event):
        if event.button == Gdk.BUTTON_PRIMARY:
            if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
                self.on_full_screen()

    def on_full_screen(self, item=None):
        self._full_screen = not self._full_screen
        self.update_state_on_full_screen(not self._full_screen)
        self._main_window.fullscreen() if self._full_screen else self._main_window.unfullscreen()

    @run_idle
    def update_state_on_full_screen(self, visible):
        self._main_data_box.set_visible(visible)
        self._player_tool_bar.set_visible(visible)
        self._status_bar_box.set_visible(visible and not self._app_info_box.get_visible())

    # ************************* Record ***************************** #

    def on_record(self, button):
        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return True

        if not self._recorder:
            try:
                self._recorder = Recorder.get_instance(self._settings)
            except (ImportError, NameError, AttributeError):
                self.show_error_dialog("No VLC is found. Check that it is installed!")
                return

        is_record = self._recorder.is_record()

        if is_record:
            self._recorder.stop()
        else:
            self._http_api.send(HttpAPI.Request.STREAM_CURRENT, None, self.record)

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
        self._fav_click_mode = FavClickMode(self._settings.fav_click_mode)
        http_api_enable = self._settings.http_api_support
        st = all((http_api_enable, self._s_type is SettingsType.ENIGMA_2, not self._receiver_info_box.get_visible()))
        GLib.idle_add(self._http_status_image.set_visible, st)

        if self._s_type is SettingsType.NEUTRINO_MP or not http_api_enable:
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
            GLib.timeout_add_seconds(3, self.update_info, priority=GLib.PRIORITY_LOW)
        else:
            self._http_api.init()

        self.init_send_to(http_api_enable and self._settings.enable_send_to)
        yield True

    @run_idle
    def init_send_to(self, enable):
        if enable and not self._links_transmitter:
            self._links_transmitter = LinksTransmitter(self._http_api, self._main_window, self._settings)
        elif self._links_transmitter:
            self._links_transmitter.show(enable)

    def on_stream(self, item=None):
        path, column = self._fav_view.get_cursor()
        if not path or not self._http_api:
            return

        ref = self.get_service_ref(path)
        if not ref:
            return

        if self._player and self._player.is_playing():
            self._player.stop()

        self._http_api.send(HttpAPI.Request.STREAM, ref, self.watch)

    def on_watch(self, item=None):
        """ Switch to the channel and watch in the player """
        if self._app_info_box.get_visible() and self._settings.play_streams_mode is PlayStreamsMode.BUILT_IN:
            self.set_player_area_size(self._player_box)
            self._player_box.set_visible(True)
            GLib.idle_add(self._app_info_box.set_visible, False)

        self._http_api.send(HttpAPI.Request.STREAM_CURRENT, None, self.watch)

    def watch(self, data):
        url = self.get_url_from_m3u(data)
        if url:
            GLib.timeout_add_seconds(1, self.play, url)

    def get_url_from_m3u(self, data):
        error_code = data.get("error_code", 0)
        if error_code or self._http_status_image.get_visible():
            self.show_error_dialog("No connection to the receiver!")
            self.set_playback_elms_active()
            return

        m3u = data.get("m3u", None)
        if m3u:
            return [s for s in m3u.split("\n") if not s.startswith("#")][0]

    def save_stream_to_m3u(self, url):
        path, column = self._fav_view.get_cursor()
        s_name = self._fav_model.get_value(self._fav_model.get_iter(path), Column.FAV_SERVICE) if path else "stream"

        try:
            response = show_dialog(DialogType.CHOOSER, self._main_window, settings=self._settings)
            if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
                return

            with open("{}{}.m3u".format(response, s_name), "w", encoding="utf-8") as file:
                file.writelines("#EXTM3U\n#EXTVLCOPT--http-reconnect=true\n#EXTINF:-1,{}\n{}\n".format(s_name, url))
        except IOError as e:
            self.show_error_dialog(str(e))
        else:
            show_dialog(DialogType.INFO, self._main_window, "Done!")
        finally:
            GLib.idle_add(self._fav_view.set_sensitive, True)

    @run_idle
    def on_zap(self, callback=None):
        """ Switch(zap) the channel """
        path, column = self._fav_view.get_cursor()
        if not path or not self._http_api:
            self.set_playback_elms_active()
            return

        ref = self.get_service_ref(path)
        if not ref:
            return

        if self._player and self._player.is_playing():
            self._player.stop()

        def zap(rq):
            if rq and rq.get("e2state", False):
                GLib.idle_add(scroll_to, path, self._fav_view)
                if callback:
                    callback()
            else:
                self.show_error_dialog("No connection to the receiver!")
            self.set_playback_elms_active()

        self._http_api.send(HttpAPI.Request.ZAP, ref, zap)

    def get_service_ref(self, path):
        row = self._fav_model[path][:]
        srv_type, fav_id = row[Column.FAV_TYPE], row[Column.FAV_ID]

        if srv_type in self._marker_types:
            self.show_error_dialog("Not allowed in this context!")
            self.set_playback_elms_active()
            return

        srv = self._services.get(fav_id, None)
        if srv and srv.transponder or srv_type == BqServiceType.IPTV.name:
            return srv.picon_id.rstrip(".png").replace("_", ":")

    def update_info(self):
        """ Updating current info over HTTP API """
        if not self._http_api or self._s_type is SettingsType.NEUTRINO_MP:
            GLib.idle_add(self._http_status_image.set_visible, False)
            GLib.idle_add(self._receiver_info_box.set_visible, False)
            return False

        self._http_api.send(HttpAPI.Request.INFO, None, self.update_receiver_info)
        return True

    def update_receiver_info(self, info):
        error_code = info.get("error_code", 0) if info else 0
        GLib.idle_add(self._receiver_info_box.set_visible, error_code == 0, priority=GLib.PRIORITY_LOW)
        if error_code < 0:
            return
        elif error_code == 412:
            self._http_api.init()
            return

        srv_name = info.get("e2servicename", None) if info else None
        if srv_name:
            image = info.get("e2distroversion", "")
            image_ver = info.get("e2imageversion", "")
            model = info.get("e2model", "")
            info_text = "{} Image: {} {}".format(model, image, image_ver)
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
        if self._control_box:
            self._control_box.update_signal(sig)

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
            dsc = "{} {}:{} - {}:{}".format(title, s_time.hour, s_time.minute, end_time.hour, end_time.minute)
            self._service_epg_label.set_text(dsc)
            self._service_epg_label.set_tooltip_text(evn.get("e2eventdescription", ""))

    # ******************* Control *********************** #

    def on_control(self, action, state=False):
        """ Shows/Hides [R key] remote controller. """
        action.set_state(state)
        self._control_revealer.set_visible(state)
        self._control_revealer.set_reveal_child(state)

        if not self._control_box:
            from app.ui.control import ControlBox
            self._control_box = ControlBox(self, self._http_api, self._settings)
            self._control_revealer.add(self._control_box)

        if state:
            self._http_api.send(HttpAPI.Request.VOL, "state", self._control_box.update_volume)

    def on_http_status_visible(self, img):
        self._control_button.set_active(False)

    # ****************** FTP client ********************* #

    def on_ftp_realize(self, revealer):
        if not self._ftp_client:
            from app.ui.ftp import FtpClientBox
            revealer.set_visible(True)
            self._ftp_client = FtpClientBox(self, self._settings)
            revealer.add(self._ftp_client)

    # ***************** Filter and search ********************* #

    def on_filter_toggled(self, action, value):
        if self._app_info_box.get_visible():
            return True

        action.set_state(value)
        if value:
            self.update_filter_sat_positions()
            self._filter_entry.grab_focus()
        else:
            self.filter_set_default()

        self._filter_bar.set_search_mode(value)

    def filter_set_default(self):
        """ Setting defaults for filter elements. """
        self._filter_entry.set_text("")
        self._filter_sat_positions_box.set_active(0)
        self._filter_types_box.set_active(0)
        self._filter_only_free_button.set_active(False)

    def init_sat_positions(self):
        self._sat_positions.clear()
        first = (self._filter_sat_positions_model[0][0],)
        self._filter_sat_positions_model.clear()
        self._filter_sat_positions_model.append(first)
        self._filter_sat_positions_box.set_active(0)

    def update_sat_positions(self):
        """ Updates positions values for the filtering function """
        self._sat_positions.clear()
        sat_positions = set()

        if self._s_type is SettingsType.ENIGMA_2:
            terrestrial = False
            cable = False

            for srv in self._services.values():
                tr_type = srv.transponder_type
                if tr_type == "s" and srv.pos:
                    sat_positions.add(srv.pos)
                elif tr_type == "t":
                    terrestrial = True
                elif tr_type == "c":
                    cable = True

            if terrestrial:
                self._sat_positions.append("T")
            if cable:
                self._sat_positions.append("C")
        elif self._s_type is SettingsType.NEUTRINO_MP:
            list(map(lambda s: sat_positions.add(s.pos), filter(lambda s: s.pos, self._services.values())))

        self._sat_positions.extend(map(str, sorted(sat_positions)))
        if self._filter_bar.is_visible():
            self.update_filter_sat_positions()

    @run_idle
    def update_filter_sat_positions(self):
        model = self._filter_sat_positions_model
        if len(model) < 2:
            list(map(self._filter_sat_positions_model.append, map(lambda x: (str(x),), self._sat_positions)))
        else:
            selected = self._filter_sat_positions_box.get_active_id()
            active = self._filter_sat_positions_box.get_active()
            itrs = list(filter(lambda it: model[it][0] not in self._sat_positions, [row.iter for row in model][1:]))
            list(map(model.remove, itrs))

            if active != 0 and selected not in self._sat_positions:
                self._filter_sat_positions_box.set_active(0)

    @run_with_delay(1)
    def on_filter_changed(self, item):
        GLib.idle_add(self._services_model_filter.refilter, priority=GLib.PRIORITY_LOW)

    def services_filter_function(self, model, itr, data):
        if self._services_model_filter is None or self._services_model_filter == "None":
            return True
        else:
            r_txt = str(model.get(itr, Column.SRV_SERVICE, Column.SRV_PACKAGE, Column.SRV_TYPE, Column.SRV_SSID,
                                  Column.SRV_FREQ, Column.SRV_RATE, Column.SRV_POL, Column.SRV_FEC, Column.SRV_SYSTEM,
                                  Column.SRV_POS)).upper()
            txt = self._filter_entry.get_text().upper() in r_txt
            type_active = self._filter_types_box.get_active() > 0
            pos_active = self._filter_sat_positions_box.get_active() > 0
            free = not model.get(itr, Column.SRV_CODED)[0] if self._filter_only_free_button.get_active() else True

            if type_active and pos_active:
                active_id = self._filter_types_box.get_active_id() == model.get(itr, Column.SRV_TYPE)[0]
                pos = self._filter_sat_positions_box.get_active_id() == model.get(itr, Column.SRV_POS)[0]
                return active_id and pos and txt and free
            elif type_active:
                return self._filter_types_box.get_active_id() == model.get(itr, Column.SRV_TYPE)[0] and txt and free
            elif pos_active:
                pos = self._filter_sat_positions_box.get_active_id() == model.get(itr, Column.SRV_POS)[0]
                return pos and txt and free

            return txt and free

    def on_search_toggled(self, action, value):
        if self._app_info_box.get_visible():
            return True

        action.set_state(value)
        self._search_bar.set_search_mode(value)
        if value:
            self._search_entry.grab_focus()
        else:
            self._search_entry.set_text("")

    def on_search_down(self, item):
        self._search_provider.on_search_down()

    def on_search_up(self, item):
        self._search_provider.on_search_up()

    @run_with_delay(1)
    def on_search(self, entry):
        self._search_provider.search(entry.get_text())

    # ***************** Editing *********************#

    def on_service_edit(self, view):
        model, paths = view.get_selection().get_selected_rows()
        if is_only_one_item_selected(paths, self._main_window):
            model_name = get_base_model(model).get_name()
            if model_name == self.FAV_MODEL_NAME:
                srv_type = model.get_value(model.get_iter(paths), Column.FAV_TYPE)
                if srv_type == BqServiceType.ALT.name:
                    return self.show_error_dialog("Operation not allowed in this context!")

                if srv_type in self._marker_types:
                    return self.on_rename(view)
                elif srv_type == BqServiceType.IPTV.name:
                    return IptvDialog(self._main_window,
                                      self._fav_view,
                                      self._services,
                                      self._bouquets.get(self._bq_selected, None),
                                      self._settings,
                                      Action.EDIT).show()
                self.on_locate_in_services(view)

            dialog = ServiceDetailsDialog(self._main_window,
                                          self._settings,
                                          self._services_view,
                                          self._fav_view,
                                          self._services,
                                          self._bouquets,
                                          self._NEW_COLOR)
            dialog.show()

    def on_services_add_new(self, item):
        dialog = ServiceDetailsDialog(self._main_window,
                                      self._settings,
                                      self._services_view,
                                      self._fav_view,
                                      self._services,
                                      self._bouquets,
                                      action=Action.ADD)
        dialog.show()

    def on_bouquets_edit(self, view):
        """ Renaming bouquets. """
        if not self._bq_selected:
            self.show_error_dialog("This item is not allowed to edit!")
            return

        model, paths = view.get_selection().get_selected_rows()

        if paths:
            itr = model.get_iter(paths[0])
            bq_name, bq_type = model.get(itr, 0, 3)
            response = show_dialog(DialogType.INPUT, self._main_window, bq_name)
            if response == Gtk.ResponseType.CANCEL:
                return

            bq = "{}:{}".format(response, bq_type)
            if bq in self._bouquets:
                self.show_error_dialog(get_message("A bouquet with that name exists!"))
                return

            model.set_value(itr, 0, response)
            old_bq_name = "{}:{}".format(bq_name, bq_type)
            self._bouquets[bq] = self._bouquets.pop(old_bq_name)
            self._bq_file[bq] = self._bq_file.pop(old_bq_name, None)
            self._current_bq_name = response
            self._bq_name_label.set_text(self._current_bq_name)
            self._bq_selected = bq
            # services with extra names for the bouquet
            ext_bq = self._extra_bouquets.get(old_bq_name, None)
            if ext_bq:
                self._extra_bouquets[bq] = ext_bq

    def on_rename(self, view):
        name, model = get_model_data(view)
        if name == self.BQ_MODEL_NAME:
            self.on_bouquets_edit(view)
        elif name == self.FAV_MODEL_NAME:
            rename(view, self._main_window, ViewTarget.FAV, service_view=self._services_view,
                   services=self._services)
        elif name == self.SERVICE_MODEL_NAME:
            rename(view, self._main_window, ViewTarget.SERVICES, fav_view=self._fav_view, services=self._services)

    def on_rename_for_bouquet(self, item):
        selection = get_selection(self._fav_view, self._main_window)
        if not selection:
            return

        model, paths = selection
        data = model[paths][:]
        cur_name, srv_type, fav_id = data[Column.FAV_SERVICE], data[Column.FAV_TYPE], data[Column.FAV_ID]

        if srv_type == BqServiceType.IPTV.name or srv_type == BqServiceType.MARKER.name:
            self.show_error_dialog("Not allowed in this context!")
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

        model.set(model.get_iter(paths), {Column.FAV_SERVICE: response, Column.FAV_TOOLTIP: None,
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
            self.show_error_dialog("No changes required!")
            return
        else:
            if not ex_bq.pop(fav_id, None):
                self.show_error_dialog("No changes required!")
                return
            if not ex_bq:
                self._extra_bouquets.pop(self._bq_selected, None)

        model.set(model.get_iter(paths), {Column.FAV_SERVICE: srv.service, Column.FAV_TOOLTIP: None,
                                          Column.FAV_BACKGROUND: None})

    def on_locate_in_services(self, view):
        locate_in_services(view, self._services_view, self._main_window)

    # ***************** Picons *********************#

    def on_picons_manager_show(self, action, value=None):
        ids = {}
        if self._s_type is SettingsType.ENIGMA_2:
            for r in self._services_model:
                data = r[Column.SRV_PICON_ID].split("_")
                ids["{}:{}:{}".format(data[3], data[5], data[6])] = r[Column.SRV_PICON_ID]

        PiconsDialog(self._main_window, self._settings, ids, self._sat_positions, self).show()

    @run_task
    def update_picons(self):
        update_picons_data(self._settings.picons_local_path, self._picons)
        append_picons(self._picons, self._services_model)

    def on_assign_picon(self, view, src_path=None, dst_path=None):
        return assign_picons(self.get_target_view(view), self._services_view, self._fav_view, self._main_window,
                             self._picons, self._settings, self._services, src_path, dst_path)

    def on_remove_picon(self, view):
        remove_picon(self.get_target_view(view), self._services_view, self._fav_view, self._picons, self._settings)

    def on_reference_picon(self, view):
        """ Copying picon id to clipboard """
        copy_picon_reference(self.get_target_view(view), view, self._services, self._clipboard, self._main_window)

    def on_remove_unused_picons(self, item):
        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return

        remove_all_unused_picons(self._settings, self._picons, self._services.values())

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
        gen_bouquets(self._services_view, self._bouquets_view, self._main_window, g_type, self._TV_TYPES,
                     self._s_type, self.append_bouquet)

    # ***************** Alternatives ********************* #

    def on_add_alternatives(self, item):
        """ Adding alternatives. """
        model, paths = self._fav_view.get_selection().get_selected_rows()
        if not paths:
            return

        if len(paths) > 1:
            self.show_error_dialog("Please, select only one item!")
            return

        row = model[paths][:]
        s_types = {BqServiceType.MARKER.name, BqServiceType.SPACE.name, BqServiceType.ALT.name, BqServiceType.IPTV.name}
        if row[Column.FAV_TYPE] in s_types:
            self.show_error_dialog("Operation not allowed in this context!")
            return

        srv = self._services.get(row[Column.FAV_ID], None)
        bq = self._bouquets.get(self._bq_selected, None)
        if not srv or not bq:
            return

        bq_name, sep, bq_type = self._bq_selected.partition(":")
        fav_id = srv.fav_id

        key = "de{:02d}:{}".format(self._alt_counter, bq_type)
        #  Generating file name for alternative
        while key in self._alt_file:
            self._alt_counter += 1
            key = "de{:02d}:{}".format(self._alt_counter, bq_type)

        alt_name = "de{:02d}".format(self._alt_counter)
        alt_id = "alternatives_{}_{}".format(self._bq_selected, fav_id)
        if alt_id in bq:
            self.show_error_dialog("A similar service is already in this list!")
            return

        dt, it = BqServiceType.DEFAULT, BqServiceType.IPTV
        bq_srv = BouquetService(None, dt if srv.service_type != it.name else it, fav_id, 0)
        s_type = BqServiceType.ALT.name
        a_srv = srv._replace(service_type=s_type, pos=None, data_id=alt_name, fav_id=alt_id, transponder=(bq_srv,))
        try:
            index = bq.index(fav_id)
        except ValueError as e:
            log("[on_add_alternatives] error: {}".format(e))
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
            if source == self.SERVICE_MODEL_NAME:
                model, id_col, t_col = self._services_view.get_model(), Column.SRV_FAV_ID, Column.SRV_TYPE
            elif source == self.FAV_MODEL_NAME:
                model, id_col, t_col = self._fav_view.get_model(), Column.FAV_ID, Column.FAV_TYPE
            elif source == self.ALT_MODEL_NAME:
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
        if self._control_box and self._control_box.update_epg:
            row = model[path][:]
            srv = self._services.get(row[Column.ALT_FAV_ID], None)
            if srv and srv.transponder or row[Column.ALT_TYPE] == BqServiceType.IPTV.name:
                self._control_box.on_service_changed(srv.picon_id.rstrip(".png").replace("_", ":"))

    # ***************** Profile label ********************* #

    @run_idle
    def update_profile_label(self):
        label, sep, ip = self._current_ip_label.get_text().partition(":")
        self._current_ip_label.set_text("{}: {}".format(label, self._settings.host))

        profile_name = self._profile_combo_box.get_active_text()
        msg = get_message("Profile:")
        if self._s_type is SettingsType.ENIGMA_2:
            title = "DemonEditor [{} {} - Enigma2 v.{}]".format(msg, profile_name, self.get_format_version())
            self._main_window.set_title(title)
        elif self._s_type is SettingsType.NEUTRINO_MP:
            self._main_window.set_title("DemonEditor [{} {} - Neutrino-MP]".format(msg, profile_name))

    def get_format_version(self):
        return 5 if self._settings.v5_support else 4

    @run_idle
    def show_error_dialog(self, message):
        show_dialog(DialogType.ERROR, self._main_window, message)

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
    def bouquets_view(self):
        return self._bouquets_view

    @property
    def filter_entry(self):
        return self._filter_entry

    @property
    def current_services(self):
        return self._services

    @property
    def picons_buffer(self):
        """ Returns a copy and clears the current buffer. """
        buf = list(self._picons_buffer)
        self._picons_buffer.clear()
        return buf

    @picons_buffer.setter
    def picons_buffer(self, value):
        self._picons_buffer.extend(value)


def start_app():
    try:
        Settings.get_instance()
    except SettingsReadException as e:
        msg = "{}\n {}".format(get_message("Error reading or writing program settings!"), e)
        show_dialog(DialogType.INFO, transient=Gtk.Dialog(), text=msg)
    except SettingsException as e:
        msg = "{} \n{}".format(e, get_message("All setting were reset. Restart the program!"))
        show_dialog(DialogType.INFO, transient=Gtk.Dialog(), text=msg)
        Settings.reset_to_default()
    else:
        app = Application()
        app.run(sys.argv)


if __name__ == "__main__":
    pass

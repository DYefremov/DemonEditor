import os
import sys

from contextlib import suppress
from functools import lru_cache

from gi.repository import GLib

from app.commons import run_idle, log, run_task, run_with_delay
from app.connections import http_request, HttpRequestType
from app.eparser import get_blacklist, write_blacklist, parse_m3u
from app.eparser import get_services, get_bouquets, write_bouquets, write_services, Bouquets, Bouquet, Service
from app.eparser.ecommons import CAS, Flag
from app.eparser.enigma.bouquets import BqServiceType, get_bouquet
from app.eparser.neutrino.bouquets import BqType
from app.properties import get_config, write_config, Profile
from app.tools.media import Player
from .backup import BackupDialog, backup_data, clear_data_path
from .import_dialog import ImportDialog
from .download_dialog import DownloadDialog
from .iptv import IptvDialog, SearchUnavailableDialog, IptvListConfigurationDialog
from .search import SearchProvider
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, LOCKED_ICON, HIDE_ICON, IPTV_ICON, MOVE_KEYS, KeyboardKey, Column, \
    EXTRA_COLOR, NEW_COLOR
from .dialogs import show_dialog, DialogType, get_chooser_dialog, WaitDialog, get_message
from .main_helper import insert_marker, move_items, rename, ViewTarget, set_flags, locate_in_services, \
    scroll_to, get_base_model, update_picons_data, copy_picon_reference, assign_picon, remove_picon, \
    is_only_one_item_selected, gen_bouquets, BqGenType, get_iptv_url, append_picons, get_selection, get_model_data
from .picons_downloader import PiconsDialog
from .satellites_dialog import show_satellites_dialog
from .settings_dialog import show_settings_dialog
from .service_details_dialog import ServiceDetailsDialog, Action


class Application(Gtk.Application):
    _TV_TYPES = ("TV", "TV (HD)", "TV (UHD)", "TV (H264)")

    _SERVICE_LIST_NAME = "services_list_store"
    _FAV_LIST_NAME = "fav_list_store"
    _BOUQUETS_LIST_NAME = "bouquets_tree_store"

    # Dynamically active elements depending on the selected view
    _SERVICE_ELEMENTS = ("services_popup_menu",)

    _FAV_ELEMENTS = ("fav_cut_popup_item", "fav_paste_popup_item", "fav_locate_popup_item", "fav_iptv_popup_item",
                     "fav_insert_marker_popup_item", "fav_edit_sub_menu_popup_item", "fav_edit_popup_item",
                     "fav_picon_popup_item", "fav_copy_popup_item")

    _BOUQUET_ELEMENTS = ("bouquets_new_popup_item", "bouquets_edit_popup_item", "bouquets_cut_popup_item",
                         "bouquets_copy_popup_item", "bouquets_paste_popup_item", "edit_header_button",
                         "new_header_button", "bouquet_import_popup_item")

    _COMMONS_ELEMENTS = ("edit_header_button", "bouquets_remove_popup_item",
                         "fav_remove_popup_item", "import_bq_menu_button")

    _FAV_ENIGMA_ELEMENTS = ("fav_insert_marker_popup_item",)

    _FAV_IPTV_ELEMENTS = ("fav_iptv_popup_item",)

    _LOCK_HIDE_ELEMENTS = ("locked_tool_button", "hide_tool_button")

    _DYNAMIC_ELEMENTS = ("services_popup_menu", "new_header_button", "edit_header_button", "locked_tool_button",
                         "fav_cut_popup_item", "fav_paste_popup_item", "bouquets_new_popup_item", "hide_tool_button",
                         "bouquets_remove_popup_item", "fav_remove_popup_item", "bouquets_edit_popup_item",
                         "fav_insert_marker_popup_item", "fav_edit_popup_item", "fav_edit_sub_menu_popup_item",
                         "fav_locate_popup_item", "fav_picon_popup_item", "fav_iptv_popup_item", "fav_copy_popup_item",
                         "bouquets_cut_popup_item", "bouquets_copy_popup_item", "bouquets_paste_popup_item",
                         "bouquet_import_popup_item", "import_bq_menu_button")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        handlers = {"on_close_app": self.on_close_app,
                    "on_resize": self.on_resize,
                    "on_about_app": self.on_about_app,
                    "on_preferences": self.on_preferences,
                    "on_download": self.on_download,
                    "on_data_open": self.on_data_open,
                    "on_data_save": self.on_data_save,
                    "on_new_configuration": self.on_new_configuration,
                    "on_tree_view_key_press": self.on_tree_view_key_press,
                    "on_tree_view_key_release": self.on_tree_view_key_release,
                    "on_bouquets_selection": self.on_bouquets_selection,
                    "on_satellite_editor_show": self.on_satellite_editor_show,
                    "on_services_selection": self.on_services_selection,
                    "on_fav_cut": self.on_fav_cut,
                    "on_bouquets_cut": self.on_bouquets_cut,
                    "on_services_copy": self.on_services_copy,
                    "on_fav_copy": self.on_fav_copy,
                    "on_bouquets_copy": self.on_bouquets_copy,
                    "on_fav_paste": self.on_fav_paste,
                    "on_bouquets_paste": self.on_bouquets_paste,
                    "on_edit": self.on_rename,
                    "on_rename_for_bouquet": self.on_rename_for_bouquet,
                    "on_set_default_name_for_bouquet": self.on_set_default_name_for_bouquet,
                    "on_service_edit": self.on_service_edit,
                    "on_services_add_new": self.on_services_add_new,
                    "on_delete": self.on_delete,
                    "on_tool_edit": self.on_header_edit,
                    "on_to_fav_copy": self.on_to_fav_copy,
                    "on_to_fav_end_copy": self.on_to_fav_end_copy,
                    "on_view_drag_begin": self.on_view_drag_begin,
                    "on_view_drag_data_get": self.on_view_drag_data_get,
                    "on_view_drag_data_received": self.on_view_drag_data_received,
                    "on_bq_view_drag_data_received": self.on_bq_view_drag_data_received,
                    "on_view_press": self.on_view_press,
                    "on_view_popup_menu": self.on_view_popup_menu,
                    "on_popover_release": self.on_popover_release,
                    "on_view_focus": self.on_view_focus,
                    "on_hide": self.on_hide,
                    "on_locked": self.on_locked,
                    "on_model_changed": self.on_model_changed,
                    "on_import_m3u": self.on_import_m3u,
                    "on_import_bouquet": self.on_import_bouquet,
                    "on_import_bouquets": self.on_import_bouquets,
                    "on_backup_tool_show": self.on_backup_tool_show,
                    "on_insert_marker": self.on_insert_marker,
                    "on_fav_press": self.on_fav_press,
                    "on_locate_in_services": self.on_locate_in_services,
                    "on_picons_loader_show": self.on_picons_loader_show,
                    "on_filter_changed": self.on_filter_changed,
                    "on_assign_picon": self.on_assign_picon,
                    "on_remove_picon": self.on_remove_picon,
                    "on_reference_picon": self.on_reference_picon,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_search_toggled": self.on_search_toggled,
                    "on_search_down": self.on_search_down,
                    "on_search_up": self.on_search_up,
                    "on_search": self.on_search,
                    "on_iptv": self.on_iptv,
                    "on_iptv_list_configuration": self.on_iptv_list_configuration,
                    "on_play_stream": self.on_play_stream,
                    "on_player_play": self.on_player_play,
                    "on_player_stop": self.on_player_stop,
                    "on_player_previous": self.on_player_previous,
                    "on_player_next": self.on_player_next,
                    "on_player_close": self.on_player_close,
                    "on_player_press": self.on_player_press,
                    "on_full_screen": self.on_full_screen,
                    "on_drawing_area_realize": self.on_drawing_area_realize,
                    "on_player_drawing_area_draw": self.on_player_drawing_area_draw,
                    "on_main_window_state": self.on_main_window_state,
                    "on_remove_all_unavailable": self.on_remove_all_unavailable,
                    "on_new_bouquet": self.on_new_bouquet,
                    "on_bouquets_edit": self.on_bouquets_edit,
                    "on_create_bouquet_for_current_satellite": self.on_create_bouquet_for_current_satellite,
                    "on_create_bouquet_for_each_satellite": self.on_create_bouquet_for_each_satellite,
                    "on_create_bouquet_for_current_package": self.on_create_bouquet_for_current_package,
                    "on_create_bouquet_for_each_package": self.on_create_bouquet_for_each_package,
                    "on_create_bouquet_for_current_type": self.on_create_bouquet_for_current_type,
                    "on_create_bouquet_for_each_type": self.on_create_bouquet_for_each_type}

        self._options = get_config()
        self._profile = self._options.get("profile")
        os.makedirs(os.path.dirname(self._options.get(self._profile).get("data_dir_path")), exist_ok=True)
        # Used for copy/paste. When adding the previous data will not be deleted.
        # Clearing only after the insertion!
        self._rows_buffer = []
        self._bouquets_buffer = []
        self._services = {}
        self._bouquets = {}
        # For bouquets with different names of services in bouquet and main list
        self._extra_bouquets = {}
        self._picons = {}
        self._blacklist = set()
        self._current_bq_name = None
        self._bq_selected = ""  # Current selected bouquet
        # Current satellite positions in the services list
        self._sat_positions = []
        # Player
        self._player = None
        self._full_screen = False
        self._drawing_area_xid = None
        # http api
        self._http_api = None
        self._monitor_signal = False
        # Colors
        self._use_colors = False
        self._NEW_COLOR = None  # Color for new services in the main list
        self._EXTRA_COLOR = None  # Color for services with a extra name for the bouquet

        builder = Gtk.Builder()
        builder.set_translation_domain("demon-editor")
        builder.add_from_file(UI_RESOURCES_PATH + "main_window.glade")
        builder.connect_signals(handlers)
        self._main_window = builder.get_object("main_window")
        main_window_size = self._options.get("window_size", None)
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
        self._player_drawing_area = builder.get_object("player_drawing_area")
        self._player_box = builder.get_object("player_box")
        self._player_tool_bar = builder.get_object("player_tool_bar")
        self._player_prev_button = builder.get_object("player_prev_button")
        self._player_next_button = builder.get_object("player_next_button")
        self._status_bar_box = builder.get_object("status_bar_box")
        self._services_main_box = builder.get_object("services_main_box")
        self._bouquets_main_box = builder.get_object("bouquets_main_box")
        # Enabling events for the drawing area
        self._player_drawing_area.set_events(Gdk.ModifierType.BUTTON1_MASK)
        self._player_frame = builder.get_object("player_frame")
        self._header_bar = builder.get_object("header_bar")
        self._bq_name_label = builder.get_object("bq_name_label")
        # Status bar
        self._ip_label = builder.get_object("ip_label")
        self._ip_label.set_text(self._options.get(self._profile).get("host"))
        self._receiver_info_box = builder.get_object("receiver_info_box")
        self._receiver_info_label = builder.get_object("receiver_info_label")
        self._signal_box = builder.get_object("signal_box")
        self._service_name_label = builder.get_object("service_name_label")
        self._signal_level_bar = builder.get_object("signal_level_bar")
        # Dynamically active elements depending on the selected view
        self._tool_elements = {k: builder.get_object(k) for k in self._DYNAMIC_ELEMENTS}
        self._cas_label = builder.get_object("cas_label")
        self._fav_count_label = builder.get_object("fav_count_label")
        self._bouquets_count_label = builder.get_object("bouquets_count_label")
        self._tv_count_label = builder.get_object("tv_count_label")
        self._radio_count_label = builder.get_object("radio_count_label")
        self._data_count_label = builder.get_object("data_count_label")
        # Force ctrl press event for view. Multiple selections in lists only with Space key(as in file managers)!!!
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
        # Search
        self._search_bar = builder.get_object("search_bar")
        self._search_provider = SearchProvider((self._services_view, self._fav_view, self._bouquets_view),
                                               builder.get_object("search_down_button"),
                                               builder.get_object("search_up_button"))

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.update_profile_label()
        self.init_drag_and_drop()
        self.init_colors()
        self.init_http_api()

    def do_activate(self):
        self._main_window.set_application(self)
        self._main_window.set_wmclass("DemonEditor", "DemonEditor")
        self._main_window.present()

    def do_shutdown(self):
        """  Performs shutdown tasks """
        write_config(self._options)  # storing current config
        if self._player:
            self._player.release()
        Gtk.Application.do_shutdown(self)

    def init_drag_and_drop(self):
        """ Enable drag-and-drop """
        target = []
        bq_target = []
        self._services_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.COPY)
        self._fav_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target,
                                                Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._fav_view.enable_model_drag_dest(target, Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._bouquets_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, bq_target,
                                                     Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._bouquets_view.enable_model_drag_dest(bq_target, Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._fav_view.drag_dest_set_target_list(None)
        self._fav_view.drag_source_set_target_list(None)
        self._fav_view.drag_dest_add_text_targets()
        self._fav_view.drag_source_add_text_targets()
        self._services_view.drag_source_set_target_list(None)
        self._services_view.drag_source_add_text_targets()
        self._bouquets_view.drag_dest_set_target_list(None)
        self._bouquets_view.drag_source_set_target_list(None)
        self._bouquets_view.drag_dest_add_text_targets()
        self._bouquets_view.drag_source_add_text_targets()

    def init_colors(self, update=False):
        """ Initialisation of background colors for the services.

            If update=False - first call on program start, else - after options changes!
        """
        profile = Profile(self._profile)
        if profile is Profile.ENIGMA_2:
            opts = self._options.get(self._profile)
            self._use_colors = opts.get("use_colors", False)
            if self._use_colors:
                new_rgb = Gdk.RGBA()
                extra_rgb = Gdk.RGBA()
                new_rgb = new_rgb if new_rgb.parse(opts.get("new_color", NEW_COLOR)) else None
                extra_rgb = extra_rgb if extra_rgb.parse(opts.get("extra_color", EXTRA_COLOR)) else None
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
        event.state |= Gdk.ModifierType.CONTROL_MASK

    @run_idle
    def on_close_app(self, *args):
        self.quit()

    def on_resize(self, window):
        """ Stores new size properties for app window after resize """
        self._options["window_size"] = window.get_size()

    @run_idle
    def on_about_app(self, item):
        show_dialog(DialogType.ABOUT, self._main_window)

    @run_idle
    def move_items(self, key):
        """ Move items in fav or bouquets tree view """
        if self._services_view.is_focus():
            return
        move_items(key, self._fav_view if self._fav_view.is_focus() else self._bouquets_view)

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
        self.on_view_focus(view, None)

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

        if model.get_name() == self._FAV_LIST_NAME:
            self.update_fav_num_column(model)

        self._rows_buffer.clear()

    def bouquet_paste(self, selection):
        model, paths = selection.get_selected_rows()
        if len(paths) > 1:
            show_dialog(DialogType.ERROR, self._main_window, "Please, select only one item!")
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

        if model_name == self._FAV_LIST_NAME:
            next(self.remove_favs(itrs, model), False)
        elif model_name == self._BOUQUETS_LIST_NAME:
            self.delete_bouquets(itrs, model)
        elif model_name == self._SERVICE_LIST_NAME:
            next(self.delete_services(itrs, model, rows), False)

        self.on_view_focus(view, None)

        return rows

    def remove_favs(self, itrs, model):
        """ Deleting bouquet services """
        if self._bq_selected:
            fav_bouquet = self._bouquets.get(self._bq_selected, None)
            if fav_bouquet:
                for itr in itrs:
                    del fav_bouquet[int(model.get_path(itr)[0])]
                    self._fav_model.remove(itr)
                self.update_fav_num_column(model)
        yield True

    def delete_services(self, itrs, model, rows):
        """ Deleting services """
        srv_itrs = [self._services_model_filter.convert_iter_to_child_iter(
            model.convert_iter_to_child_iter(itr)) for itr in itrs]
        for s_itr in srv_itrs:
            self._services_model.remove(s_itr)

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
        yield True

    def delete_bouquets(self, itrs, model):
        """ Deleting bouquets """
        if len(itrs) == 1 and len(model.get_path(itrs[0])) < 2:
            show_dialog(DialogType.ERROR, self._main_window, "This item is not allowed to be removed!")
            return

        for itr in itrs:
            if len(model.get_path(itr)) < 2:
                continue

            self._fav_model.clear()
            self._bouquets_model.remove(itr)

    # ***************** ####### *********************#

    def get_bouquet_file_name(self, bouquet):
        bouquet_file_name = "{}userbouquet.{}.{}".format(self._options.get(self._profile).get("data_dir_path"),
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
            self._current_bq_name = response

            if model.iter_n_children(itr):  # parent
                ch_itr = model.insert(itr, 0, bq)
                scroll_to(model.get_path(ch_itr), view, paths)
            else:
                p_itr = model.iter_parent(itr)
                it = model.insert(p_itr, int(model.get_path(itr)[1]) + 1, bq) if p_itr else model.append(itr, bq)
                scroll_to(model.get_path(it), view, paths)
            self._bouquets[key] = []

    def on_header_edit(self, item):
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
        for index, row in enumerate(model):
            row[0] = index + 1
        yield True

    def update_bouquet_list(self):
        """ Update bouquet after move items """
        if self._bq_selected:
            fav_bouquet = self._bouquets[self._bq_selected]
            fav_bouquet.clear()
            for row in self._fav_model:
                fav_bouquet.append(row[Column.FAV_ID])

    # ***************** Drag-and-drop *********************#

    def on_view_drag_begin(self, view, context):
        """ Selects a row under the cursor in the view at the dragging beginning. """
        selection = view.get_selection()
        if selection.count_selected_rows() > 1:
            view.do_toggle_cursor_row(view)

    def on_view_drag_data_get(self, view, drag_context, data, info, time):
        selection = self.get_selection(view)
        if selection:
            data.set_text(selection, -1)

    def on_view_drag_data_received(self, view, drag_context, x, y, data, info, time):
        self.receive_selection(view=view, drop_info=view.get_dest_row_at_pos(x, y), data=data.get_text())
        return False

    def on_bq_view_drag_data_received(self, view, drag_context, x, y, data, info, time):
        model_name, model = get_model_data(view)
        drop_info = view.get_dest_row_at_pos(x, y)
        data = data.get_text()
        if not data:
            return
        itr_str, sep, source = data.partition("::::")
        if source != self._BOUQUETS_LIST_NAME:
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
                    if p_itr and model.get_path(p_itr)[0] == p_path:
                        top_iter = model.move_before(itr, top_iter)
                    else:
                        model.insert(parent_itr, model.get_path(top_iter)[1], model[itr][:])
                        to_del.append(itr)
            elif not model.iter_has_child(top_iter):
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
            itr_str, sep, source = data.partition("::::")
            if source == self._BOUQUETS_LIST_NAME:
                return

            bq_selected = self.check_bouquet_selection()
            if not bq_selected:
                return

            model = get_base_model(view.get_model())
            dest_index = 0
            if drop_info:
                path, position = drop_info
                dest_iter = model.get_iter(path)
                if dest_iter:
                    dest_index = model.get_value(dest_iter, 0)
            fav_bouquet = self._bouquets[bq_selected]
            itrs = itr_str.split(",")

            if source == self._SERVICE_LIST_NAME:
                ext_model = self._services_view.get_model()
                ext_itrs = [ext_model.get_iter_from_string(itr) for itr in itrs]
                ext_rows = [ext_model[ext_itr][:] for ext_itr in ext_itrs]
                dest_index -= 1
                for ext_row in ext_rows:
                    dest_index += 1
                    fav_id = ext_row[Column.SRV_FAV_ID]
                    ch = self._services[fav_id]
                    model.insert(dest_index, (0, ch.coded, ch.service, ch.locked, ch.hide, ch.service_type, ch.pos,
                                              ch.fav_id, self._picons.get(ch.picon_id, None), None, None))
                    fav_bouquet.insert(dest_index, ch.fav_id)
            elif source == self._FAV_LIST_NAME:
                in_itrs = [model.get_iter_from_string(itr) for itr in itrs]
                in_rows = [model[in_itr][:] for in_itr in in_itrs]
                for row in in_rows:
                    model.insert(dest_index, row)
                    fav_bouquet.insert(dest_index, row[Column.FAV_ID])
                for in_itr in in_itrs:
                    del fav_bouquet[int(model.get_path(in_itr)[0])]
                    model.remove(in_itr)
            self.update_fav_num_column(model)
        except ValueError as e:
            show_dialog(DialogType.ERROR, self._main_window, str(e))

    def on_view_press(self, view, event):
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_PRIMARY:
            name, model = get_model_data(view)
            self.delete_views_selection(name)

    def delete_views_selection(self, name):
        if name == self._SERVICE_LIST_NAME:
            self.delete_selection(self._fav_view)
        elif name == self._FAV_LIST_NAME:
            self.delete_selection(self._services_view)
        elif name == self._BOUQUETS_LIST_NAME:
            self.delete_selection(self._services_view, self._fav_view)

    def on_view_popup_menu(self, menu, event):
        """ Shows popup menu for any view """
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
            name = Gtk.Buildable.get_name(menu)
            if name == "services_popup_menu":
                self.delete_selection(self._fav_view, self._bouquets_view)
                self.on_view_focus(self._services_view, None)
            elif name == "fav_popup_menu":
                self.delete_selection(self._services_view, self._bouquets_view)
                self.on_view_focus(self._fav_view, None)
            elif name == "bouquets_popup_menu":
                self.delete_selection(self._services_view, self._fav_view)
                self.on_view_focus(self._bouquets_view, None)

            menu.popup(None, None, None, None, event.button, event.time)
            return True

    def on_popover_release(self, menu, event):
        """ Hides popover after mouse click. Used if element of Popover menu is Gtk.Button! """
        menu.hide()

    @run_idle
    def on_satellite_editor_show(self, model):
        """ Shows satellites editor dialog """
        show_satellites_dialog(self._main_window, self._options.get(self._profile))

    @run_idle
    def on_data_open(self, model):
        response = show_dialog(DialogType.CHOOSER, self._main_window, options=self._options.get(self._profile))
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return
        self.open_data(response)

    def open_data(self, data_path=None):
        """ Opening data and fill views. """
        self._wait_dialog.show()
        self.clear_current_data()
        GLib.idle_add(self.append_data, data_path, priority=GLib.PRIORITY_LOW)

    def append_data(self, data_path):
        profile = Profile(self._profile)
        data_path = self._options.get(self._profile).get("data_dir_path") if data_path is None else data_path

        try:
            black_list = get_blacklist(data_path)
            bouquets = get_bouquets(data_path, Profile(self._profile))
            services = get_services(data_path, profile, self.get_format_version() if profile is Profile.ENIGMA_2 else 0)
            update_picons_data(self._options.get(self._profile).get("picons_dir_path"), self._picons)
        except FileNotFoundError as e:
            self._wait_dialog.hide()
            show_dialog(DialogType.ERROR, self._main_window, getattr(e, "message", str(e)) + "\n\n" +
                        get_message("Please, download files from receiver or setup your path for read data!"))
        except SyntaxError as e:
            self._wait_dialog.hide()
            show_dialog(DialogType.ERROR, self._main_window, str(e))
        except Exception as e:
            self._wait_dialog.hide()
            log("Append services error: " + str(e))
            show_dialog(DialogType.ERROR, self._main_window, "Reading data error!\n" + str(e))
        else:
            self.append_blacklist(black_list)
            self.append_bouquets(bouquets)
            self.append_services(services)
            self.update_sat_positions()

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
        name, bt_type, locked, hidden = bq.name, bq.type, bq.locked, bq.hidden
        self._bouquets_model.append(parent, [name, locked, hidden, bt_type])
        bq_id = "{}:{}".format(name, bt_type)
        services = []
        extra_services = {}  # for services with different names in bouquet and main list
        agr = [None] * 7
        for srv in bq.services:
            fav_id = srv.data
            # IPTV and MARKER services
            s_type = srv.type
            if s_type is BqServiceType.MARKER or s_type is BqServiceType.IPTV:
                icon = None
                picon_id = None
                if s_type is BqServiceType.IPTV:
                    icon = IPTV_ICON
                    id_data = fav_id.lstrip().split(":")
                    picon_id = "{}_{}_{}_{}_{}_{}_{}_{}_{}_{}.png".format(*id_data[0:10])
                srv = Service(*agr[0:2], icon, srv.name, *agr[0:3], s_type.name, self._picons.get(picon_id, None),
                              picon_id, *agr, srv.num, fav_id, None)
                self._services[fav_id] = srv
            elif srv.name:
                extra_services[fav_id] = srv.name
            services.append(fav_id)

        self._bouquets[bq_id] = services
        if extra_services:
            self._extra_bouquets[bq_id] = extra_services

    def append_services(self, services):
        for srv in services:
            #  adding channels to dict with fav_id as keys
            self._services[srv.fav_id] = srv
        self.update_services_counts(len(self._services.values()))
        gen = self.append_services_data(services)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def append_services_data(self, services):
        for srv in services:
            tooltip, background = None, None
            if self._use_colors:
                flags = srv.flags_cas
                if flags:
                    f_flags = list(filter(lambda x: x.startswith("f:"), flags.split(",")))
                    if f_flags and Flag.is_new(int(f_flags[0][2:])):
                        background = self._NEW_COLOR

            s = srv + (tooltip, background)
            itr = self._services_model.append(s)
            self._services_model.set_value(itr, Column.SRV_PICON, self._picons.get(srv.picon_id, None))
            yield True
        self._wait_dialog.hide()

    def clear_current_data(self):
        """ Clearing current data from lists """
        self._bouquets_model.clear()
        self._fav_model.clear()
        self._services_model.clear()
        self._blacklist.clear()
        self._services.clear()
        self._rows_buffer.clear()
        self._bouquets.clear()
        self._extra_bouquets.clear()
        self._current_bq_name = None
        self._bq_name_label.set_text("")
        self.init_sat_positions()

    @run_idle
    def on_data_save(self, *args):
        if len(self._bouquets_model) == 0:
            show_dialog(DialogType.ERROR, self._main_window, get_message("No data to save!"))
            return

        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return

        profile = Profile(self._profile)
        options = self._options.get(self._profile)
        path = options.get("data_dir_path")
        backup_path = options.get("backup_dir_path", path + "backup/")
        # Backup data or clearing data path
        backup_data(path, backup_path) if options.get("backup_before_save", True) else clear_data_path(path)

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
                    ex_s = self._extra_bouquets.get(bq_id)
                    bq_s = list(filter(None, [self._services.get(f_id, None) for f_id in favs]))
                    if profile is Profile.ENIGMA_2:
                        bq_s = list(map(lambda s: s._replace(service=ex_s.get(s.fav_id, None) if ex_s else None), bq_s))
                    bq = Bouquet(bq_name, bq_type, bq_s, locked, hidden)
                    bqs.append(bq)
            if len(b_path) == 1:
                bouquets.append(Bouquets(*model.get(itr, Column.BQ_NAME, Column.BQ_TYPE), bqs if bqs else []))

        profile = Profile(self._profile)
        # Getting bouquets
        self._bouquets_view.get_model().foreach(parse_bouquets)
        write_bouquets(path, bouquets, profile)
        # Getting services
        services_model = get_base_model(self._services_view.get_model())
        services = [Service(*row[: Column.SRV_TOOLTIP]) for row in services_model]
        write_services(path, services, profile, self.get_format_version() if profile is Profile.ENIGMA_2 else 0)
        # removing bouquet files
        if profile is Profile.ENIGMA_2:
            # blacklist
            write_blacklist(path, self._blacklist)

    def on_new_configuration(self, item):
        """ Creates new empty configuration """
        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return

        self.clear_current_data()

        profile = Profile(self._profile)
        if profile is Profile.ENIGMA_2:
            parent = self._bouquets_model.append(None, ["Favourites (TV)", None, None, BqType.TV.value])
            self.append_bouquet(Bouquet("Favourites (TV)", BqType.TV.value, [], None, None), parent)
            parent = self._bouquets_model.append(None, ["Favourites (Radio)", None, None, BqType.RADIO.value])
            self.append_bouquet(Bouquet("Favourites (Radio)", BqType.RADIO.value, [], None, None), parent)
        elif profile is Profile.NEUTRINO_MP:
            self._bouquets_model.append(None, ["Providers", None, None, BqType.BOUQUET.value])
            self._bouquets_model.append(None, ["FAV", None, None, BqType.TV.value])
            self._bouquets_model.append(None, ["WEBTV", None, None, BqType.WEBTV.value])

    def on_services_selection(self, model, path, column):
        self.update_service_bar(model, path)

    def update_service_bar(self, model, path):
        def_val = "Unknown"
        cas = model.get_value(model.get_iter(path), Column.SRV_CAS_FLAGS)
        if not cas:
            return
        cas_values = list(filter(lambda val: val.startswith("C:"), cas.split(",")))
        self._cas_label.set_text(",".join(map(str, sorted(set(CAS.get(val, def_val) for val in cas_values)))))

    def on_bouquets_selection(self, model, path, column):
        self._current_bq_name = model[path][0] if len(path) > 1 else None
        self._bq_name_label.set_text(self._current_bq_name if self._current_bq_name else "")
        self._fav_model.clear()

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
            next(self.update_bouquet_services(model, path), False)

    def update_bouquet_services(self, model, path, bq_key=None):
        """ Updates list of bouquet services """
        tree_iter = None
        if path:
            tree_iter = model.get_iter(path)

        key = bq_key if bq_key else "{}:{}".format(*model.get(tree_iter, Column.BQ_NAME, Column.BQ_TYPE))
        services = self._bouquets.get(key, None)
        ex_services = self._extra_bouquets.get(key, None)
        if not services:
            return

        for num, srv_id in enumerate(services):
            srv = self._services.get(srv_id, None)
            ex_srv_name = None
            if ex_services:
                ex_srv_name = ex_services.get(srv_id)
            if srv:
                tooltip, background = None, self._EXTRA_COLOR if self._use_colors and ex_srv_name else None
                self._fav_model.append((num + 1, srv.coded, ex_srv_name if ex_srv_name else srv.service, srv.locked,
                                        srv.hide, srv.service_type, srv.pos, srv.fav_id,
                                        self._picons.get(srv.picon_id, None), tooltip, background))
        yield True

    def check_bouquet_selection(self):
        """ checks and returns bouquet if selected """
        if not self._bq_selected:
            show_dialog(DialogType.ERROR, self._main_window, "Error. No bouquet is selected!")
            return

        if Profile(self._profile) is Profile.NEUTRINO_MP and self._bq_selected.endswith(BqType.WEBTV.value):
            show_dialog(DialogType.ERROR, self._main_window, "Operation not allowed in this context!")
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

    @run_idle
    def on_preferences(self, item):
        response = show_settings_dialog(self._main_window, self._options)
        if response != Gtk.ResponseType.CANCEL:
            profile = self._options.get("profile")
            self._ip_label.set_text(self._options.get(profile).get("host"))

            if profile != self._profile:
                self._profile = profile
                self.clear_current_data()
                self.update_services_counts()

            self.update_profile_label()
            self.init_colors(True)
            self.init_http_api()

    def on_tree_view_key_press(self, view, event):
        """  Handling  keystrokes on press """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        model_name, model = get_model_data(view)

        if ctrl and key in MOVE_KEYS:
            self.move_items(key)
        elif ctrl and key is KeyboardKey.C:
            if model_name == self._SERVICE_LIST_NAME:
                self.on_copy(view, ViewTarget.FAV)
            elif model_name == self._FAV_LIST_NAME:
                self.on_copy(view, ViewTarget.SERVICES)
            else:
                self.on_copy(view, ViewTarget.BOUQUET)
        elif ctrl and key is KeyboardKey.X:
            if model_name == self._FAV_LIST_NAME:
                self.on_cut(view, ViewTarget.FAV)
            elif model_name == self._BOUQUETS_LIST_NAME:
                self.on_cut(view, ViewTarget.BOUQUET)
        elif ctrl and key is KeyboardKey.V:
            if model_name == self._FAV_LIST_NAME:
                self.on_paste(view, ViewTarget.FAV)
            elif model_name == self._BOUQUETS_LIST_NAME:
                self.on_paste(view, ViewTarget.BOUQUET)
        elif key is KeyboardKey.DELETE:
            self.on_delete(view)

    def on_tree_view_key_release(self, view, event):
        """  Handling  keystrokes on release """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        model_name, model = get_model_data(view)

        if ctrl and key is KeyboardKey.INSERT:
            # Move items from app to fav list
            if model_name == self._SERVICE_LIST_NAME:
                self.on_to_fav_copy(view)
            elif model_name == self._BOUQUETS_LIST_NAME:
                self.on_new_bouquet(view)
        elif ctrl and key is KeyboardKey.BACK_SPACE and model_name == self._SERVICE_LIST_NAME:
            self.on_to_fav_end_copy(view)
        elif ctrl and key is KeyboardKey.S:
            self.on_data_save()
        elif ctrl and key is KeyboardKey.L:
            self.on_locked(None)
        elif ctrl and key is KeyboardKey.H:
            self.on_hide(None)
        elif ctrl and key is KeyboardKey.R or key is KeyboardKey.F2:
            self.on_rename(view)
        elif ctrl and key is KeyboardKey.E:
            if model_name == self._BOUQUETS_LIST_NAME:
                self.on_rename(view)
                return
            self.on_service_edit(view)
        elif key is KeyboardKey.LEFT or key is KeyboardKey.RIGHT:
            view.do_unselect_all(view)
        elif ctrl and model_name == self._FAV_LIST_NAME:
            if key is KeyboardKey.P:
                self.on_play_stream()
            if key is KeyboardKey.W:
                self.on_zap(self.on_watch)
            if key is KeyboardKey.Z:
                self.on_zap()
            elif key is KeyboardKey.CTRL_L or key is KeyboardKey.CTRL_R:
                self.update_fav_num_column(model)
                self.update_bouquet_list()

    def on_download(self, item):
        DownloadDialog(transient=self._main_window,
                       properties=self._options,
                       open_data_callback=self.open_data,
                       profile=Profile(self._profile)).show()

    def on_view_focus(self, view, focus_event):
        profile = Profile(self._profile)
        model_name, model = get_model_data(view)
        not_empty = len(model) > 0  # if  > 0 model has items

        if model_name == self._BOUQUETS_LIST_NAME:
            for elem in self._tool_elements:
                self._tool_elements[elem].set_sensitive(False)
            for elem in self._BOUQUET_ELEMENTS:
                self._tool_elements[elem].set_sensitive(not_empty)
                if elem == "bouquets_paste_popup_item":
                    self._tool_elements[elem].set_sensitive(not_empty and self._bouquets_buffer)
            if profile is Profile.NEUTRINO_MP:
                for elem in self._LOCK_HIDE_ELEMENTS:
                    self._tool_elements[elem].set_sensitive(not_empty)
        else:
            is_service = model_name == self._SERVICE_LIST_NAME

            for elem in self._FAV_ELEMENTS:
                if elem in ("paste_tool_button", "fav_paste_popup_item"):
                    self._tool_elements[elem].set_sensitive(not is_service and self._rows_buffer)
                elif elem in self._FAV_ENIGMA_ELEMENTS:
                    if profile is Profile.ENIGMA_2:
                        self._tool_elements[elem].set_sensitive(self._bq_selected and not is_service)
                elif elem in self._FAV_IPTV_ELEMENTS:
                    self._tool_elements[elem].set_sensitive(self._bq_selected and not is_service)
                else:
                    self._tool_elements[elem].set_sensitive(not_empty and not is_service)
            for elem in self._SERVICE_ELEMENTS:
                self._tool_elements[elem].set_sensitive(not_empty and is_service)
            for elem in self._BOUQUET_ELEMENTS:
                self._tool_elements[elem].set_sensitive(False)
            for elem in self._LOCK_HIDE_ELEMENTS:
                self._tool_elements[elem].set_sensitive(not_empty and profile is Profile.ENIGMA_2)

        for elem in self._COMMONS_ELEMENTS:
            self._tool_elements[elem].set_sensitive(not_empty)

    def on_hide(self, item):
        self.set_service_flags(Flag.HIDE)

    def on_locked(self, item):
        self.set_service_flags(Flag.LOCK)

    def set_service_flags(self, flag):
        profile = Profile(self._profile)

        if profile is Profile.ENIGMA_2:
            set_flags(flag, self._services_view, self._fav_view, self._services, self._blacklist)
        elif profile is Profile.NEUTRINO_MP and self._bq_selected:
            model, paths = self._bouquets_view.get_selection().get_selected_rows()
            itr = model.get_iter(paths[0])
            value = model.get_value(itr, 1 if flag is Flag.LOCK else 2)
            value = None if value else LOCKED_ICON if flag is Flag.LOCK else HIDE_ICON
            model.set_value(itr, 1 if flag is Flag.LOCK else 2, value)

    @run_idle
    def on_model_changed(self, model, path, itr=None):
        model_name = model.get_name()

        if model_name == self._FAV_LIST_NAME:
            self._fav_count_label.set_text(str(len(model)))
        elif model_name == self._SERVICE_LIST_NAME:
            self.update_services_counts(len(model))
        elif model_name == self._BOUQUETS_LIST_NAME:
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

    def on_insert_marker(self, view):
        """ Inserts marker into bouquet services list. """
        insert_marker(view, self._bouquets, self._bq_selected, self._services, self._main_window)
        self.update_fav_num_column(self._fav_model)

    def on_fav_press(self, menu, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.on_play_stream()
            self.on_zap()
        else:
            return self.on_view_popup_menu(menu, event)

    # ***************** IPTV *********************#

    def on_iptv(self, item):
        response = IptvDialog(self._main_window,
                              self._fav_view,
                              self._services,
                              self._bouquets.get(self._bq_selected, None),
                              Profile(self._profile),
                              Action.ADD).show()
        if response != Gtk.ResponseType.CANCEL:
            self.update_fav_num_column(self._fav_model)

    @run_idle
    def on_iptv_list_configuration(self, item):
        profile = Profile(self._profile)
        if profile is Profile.NEUTRINO_MP:
            show_dialog(DialogType.ERROR, transient=self._main_window, text="Neutrino at the moment not supported!")
            return

        iptv_rows = list(filter(lambda r: r[Column.FAV_TYPE] == BqServiceType.IPTV.value, self._fav_model))
        if not iptv_rows:
            show_dialog(DialogType.ERROR, self._main_window, "This list does not contains IPTV streams!")
            return

        if not self._bq_selected:
            return

        bouquet = self._bouquets.get(self._bq_selected, [])
        IptvListConfigurationDialog(self._main_window, self._services, iptv_rows, bouquet, profile).show()

    @run_idle
    def on_remove_all_unavailable(self, item):
        iptv_rows = list(filter(lambda r: r[5] == BqServiceType.IPTV.value, self._fav_model))
        if not iptv_rows:
            show_dialog(DialogType.ERROR, self._main_window, "This list does not contains IPTV streams!")
            return

        if not self._bq_selected:
            return

        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return

        fav_bqt = self._bouquets.get(self._bq_selected, None)
        prf = Profile(self._profile)
        response = SearchUnavailableDialog(self._main_window, self._fav_model, fav_bqt, iptv_rows, prf).show()
        if response:
            next(self.remove_favs(response, self._fav_model), False)

    # ***************** Import  ********************#

    def on_import_m3u(self, item):
        """ Imports iptv from m3u files. """
        response = get_chooser_dialog(self._main_window, self._options.get(self._profile), "*.m3u", "m3u files")
        if response == Gtk.ResponseType.CANCEL:
            return

        if not str(response).endswith("m3u"):
            show_dialog(DialogType.ERROR, self._main_window, text="No m3u file is selected!")
            return

        channels = parse_m3u(response, Profile(self._profile))

        if channels and self._bq_selected:
            bq_services = self._bouquets.get(self._bq_selected)
            self._fav_model.clear()
            for ch in channels:
                self._services[ch.fav_id] = ch
                bq_services.append(ch.fav_id)
            next(self.update_bouquet_services(self._fav_model, None, self._bq_selected), False)

    def on_import_bouquet(self, item):
        profile = Profile(self._profile)
        if profile is not Profile.ENIGMA_2:
            show_dialog(DialogType.ERROR, transient=self._main_window, text="Not implemented yet!")
            return

        model, paths = self._bouquets_view.get_selection().get_selected_rows()
        if not paths:
            show_dialog(DialogType.ERROR, self._main_window, "No selected item!")
            return

        itr = model.get_iter(paths[0])
        pat = ".{}".format(model.get(itr, Column.BQ_TYPE)[0])
        f_pattern = "userbouquet.*{}".format(pat)

        response = get_chooser_dialog(self._main_window, self._options.get(self._profile), f_pattern, "bouquet files")
        if response == Gtk.ResponseType.CANCEL:
            return

        if not str(response).endswith(pat):
            show_dialog(DialogType.ERROR, self._main_window, text="No bouquet file is selected!")
            return

        path, sep, f_name = response.rpartition("userbouquet.")
        name, sep, suf = f_name.rpartition(".")
        bq = get_bouquet(path, name, suf)
        bouquet = Bouquet(name=bq[0], type=BqType(suf).value, services=bq[1], locked=None, hidden=None)

        s_values = self._services
        imported = list(filter(lambda x: x.data in s_values or x.type is BqServiceType.IPTV, bouquet.services))
        if len(imported) == 0:
            show_dialog(DialogType.ERROR, self._main_window,
                        text="The main list does not contain services for this bouquet!")
            return

        if model.iter_n_children(itr):
            self.append_bouquet(bouquet, itr)
        else:
            p_itr = model.iter_parent(itr)
            self.append_bouquet(bouquet, p_itr)

    def on_import_bouquets(self, item):
        response = show_dialog(DialogType.CHOOSER, self._main_window, options=self._options.get(self._profile))
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        ImportDialog(self._main_window,
                     response,
                     Profile(self._profile),
                     self._services.keys(),
                     self.append_services,
                     self.append_bouquets).show()

    # ***************** Backup  ********************#

    def on_backup_tool_show(self, item):
        """ Shows backup tool dialog """
        BackupDialog(self._main_window,
                     self._options,
                     Profile(self._profile),
                     self.open_data).show()

    # ***************** Player *********************#

    def on_play_stream(self, item=None):
        self.on_player_play()

    @run_idle
    def on_player_play(self, item=None):
        url = self.get_stream_url()
        self.update_player_buttons()
        if not url:
            return
        self.play(url)

    def play(self, url):
        if not self._player:
            try:
                self._player = Player()
            except (NameError, AttributeError):
                show_dialog(DialogType.ERROR, self._main_window, "No VLC is found. Check that it is installed!")
                return
            else:
                if self._drawing_area_xid:
                    self._player.set_xwindow(self._drawing_area_xid)
                self._services_main_box.set_visible(False)
                self._bouquets_main_box.set_visible(False)
                w, h = self._main_window.get_size()
                self._player_box.set_size_request(w * 0.6, -1)

        self._player_box.set_visible(True)
        GLib.idle_add(self._player.play, url, priority=GLib.PRIORITY_LOW)

    def get_stream_url(self):
        path, column = self._fav_view.get_cursor()
        if path:
            row = self._fav_model[path][:]
            if row[5] == BqServiceType.IPTV.name:
                return get_iptv_url(row, Profile(self._profile))

    def on_player_stop(self, item=None):
        if self._player:
            self._player.stop()

    def on_player_previous(self, item):
        if self._fav_view.do_move_cursor(self._fav_view, Gtk.MovementStep.DISPLAY_LINES, -1):
            self.on_play_stream()

    def on_player_next(self, item):
        if self._fav_view.do_move_cursor(self._fav_view, Gtk.MovementStep.DISPLAY_LINES, 1):
            self.on_play_stream()

    def update_player_buttons(self):
        if self._player:
            path, column = self._fav_view.get_cursor()
            current_index = path[0]
            self._player_prev_button.set_sensitive(current_index != 0)
            self._player_next_button.set_sensitive(len(self._fav_model) != current_index + 1)

    def on_player_close(self, item=None):
        if self._player:
            self._player.release()
            self._player = None
        GLib.idle_add(self._player_box.set_visible, False, priority=GLib.PRIORITY_LOW)
        GLib.idle_add(self._services_main_box.set_visible, True, priority=GLib.PRIORITY_LOW)
        GLib.idle_add(self._bouquets_main_box.set_visible, True, priority=GLib.PRIORITY_LOW)

    def on_drawing_area_realize(self, widget):
        self._drawing_area_xid = widget.get_window().get_xid()
        self._player.set_xwindow(self._drawing_area_xid)

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
        self._main_window.fullscreen() if self._full_screen else self._main_window.unfullscreen()

    def on_main_window_state(self, window, event):
        full = not event.new_window_state & Gdk.WindowState.FULLSCREEN
        self._main_data_box.set_visible(full)
        self._status_bar_box.set_visible(full)
        self._player_tool_bar.set_visible(full)

    # ************************ HTTP API ****************************#
    @run_task
    def init_http_api(self):
        if self._http_api:
            self._http_api.close()
            self._http_api = None

        prp = self._options.get(self._profile)
        if prp is Profile.NEUTRINO_MP or not prp.get("http_api_support", False):
            self.update_info_boxes_visible(False)
            return

        self._http_api = http_request(prp.get("host", "127.0.0.1"), prp.get("http_port", "80"),
                                      prp.get("http_user", ""), prp.get("http_password", ""))

        next(self._http_api)
        GLib.timeout_add_seconds(1, self.update_receiver_info)

    @run_idle
    def on_watch(self):
        """ Switch to the channel and watch in the player """
        m3u = self._http_api.send((HttpRequestType.STREAM, None))
        next(self._http_api)
        if m3u:
            url = [s for s in m3u.split("\n") if not s.startswith("#")]
            if url:
                GLib.timeout_add_seconds(1, self.play, url[0])

    @run_idle
    def on_zap(self, callback=None):
        """ Switch(zap) the channel """
        path, column = self._fav_view.get_cursor()
        if not path or not self._http_api:
            return

        if self._player and self._player.is_playing():
            self._player.stop()

        row = self._fav_model[path][:]
        srv = self._services.get(row[Column.FAV_ID], None)
        if srv and srv.transponder:
            ref = srv.picon_id.rstrip(".png").replace("_", ":")

            req = self._http_api.send((HttpRequestType.ZAP, ref))
            next(self._http_api)
            if req and req.get("result", False):
                GLib.timeout_add_seconds(2, self.update_service_info)
                GLib.idle_add(scroll_to, path, self._fav_view)
                if callback is not None:
                    callback()

    @run_task
    def update_receiver_info(self):
        info = self._http_api.send((HttpRequestType.INFO, None))
        next(self._http_api)
        if not info:
            self._http_api.close()
            self._http_api = None
            GLib.idle_add(self.update_info_boxes_visible, False)
            return

        service_info = info.get("service", None)
        res_info = info.get("info", None)
        if res_info:
            image = res_info.get("friendlyimagedistro", "")
            image_ver = res_info.get("imagever", "")
            brand = res_info.get("brand", "")
            model = res_info.get("model", "")
            info_text = "{} {}  Image: {} {}".format(brand, model, image, image_ver)
            GLib.idle_add(self._receiver_info_label.set_text, info_text)
        GLib.idle_add(self._receiver_info_box.set_visible, res_info)

        if service_info:
            GLib.idle_add(self._service_name_label.set_text, service_info.get("name", ""))
            GLib.timeout_add_seconds(2, self.update_signal)
        GLib.idle_add(self._signal_box.set_visible, service_info)

    def update_signal(self):
        sig = self._http_api.send((HttpRequestType.SIGNAL, None))
        next(self._http_api)
        val = sig.get("snr", 0)
        self._signal_level_bar.set_value(val if val else 0)
        self._signal_level_bar.set_visible(val)

        return self._monitor_signal

    def update_service_info(self):
        info = self._http_api.send((HttpRequestType.INFO, None))
        next(self._http_api)
        if info:
            service_info = info.get("service", None)
            if service_info:
                GLib.idle_add(self._service_name_label.set_text, service_info.get("name", ""))
                GLib.timeout_add_seconds(1, self.update_signal)

    # ***************** Filter and search *********************#

    def on_filter_toggled(self, toggle_button: Gtk.ToggleToolButton):
        active = toggle_button.get_active()
        if active:
            self.update_filter_sat_positions()

        self._filter_bar.set_search_mode(active)
        self._filter_bar.set_visible(active)

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
        terrestrial = False
        cable = False

        for srv in self._services.values():
            tr_type = srv.transponder_type
            if tr_type == "s" and srv.pos:
                sat_positions.add(float(srv.pos))
            elif tr_type == "t":
                terrestrial = True
            elif tr_type == "c":
                cable = True

        if terrestrial:
            self._sat_positions.append("T")
        if cable:
            self._sat_positions.append("C")

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
            txt = self._filter_entry.get_text() in str(model.get(itr, Column.SRV_SERVICE, Column.SRV_PACKAGE,
                                                                 Column.SRV_TYPE, Column.SRV_SSID, Column.SRV_FREQ,
                                                                 Column.SRV_RATE, Column.SRV_POL, Column.SRV_FEC,
                                                                 Column.SRV_SYSTEM, Column.SRV_POS))
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

    def on_search_toggled(self, toggle_button: Gtk.ToggleToolButton):
        self._search_bar.set_search_mode(toggle_button.get_active())

    def on_search_down(self, item):
        self._search_provider.on_search_down()

    def on_search_up(self, item):
        self._search_provider.on_search_up()

    @run_with_delay(1)
    def on_search(self, entry):
        self._search_provider.search(entry.get_text())

    # ***************** Editing *********************#

    @run_idle
    def on_service_edit(self, view):
        model, paths = view.get_selection().get_selected_rows()
        if is_only_one_item_selected(paths, self._main_window):
            model_name = get_base_model(model).get_name()
            if model_name == self._FAV_LIST_NAME:
                srv_type = model.get_value(model.get_iter(paths), Column.FAV_TYPE)
                if srv_type == BqServiceType.MARKER.name:
                    return self.on_rename(view)
                elif srv_type == BqServiceType.IPTV.name:
                    return IptvDialog(self._main_window,
                                      self._fav_view,
                                      self._services,
                                      self._bouquets.get(self._bq_selected, None),
                                      Profile(self._profile),
                                      Action.EDIT).show()
                self.on_locate_in_services(view)

            dialog = ServiceDetailsDialog(self._main_window,
                                          self._options,
                                          self._services_view,
                                          self._fav_view,
                                          self._services,
                                          self._bouquets,
                                          self._NEW_COLOR)
            dialog.show()

    def on_services_add_new(self, item):
        dialog = ServiceDetailsDialog(self._main_window,
                                      self._options,
                                      self._services_view,
                                      self._fav_view,
                                      self._services,
                                      self._bouquets,
                                      action=Action.ADD)
        dialog.show()

    def on_bouquets_edit(self, view):
        """ Rename bouquets """
        if not self._bq_selected:
            show_dialog(DialogType.ERROR, self._main_window, "This item is not allowed to edit!")
            return

        model, paths = view.get_selection().get_selected_rows()

        if paths:
            itr = model.get_iter(paths[0])
            bq_name, bq_type = model.get(itr, 0, 3)
            response = show_dialog(DialogType.INPUT, self._main_window, bq_name)
            if response == Gtk.ResponseType.CANCEL:
                return

            model.set_value(itr, 0, response)
            self._bouquets["{}:{}".format(response, bq_type)] = self._bouquets.pop("{}:{}".format(bq_name, bq_type))

    def on_rename(self, view):
        name, model = get_model_data(view)
        if name == self._BOUQUETS_LIST_NAME:
            self.on_bouquets_edit(view)
        elif name == self._FAV_LIST_NAME:
            rename(view, self._main_window, ViewTarget.FAV, service_view=self._services_view,
                   services=self._services)
        elif name == self._SERVICE_LIST_NAME:
            rename(view, self._main_window, ViewTarget.SERVICES, fav_view=self._fav_view, services=self._services)

    def on_rename_for_bouquet(self, item):
        selection = get_selection(self._fav_view, self._main_window)
        if not selection:
            return

        model, paths = selection
        data = model[paths][:]
        cur_name, srv_type, fav_id = data[Column.FAV_SERVICE], data[Column.FAV_TYPE], data[Column.FAV_ID]

        if srv_type == BqServiceType.IPTV.name or srv_type == BqServiceType.MARKER.name:
            show_dialog(DialogType.ERROR, self._main_window, "Not allowed in this context!")
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
            show_dialog(DialogType.ERROR, self._main_window, "No changes required!")
            return
        else:
            if not ex_bq.pop(fav_id, None):
                show_dialog(DialogType.ERROR, self._main_window, "No changes required!")
                return
            if not ex_bq:
                self._extra_bouquets.pop(self._bq_selected, None)

        model.set(model.get_iter(paths), {Column.FAV_SERVICE: srv.service, Column.FAV_TOOLTIP: None,
                                          Column.FAV_BACKGROUND: None})

    def on_locate_in_services(self, view):
        locate_in_services(view, self._services_view, self._main_window)

    # ***************** Picons *********************#

    @run_idle
    def on_picons_loader_show(self, item):
        ids = {}
        if Profile(self._profile) is Profile.ENIGMA_2:
            for r in self._services_model:
                data = r[Column.SRV_PICON_ID].split("_")
                ids["{}:{}:{}".format(data[3], data[5], data[6])] = r[Column.SRV_PICON_ID]

        dialog = PiconsDialog(self._main_window, self._options, ids, self._sat_positions, Profile(self._profile))
        dialog.show()
        self.update_picons()

    @run_task
    def update_picons(self):
        update_picons_data(self._options.get(self._profile).get("picons_dir_path"), self._picons)
        append_picons(self._picons, self._services_model)

    def on_assign_picon(self, view):
        assign_picon(self.get_target_view(view),
                     self._services_view,
                     self._fav_view,
                     self._main_window,
                     self._picons,
                     self._options.get(self._profile),
                     self._services)

    def on_remove_picon(self, view):
        remove_picon(self.get_target_view(view),
                     self._services_view,
                     self._fav_view, self._picons,
                     self._options.get(self._profile))

    def on_reference_picon(self, view):
        """ Copying picon id to clipboard """
        copy_picon_reference(self.get_target_view(view), view, self._services, self._clipboard, self._main_window)

    def get_target_view(self, view):
        return ViewTarget.SERVICES if Gtk.Buildable.get_name(view) == "services_tree_view" else ViewTarget.FAV

    # ***************** Bouquets *********************#

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
                     Profile(self._profile), self.append_bouquet)

    # ***************** Profile label *********************#

    def update_profile_label(self):
        profile = Profile(self._profile)
        if profile is Profile.ENIGMA_2:
            self._header_bar.set_subtitle("{} Enigma2 v.{}".format(get_message("Profile:"), self.get_format_version()))
        elif profile is Profile.NEUTRINO_MP:
            self._header_bar.set_subtitle("{} Neutrino-MP".format(get_message("Profile:")))

    def get_format_version(self):
        return 5 if self._options.get(self._profile).get("v5_support", False) else 4

    @run_idle
    def update_info_boxes_visible(self, visible):
        self._signal_box.set_visible(visible)
        self._receiver_info_box.set_visible(visible)


def start_app():
    app = Application()
    app.run(sys.argv)


if __name__ == "__main__":
    pass

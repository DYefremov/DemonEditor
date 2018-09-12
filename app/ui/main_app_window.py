import os
import shutil

from contextlib import suppress
from functools import lru_cache

from gi.repository import GLib

from app.commons import run_idle, log, run_task, run_with_delay
from app.eparser import get_blacklist, write_blacklist, parse_m3u
from app.eparser import get_services, get_bouquets, write_bouquets, write_services, Bouquets, Bouquet, Service
from app.eparser.ecommons import CAS, Flag
from app.eparser.enigma.bouquets import BqServiceType
from app.eparser.neutrino.bouquets import BqType
from app.properties import get_config, write_config, Profile
from app.tools.media import Player
from .iptv import IptvDialog, SearchUnavailableDialog, IptvListConfigurationDialog
from .search import SearchProvider
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, LOCKED_ICON, HIDE_ICON, IPTV_ICON, MOVE_KEYS
from .dialogs import show_dialog, DialogType, get_chooser_dialog, WaitDialog, get_message
from .download_dialog import show_download_dialog
from .main_helper import edit_marker, insert_marker, move_items, rename, ViewTarget, set_flags, locate_in_services, \
    scroll_to, get_base_model, update_picons_data, copy_picon_reference, assign_picon, remove_picon, \
    is_only_one_item_selected, gen_bouquets, BqGenType, get_iptv_url, append_picons, get_selection
from .picons_downloader import PiconsDialog
from .satellites_dialog import show_satellites_dialog
from .settings_dialog import show_settings_dialog
from .service_details_dialog import ServiceDetailsDialog, Action


class MainAppWindow:
    _TV_TYPES = ("TV", "TV (HD)", "TV (UHD)", "TV (H264)")

    _SERVICE_LIST_NAME = "services_list_store"

    _FAV_LIST_NAME = "fav_list_store"

    _BOUQUETS_LIST_NAME = "bouquets_tree_store"

    # dynamically active elements depending on the selected view
    _SERVICE_ELEMENTS = ("services_to_fav_move_popup_item", "services_edit_popup_item", "services_copy_popup_item",
                         "services_picon_popup_item", "services_create_bouquet_popup_item")

    _BOUQUET_ELEMENTS = ("edit_tool_button", "new_tool_button", "bouquets_new_popup_item", "bouquets_edit_popup_item")

    _COMMONS_ELEMENTS = ("edit_tool_button", "services_remove_popup_item", "bouquets_remove_popup_item",
                         "fav_remove_popup_item")

    _FAV_ELEMENTS = ("fav_cut_popup_item", "fav_paste_popup_item", "fav_locate_popup_item", "fav_iptv_popup_item",
                     "fav_insert_marker_popup_item", "fav_edit_sub_menu_popup_item", "fav_picon_popup_item")

    _FAV_ENIGMA_ELEMENTS = ("fav_insert_marker_popup_item",)

    _FAV_IPTV_ELEMENTS = ("fav_iptv_popup_item",)

    _LOCK_HIDE_ELEMENTS = ("locked_tool_button", "hide_tool_button")

    _DYNAMIC_ELEMENTS = ("services_create_bouquet_popup_item", "new_tool_button", "edit_tool_button",
                         "services_to_fav_move_popup_item", "services_edit_popup_item", "locked_tool_button",
                         "services_remove_popup_item", "fav_cut_popup_item", "fav_paste_popup_item",
                         "bouquets_new_popup_item", "bouquets_edit_popup_item", "services_remove_popup_item",
                         "bouquets_remove_popup_item", "fav_remove_popup_item", "hide_tool_button",
                         "fav_insert_marker_popup_item", "fav_edit_sub_menu_popup_item", "fav_locate_popup_item",
                         "services_copy_popup_item", "services_picon_popup_item", "fav_picon_popup_item",
                         "services_add_new_popup_item", "fav_iptv_popup_item")

    def __init__(self):
        handlers = {"on_close_app": self.on_close_app,
                    "on_resize": self.on_resize,
                    "on_about_app": self.on_about_app,
                    "on_preferences": self.on_preferences,
                    "on_download": self.on_download,
                    "on_data_open": self.on_data_open,
                    "on_data_save": self.on_data_save,
                    "on_tree_view_key_release": self.on_tree_view_key_release,
                    "on_bouquets_selection": self.on_bouquets_selection,
                    "on_satellite_editor_show": self.on_satellite_editor_show,
                    "on_services_selection": self.on_services_selection,
                    "on_fav_selection": self.on_fav_selection,
                    "on_up": self.on_up,
                    "on_down": self.on_down,
                    "on_cut": self.on_cut,
                    "on_copy": self.on_copy,
                    "on_paste": self.on_paste,
                    "on_edit": self.on_rename,
                    "on_rename_for_bouquet": self.on_rename_for_bouquet,
                    "on_set_default_name_for_bouquet": self.on_set_default_name_for_bouquet,
                    "on_service_edit": self.on_service_edit,
                    "on_services_add_new": self.on_services_add_new,
                    "on_delete": self.on_delete,
                    "on_tool_edit": self.on_tool_edit,
                    "on_to_fav_move": self.on_to_fav_move,
                    "on_services_tree_view_drag_data_get": self.on_services_tree_view_drag_data_get,
                    "on_fav_tree_view_drag_data_get": self.on_fav_tree_view_drag_data_get,
                    "on_fav_tree_view_drag_data_received": self.on_fav_tree_view_drag_data_received,
                    "on_view_popup_menu": self.on_view_popup_menu,
                    "on_popover_release": self.on_popover_release,
                    "on_view_focus": self.on_view_focus,
                    "on_hide": self.on_hide,
                    "on_locked": self.on_locked,
                    "on_model_changed": self.on_model_changed,
                    "on_import_m3u": self.on_import_m3u,
                    "on_insert_marker": self.on_insert_marker,
                    "on_edit_marker": self.on_edit_marker,
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
                    "on_player_close": self.on_player_close,
                    "on_player_press": self.on_player_press,
                    "on_full_screen": self.on_full_screen,
                    "on_player_size_allocate": self.on_player_size_allocate,
                    "on_drawing_area_realize": self.on_drawing_area_realize,
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
        self._services = {}
        self._bouquets = {}
        self._extra_bouquets = {}  # for bouquets with different names of services in bouquet and main list
        self._picons = {}
        self._blacklist = set()
        self._current_bq_name = None
        # Player
        self._player = None
        self._full_screen = False
        self._drawing_area_xid = None

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
        self._status_bar = builder.get_object("status_bar")
        self._main_window_box = builder.get_object("main_window_box")
        self._player_drawing_area = builder.get_object("player_drawing_area")
        self._player_box = builder.get_object("player_box")
        # enabling events for the drawing area
        self._player_drawing_area.set_events(Gdk.ModifierType.BUTTON1_MASK)
        self._player_frame = builder.get_object("player_frame")
        self._header_bar = builder.get_object("header_bar")
        self._bq_name_label = builder.get_object("bq_name_label")
        self._ip_label = builder.get_object("ip_label")
        self._ip_label.set_text(self._options.get(self._profile).get("host"))
        self.update_profile_label()
        # dynamically active elements depending on the selected view
        self._tool_elements = {k: builder.get_object(k) for k in self._DYNAMIC_ELEMENTS}
        self._cas_label = builder.get_object("cas_label")
        self._fav_count_label = builder.get_object("fav_count_label")
        self._bouquets_count_label = builder.get_object("bouquets_count_label")
        self._tv_count_label = builder.get_object("tv_count_label")
        self._radio_count_label = builder.get_object("radio_count_label")
        self._data_count_label = builder.get_object("data_count_label")
        self.init_drag_and_drop()  # drag and drop
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
        self._main_window.show()

    def init_drag_and_drop(self):
        """ Enable drag and drop """
        target = []
        self._services_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.COPY)
        self._fav_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target,
                                                Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._fav_view.enable_model_drag_dest(target, Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._fav_view.drag_dest_set_target_list(None)
        self._fav_view.drag_source_set_target_list(None)
        self._fav_view.drag_dest_add_text_targets()
        self._fav_view.drag_source_add_text_targets()
        self._services_view.drag_source_set_target_list(None)
        self._services_view.drag_source_add_text_targets()

    def force_ctrl(self, view, event):
        """ Function for force ctrl press event for view """
        event.state |= Gdk.ModifierType.CONTROL_MASK

    @run_idle
    def on_close_app(self, *args):
        """  Called before app quit """
        write_config(self._options)  # storing current config
        self.on_player_close()
        Gtk.main_quit()

    def on_resize(self, window):
        """ Stores new size properties for app window after resize """
        self._options["window_size"] = window.get_size()

    def on_up(self, item):
        self.move_items(Gdk.KEY_Up)

    def on_down(self, item):
        self.move_items(Gdk.KEY_Down)

    @run_idle
    def on_about_app(self, item):
        show_dialog(DialogType.ABOUT, self._main_window)

    def move_items(self, key):
        """ Move items in fav or bouquets tree view """
        if self._services_view.is_focus():
            return
        move_items(key, self._fav_view if self._fav_view.is_focus() else self._bouquets_view)

    def on_cut(self, view):
        for row in tuple(self.on_delete(view)):
            self._rows_buffer.append(row)

    def on_copy(self, view):
        model, paths = view.get_selection().get_selected_rows()
        itrs = [model.get_iter(path) for path in paths]
        rows = [(0, *model.get(in_itr, 2, 3, 4, 5, 7, 16, 18, 8)) for in_itr in itrs]
        self._rows_buffer.extend(rows)

    def on_paste(self, view):
        selection = view.get_selection()
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
            fav_bouquet.insert(dest_index, row[-1])

        if model.get_name() == self._FAV_LIST_NAME:
            self.update_fav_num_column(model)

        self._rows_buffer.clear()
        self.on_view_focus(view, None)

    def on_delete(self, item):
        """ Delete selected items from views

            returns deleted rows list!
        """
        for view in [self._services_view, self._fav_view, self._bouquets_view]:
            if view.is_focus():
                selection = view.get_selection()
                model, paths = selection.get_selected_rows()
                model_name = get_base_model(model).get_name()
                itrs = [model.get_iter(path) for path in paths]
                rows = [model[in_itr][:] for in_itr in itrs]
                bq_selected = self.get_selected_bouquet()
                fav_bouquet = None
                if bq_selected:
                    fav_bouquet = self._bouquets.get(bq_selected, None)

                if model_name == self._FAV_LIST_NAME:
                    self.remove_favs(fav_bouquet, itrs, model)
                elif model_name == self._BOUQUETS_LIST_NAME:
                    self.delete_bouquets(itrs, model, bq_selected)
                elif model_name == self._SERVICE_LIST_NAME:
                    self.delete_services(bq_selected, itrs, model, rows)

                self.on_view_focus(view, None)

                return rows

    @run_idle
    def remove_favs(self, fav_bouquet, itrs, model):
        """ Deleting bouquet services """
        if fav_bouquet:
            for itr in itrs:
                del fav_bouquet[int(model.get_path(itr)[0])]
                self._fav_model.remove(itr)
        self.update_fav_num_column(model)

    @run_idle
    def delete_services(self, bq_selected, itrs, model, rows):
        """ Deleting services """
        srv_itrs = [self._services_model_filter.convert_iter_to_child_iter(
            model.convert_iter_to_child_iter(itr)) for itr in itrs]
        for s_itr in srv_itrs:
            self._services_model.remove(s_itr)

        srv_ids_to_delete = set()
        for row in rows:
            # There are channels with the same parameters except for the name.
            # None because it can have duplicates! Need fix
            fav_id = row[-2]
            for bq in self._bouquets:
                services = self._bouquets[bq]
                if services:
                    with suppress(ValueError):
                        services.remove(fav_id)
                        srv_ids_to_delete.add(fav_id)
            self._services.pop(fav_id, None)

        for f_itr in filter(lambda r: r[7] in srv_ids_to_delete, self._fav_model):
            self._fav_model.remove(f_itr.iter)
        self.update_fav_num_column(self._fav_model)

    def delete_bouquets(self, itrs, model, bouquet):
        """ Deleting bouquets """
        if len(itrs) == 1 and len(model.get_path(itrs[0])) < 2:
            show_dialog(DialogType.ERROR, self._main_window, "This item is not allowed to be removed!")
            return

        for itr in itrs:
            if len(model.get_path(itr)) < 2:
                continue
            row = model[itr][:]
            self._bouquets.pop("{}:{}".format(row[0], row[3]))
            self._fav_model.clear()
            self._bouquets_model.remove(itr)

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

    def on_tool_edit(self, item):
        """ Edit tool bar button """
        if self._services_view.is_focus():
            self.on_service_edit(self._services_view)
        elif self._fav_view.is_focus():
            self.on_service_edit(self._fav_view)
        elif self._bouquets_view.is_focus():
            self.on_rename(self._bouquets_view)

    def on_to_fav_move(self, view):
        """ Move items from app to fav list """
        selection = self.get_selection(view)

        if selection:
            self.receive_selection(view=self._fav_view, drop_info=None, data=selection)

    def get_selection(self, view):
        """ Creates a string from the iterators of the selected rows """
        model, paths = view.get_selection().get_selected_rows()
        model = get_base_model(model)

        if len(paths) > 0:
            itrs = [model.get_iter(path) for path in paths]
            return "{}:{}".format(",".join([model.get_string_from_iter(itr) for itr in itrs]), model.get_name())

    def receive_selection(self, *, view, drop_info, data):
        """  Update fav view  after data received  """
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

        itr_str, sep, source = data.partition(":")
        itrs = itr_str.split(",")

        try:
            fav_bouquet = self._bouquets[bq_selected]

            if source == self._SERVICE_LIST_NAME:
                ext_model = self._services_view.get_model()
                ext_itrs = [ext_model.get_iter_from_string(itr) for itr in itrs]
                ext_rows = [ext_model[ext_itr][:] for ext_itr in ext_itrs]
                dest_index -= 1
                for ext_row in ext_rows:
                    dest_index += 1
                    fav_id = ext_row[18]
                    ch = self._services[fav_id]
                    model.insert(dest_index, (0, ch.coded, ch.service, ch.locked, ch.hide,
                                              ch.service_type, ch.pos, ch.fav_id, self._picons.get(ch.picon_id, None)))
                    fav_bouquet.insert(dest_index, ch.fav_id)
            elif source == self._FAV_LIST_NAME:
                in_itrs = [model.get_iter_from_string(itr) for itr in itrs]
                in_rows = [model[in_itr][:] for in_itr in in_itrs]
                for row in in_rows:
                    model.insert(dest_index, row)
                    fav_bouquet.insert(dest_index, row[7])
                for in_itr in in_itrs:
                    del fav_bouquet[int(model.get_path(in_itr)[0])]
                    model.remove(in_itr)
            self.update_fav_num_column(model)
        except ValueError as e:
            self._status_bar.push(1, getattr(e, "message", repr(e)))

    def update_fav_num_column(self, model):
        """ Iterate through model and updates values for Num column """
        model.foreach(lambda store, pth, itr: store.set_value(itr, 0, int(pth[0]) + 1))  # iter , column, value

    def update_bouquet_list(self):
        """ Update bouquet after move items """
        bq_selected = self.get_selected_bouquet()
        if bq_selected:
            fav_bouquet = self._bouquets[bq_selected]
            fav_bouquet.clear()
            for row in self._fav_model:
                fav_bouquet.append(row[7])

    def on_services_tree_view_drag_data_get(self, view, drag_context, data, info, time):
        """  DnD  """
        data.set_text(self.get_selection(view), -1)

    def on_fav_tree_view_drag_data_get(self, view, drag_context, data, info, time):
        """ DnD """
        data.set_text(self.get_selection(view), -1)

    def on_fav_tree_view_drag_data_received(self, view, drag_context, x, y, data, info, time):
        """ DnD """
        self.receive_selection(view=view, drop_info=view.get_dest_row_at_pos(x, y), data=data.get_text())

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
            self.update_services_counts(len(self._services.values()))

    def append_blacklist(self, black_list):
        if black_list:
            self._blacklist.update(black_list)

    def append_bouquets(self, bqs):
        for bouquet in bqs:
            parent = self._bouquets_model.append(None, [bouquet.name, None, None, bouquet.type])
            for bq in bouquet.bouquets:
                self.append_bouquet(bq, parent)

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
        if services:
            for srv in services:
                #  adding channels to dict with fav_id as keys
                self._services[srv.fav_id] = srv
            gen = self.append_services_data(services)
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def append_services_data(self, services):
        for srv in services:
            itr = self._services_model.append(srv)
            self._services_model.set_value(itr, 8, self._picons.get(srv.picon_id, None))
            yield True
        self._wait_dialog.hide()
        self.update_filter_sat_positions()

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

    @run_idle
    def on_data_save(self, *args):
        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return

        path = self._options.get(self._profile).get("data_dir_path")
        backup_path = path + "backup/"
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        # backup files in data dir(skipping dirs and satellites.xml)
        for file in filter(lambda f: f != "satellites.xml" and os.path.isfile(os.path.join(path, f)), os.listdir(path)):
            shutil.move(os.path.join(path, file), backup_path + file)

        bouquets = []
        services_model = get_base_model(self._services_view.get_model())

        def parse_bouquets(model, b_path, itr):
            bqs = None
            if model.iter_has_child(itr):
                bqs = []
                num_of_children = model.iter_n_children(itr)
                for num in range(num_of_children):
                    bq_itr = model.iter_nth_child(itr, num)
                    bq_name, locked, hidden, bq_type = model.get(bq_itr, 0, 1, 2, 3)
                    bq_id = "{}:{}".format(bq_name, bq_type)
                    favs = self._bouquets[bq_id]
                    ex_srvs = self._extra_bouquets.get(bq_id)
                    # Don't repeat so! Please! :)
                    bq_srvs = list(map(lambda s: s._replace(service=ex_srvs.get(s.fav_id, None) if ex_srvs else None),
                                       filter(None, [self._services.get(f_id, None) for f_id in favs])))
                    bq = Bouquet(bq_name, bq_type, bq_srvs, locked, hidden)
                    bqs.append(bq)
            if len(b_path) == 1:
                bouquets.append(Bouquets(*model.get(itr, 0, 3), bqs if bqs else []))

        profile = Profile(self._profile)
        # Getting bouquets
        self._bouquets_view.get_model().foreach(parse_bouquets)
        write_bouquets(path, bouquets, profile)
        # Getting services
        services = [Service(*row[:]) for row in services_model]
        write_services(path, services, profile, self.get_format_version() if profile is Profile.ENIGMA_2 else 0)
        # removing bouquet files
        if profile is Profile.ENIGMA_2:
            # blacklist
            write_blacklist(path, self._blacklist)

    def on_services_selection(self, model, path, column):
        self.delete_selection(self._fav_view, self._bouquets_view)
        self.update_service_bar(model, path)

    def update_service_bar(self, model, path):
        def_val = "Unknown"
        cas = model.get_value(model.get_iter(path), 0)
        if not cas:
            return
        cas_values = list(filter(lambda val: val.startswith("C:"), cas.split(",")))
        self._cas_label.set_text(",".join(map(str, sorted(set(CAS.get(val, def_val) for val in cas_values)))))

    def on_fav_selection(self, model, path, column):
        self.delete_selection(self._services_view, self._bouquets_view)

    def on_bouquets_selection(self, model, path, column):
        self._current_bq_name = model[path][0] if len(path) > 1 else None
        self._bq_name_label.set_text(self._current_bq_name if self._current_bq_name else "")
        self._fav_model.clear()

        if self._bouquets_view.row_expanded(path):
            self._bouquets_view.collapse_row(path)
        else:
            self._bouquets_view.expand_row(path, column)

        if len(path) > 1:
            self.delete_selection(self._services_view)
            self.update_bouquet_services(model, path)

    @run_idle
    def update_bouquet_services(self, model, path, bq_key=None):
        """ Updates list of bouquet services """
        tree_iter = None
        if path:
            tree_iter = model.get_iter(path)

        key = bq_key if bq_key else "{}:{}".format(*model.get(tree_iter, 0, 3))
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
                self._fav_model.append((num + 1, srv.coded, ex_srv_name if ex_srv_name else srv.service, srv.locked,
                                        srv.hide, srv.service_type, srv.pos, srv.fav_id,
                                        self._picons.get(srv.picon_id, None)))

    def check_bouquet_selection(self):
        """ checks and returns bouquet if selected """
        bq_selected = self.get_selected_bouquet()

        if not bq_selected:
            show_dialog(DialogType.ERROR, self._main_window, "Error. No bouquet is selected!")
            return

        if Profile(self._profile) is Profile.NEUTRINO_MP and bq_selected.endswith(BqType.WEBTV.value):
            show_dialog(DialogType.ERROR, self._main_window, "Operation not allowed in this context!")
            return

        return bq_selected

    def get_selected_bouquet(self):
        """  returns 'name:type' of last selected bouquet or False  """
        if self._current_bq_name is None:
            return False

        for row in self._bouquets_model:
            chs_rows = row.iterchildren()
            for ch_row in chs_rows:
                name = ch_row[0]
                if name == self._current_bq_name:
                    return "{}:{}".format(name, ch_row[3])
        return False

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

    def on_tree_view_key_release(self, view, event):
        """  Handling  keystrokes  """
        key = event.keyval
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        alt = event.state & Gdk.ModifierType.MOD1_MASK
        model = get_base_model(view.get_model())
        model_name = model.get_name()

        if key == Gdk.KEY_Delete:
            self.on_delete(view)
        elif ctrl and key in MOVE_KEYS:
            self.move_items(key)
        elif model_name == self._FAV_LIST_NAME and key == Gdk.KEY_Control_L or key == Gdk.KEY_Control_R:
            self.update_fav_num_column(model)
            self.update_bouquet_list()
        elif key == Gdk.KEY_Insert:
            # Move items from app to fav list
            if model_name == self._SERVICE_LIST_NAME:
                self.on_to_fav_move(view)
            elif model_name == self._BOUQUETS_LIST_NAME:
                self.on_new_bouquet(view)
        elif ctrl and (key == Gdk.KEY_c or key == Gdk.KEY_C) and model_name == self._SERVICE_LIST_NAME:
            self.on_copy(view)
        elif ctrl and key == Gdk.KEY_x or key == Gdk.KEY_X:
            if model_name == self._FAV_LIST_NAME:
                self.on_cut(view)
        elif ctrl and key == Gdk.KEY_v or key == Gdk.KEY_V:
            self.on_paste(view)
        elif ctrl and key == Gdk.KEY_s or key == Gdk.KEY_S:
            self.on_data_save()
        elif ctrl and key == Gdk.KEY_l or key == Gdk.KEY_L:
            self.on_locked(None)
        elif ctrl and key == Gdk.KEY_h or key == Gdk.KEY_H:
            self.on_hide(None)
        elif ctrl and key == Gdk.KEY_R or key == Gdk.KEY_r or key == Gdk.KEY_F2:
            self.on_rename(view)
        elif ctrl and key == Gdk.KEY_E or key == Gdk.KEY_e:
            if model_name == self._BOUQUETS_LIST_NAME:
                self.on_rename(view)
                return
            self.on_service_edit(view)
        elif key == Gdk.KEY_Left or key == Gdk.KEY_Right:
            view.do_unselect_all(view)
        elif ctrl and model_name == self._FAV_LIST_NAME and key in (Gdk.KEY_P, Gdk.KEY_p):
            self.on_play_stream()

    def on_download(self, item):
        show_download_dialog(transient=self._main_window,
                             options=self._options.get(self._profile),
                             open_data=self.open_data,
                             profile=Profile(self._profile))

    def on_view_focus(self, view, focus_event):
        profile = Profile(self._profile)
        model = get_base_model(view.get_model())
        model_name = model.get_name()
        not_empty = len(model) > 0  # if  > 0 model has items

        if model_name == self._BOUQUETS_LIST_NAME:
            for elem in self._tool_elements:
                self._tool_elements[elem].set_sensitive(False)
            for elem in self._BOUQUET_ELEMENTS:
                self._tool_elements[elem].set_sensitive(not_empty)
            if profile is Profile.NEUTRINO_MP:
                for elem in self._LOCK_HIDE_ELEMENTS:
                    self._tool_elements[elem].set_sensitive(not_empty)
        else:
            is_service = model_name == self._SERVICE_LIST_NAME
            bq_selected = False
            if model_name == self._FAV_LIST_NAME:
                bq_selected = self.get_selected_bouquet()
                if profile is Profile.NEUTRINO_MP and bq_selected:
                    name, bq_type = bq_selected.split(":")
                    bq_selected = BqType(bq_type) is BqType.WEBTV

            for elem in self._FAV_ELEMENTS:
                if elem in ("paste_tool_button", "fav_paste_popup_item"):
                    self._tool_elements[elem].set_sensitive(not is_service and self._rows_buffer)
                elif elem in self._FAV_ENIGMA_ELEMENTS:
                    if profile is Profile.ENIGMA_2:
                        self._tool_elements[elem].set_sensitive(bq_selected and not is_service)
                elif elem in self._FAV_IPTV_ELEMENTS:
                    self._tool_elements[elem].set_sensitive(bq_selected and not is_service)
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

        self._tool_elements["services_add_new_popup_item"].set_sensitive(len(self._bouquets_model))

    def on_hide(self, item):
        self.set_service_flags(Flag.HIDE)

    def on_locked(self, item):
        self.set_service_flags(Flag.LOCK)

    def set_service_flags(self, flag):
        profile = Profile(self._profile)
        bq_selected = self.get_selected_bouquet()
        if profile is Profile.ENIGMA_2:
            if set_flags(flag, self._services_view, self._fav_view, self._services, self._blacklist) and bq_selected:
                self._fav_model.clear()
                self.update_bouquet_services(self._fav_model, None, bq_selected)
        elif profile is Profile.NEUTRINO_MP and bq_selected:
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
        insert_marker(view, self._bouquets, self.get_selected_bouquet(), self._services, self._main_window)
        self.update_fav_num_column(self._fav_model)

    def on_edit_marker(self, view):
        edit_marker(view, self._bouquets, self.get_selected_bouquet(), self._services, self._main_window)

    def on_fav_press(self, menu, event):
        self.on_view_popup_menu(menu, event)
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.on_play_stream()

    # ***************** IPTV *********************#

    def on_iptv(self, item):
        response = IptvDialog(self._main_window,
                              self._fav_view,
                              self._services,
                              self._bouquets.get(self.get_selected_bouquet(), None),
                              Profile(self._profile),
                              Action.ADD).show()
        if response != Gtk.ResponseType.CANCEL:
            self.update_fav_num_column(self._fav_model)

    @run_idle
    def on_iptv_list_configuration(self, item):
        profile = Profile(self._profile)
        if profile is not Profile.ENIGMA_2:
            show_dialog(DialogType.ERROR, transient=self._main_window, text="Not implemented yet!")
            return

        iptv_rows = list(filter(lambda r: r[5] == BqServiceType.IPTV.value, self._fav_model))
        if not iptv_rows:
            show_dialog(DialogType.ERROR, self._main_window, "This list does not contains iptv streams!")
            return

        bq_selected = self.get_selected_bouquet()
        if not bq_selected:
            return

        bouquet = self._bouquets.get(bq_selected, [])
        IptvListConfigurationDialog(self._main_window, self._services, iptv_rows, bouquet, profile).show()

    @run_idle
    def on_remove_all_unavailable(self, item):
        iptv_rows = list(filter(lambda r: r[5] == BqServiceType.IPTV.value, self._fav_model))
        if not iptv_rows:
            show_dialog(DialogType.ERROR, self._main_window, "This list does not contains iptv streams!")
            return

        bq_selected = self.get_selected_bouquet()
        if not bq_selected:
            return

        if show_dialog(DialogType.QUESTION, self._main_window) == Gtk.ResponseType.CANCEL:
            return

        fav_bqt = self._bouquets.get(bq_selected, None)
        prf = Profile(self._profile)
        response = SearchUnavailableDialog(self._main_window, self._fav_model, fav_bqt, iptv_rows, prf).show()
        if response:
            self.remove_favs(fav_bqt, response, self._fav_model)

    def on_import_m3u(self, item):
        """ Imports iptv from m3u files. """
        response = get_chooser_dialog(self._main_window, self._options.get(self._profile), "*.m3u", "m3u files")
        if response == Gtk.ResponseType.CANCEL:
            return

        if not str(response).endswith("m3u"):
            show_dialog(DialogType.ERROR, self._main_window, text="No m3u file is selected!")
            return

        channels = parse_m3u(response, Profile(self._profile))
        bq_selected = self.get_selected_bouquet()
        if channels and bq_selected:
            bq_services = self._bouquets.get(bq_selected)
            self._fav_model.clear()
            for ch in channels:
                self._services[ch.fav_id] = ch
                bq_services.append(ch.fav_id)
            self.update_bouquet_services(self._fav_model, None, bq_selected)

    # ***************** Player *********************#

    @run_idle
    def on_play_stream(self, item=None):
        self._player_box.set_visible(True)
        self.on_player_play()

    @run_idle
    def on_player_play(self, item=None):
        self.on_player_stop(None)
        if self._player:
            self.play()

    @run_task
    def play(self):
        path, column = self._fav_view.get_cursor()
        if path:
            row = self._fav_model[path][:]
            if row[5] == BqServiceType.IPTV.value:
                url = get_iptv_url(row, Profile(self._profile))
                if not url:
                    return

                self._player.set_mrl(url)
                self._player.play()
                GLib.idle_add(self.on_player_size_allocate, self._player_drawing_area, priority=GLib.PRIORITY_LOW)

    def on_player_stop(self, item=None):
        if self._player:
            self._player.stop()
            self.on_player_size_allocate(self._player_drawing_area)

    @run_idle
    def on_player_close(self, item=None):
        if self._player:
            self._player.stop()
            self._player.release()
            self._player = None
        GLib.idle_add(self._player_box.set_visible, False, priority=GLib.PRIORITY_LOW)

    def on_player_size_allocate(self, area, rectangle=None):
        area.hide()
        GLib.idle_add(area.show, priority=GLib.PRIORITY_LOW)

    def on_drawing_area_realize(self, widget):
        self._drawing_area_xid = widget.get_window().get_xid()
        if not self._player:
            try:
                self._player = Player.get_vlc_instance().media_player_new()
            except (NameError, AttributeError):
                show_dialog(DialogType.ERROR, self._main_window, "No VLC is found. Check that it is installed!")
            else:
                self._player.set_xwindow(self._drawing_area_xid)
                GLib.idle_add(self.play, priority=GLib.PRIORITY_LOW)

    def on_player_press(self, area, event):
        if event.button == Gdk.BUTTON_PRIMARY:
            if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
                self.on_full_screen()
            elif event.type == Gdk.EventType.BUTTON_PRESS:
                if self._player:
                    self._player.stop() if self._player.is_playing() else self._player.play()

    def on_full_screen(self, item=None):
        self._full_screen = not self._full_screen
        self._main_window.fullscreen() if self._full_screen else self._main_window.unfullscreen()
        self.on_player_size_allocate(self._player_drawing_area)

    def on_main_window_state(self, window, event):
        if event.new_window_state & Gdk.WindowState.FULLSCREEN:
            if self._main_window_box in window:
                window.remove(self._main_window_box)
                self._player_drawing_area.reparent(window)
        elif self._player_drawing_area in window:
            window.remove(self._player_drawing_area)
            window.add(self._main_window_box)
            self._player_frame.add(self._player_drawing_area)

        if self._player:
            self.on_player_size_allocate(self._player_drawing_area)
            self._player.set_xwindow(self._drawing_area_xid)

    # ***************** Filter and search *********************#

    @run_idle
    def on_filter_toggled(self, toggle_button: Gtk.ToggleToolButton):
        active = toggle_button.get_active()
        if active:
            self.update_filter_sat_positions()

        self._filter_bar.set_search_mode(active)
        self._filter_bar.set_visible(active)

    @run_idle
    def update_filter_sat_positions(self):
        self._filter_sat_positions_model.clear()
        self._filter_sat_positions_model.append(("All positions",))
        self._filter_sat_positions_box.set_active(0)
        sats = {float(x[16]) for x in self._services_model}
        list(map(self._filter_sat_positions_model.append, map(lambda x: (str(x),), sorted(sats))))

    @run_with_delay(1)
    def on_filter_changed(self, item):
        GLib.idle_add(self._services_model_filter.refilter, priority=GLib.PRIORITY_LOW)

    def services_filter_function(self, model, iter, data):
        if self._services_model_filter is None or self._services_model_filter == "None":
            return True
        else:
            txt = self._filter_entry.get_text() in str(model.get(iter, 3, 6, 7, 10, 11, 12, 13, 14, 15, 16))
            type_active = self._filter_types_box.get_active() > 0
            pos_active = self._filter_sat_positions_box.get_active() > 0
            free = not model.get(iter, 2)[0] if self._filter_only_free_button.get_active() else True

            if type_active and pos_active:
                return self._filter_types_box.get_active_id() == model.get(iter, 7)[
                    0] and self._filter_sat_positions_box.get_active_id() == model.get(iter, 16)[0] and txt and free
            elif type_active:
                return self._filter_types_box.get_active_id() == model.get(iter, 7)[0] and txt and free
            elif pos_active:
                return self._filter_sat_positions_box.get_active_id() == model.get(iter, 16)[0] and txt and free

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
                srv_type = model.get_value(model.get_iter(paths), 5)
                if srv_type == BqServiceType.MARKER.name:
                    return self.on_rename(view)
                elif srv_type == BqServiceType.IPTV.name:
                    return IptvDialog(self._main_window,
                                      self._fav_view,
                                      self._services,
                                      self._bouquets.get(self.get_selected_bouquet(), None),
                                      Profile(self._profile),
                                      Action.EDIT).show()
                self.on_locate_in_services(view)

            dialog = ServiceDetailsDialog(self._main_window,
                                          self._options,
                                          self._services_view,
                                          self._fav_view,
                                          self._services,
                                          self._bouquets)
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
        bq_selected = self.get_selected_bouquet()
        if not bq_selected:
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
        model = get_base_model(view.get_model())
        name = model.get_name()
        if name == self._BOUQUETS_LIST_NAME:
            self.on_bouquets_edit(view)
        elif name == self._FAV_LIST_NAME:
            rename(view, self._main_window, ViewTarget.FAV, service_view=self._services_view,
                   channels=self._services)
        elif name == self._SERVICE_LIST_NAME:
            rename(view, self._main_window, ViewTarget.SERVICES, fav_view=self._fav_view, channels=self._services)

    def on_rename_for_bouquet(self, item):
        selection = get_selection(self._fav_view, self._main_window)
        if not selection:
            return

        model, paths = selection
        data = model[paths][:]
        cur_name, fav_id = data[2], data[7]
        response = show_dialog(DialogType.INPUT, self._main_window, cur_name)
        if response == Gtk.ResponseType.CANCEL:
            return

        srv = self._services.get(fav_id, None)
        selected_bq = self.get_selected_bouquet()
        ex_bq = self._extra_bouquets.get(selected_bq, None)

        if srv.service == response and ex_bq:
            ex_bq.pop(fav_id, None)
            if not ex_bq:
                self._extra_bouquets.pop(selected_bq, None)
        else:
            if ex_bq:
                ex_bq[fav_id] = response
            else:
                self._extra_bouquets[selected_bq] = {fav_id: response}

        model.set_value(model.get_iter(paths), 2, response)

    def on_set_default_name_for_bouquet(self, item):
        selection = get_selection(self._fav_view, self._main_window)
        if not selection:
            return

        model, paths = selection
        fav_id = model[paths][7]
        srv = self._services.get(fav_id, None)
        selected_bq = self.get_selected_bouquet()
        ex_bq = self._extra_bouquets.get(selected_bq, None)

        if not ex_bq:
            show_dialog(DialogType.ERROR, self._main_window, "No changes required!")
            return
        else:
            if not ex_bq.pop(fav_id, None):
                show_dialog(DialogType.ERROR, self._main_window, "No changes required!")
                return
            if not ex_bq:
                self._extra_bouquets.pop(selected_bq, None)

        model.set_value(model.get_iter(paths), 2, srv.service)

    def on_locate_in_services(self, view):
        locate_in_services(view, self._services_view, self._main_window)

    # ***************** Picons *********************#

    @run_idle
    def on_picons_loader_show(self, item):
        ids = {}
        if Profile(self._profile) is Profile.ENIGMA_2:
            for r in self._services_model:
                data = r[9].split("_")
                ids["{}:{}:{}".format(data[3], data[5], data[6])] = r[9]

        dialog = PiconsDialog(self._main_window, self._options, ids, Profile(self._profile))
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


def start_app():
    MainAppWindow()
    Gtk.main()


def close_app():
    Gtk.main_quit()


if __name__ == "__main__":
    pass

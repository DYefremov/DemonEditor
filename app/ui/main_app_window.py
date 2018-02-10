import os
from contextlib import suppress
from functools import lru_cache

import shutil

from app.commons import run_idle, log
from app.eparser import get_blacklist, write_blacklist, parse_m3u
from app.eparser import get_services, get_bouquets, write_bouquets, write_services, Bouquets, Bouquet, Service
from app.eparser.ecommons import CAS, FLAG
from app.eparser.enigma.bouquets import BqServiceType
from app.properties import get_config, write_config, Profile
from . import Gtk, Gdk, UI_RESOURCES_PATH, LOCKED_ICON, HIDE_ICON
from .dialogs import show_dialog, DialogType, get_chooser_dialog
from .download_dialog import show_download_dialog
from .main_helper import edit_marker, insert_marker, move_items, edit, ViewTarget, set_flags, locate_in_services, \
    scroll_to, get_base_model, update_picons, copy_picon_reference, assign_picon, remove_picon, search
from .picons_dialog import PiconsDialog
from .satellites_dialog import show_satellites_dialog
from .settings_dialog import show_settings_dialog


class MainAppWindow:
    _SERVICE_LIST_NAME = "services_list_store"
    _FAV_LIST_NAME = "fav_list_store"
    _BOUQUETS_LIST_NAME = "bouquets_tree_store"
    # dynamically active elements depending on the selected view
    _SERVICE_ELEMENTS = ("copy_tool_button", "to_fav_tool_button", "copy_menu_item", "services_to_fav_move_popup_item",
                         "services_edit_popup_item", "services_copy_popup_item", "services_picon_popup_item")

    _BOUQUET_ELEMENTS = ("edit_tool_button", "new_tool_button",
                         "bouquets_new_popup_item", "bouquets_edit_popup_item")

    _COMMONS_ELEMENTS = ("edit_tool_button", "remove_tool_button", "delete_menu_item", "services_remove_popup_item",
                         "bouquets_remove_popup_item", "fav_remove_popup_item", "up_tool_button", "down_tool_button")

    _FAV_ELEMENTS = ("cut_tool_button", "paste_tool_button", "cut_menu_item",
                     "paste_menu_item", "fav_cut_popup_item", "fav_paste_popup_item", "import_m3u_tool_button",
                     "fav_import_m3u_popup_item", "fav_insert_marker_popup_item", "fav_edit_popup_item",
                     "fav_locate_popup_item", "fav_picon_popup_item")

    _FAV_ONLY_ELEMENTS = ("import_m3u_tool_button", "fav_import_m3u_popup_item", "fav_insert_marker_popup_item",
                          "fav_edit_marker_popup_item")

    _LOCK_HIDE_ELEMENTS = ("locked_tool_button", "hide_tool_button")

    __DYNAMIC_ELEMENTS = ("up_tool_button", "down_tool_button", "cut_tool_button", "copy_tool_button",
                          "paste_tool_button", "to_fav_tool_button", "new_tool_button", "remove_tool_button",
                          "cut_menu_item", "copy_menu_item", "paste_menu_item", "delete_menu_item", "edit_tool_button",
                          "services_to_fav_move_popup_item", "services_edit_popup_item", "locked_tool_button",
                          "services_remove_popup_item", "fav_cut_popup_item", "fav_paste_popup_item",
                          "bouquets_new_popup_item", "bouquets_edit_popup_item", "services_remove_popup_item",
                          "bouquets_remove_popup_item", "fav_remove_popup_item", "hide_tool_button",
                          "import_m3u_tool_button", "fav_import_m3u_popup_item", "fav_insert_marker_popup_item",
                          "fav_edit_marker_popup_item", "fav_edit_popup_item", "fav_locate_popup_item",
                          "services_copy_popup_item", "services_picon_popup_item", "fav_picon_popup_item")

    def __init__(self):
        handlers = {"on_close_main_window": self.on_quit,
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
                    "on_edit": self.on_edit,
                    "on_delete": self.on_delete,
                    "on_new_bouquet": self.on_new_bouquet,
                    "on_bouquets_edit": self.on_bouquets_edit,
                    "on_tool_edit": self.on_tool_edit,
                    "on_to_fav_move": self.on_to_fav_move,
                    "on_services_tree_view_drag_data_get": self.on_services_tree_view_drag_data_get,
                    "on_fav_tree_view_drag_data_get": self.on_fav_tree_view_drag_data_get,
                    "on_fav_tree_view_drag_data_received": self.on_fav_tree_view_drag_data_received,
                    "on_view_popup_menu": self.on_view_popup_menu,
                    "on_view_focus": self.on_view_focus,
                    "on_hide": self.on_hide,
                    "on_locked": self.on_locked,
                    "on_model_changed": self.on_model_changed,
                    "on_import_m3u": self.on_import_m3u,
                    "on_insert_marker": self.on_insert_marker,
                    "on_edit_marker": self.on_edit_marker,
                    "on_fav_popup": self.on_fav_popup,
                    "on_locate_in_services": self.on_locate_in_services,
                    "on_picons_loader_show": self.on_picons_loader_show,
                    "on_filter_changed": self.on_filter_changed,
                    "on_assign_picon": self.on_assign_picon,
                    "on_remove_picon": self.on_remove_picon,
                    "on_reference_picon": self.on_reference_picon,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_search_toggled": self.on_search_toggled,
                    "on_search": self.on_search}

        self.__options = get_config()
        self.__profile = self.__options.get("profile")
        os.makedirs(os.path.dirname(self.__options.get(self.__profile).get("data_dir_path")), exist_ok=True)
        # Used for copy/paste. When adding the previous data will not be deleted.
        # Clearing only after the insertion!
        self.__rows_buffer = []
        self.__services = {}
        self.__bouquets = {}
        self.__picons = {}
        self.__blacklist = set()

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "main_window.glade")
        builder.connect_signals(handlers)
        self.__main_window = builder.get_object("main_window")
        main_window_size = self.__options.get("window_size", None)
        # Setting the last size of the window if it was saved
        if main_window_size:
            self.__main_window.resize(*main_window_size)
        self.__services_view = builder.get_object("services_tree_view")
        self.__fav_view = builder.get_object("fav_tree_view")
        self.__bouquets_view = builder.get_object("bouquets_tree_view")
        self.__fav_model = builder.get_object("fav_list_store")
        self.__services_model = builder.get_object("services_list_store")
        self.__bouquets_model = builder.get_object("bouquets_tree_store")
        self.__status_bar = builder.get_object("status_bar")
        self.__profile_label = builder.get_object("profile_label")
        self.__status_bar.push(0, "Current IP: " + self.__options.get(self.__profile).get("host"))
        self.__profile_label.set_text("Enigma2 v.4" if Profile(self.__profile) is Profile.ENIGMA_2 else "Neutrino-MP")
        # dynamically active elements depending on the selected view
        self.__tool_elements = {k: builder.get_object(k) for k in self.__DYNAMIC_ELEMENTS}
        self.__picons_download_tool_button = builder.get_object("picons_download_tool_button")
        self.__cas_label = builder.get_object("cas_label")
        self.__fav_count_label = builder.get_object("fav_count_label")
        self.__bouquets_count_label = builder.get_object("bouquets_count_label")
        self.__tv_count_label = builder.get_object("tv_count_label")
        self.__radio_count_label = builder.get_object("radio_count_label")
        self.__data_count_label = builder.get_object("data_count_label")
        self.__fav_edit_marker_popup_item = builder.get_object("fav_edit_marker_popup_item")
        self.__search_info_bar = builder.get_object("search_info_bar")
        # Filter
        self.__services_model_filter = builder.get_object("services_model_filter")
        self.__services_model_filter.set_visible_func(self.services_filter_function)
        self.__filter_entry = builder.get_object("filter_entry")
        self.__filter_info_bar = builder.get_object("filter_info_bar")
        self.init_drag_and_drop()  # drag and drop
        # Force ctrl press event for view. Multiple selections in lists only with Space key(as in file managers)!!!
        self.__services_view.connect("key-press-event", self.force_ctrl)
        self.__fav_view.connect("key-press-event", self.force_ctrl)
        # Clipboard
        self.__clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.__main_window.show()

    def init_drag_and_drop(self):
        """ Enable drag and drop """
        target = []
        self.__services_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.COPY)
        self.__fav_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target,
                                                 Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self.__fav_view.enable_model_drag_dest(target, Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self.__fav_view.drag_dest_set_target_list(None)
        self.__fav_view.drag_source_set_target_list(None)
        self.__fav_view.drag_dest_add_text_targets()
        self.__fav_view.drag_source_add_text_targets()
        self.__services_view.drag_source_set_target_list(None)
        self.__services_view.drag_source_add_text_targets()

    def force_ctrl(self, view, event):
        """ Function for force ctrl press event for view """
        event.state |= Gdk.ModifierType.CONTROL_MASK

    def on_quit(self, *args):
        """  Called before app quit """
        write_config(self.__options)  # storing current config
        Gtk.main_quit()

    def on_resize(self, window):
        """ Stores new size properties for app window after resize """
        self.__options["window_size"] = window.get_size()

    def on_up(self, item):
        self.move_items(Gdk.KEY_Up)

    def on_down(self, item):
        self.move_items(Gdk.KEY_Down)

    def on_about_app(self, item):
        show_dialog(DialogType.ABOUT, self.__main_window)

    def move_items(self, key):
        """ Move items in fav or bouquets tree view """
        if self.__services_view.is_focus():
            return
        elif self.__fav_view.is_focus():
            move_items(key, self.__fav_view)
        elif self.__bouquets_view and key not in (Gdk.KEY_Page_Up, Gdk.KEY_Page_Down):
            move_items(key, self.__bouquets_view)

    def on_cut(self, view):
        for row in tuple(self.on_delete(view)):
            self.__rows_buffer.append(row)

    def on_copy(self, view):
        model, paths = view.get_selection().get_selected_rows()
        itrs = [model.get_iter(path) for path in paths]
        rows = [(0, *model.get(in_itr, 2, 3, 4, 5, 7, 16, 18, 8)) for in_itr in itrs]
        self.__rows_buffer.extend(rows)

    def on_paste(self, view):
        selection = view.get_selection()
        dest_index = 0
        bq_selected = self.is_bouquet_selected()

        if not bq_selected:
            show_dialog(DialogType.ERROR, self.__main_window, "Error. No bouquet is selected!")
            return

        fav_bouquet = self.__bouquets[bq_selected]
        model, paths = selection.get_selected_rows()

        if paths:
            dest_index = int(paths[0][0])

        for row in self.__rows_buffer:
            dest_index += 1
            model.insert(dest_index, row)
            fav_bouquet.insert(dest_index, row[-1])

        if model.get_name() == self._FAV_LIST_NAME:
            self.update_fav_num_column(model)

        self.__rows_buffer.clear()
        self.on_view_focus(view, None)

    def on_edit(self, view):
        model = get_base_model(view.get_model())
        name = model.get_name()
        if name == self._BOUQUETS_LIST_NAME:
            self.on_bouquets_edit(view)
            # edit(view, self.__main_window, ViewTarget.BOUQUET)
        elif name == self._FAV_LIST_NAME:
            edit(view, self.__main_window, ViewTarget.FAV, service_view=self.__services_view, channels=self.__services)
        elif name == self._SERVICE_LIST_NAME:
            edit(view, self.__main_window, ViewTarget.SERVICES, fav_view=self.__fav_view, channels=self.__services)

    def on_delete(self, item):
        """ Delete selected items from views

            returns deleted rows list!
        """
        for view in [self.__services_view, self.__fav_view, self.__bouquets_view]:
            if view.is_focus():
                selection = view.get_selection()
                model, paths = selection.get_selected_rows()
                model_name = get_base_model(model).get_name()
                itrs = [model.get_iter(path) for path in paths]
                rows = [model[in_itr][:] for in_itr in itrs]
                bq_selected = self.is_bouquet_selected()
                fav_bouquet = None

                if bq_selected:
                    fav_bouquet = self.__bouquets.get(bq_selected, None)

                if model_name == self._FAV_LIST_NAME:
                    self.remove_favs(fav_bouquet, itrs, model)
                elif model_name == self._BOUQUETS_LIST_NAME:
                    self.delete_bouquets(itrs, model, bq_selected)
                elif model_name == self._SERVICE_LIST_NAME:
                    self.delete_services(bq_selected, itrs, model, rows)

                self.on_view_focus(view, None)

                return rows

    def remove_favs(self, fav_bouquet, itrs, model):
        """ Deleting bouquet services """
        if fav_bouquet:
            for itr in itrs:
                del fav_bouquet[int(model.get_path(itr)[0])]
                self.__fav_model.remove(itr)
        self.update_fav_num_column(model)

    def delete_services(self, bq_selected, itrs, model, rows):
        """ Deleting services """
        srv_itrs = [self.__services_model_filter.convert_iter_to_child_iter(
            model.convert_iter_to_child_iter(itr)) for itr in itrs]
        for s_itr in srv_itrs:
            self.__services_model.remove(s_itr)

        for row in rows:
            # There are channels with the same parameters except for the name.
            # None because it can have duplicates! Need fix
            fav_id = row[-2]
            for bq in self.__bouquets:
                services = self.__bouquets[bq]
                if services:
                    with suppress(ValueError):
                        services.remove(fav_id)
            self.__services.pop(fav_id, None)
        self.__fav_model.clear()

        if bq_selected:
            self.update_bouquet_channels(self.__fav_model, None, bq_selected)

    def delete_bouquets(self, itrs, model, bouquet):
        """ Deleting bouquets """
        for itr in itrs:
            if len(model.get_path(itr)) < 2:
                show_dialog(DialogType.ERROR, self.__main_window, "This item is not allowed to be removed!")
                return
            else:
                self.__bouquets.pop(bouquet)
                self.__fav_model.clear()
                self.__bouquets_model.remove(itr)

    def get_bouquet_file_name(self, bouquet):
        bouquet_file_name = "{}userbouquet.{}.{}".format(self.__options.get(self.__profile).get("data_dir_path"),
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
            while key in self.__bouquets:
                count += 1
                bq_name = "bouquet{}".format(count)
                key = "{}:{}".format(bq_name, bq_type)

            response = show_dialog(DialogType.INPUT, self.__main_window, bq_name)
            if response == Gtk.ResponseType.CANCEL:
                return

            bq = response, None, None, bq_type
            key = "{}:{}".format(response, bq_type)

            if model.iter_n_children(itr):  # parent
                ch_itr = model.insert(itr, 0, bq)
                scroll_to(model.get_path(ch_itr), view, paths)
            else:
                p_itr = model.iter_parent(itr)
                it = model.insert(p_itr, int(model.get_path(itr)[1]) + 1, bq) if p_itr else model.append(itr, bq)
                scroll_to(model.get_path(it), view, paths)
            self.__bouquets[key] = []

    def on_tool_edit(self, item):
        """ Edit tool bar button """
        if self.__services_view.is_focus():
            self.on_edit(self.__services_view)
        elif self.__fav_view.is_focus():
            self.on_edit(self.__fav_view)
        elif self.__bouquets_view.is_focus():
            self.on_edit(self.__bouquets_view)

    def on_bouquets_edit(self, view):
        """ Rename bouquets """
        bq_selected = self.is_bouquet_selected()
        if not bq_selected:
            show_dialog(DialogType.ERROR, self.__main_window, "This item is not allowed to edit!")
            return

        model, paths = view.get_selection().get_selected_rows()

        if paths:
            itr = model.get_iter(paths[0])
            bq_name, bq_type = model.get(itr, 0, 3)
            response = show_dialog(DialogType.INPUT, self.__main_window, bq_name)
            if response == Gtk.ResponseType.CANCEL:
                return

            model.set_value(itr, 0, response)
            self.__bouquets["{}:{}".format(response, bq_type)] = self.__bouquets.pop("{}:{}".format(bq_name, bq_type))

    def on_to_fav_move(self, view):
        """ Move items from app to fav list """
        selection = self.get_selection(view)

        if selection:
            self.receive_selection(view=self.__fav_view, drop_info=None, data=selection)

    def get_selection(self, view):
        """ Creates a string from the iterators of the selected rows """
        model, paths = view.get_selection().get_selected_rows()
        model = get_base_model(model)

        if len(paths) > 0:
            itrs = [model.get_iter(path) for path in paths]
            return "{}:{}".format(",".join([model.get_string_from_iter(itr) for itr in itrs]), model.get_name())

    def receive_selection(self, *, view, drop_info, data):
        """  Update fav view  after data received  """
        bq_selected = self.is_bouquet_selected()

        if not bq_selected:
            show_dialog(DialogType.ERROR, self.__main_window, "Error. No bouquet is selected!")
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
            fav_bouquet = self.__bouquets[bq_selected]

            if source == self._SERVICE_LIST_NAME:
                ext_model = self.__services_view.get_model()
                ext_itrs = [ext_model.get_iter_from_string(itr) for itr in itrs]
                ext_rows = [ext_model[ext_itr][:] for ext_itr in ext_itrs]
                dest_index -= 1
                for ext_row in ext_rows:
                    dest_index += 1
                    fav_id = ext_row[18]
                    ch = self.__services[fav_id]
                    model.insert(dest_index, (0, ch.coded, ch.service, ch.locked, ch.hide,
                                              ch.service_type, ch.pos, ch.fav_id, self.__picons.get(ch.picon_id, None)))
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
            self.__status_bar.push(1, getattr(e, "message", repr(e)))

    def update_fav_num_column(self, model):
        """ Iterate through model and updates values for Num column """
        model.foreach(lambda store, pth, itr: store.set_value(itr, 0, int(pth[0]) + 1))  # iter , column, value

    def update_bouquet_list(self):
        """ Update bouquet after move items """
        bq_selected = self.is_bouquet_selected()
        if bq_selected:
            fav_bouquet = self.__bouquets[bq_selected]
            fav_bouquet.clear()
            for row in self.__fav_model:
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
            menu.popup(None, None, None, None, event.button, event.time)

    @run_idle
    def on_satellite_editor_show(self, model):
        """ Shows satellites editor dialog """
        show_satellites_dialog(self.__main_window, self.__options.get(self.__profile))

    def on_data_open(self, model):
        response = show_dialog(DialogType.CHOOSER, self.__main_window, options=self.__options.get(self.__profile))
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return
        self.open_data(response)

    @run_idle
    def open_data(self, data_path=None):
        """ Opening data and fill views. """
        self.clear_current_data()

        data_path = self.__options.get(self.__profile).get("data_dir_path") if data_path is None else data_path
        try:
            self.append_blacklist(data_path)
            self.append_bouquets(data_path)
            self.append_services(data_path)
            self.update_services_counts(len(self.__services_model))
            self.update_picons()
            self.__picons_download_tool_button.set_sensitive(len(self.__services_model))
        except FileNotFoundError as e:
            show_dialog(DialogType.ERROR, self.__main_window, getattr(e, "message", str(e)) +
                        "\n\nPlease, download files from receiver or setup your path for read data!")
        except SyntaxError as e:
            show_dialog(DialogType.ERROR, self.__main_window, str(e))

    def append_blacklist(self, data_path):
        black_list = get_blacklist(data_path)
        if black_list:
            self.__blacklist.update(black_list)

    def append_bouquets(self, data_path):
        for bouquet in get_bouquets(data_path, Profile(self.__profile)):
            parent = self.__bouquets_model.append(None, [bouquet.name, None, None, bouquet.type])
            for bt in bouquet.bouquets:
                name, bt_type, locked, hidden = bt.name, bt.type, bt.locked, bt.hidden
                self.__bouquets_model.append(parent, [name, locked, hidden, bt_type])
                services = []
                agr = [None] * 9
                for srv in bt.services:
                    fav_id = srv.data
                    # IPTV and MARKER services
                    s_type = srv.type
                    if s_type is BqServiceType.MARKER or s_type is BqServiceType.IPTV:
                        srv = Service(*agr[0:3], srv.name, *agr[0:3], s_type.name, *agr, srv.num, fav_id, None)
                        self.__services[fav_id] = srv
                    services.append(fav_id)
                self.__bouquets["{}:{}".format(name, bt_type)] = services

    def append_services(self, data_path):
        try:
            services = get_services(data_path, Profile(self.__profile))
        except Exception as e:
            print(e)
            log("Append services error: " + str(e))
            show_dialog(DialogType.ERROR, self.__main_window, "Error opening data!")
        else:
            if services:
                for srv in services:
                    #  adding channels to dict with fav_id as keys
                    self.__services[srv.fav_id] = srv
                    self.__services_model.append(srv)

    def clear_current_data(self):
        """ Clearing current data from lists """
        self.__bouquets_model.clear()
        self.__fav_model.clear()
        self.__services_model.clear()
        self.__blacklist.clear()
        self.__services.clear()
        self.__rows_buffer.clear()
        self.__bouquets.clear()

    def on_data_save(self, *args):
        if show_dialog(DialogType.QUESTION, self.__main_window) == Gtk.ResponseType.CANCEL:
            return

        path = self.__options.get(self.__profile).get("data_dir_path")
        backup_path = path + "backup/"
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        # backup files in data dir(skipping dirs and satellites.xml)
        for file in filter(lambda f: f != "satellites.xml" and os.path.isfile(os.path.join(path, f)), os.listdir(path)):
            shutil.move(os.path.join(path, file), backup_path + file)

        bouquets = []
        services_model = self.__services_view.get_model()

        def parse_bouquets(model, b_path, itr):
            bqs = None
            if model.iter_has_child(itr):
                bqs = []
                num_of_children = model.iter_n_children(itr)
                for num in range(num_of_children):
                    bq_itr = model.iter_nth_child(itr, num)
                    bq_name, locked, hidden, bq_type = model.get(bq_itr, 0, 1, 2, 3)
                    favs = self.__bouquets["{}:{}".format(bq_name, bq_type)]
                    bq = Bouquet(bq_name, bq_type, [self.__services.get(f_id, None) for f_id in favs], locked, hidden)
                    bqs.append(bq)
            if len(b_path) == 1:
                bouquets.append(Bouquets(*model.get(itr, 0, 3), bqs if bqs else []))

        profile = Profile(self.__profile)
        # Getting bouquets
        self.__bouquets_view.get_model().foreach(parse_bouquets)
        write_bouquets(path, bouquets, profile)
        # Getting services
        services = [Service(*row[:]) for row in services_model]
        write_services(path, services, profile)
        # removing bouquet files
        if profile is Profile.ENIGMA_2:
            # blacklist
            write_blacklist(path, self.__blacklist)

    def on_services_selection(self, model, path, column):
        self.delete_selection(self.__fav_view)
        self.update_service_bar(model, path)

    def update_service_bar(self, model, path):
        def_val = "Unknown"
        cas = model.get_value(model.get_iter(path), 0)
        if not cas:
            return
        cas_values = list(filter(lambda val: val.startswith("C:"), cas.split(",")))
        self.__cas_label.set_text(",".join(map(str, sorted(set(CAS.get(val, def_val) for val in cas_values)))))

    def on_fav_selection(self, model, path, column):
        self.delete_selection(self.__services_view)

    def on_bouquets_selection(self, model, path, column):
        self.__fav_model.clear()

        if self.__bouquets_view.row_expanded(path):
            self.__bouquets_view.collapse_row(path)
        else:
            self.__bouquets_view.expand_row(path, column)

        if len(path) > 1:
            self.delete_selection(self.__services_view)
            self.update_bouquet_channels(model, path)

    def update_bouquet_channels(self, model, path, bq_key=None):
        """ Updates list of bouquet channels """
        tree_iter = None
        if path:
            tree_iter = model.get_iter(path)

        key = bq_key if bq_key else "{}:{}".format(*model.get(tree_iter, 0, 3))
        services = self.__bouquets[key]

        for num, ch_id in enumerate(services):
            channel = self.__services.get(ch_id, None)
            if channel:
                self.__fav_model.append((num + 1, channel.coded, channel.service, channel.locked,
                                         channel.hide, channel.service_type, channel.pos, channel.fav_id,
                                         self.__picons.get(channel.picon_id, None)))

    def is_bouquet_selected(self):
        """ Checks whether the bouquet is selected

            returns 'name:type' of selected bouquet or False
        """
        model, path = self.__bouquets_view.get_selection().get_selected_rows()

        if not path or len(path[0]) < 2:
            return False

        return "{}:{}".format(*model.get(model.get_iter(path), 0, 3))

    @run_idle
    def delete_selection(self, view, *args):
        """ Used for clear selection on given view(s) """
        for v in [view, *args]:
            v.get_selection().unselect_all()

    @run_idle
    def on_preferences(self, item):
        response = show_settings_dialog(self.__main_window, self.__options)
        if response != Gtk.ResponseType.CANCEL:
            profile = self.__options.get("profile")
            self.__status_bar.push(0, "Current IP: " + self.__options.get(profile).get("host"))
            if profile != self.__profile:
                self.__profile_label.set_text("Enigma 2 v.4" if Profile(profile) is Profile.ENIGMA_2 else "Neutrino-MP")
                self.__profile = profile
                self.clear_current_data()
                self.update_services_counts()
                self.__picons_download_tool_button.set_sensitive(len(self.__services_model))

    def on_tree_view_key_release(self, view, event):
        """  Handling  keystrokes  """
        key = event.keyval
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        alt = event.state & Gdk.ModifierType.MOD1_MASK
        model = get_base_model(view.get_model())
        model_name = model.get_name()

        if key == Gdk.KEY_Delete:
            self.on_delete(view)
        elif ctrl and key in (Gdk.KEY_Up, Gdk.KEY_Page_Up, Gdk.KEY_KP_Page_Up):  # KEY_KP_Page_Up for laptop!
            self.move_items(key)
        elif ctrl and key in (Gdk.KEY_Down, Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
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
        elif ctrl and key == Gdk.KEY_E or key == Gdk.KEY_e or key == Gdk.KEY_F2:
            self.on_edit(view)
        elif key == Gdk.KEY_Left or key == Gdk.KEY_Right:
            view.do_unselect_all(view)

    def on_download(self, item):
        show_download_dialog(transient=self.__main_window,
                             options=self.__options.get(self.__profile),
                             open_data=self.open_data,
                             profile=Profile(self.__profile))

    @run_idle
    def on_view_focus(self, view, focus_event):
        profile = Profile(self.__profile)
        model = get_base_model(view.get_model())
        model_name = model.get_name()
        not_empty = len(model) > 0  # if  > 0 model has items

        if model_name == self._BOUQUETS_LIST_NAME:
            for elem in self.__tool_elements:
                self.__tool_elements[elem].set_sensitive(False)
            for elem in self._BOUQUET_ELEMENTS:
                self.__tool_elements[elem].set_sensitive(not_empty)
            if profile is Profile.NEUTRINO_MP:
                for elem in self._LOCK_HIDE_ELEMENTS:
                    self.__tool_elements[elem].set_sensitive(not_empty)
        else:
            is_service = model_name == self._SERVICE_LIST_NAME
            for elem in self._FAV_ELEMENTS:
                if elem in ("paste_tool_button", "paste_menu_item", "fav_paste_popup_item"):
                    self.__tool_elements[elem].set_sensitive(not is_service and self.__rows_buffer)
                elif elem in self._FAV_ONLY_ELEMENTS:
                    if profile is Profile.ENIGMA_2:
                        self.__tool_elements[elem].set_sensitive(self.is_bouquet_selected() and not is_service)
                else:
                    self.__tool_elements[elem].set_sensitive(not_empty and not is_service)
            for elem in self._SERVICE_ELEMENTS:
                self.__tool_elements[elem].set_sensitive(not_empty and is_service)
            for elem in self._BOUQUET_ELEMENTS:
                self.__tool_elements[elem].set_sensitive(False)
            for elem in self._LOCK_HIDE_ELEMENTS:
                self.__tool_elements[elem].set_sensitive(not_empty and profile is Profile.ENIGMA_2)

        for elem in self._COMMONS_ELEMENTS:
            self.__tool_elements[elem].set_sensitive(not_empty)

    def on_hide(self, item):
        self.set_service_flags(FLAG.HIDE)

    def on_locked(self, item):
        self.set_service_flags(FLAG.LOCK)

    def set_service_flags(self, flag):
        profile = Profile(self.__profile)
        bq_selected = self.is_bouquet_selected()
        if profile is Profile.ENIGMA_2:
            if set_flags(flag, self.__services_view, self.__fav_view, self.__services, self.__blacklist):
                if bq_selected:
                    self.__fav_model.clear()
                    self.update_bouquet_channels(self.__fav_model, None, bq_selected)
        elif profile is Profile.NEUTRINO_MP:
            if bq_selected:
                model, path = self.__bouquets_view.get_selection().get_selected()
                value = model.get_value(path, 1 if flag is FLAG.LOCK else 2)
                value = None if value else LOCKED_ICON if flag is FLAG.LOCK else HIDE_ICON
                model.set_value(path, 1 if flag is FLAG.LOCK else 2, value)

    @run_idle
    def on_model_changed(self, model, path, itr=None):
        model_name = model.get_name()

        if model_name == self._FAV_LIST_NAME:
            self.__fav_count_label.set_text(str(len(model)))
        elif model_name == self._SERVICE_LIST_NAME:
            self.update_services_counts(len(model))
        elif model_name == self._BOUQUETS_LIST_NAME:
            self.__bouquets_count_label.set_text(str(len(self.__bouquets.keys())))

    @lru_cache(maxsize=1)
    def update_services_counts(self, size=0):
        """ Updates counters for services. May be temporary! """
        tv_count = 0
        radio_count = 0
        data_count = 0

        for ch in self.__services.values():
            ch_type = ch.service_type
            if ch_type in ("TV", "TV (HD)"):
                tv_count += 1
            elif ch_type == "Radio":
                radio_count += 1
            elif ch_type == "Data":
                data_count += 1

        self.__tv_count_label.set_text(str(tv_count))
        self.__radio_count_label.set_text(str(radio_count))
        self.__data_count_label.set_text(str(data_count))

    def on_import_m3u(self, item):
        """ Imports iptv from m3u files. """
        response = get_chooser_dialog(self.__main_window, self.__options.get(self.__profile), "*.m3u", "m3u files")
        if response == Gtk.ResponseType.CANCEL:
            return

        if not str(response).endswith("m3u"):
            show_dialog(DialogType.ERROR, self.__main_window, text="No m3u file is selected!")
            return

        channels = parse_m3u(response)
        bq_selected = self.is_bouquet_selected()
        if channels and bq_selected:
            bq_services = self.__bouquets.get(bq_selected)
            self.__fav_model.clear()
            for ch in channels:
                self.__services[ch.fav_id] = ch
                bq_services.append(ch.fav_id)
            self.update_bouquet_channels(self.__fav_model, None, bq_selected)

    def on_insert_marker(self, view):
        """ Inserts marker into bouquet services list. """
        insert_marker(view, self.__bouquets, self.is_bouquet_selected(), self.__services, self.__main_window)
        self.update_fav_num_column(self.__fav_model)

    def on_edit_marker(self, view):
        edit_marker(view, self.__bouquets, self.is_bouquet_selected(), self.__services, self.__main_window)

    @run_idle
    def on_fav_popup(self, view, event):
        model, paths = view.get_selection().get_selected_rows()
        self.__fav_edit_marker_popup_item.set_sensitive(
            len(paths) == 1 and model.get_value(model.get_iter(paths[0]), 5) == BqServiceType.MARKER.name)

    def on_locate_in_services(self, view):
        locate_in_services(view, self.__services_view, self.__main_window)

    @run_idle
    def on_picons_loader_show(self, item):
        ids = {}
        if Profile(self.__profile) is Profile.ENIGMA_2:
            for r in self.__services_model:
                data = r[9].split("_")
                ids["{}:{}:{}".format(data[3], data[5], data[6])] = r[9]

        dialog = PiconsDialog(self.__main_window, self.__options.get(self.__profile), ids, Profile(self.__profile))
        dialog.show()
        self.update_picons()

    @run_idle
    def on_filter_toggled(self, toggle_button: Gtk.ToggleToolButton):
        self.__filter_info_bar.set_visible(toggle_button.get_active())

    @run_idle
    def on_filter_changed(self, entry):
        self.__services_model_filter.refilter()

    def services_filter_function(self, model, iter, data):
        if self.__services_model_filter is None or self.__services_model_filter == "None":
            return True
        else:
            return self.__filter_entry.get_text() in str(model.get(iter, 3, 6, 7, 10, 11, 12, 13, 14, 15, 16))

    def on_search_toggled(self, toggle_button: Gtk.ToggleToolButton):
        self.__search_info_bar.set_visible(toggle_button.get_active())

    @run_idle
    def on_search(self, entry, event):
        search(entry.get_text(),
               self.__services_view,
               self.__fav_view,
               self.__bouquets_view,
               self.__services,
               self.__bouquets)

    @run_idle
    def update_picons(self):
        update_picons(self.__options.get(self.__profile).get("picons_dir_path"), self.__picons, self.__services_model)

    def on_assign_picon(self, view):
        assign_picon(self.get_target_view(view),
                     self.__services_view,
                     self.__fav_view,
                     self.__main_window,
                     self.__picons,
                     self.__options.get(self.__profile),
                     self.__services)

    def on_remove_picon(self, view):
        remove_picon(self.get_target_view(view),
                     self.__services_view,
                     self.__fav_view, self.__picons,
                     self.__options.get(self.__profile))

    def on_reference_picon(self, view):
        """ Copying picon id to clipboard """
        copy_picon_reference(self.get_target_view(view), view, self.__services, self.__clipboard, self.__main_window)

    def get_target_view(self, view):
        return ViewTarget.SERVICES if Gtk.Buildable.get_name(view) == "services_tree_view" else ViewTarget.FAV


def start_app():
    MainAppWindow()
    Gtk.main()


def close_app():
    Gtk.main_quit()


if __name__ == "__main__":
    pass

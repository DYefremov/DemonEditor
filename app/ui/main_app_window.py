import os
from contextlib import suppress

from app.commons import run_idle
from app.eparser import get_channels, get_bouquets, write_bouquets, write_channels, Bouquets, Bouquet, Channel
from app.properties import get_config, write_config
from . import Gtk, Gdk
from .dialogs import show_dialog
from .download_dialog import show_download_dialog
from .satellites_dialog import show_satellites_dialog
from .settings_dialog import show_settings_dialog


class MainAppWindow:
    _SERVICE_LIST_NAME = "services_list_store"
    _FAV_LIST_NAME = "fav_list_store"
    _BOUQUETS_LIST_NAME = "bouquets_tree_store"
    # dynamically active elements depending on the selected view
    _SERVICE_ELEMENTS = ("copy_tool_button", "to_fav_tool_button", "copy_menu_item", "services_to_fav_move_popup_item")
    _BOUQUET_ELEMENTS = ("edit_tool_button", "new_tool_button", "bouquets_new_popup_item", "bouguets_edit_popup_item")
    _REMOVE_ELEMENTS = ("remove_tool_button", "delete_menu_item", "services_remove_popup_item",
                        "bouquets_remove_popup_item", "fav_remove_popoup_item")
    _FAV_ELEMENTS = ("up_tool_button", "down_tool_button", "cut_tool_button", "paste_tool_button", "cut_menu_item",
                     "paste_menu_item", "fav_cut_popoup_item", "fav_paste_popup_item")
    __DYNAMIC_ELEMENTS = ("up_tool_button", "down_tool_button", "cut_tool_button", "copy_tool_button",
                          "paste_tool_button", "to_fav_tool_button", "new_tool_button", "remove_tool_button",
                          "cut_menu_item", "copy_menu_item", "paste_menu_item", "delete_menu_item", "edit_tool_button",
                          "services_to_fav_move_popup_item", "services_remove_popup_item", "fav_cut_popoup_item",
                          "fav_paste_popup_item", "bouquets_new_popup_item", "bouguets_edit_popup_item",
                          "services_remove_popup_item", "bouquets_remove_popup_item", "fav_remove_popoup_item")

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
                    "on_delete": self.on_delete,
                    "on_new_bouquet": self.on_new_bouquet,
                    "on_bouquets_edit": self.on_bouquets_edit,
                    "on_to_fav_move": self.on_to_fav_move,
                    "on_services_tree_view_drag_data_get": self.on_services_tree_view_drag_data_get,
                    "on_fav_tree_view_drag_data_get": self.on_fav_tree_view_drag_data_get,
                    "on_fav_tree_view_drag_data_received": self.on_fav_tree_view_drag_data_received,
                    "on_view_popup_menu": self.on_view_popup_menu,
                    "on_view_focus": self.on_view_focus}

        self.__options = get_config()
        # Used for copy/paste. When adding the previous data will not be deleted.
        # Clearing only after the insertion!
        self.__rows_buffer = []
        self.__channels = {}
        self.__bouquets = {}

        builder = Gtk.Builder()
        builder.add_from_file("app/ui/main_window.glade")
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
        self.__status_bar.push(0, "Current IP: " + self.__options["host"])
        # dynamically active elements depending on the selected view
        self.__tool_elements = {k: builder.get_object(k) for k in self.__DYNAMIC_ELEMENTS}
        builder.connect_signals(handlers)
        self.init_drag_and_drop()  # drag and drop
        self.__main_window.show_all()

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
        show_dialog("about_dialog", self.__main_window)

    def move_items(self, key):
        """ Move items in fav tree view """
        selection = self.__fav_view.get_selection()
        model, paths = selection.get_selected_rows()

        if paths:
            # for correct down move!
            if key in (Gdk.KEY_Down, Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
                paths = reversed(paths)

            for path in paths:
                itr = model.get_iter(path)
                if key == Gdk.KEY_Down:
                    next_itr = model.iter_next(itr)
                    if next_itr:
                        model.move_after(itr, next_itr)
                elif key == Gdk.KEY_Up:
                    prev_itr = model.iter_previous(itr)
                    if prev_itr:
                        model.move_before(itr, prev_itr)
                elif key == Gdk.KEY_Page_Up or key == Gdk.KEY_KP_Page_Up:
                    up_itr = model.get_iter(self.__fav_view.get_cursor()[0])
                    if up_itr:
                        model.move_before(itr, up_itr)
                elif key == Gdk.KEY_Page_Down or key == Gdk.KEY_KP_Page_Down:
                    down_itr = model.get_iter(self.__fav_view.get_cursor()[0])
                    if down_itr:
                        model.move_after(itr, down_itr)

    def on_cut(self, view):
        for row in self.on_delete(view):
            self.__rows_buffer.append(row)

    def on_copy(self, view):
        model, paths = view.get_selection().get_selected_rows()
        itrs = [model.get_iter(path) for path in paths]
        rows = [(0, *model.get(in_itr, 2, 4, 11, 13)) for in_itr in itrs]
        self.__rows_buffer.extend(rows)

    def on_paste(self, view):
        selection = view.get_selection()
        dest_index = 0
        bq_selected = self.is_bouquet_selected()

        if not bq_selected:
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

    def on_delete(self, item):
        """ Delete selected items from views

            returns deleted rows list!
        """
        for view in [self.__services_view, self.__fav_view, self.__bouquets_view]:
            if view.is_focus():
                selection = view.get_selection()
                model, paths = selection.get_selected_rows()
                model_name = model.get_name()
                itrs = [model.get_iter(path) for path in paths]
                rows = [model.get(in_itr, *[x for x in range(view.get_n_columns())]) for in_itr in itrs]
                bq_selected = self.is_bouquet_selected()
                fav_bouquet = None

                if bq_selected:
                    fav_bouquet = self.__bouquets.get(bq_selected, None)

                for itr in itrs:
                    if fav_bouquet and model_name == self._FAV_LIST_NAME:
                        del fav_bouquet[int(model.get_path(itr)[0])]
                    if model_name == self._BOUQUETS_LIST_NAME:
                        if len(model.get_path(itr)) < 2:
                            show_dialog("error_dialog", self.__main_window, "This item is not allowed to be removed!")
                            return
                        else:
                            self.delete_bouquet(bq_selected)
                    model.remove(itr)
                if model_name == self._FAV_LIST_NAME:
                    self.update_fav_num_column(model)
                elif model_name == self._SERVICE_LIST_NAME:
                    self.delete_services(bq_selected, rows)

                self.on_view_focus(view, None)

                return rows

    def delete_services(self, bq_selected, rows):
        """ Deleting services """
        for row in rows:
            # There are channels with the same parameters except for the name.
            # None because it can have duplicates! Need fix
            fav_id = row[-2]
            for bq in self.__bouquets:
                services = self.__bouquets[bq]
                with suppress(ValueError):
                    services.remove(fav_id)
            self.__channels.pop(fav_id, None)
        self.__fav_model.clear()

        if bq_selected:
            self.update_bouquet_channels(self.__fav_model, None, bq_selected)

    def delete_bouquet(self, bouquet):
        """ Deleting bouquet """
        self.__bouquets.pop(bouquet)
        self.__fav_model.clear()
        # removing bouquet file
        bqf = "{}userbouquet.{}.{}".format(self.__options["data_dir_path"], *bouquet.split(":"))
        with suppress(FileNotFoundError):
            os.remove(bqf)

    def on_new_bouquet(self, view):
        """ Creates a new item in the bouquets tree """
        model, paths = view.get_selection().get_selected_rows()

        if paths:
            itr = model.get_iter(paths[0])
            bq_type = model.get_value(itr, 1)
            bq_name = "bouquet"
            count = 0
            key = "{}:{}".format(bq_name, bq_type)
            #  Generating name of new bouquet
            while key in self.__bouquets:
                count += 1
                bq_name = "bouquet{}".format(count)
                key = "{}:{}".format(bq_name, bq_type)

            response = show_dialog("input_dialog", self.__main_window, bq_name)

            if response == Gtk.ResponseType.CANCEL:
                return

            bq = response, bq_type

            if model.iter_n_children(itr):  # parent
                model.insert(itr, 0, bq)
            else:
                parent_itr = model.iter_parent(itr)
                if parent_itr:
                    index = int(model.get_path(itr)[1]) + 1
                    model.insert(parent_itr, index, bq)
                else:
                    model.append(itr, bq)
            self.__bouquets[key] = []

    def on_bouquets_edit(self, view):
        """ Rename bouquets """
        if not self.is_bouquet_selected():
            show_dialog("error_dialog", self.__main_window, "This item is not allowed to edit!")
            return

        model, paths = view.get_selection().get_selected_rows()

        if paths:
            itr = model.get_iter(paths[0])
            bq_name, bq_type = model.get(itr, 0, 1)
            response = show_dialog("input_dialog", self.__main_window, bq_name)

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
        selection = view.get_selection()
        model, paths = selection.get_selected_rows()

        if len(paths) > 0:
            itrs = [model.get_iter(path) for path in paths]
            return "{}:{}".format(",".join([model.get_string_from_iter(itr) for itr in itrs]), model.get_name())

    def receive_selection(self, *, view, drop_info, data):
        """  Update fav view  after data received  """
        bq_selected = self.is_bouquet_selected()

        if not bq_selected:
            show_dialog("error_dialog", self.__main_window, "Error. No bouquet is selected!")
            return

        model = view.get_model()
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
                ext_rows = [ext_model.get(ext_itr, *[x for x in range(self.__services_view.get_n_columns())]) for
                            ext_itr in
                            ext_itrs]
                dest_index -= 1
                for ext_row in ext_rows:
                    dest_index += 1
                    fav_id = ext_row[13]
                    channel = self.__channels[fav_id]
                    model.insert(dest_index, (0, channel.service, channel.service_type, channel.pos, channel.fav_id))
                    fav_bouquet.insert(dest_index, channel.fav_id)
            elif source == self._FAV_LIST_NAME:
                in_itrs = [model.get_iter_from_string(itr) for itr in itrs]
                in_rows = [model.get(in_itr, *[x for x in range(view.get_n_columns())]) for in_itr in in_itrs]
                for row in in_rows:
                    model.insert(dest_index, row)
                    fav_bouquet.insert(dest_index, row[4])
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
                fav_bouquet.append(row[4])

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

    def on_satellite_editor_show(self, model):
        """ Shows satellites editor dialog """
        show_satellites_dialog(self.__main_window, self.__options)

    def on_data_open(self, model):
        if show_dialog("path_chooser_dialog", self.__main_window, options=self.__options) == Gtk.ResponseType.CANCEL:
            return
        self.open_data()

    @run_idle
    def open_data(self):
        """ Opening data and fill views. """
        self.__bouquets_model.clear()
        self.__fav_model.clear()
        self.__services_model.clear()
        data_path = self.__options["data_dir_path"]
        try:
            self.append_services(data_path)
            self.append_bouquets(data_path)
        except FileNotFoundError as e:
            show_dialog("error_dialog", self.__main_window, getattr(e, "message", str(e)) +
                        "\n\nPlease, download files from receiver or setup your path for read data!")

    def append_bouquets(self, data_path):
        for bouquet in get_bouquets(data_path):
            parent = self.__bouquets_model.append(None, [bouquet.name, bouquet.type])
            for bt in bouquet.bouquets:
                name, bt_type = bt.name, bt.type
                self.__bouquets_model.append(parent, [name, bt_type])
                self.__bouquets["{}:{}".format(name, bt_type)] = bt.services

    def append_services(self, data_path):
        for ch in get_channels(data_path + "lamedb"):
            #  adding channels to dict with fav_id as keys
            self.__channels[ch.fav_id] = ch
            self.__services_model.append(ch)

    def on_data_save(self, *args):
        if show_dialog("question_dialog", self.__main_window) == Gtk.ResponseType.CANCEL:
            return

        path = self.__options["data_dir_path"]
        bouquets = []
        services_model = self.__services_view.get_model()

        def parse_bouquets(model, b_path, itr):
            if model.iter_has_child(itr):
                num_of_children = model.iter_n_children(itr)
                bqs = []

                for num in range(num_of_children):
                    bq_itr = model.iter_nth_child(itr, num)
                    bq_name, bq_type = model.get(bq_itr, 0, 1)
                    favs = self.__bouquets["{}:{}".format(bq_name, bq_type)]
                    bq = Bouquet(bq_name, bq_type, [self.__channels[f_id] for f_id in favs])
                    bqs.append(bq)
                bqs = Bouquets(*model.get(itr, 0, 1), bqs)
                bouquets.append(bqs)

        # Getting bouquets
        self.__bouquets_view.get_model().foreach(parse_bouquets)
        write_bouquets(path, bouquets, self.__bouquets)
        # Getting services
        services = [Channel(*row[:]) for row in services_model]
        write_channels(path, services)

    def on_services_selection(self, model, path, column):
        self.delete_selection(self.__fav_view)

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

        key = bq_key if bq_key else "{}:{}".format(*model.get(tree_iter, 0, 1))
        services = self.__bouquets[key]

        for num, ch_id in enumerate(services):
            channel = self.__channels.get(ch_id, None)
            if channel:
                self.__fav_model.append((num + 1, channel.service, channel.service_type, channel.pos, channel.fav_id))

    def is_bouquet_selected(self):
        """ Checks whether the bouquet is selected

            returns 'name:type' of selected bouquet or False
        """
        selection = self.__bouquets_view.get_selection()
        model, path = selection.get_selected_rows()

        if not path or len(path[0]) < 2:
            return False

        return "{}:{}".format(*model.get(model.get_iter(path), 0, 1))

    def delete_selection(self, view, *args):
        """ Used for clear selection on given view(s) """
        for v in [view, *args]:
            v.get_selection().unselect_all()

    def on_preferences(self, item):
        show_settings_dialog(self.__main_window, self.__options)
        self.__status_bar.push(0, "Current IP: " + self.__options["host"])

    def on_tree_view_key_release(self, view, event):
        """  Handling  keystrokes  """
        key = event.keyval
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        alt = event.state & Gdk.ModifierType.MOD1_MASK
        model_name = view.get_model().get_name()

        if key == Gdk.KEY_Delete:
            self.on_delete(view)
        elif ctrl and key in (Gdk.KEY_Up, Gdk.KEY_Page_Up, Gdk.KEY_KP_Page_Up):  # KEY_KP_Page_Up for laptop!
            self.move_items(key)
        elif ctrl and key in (Gdk.KEY_Down, Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
            self.move_items(key)
        elif model_name == self._FAV_LIST_NAME and key == Gdk.KEY_Control_L or key == Gdk.KEY_Control_R:
            self.update_fav_num_column(view.get_model())
            self.update_bouquet_list()
        elif key == Gdk.KEY_Insert:
            # Move items from app to fav list
            if model_name == self._SERVICE_LIST_NAME:
                self.on_to_fav_move(view)
            elif model_name == self._BOUQUETS_LIST_NAME:
                self.on_new_bouquet(view)
        elif key == Gdk.KEY_F2 and model_name == self._BOUQUETS_LIST_NAME:
            self.on_bouquets_edit(view)
        elif ctrl and (key == Gdk.KEY_c or key == Gdk.KEY_C) and model_name == self._SERVICE_LIST_NAME:
            self.on_copy(view)
        elif ctrl and key == Gdk.KEY_x or key == Gdk.KEY_X:
            if model_name == self._FAV_LIST_NAME:
                self.on_cut(view)
        elif ctrl and key == Gdk.KEY_v or key == Gdk.KEY_V:
            self.on_paste(view)
        elif ctrl and key == Gdk.KEY_s or key == Gdk.KEY_S:
            self.on_data_save()
        elif key == Gdk.KEY_space and model_name == self._FAV_LIST_NAME:
            pass

    def on_download(self, item):
        show_download_dialog(self.__main_window, self.__options, self.open_data)

    @run_idle
    def on_view_focus(self, view, focus_event):
        model = view.get_model()
        model_name = model.get_name()
        not_empty = len(model) > 0  # if  > 0 model has items

        if model_name == self._BOUQUETS_LIST_NAME:
            for elem in self.__tool_elements:
                self.__tool_elements[elem].set_sensitive(False)
            for elem in self._BOUQUET_ELEMENTS:
                self.__tool_elements[elem].set_sensitive(not_empty)
        else:
            is_service = model_name == self._SERVICE_LIST_NAME
            for elem in self._FAV_ELEMENTS:
                if elem in ("paste_tool_button", "paste_menu_item", "fav_paste_popup_item"):
                    self.__tool_elements[elem].set_sensitive(not_empty and not is_service and self.__rows_buffer)
                else:
                    self.__tool_elements[elem].set_sensitive(not_empty and not is_service)
            for elem in self._SERVICE_ELEMENTS:
                self.__tool_elements[elem].set_sensitive(not_empty and is_service)
            for elem in self._BOUQUET_ELEMENTS:
                self.__tool_elements[elem].set_sensitive(False)

        for elem in self._REMOVE_ELEMENTS:
            self.__tool_elements[elem].set_sensitive(not_empty)


def start_app():
    MainAppWindow()
    Gtk.main()


def close_app():
    Gtk.main_quit()


if __name__ == "__main__":
    pass

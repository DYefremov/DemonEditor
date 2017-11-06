from contextlib import suppress

from main.commons import run_task
from main.eparser import get_channels, get_bouquets, write_bouquets, write_channels, Bouquets, Bouquet, Channel
from main.properties import get_config, write_config
from . import Gtk, Gdk
from .download_dialog import show_download_dialog
from .satellites_dialog import show_satellites_dialog
from .settings_dialog import show_settings_dialog

SERVICE_LIST_NAME = "services_list_store"
FAV_LIST_NAME = "fav_list_store"
BOUQUETS_LIST_NAME = "bouquets_tree_store"

__main_window = None
__status_bar = None
__options = get_config()
__services_model = None
__bouquets_model = None
__fav_model = None
__services_view = None
__fav_view = None
__bouquets_view = None
# Used for copy/paste
# When adding the previous data will not be deleted.
# Clearing only after the insertion!
__rows_buffer = []
__channels = {}
__bouquets = {}
# dynamically active elements depending on the selected view
__tool_elements = None
_SERVICE_ELEMENTS = ("copy_tool_button", "to_fav_tool_button", "copy_menu_item")
_BOUQUET_ELEMENTS = ("edit_tool_button", "new_tool_button")
_REMOVE_ELEMENTS = ("remove_tool_button", "delete_menu_item")
_FAV_ELEMENTS = ("up_tool_button", "down_tool_button", "cut_tool_button",
                 "paste_tool_button", "cut_menu_item", "paste_menu_item")


def on_about_app(item):
    show_dialog("about_dialog")


def get_handlers():
    return {
        "on_close_main_window": on_quit,
        "on_resize": on_resize,
        "on_about_app": on_about_app,
        "on_preferences": on_preferences,
        "on_download": on_download,
        "on_data_open": on_data_open,
        "on_data_save": on_data_save,
        "on_tree_view_key_release": on_tree_view_key_release,
        "on_bouquets_selection": on_bouquets_selection,
        "on_satellite_editor_show": on_satellite_editor_show,
        "on_services_selection": on_services_selection,
        "on_fav_selection": on_fav_selection,
        "on_up": on_up,
        "on_down": on_down,
        "on_cut": on_cut,
        "on_copy": on_copy,
        "on_paste": on_paste,
        "on_delete": on_delete,
        "on_new_bouquet": on_new_bouquet,
        "on_bouquets_edit": on_bouquets_edit,
        "on_to_fav_move": on_to_fav_move,
        "on_services_tree_view_drag_data_get": on_services_tree_view_drag_data_get,
        "on_fav_tree_view_drag_data_get": on_fav_tree_view_drag_data_get,
        "on_fav_tree_view_drag_data_received": on_fav_tree_view_drag_data_received,
        "on_view_popup_menu": on_view_popup_menu,
        "on_view_focus": on_view_focus
    }


def on_quit(*args):
    """  Called before app quit """
    write_config(__options)  # storing current config
    Gtk.main_quit()


def on_resize(window):
    """ Stores new size properties for main window after resize """
    __options["window_size"] = window.get_size()


def on_up(item):
    move_items(Gdk.KEY_Up)


def on_down(item):
    move_items(Gdk.KEY_Down)


def move_items(key):
    """ Move items in fav tree view """
    selection = __fav_view.get_selection()
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
                up_itr = model.get_iter(__fav_view.get_cursor()[0])
                if up_itr:
                    model.move_before(itr, up_itr)
            elif key == Gdk.KEY_Page_Down or key == Gdk.KEY_KP_Page_Down:
                down_itr = model.get_iter(__fav_view.get_cursor()[0])
                if down_itr:
                    model.move_after(itr, down_itr)


def on_cut(view):
    for row in on_delete(view):
        __rows_buffer.append(row)


def on_copy(view):
    model, paths = view.get_selection().get_selected_rows()
    itrs = [model.get_iter(path) for path in paths]
    rows = [(0, *model.get(in_itr, 2, 4, 11, 13)) for in_itr in itrs]
    __rows_buffer.extend(rows)


def on_paste(view):
    selection = view.get_selection()
    dest_index = 0
    bq_selected = is_bouquet_selected()

    if not bq_selected:
        return

    fav_bouquet = __bouquets[bq_selected]
    model, paths = selection.get_selected_rows()

    if paths:
        dest_index = int(paths[0][0])

    for row in __rows_buffer:
        dest_index += 1
        model.insert(dest_index, row)
        fav_bouquet.insert(dest_index, row[-1])

    if model.get_name() == FAV_LIST_NAME:
        update_fav_num_column(model)

    __rows_buffer.clear()


def on_delete(item):
    """ Delete selected items from views

        returns deleted rows list!
    """
    for view in [__services_view, __fav_view, __bouquets_view]:
        if view.is_focus():
            selection = view.get_selection()
            model, paths = selection.get_selected_rows()
            model_name = model.get_name()
            itrs = [model.get_iter(path) for path in paths]
            rows = [model.get(in_itr, *[x for x in range(view.get_n_columns())]) for in_itr in itrs]
            bq_selected = is_bouquet_selected()
            fav_bouquet = None

            if bq_selected:
                fav_bouquet = __bouquets.get(bq_selected, None)

            for itr in itrs:
                if fav_bouquet and model_name == FAV_LIST_NAME:
                    del fav_bouquet[int(model.get_path(itr)[0])]

                if model_name == BOUQUETS_LIST_NAME:
                    if len(model.get_path(itr)) < 2:
                        show_dialog("error_dialog", "This item is not allowed to be removed!")
                        return
                    else:
                        __bouquets.pop(bq_selected)
                model.remove(itr)

            if model_name == FAV_LIST_NAME:
                update_fav_num_column(model)
            elif model_name == SERVICE_LIST_NAME:
                for row in rows:
                    # There are channels with the same parameters except for the name.
                    # None because it can have duplicates! Need fix
                    fav_id = row[-2]
                    for bq in __bouquets:
                        services = __bouquets[bq]
                        with suppress(ValueError):
                            services.remove(fav_id)
                    __channels.pop(fav_id, None)
                __fav_model.clear()
                if bq_selected:
                    update_bouquet_channels(__fav_model, None, bq_selected)

            return rows


def on_new_bouquet(view):
    """ Creates a new item in the bouquets tree """
    model, paths = view.get_selection().get_selected_rows()

    if paths:
        itr = model.get_iter(paths[0])
        bq_type = model.get_value(itr, 1)
        bq_name = "bouquet"
        count = 0
        key = "{}:{}".format(bq_name, bq_type)
        #  Generating name of new bouquet
        while key in __bouquets:
            count += 1
            bq_name = "bouquet{}".format(count)
            key = "{}:{}".format(bq_name, bq_type)

        response = show_dialog("input_dialog", bq_name)

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
        __bouquets[key] = []


def on_bouquets_edit(view):
    """ Rename bouquets """
    if not is_bouquet_selected():
        show_dialog("error_dialog", "This item is not allowed to edit!")
        return

    model, paths = view.get_selection().get_selected_rows()

    if paths:
        itr = model.get_iter(paths[0])
        bq_name, bq_type = model.get(itr, 0, 1)
        response = show_dialog("input_dialog", bq_name)

        if response == Gtk.ResponseType.CANCEL:
            return

        model.set_value(itr, 0, response)
        __bouquets["{}:{}".format(response, bq_type)] = __bouquets.pop("{}:{}".format(bq_name, bq_type))


def on_to_fav_move(view):
    """ Move items from main to fav list """
    selection = get_selection(view)

    if selection:
        receive_selection(view=__fav_view, drop_info=None, data=selection)


def get_selection(view):
    """ Creates a string from the iterators of the selected rows """
    selection = view.get_selection()
    model, paths = selection.get_selected_rows()

    if len(paths) > 0:
        itrs = [model.get_iter(path) for path in paths]
        return "{}:{}".format(",".join([model.get_string_from_iter(itr) for itr in itrs]), model.get_name())


def receive_selection(*, view, drop_info, data):
    """  Update fav view  after data received  """
    bq_selected = is_bouquet_selected()

    if not bq_selected:
        show_dialog("error_dialog", "Error. No bouquet is selected!")
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
        fav_bouquet = __bouquets[bq_selected]

        if source == SERVICE_LIST_NAME:
            ext_model = __services_view.get_model()
            ext_itrs = [ext_model.get_iter_from_string(itr) for itr in itrs]
            ext_rows = [ext_model.get(ext_itr, *[x for x in range(__services_view.get_n_columns())]) for ext_itr in
                        ext_itrs]
            dest_index -= 1
            for ext_row in ext_rows:
                dest_index += 1
                fav_id = ext_row[13]
                channel = __channels[fav_id]
                model.insert(dest_index, (0, channel.service, channel.service_type, channel.pos, channel.fav_id))
                fav_bouquet.insert(dest_index, channel.fav_id)
        elif source == FAV_LIST_NAME:
            in_itrs = [model.get_iter_from_string(itr) for itr in itrs]
            in_rows = [model.get(in_itr, *[x for x in range(view.get_n_columns())]) for in_itr in in_itrs]
            for row in in_rows:
                model.insert(dest_index, row)
                fav_bouquet.insert(dest_index, row[4])
            for in_itr in in_itrs:
                del fav_bouquet[int(model.get_path(in_itr)[0])]
                model.remove(in_itr)
        update_fav_num_column(model)
    except ValueError as e:
        __status_bar.push(1, getattr(e, "message", repr(e)))


def update_fav_num_column(model):
    """ Iterate through model and updates values for Num column """
    model.foreach(lambda store, pth, itr: store.set_value(itr, 0, int(pth[0]) + 1))  # iter , column, value


def on_services_tree_view_drag_data_get(view, drag_context, data, info, time):
    """  DnD  """
    data.set_text(get_selection(view), -1)


def on_fav_tree_view_drag_data_get(view, drag_context, data, info, time):
    """ DnD """
    data.set_text(get_selection(view), -1)


def on_fav_tree_view_drag_data_received(view, drag_context, x, y, data, info, time):
    """ DnD """
    receive_selection(view=view, drop_info=view.get_dest_row_at_pos(x, y), data=data.get_text())


def on_view_popup_menu(menu, event):
    """ Shows popup menu for any view """
    if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
        menu.popup(None, None, None, None, event.button, event.time)


def on_satellite_editor_show(model):
    """ Shows satellites editor dialog """
    show_satellites_dialog(__main_window, __options)


@run_task
def on_data_open(model):
    if show_dialog("path_chooser_dialog") == Gtk.ResponseType.CANCEL:
        return

    open_data()


def open_data():
    """ Opening data and fill views. """
    try:
        __bouquets_model.clear()
        __fav_model.clear()
        __services_model.clear()
        data_path = __options["data_dir_path"]

        for ch in get_channels(data_path + "lamedb"):
            #  adding channels to dict with fav_id as keys
            __channels[ch.fav_id] = ch
            __services_model.append(ch)

        bouquets = get_bouquets(data_path)

        for bouquet in bouquets:
            parent = __bouquets_model.append(None, [bouquet.name, bouquet.type])
            for bt in bouquet.bouquets:
                name, bt_type = bt.name, bt.type
                __bouquets_model.append(parent, [name, bt_type])
                __bouquets["{}:{}".format(name, bt_type)] = bt.services
    except Exception as e:
        __status_bar.push(1, getattr(e, "message", repr(e)))


@run_task
def on_data_save(*args):
    #  Perhaps needs a dialog to choose what we need to save!!!
    if show_dialog("question_dialog") == Gtk.ResponseType.CANCEL:
        return

    path = __options["data_dir_path"]
    bouquets = []
    services_model = __services_view.get_model()

    def parse_bouquets(model, b_path, itr):
        if model.iter_has_child(itr):
            num_of_children = model.iter_n_children(itr)
            bqs = []

            for num in range(num_of_children):
                bq_itr = model.iter_nth_child(itr, num)
                bq_name, bq_type = model.get(bq_itr, 0, 1)
                favs = __bouquets["{}:{}".format(bq_name, bq_type)]
                bq = Bouquet(bq_name, bq_type, [__channels[f_id] for f_id in favs])
                bqs.append(bq)
            bqs = Bouquets(*model.get(itr, 0, 1), bqs)
            bouquets.append(bqs)

    # Getting bouquets
    __bouquets_view.get_model().foreach(parse_bouquets)
    write_bouquets(path + "tmp/", bouquets, __bouquets)
    # Getting services
    services = [Channel(*row[:]) for row in services_model]
    write_channels(path + "tmp/", services)


def on_services_selection(model, path, column):
    delete_selection(__fav_view)


def on_fav_selection(model, path, column):
    delete_selection(__services_view)


def on_bouquets_selection(model, path, column):
    __fav_model.clear()

    if __bouquets_view.row_expanded(path):
        __bouquets_view.collapse_row(path)
    else:
        __bouquets_view.expand_row(path, column)

    if len(path) > 1:
        delete_selection(__services_view)
        update_bouquet_channels(model, path)


def update_bouquet_channels(model, path, bq_key=None):
    """ Updates list of bouquet channels """
    tree_iter = None
    if path:
        tree_iter = model.get_iter(path)

    key = bq_key if bq_key else "{}:{}".format(*model.get(tree_iter, 0, 1))
    services = __bouquets[key]

    for num, ch_id in enumerate(services):
        channel = __channels.get(ch_id, None)
        if channel:
            __fav_model.append((num + 1, channel.service, channel.service_type, channel.pos, channel.fav_id))


def is_bouquet_selected():
    """ Checks whether the bouquet is selected

        returns 'name:type' of selected bouquet or False
    """
    selection = __bouquets_view.get_selection()
    model, path = selection.get_selected_rows()

    if not path or len(path[0]) < 2:
        return False

    return "{}:{}".format(*model.get(model.get_iter(path), 0, 1))


def show_dialog(dialog_name, text=None):
    """ Shows dialogs by name id """
    builder = Gtk.Builder()
    builder.add_from_file("ui/dialogs.glade")
    dialog = builder.get_object(dialog_name)
    dialog.set_transient_for(__main_window)

    if dialog_name == "path_chooser_dialog":
        dialog.set_current_folder(__options["data_dir_path"])

    if dialog_name == "input_dialog":
        entry = builder.get_object("input_entry")
        entry.set_text(text)
        response = dialog.run()
        txt = entry.get_text()
        dialog.destroy()

        return txt if response == Gtk.ResponseType.OK else Gtk.ResponseType.CANCEL

    if text:
        dialog.set_markup(text)

    response = dialog.run()
    dialog.destroy()

    return response


def delete_selection(view, *args):
    """ Used for clear selection on given view(s) """
    for v in [view, *args]:
        v.get_selection().unselect_all()


def on_preferences(item):
    show_settings_dialog(__main_window, __options)


def on_tree_view_key_release(view: Gtk.TreeView, event):
    """  Handling  keystrokes  """
    key = event.keyval
    ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
    alt = event.state & Gdk.ModifierType.MOD1_MASK
    model_name = view.get_model().get_name()

    if key == Gdk.KEY_Delete:
        on_delete(view)
    elif ctrl and key in (Gdk.KEY_Up, Gdk.KEY_Page_Up, Gdk.KEY_KP_Page_Up):  # KEY_KP_Page_Up for laptop!
        move_items(key)
    elif ctrl and key in (Gdk.KEY_Down, Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
        move_items(key)
    elif model_name == FAV_LIST_NAME and key == Gdk.KEY_Control_L or key == Gdk.KEY_Control_R:
        update_fav_num_column(view.get_model())
    elif key == Gdk.KEY_Insert:
        # Move items from main to fav list
        if model_name == SERVICE_LIST_NAME:
            on_to_fav_move(view)
        elif model_name == BOUQUETS_LIST_NAME:
            on_new_bouquet(view)
    elif key == Gdk.KEY_F2 and model_name == BOUQUETS_LIST_NAME:
        on_bouquets_edit(view)
    elif ctrl and (key == Gdk.KEY_c or key == Gdk.KEY_C) and model_name == SERVICE_LIST_NAME:
        on_copy(view)
    elif ctrl and key == Gdk.KEY_x or key == Gdk.KEY_X:
        if model_name == FAV_LIST_NAME:
            on_cut(view)
    elif ctrl and key == Gdk.KEY_v or key == Gdk.KEY_V:
        on_paste(view)
    elif ctrl and key == Gdk.KEY_s or key == Gdk.KEY_S:
        on_data_save()
    elif key == Gdk.KEY_space and model_name == FAV_LIST_NAME:
        pass


@run_task
def on_download(item):
    show_download_dialog(__main_window, __options, open_data)


@run_task
def on_view_focus(view, focus_event):
    model = view.get_model()
    model_name = model.get_name()

    empty = len(model) == 0  # if  > 0 model has items

    if empty:
        return

    if model_name == BOUQUETS_LIST_NAME:
        for elem in __tool_elements:
            __tool_elements[elem].set_sensitive(False)
        for elem in _BOUQUET_ELEMENTS:
            __tool_elements[elem].set_sensitive(True)
    else:
        is_service = model_name == SERVICE_LIST_NAME
        for elem in _FAV_ELEMENTS:
            __tool_elements[elem].set_sensitive(not is_service)
        for elem in _SERVICE_ELEMENTS:
            __tool_elements[elem].set_sensitive(is_service)
        for elem in _BOUQUET_ELEMENTS:
            __tool_elements[elem].set_sensitive(False)

    for elem in _REMOVE_ELEMENTS:
        __tool_elements[elem].set_sensitive(not empty)


def init_ui():
    builder = Gtk.Builder()
    builder.add_from_file("ui/main_window.glade")
    global __main_window
    __main_window = builder.get_object("main_window")
    main_window_size = __options.get("window_size", None)
    # Setting the last size of the window if it was saved
    if main_window_size:
        __main_window.resize(*main_window_size)
    global __services_view
    __services_view = builder.get_object("services_tree_view")
    global __fav_view
    __fav_view = builder.get_object("fav_tree_view")
    global __bouquets_view
    __bouquets_view = builder.get_object("bouquets_tree_view")
    global __fav_model
    __fav_model = builder.get_object("fav_list_store")
    global __services_model
    __services_model = builder.get_object("services_list_store")
    global __bouquets_model
    __bouquets_model = builder.get_object("bouquets_tree_store")
    global __status_bar
    __status_bar = builder.get_object("status_bar")
    # dynamically active elements depending on the selected view
    global __tool_elements
    __tool_elements = {k: builder.get_object(k) for k in ("up_tool_button", "down_tool_button",
                                                          "cut_tool_button", "copy_tool_button",
                                                          "paste_tool_button", "to_fav_tool_button",
                                                          "new_tool_button", "remove_tool_button",
                                                          "cut_menu_item", "copy_menu_item",
                                                          "paste_menu_item", "delete_menu_item",
                                                          "edit_tool_button")}
    builder.connect_signals(get_handlers())
    init_drag_and_drop()  # drag and drop
    __main_window.show_all()


def init_drag_and_drop():
    """ Enable drag and drop """
    target = []
    __services_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.COPY)
    __fav_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target,
                                        Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
    __fav_view.enable_model_drag_dest(target, Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
    __fav_view.drag_dest_set_target_list(None)
    __fav_view.drag_source_set_target_list(None)
    __fav_view.drag_dest_add_text_targets()
    __fav_view.drag_source_add_text_targets()
    __services_view.drag_source_set_target_list(None)
    __services_view.drag_source_add_text_targets()


def start_app():
    init_ui()
    Gtk.main()


def close_app():
    Gtk.main_quit()


if __name__ == "__main__":
    start_app()

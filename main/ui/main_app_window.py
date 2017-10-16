from threading import Thread

from main.eparser import get_channels, get_bouquets, get_bouquet
from main.eparser.__constants import SERVICE_TYPE
from main.ftp import download_data, upload_data
from main.properties import get_config
from . import Gtk, Gdk
from .satellites_dialog import show_satellites_dialog
from .settings_dialog import show_settings_dialog

__main_window = None
__status_bar = None
__options = get_config()
__services_model = None
__bouquets_model = None
__fav_model = None
__services_view = None
__fav_view = None
__bouquets_view = None
__channels = {}


def on_about_app(item):
    builder = Gtk.Builder()
    builder.add_from_file("ui/main_window.glade")
    dialog = builder.get_object("about_dialog")
    dialog.run()
    dialog.destroy()


def get_handlers():
    return {
        "on_close_main_window": Gtk.main_quit,
        "on_about_app": on_about_app,
        "on_preferences": on_preferences,
        "on_download": on_download,
        "on_upload": on_upload,
        "on_data_open": on_data_open,
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
        "on_services_tree_view_drag_data_get": on_services_tree_view_drag_data_get,
        "on_fav_tree_view_drag_data_get": on_fav_tree_view_drag_data_get,
        "on_fav_tree_view_drag_data_received": on_fav_tree_view_drag_data_received
    }


def on_up(item):
    pass


def on_down(item):
    pass


def on_cut(item):
    pass


def on_copy(item):
    pass


def on_paste(item):
    pass


def on_delete(item):
    """ Delete selected items from views """
    for view in [__services_view, __fav_view, __bouquets_view]:
        selection = view.get_selection()
        model, paths = selection.get_selected_rows()
        itrs = [model.get_iter(path) for path in paths]
        for itr in itrs:
            model.remove(itr)


def on_services_tree_view_drag_data_get(view, drag_context, data, info, time):
    """  DnD  """
    # rows = [model.get(itr, *[x for x in range(view.get_n_columns())]) for itr in itrs]
    text = get_dnd_selection(view)
    # print(text)
    data.set_text(text, -1)


def on_fav_tree_view_drag_data_get(view, drag_context, data, info, time):
    """ DnD """
    data.set_text(get_dnd_selection(view), -1)


def get_dnd_selection(view):
    """ Creates a string from the iterators of the selected rows """
    selection = view.get_selection()
    model, paths = selection.get_selected_rows()
    itrs = [model.get_iter(path) for path in paths]
    return "{}:{}".format(",".join([model.get_string_from_iter(itr) for itr in itrs]), model.get_name())


def on_fav_tree_view_drag_data_received(view, drag_context, x, y, data, info, time):
    """ DnD """
    model = view.get_model()
    dest_index = 0
    drop_info = view.get_dest_row_at_pos(x, y)
    if drop_info:
        path, position = drop_info
        dest_iter = model.get_iter(path)
        if dest_iter:
            dest_index = model.get_value(dest_iter, 0)
    itr_str, sep, source = data.get_text().partition(":")
    itrs = itr_str.split(",")
    try:
        if source == "services_list_store":
            ext_model = __services_view.get_model()
            ext_itrs = [ext_model.get_iter_from_string(itr) for itr in itrs]
            ext_rows = [ext_model.get(ext_itr, *[x for x in range(__services_view.get_n_columns())]) for ext_itr in
                        ext_itrs]
            for ext_row in ext_rows:
                fav_id = ext_row[11]
                channel = __channels[fav_id]
                model.insert(dest_index, (0, channel.service, channel.service_type, channel.pos))
        elif source == "fav_list_store":
            in_itrs = [model.get_iter_from_string(itr) for itr in itrs]
            in_rows = [model.get(in_itr, *[x for x in range(view.get_n_columns())]) for in_itr in in_itrs]
            for row in in_rows:
                model.insert(dest_index, row)
            for in_itr in in_itrs:
                model.remove(in_itr)
    except ValueError as e:
        __status_bar.push(1, getattr(e, "message", repr(e)))


def on_satellite_editor_show(model):
    """ Shows satellites editor dialog """
    show_satellites_dialog(__main_window, __options["data_dir_path"])


def data_open(model):
    try:
        model.clear()
        __fav_model.clear()
        model_id = model.get_name()
        data_path = get_config()["data_dir_path"]
        if model_id == "services_list_store":
            for ch in get_channels(data_path + "lamedb"):
                #  adding channels to dict with fav_id as keys
                __channels[ch.fav_id] = ch
                model.append(ch)
        if model_id == "bouquets_tree_store":
            data = get_bouquets(data_path)
            for name, bouquets in data:
                parent = model.append(None, [name])
                for bouquet in bouquets:
                    model.append(parent, [bouquet])
    except Exception as e:
        __status_bar.push(1, getattr(e, "message", repr(e)))


def on_data_open(model):
    # Maybe is not necessary? Need testing.
    task = Thread(target=data_open(model))
    task.start()


def on_services_selection(model, path, column):
    delete_selection(__fav_view, __bouquets_view)


def on_fav_selection(model, path, column):
    delete_selection(__services_view, __bouquets_view)


def on_bouquets_selection(model, path, column):
    if len(path) > 1:
        delete_selection(__services_view)
        tree_iter = model.get_iter(path)
        name = model.get_value(tree_iter, 0)
        # 'tv' Temporary! It is necessary to implement a row type attribute.
        bq = get_bouquet(__options["data_dir_path"], name, SERVICE_TYPE[1].lower())
        __fav_model.clear()
        for num, ch_id in enumerate(bq):
            channel = __channels.get(ch_id, None)
            __fav_model.append((num + 1, channel[0], channel[2], channel[9]))


def delete_selection(view, *args):
    """ Used for clear selection on given view(s) """
    for v in [view, *args]:
        v.get_selection().unselect_all()


def on_preferences(item):
    show_settings_dialog(__main_window, __options)


def on_tree_view_key_release(widget, event):
    key = event.keyval
    if key == Gdk.KEY_Tab:
        print("Tab")
    if key == Gdk.KEY_Delete:
        print("Delete")
        on_delete(widget)
    if key == Gdk.KEY_Up:
        print("Up")
    if key == Gdk.KEY_Down:
        print("Down")


def on_upload(item):
    connect(__options, False)


def on_download(item):
    connect(__options)


def on_reload(item):
    pass


def connect(properties, download=True):
    try:
        res = download_data(properties=properties) if download else upload_data(properties=properties)
        __status_bar.push(1, res)
    except Exception as e:
        __status_bar.remove_all(1)
        __status_bar.push(1, getattr(e, "message", repr(e)))  # Or maybe so: getattr(e, 'message', str(e))


def init_ui():
    builder = Gtk.Builder()
    builder.add_from_file("ui/main_window.glade")
    global __main_window
    __main_window = builder.get_object("main_window")
    global __services_view
    __services_view = builder.get_object("services_tree_view")
    global __fav_view
    __fav_view = builder.get_object("fav_tree_view")
    global __bouquets_view
    __bouquets_view = builder.get_object("bouquets_tree_view")
    global __fav_model
    __fav_model = builder.get_object("fav_list_store")
    global __status_bar
    __status_bar = builder.get_object("status_bar")
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

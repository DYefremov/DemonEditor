""" This is helper module for main_app_window """
from app.eparser import Channel
from app.eparser.bouquets import BqServiceType
from . import Gtk, Gdk
from .dialogs import show_dialog, DialogType


# ***************** Markers section *******************#

def insert_marker(view, bouquets, selected_bouquet, channels, parent_window):
    """" Inserts marker into bouquet services list. """
    response = show_dialog(DialogType.INPUT, parent_window)
    if response == Gtk.ResponseType.CANCEL:
        return

    if not response.strip():
        show_dialog(DialogType.ERROR, parent_window, "The text of marker is empty, please try again!")
        return

    # Searching for max num value in all marker services (if empty default = 0)
    max_num = max(map(lambda num: int(num.data_id, 16),
                      filter(lambda ch: ch.service_type == BqServiceType.MARKER.name, channels.values())), default=0)
    max_num = '{:x}'.format(max_num + 1)
    fav_id = "1:64:{}:0:0:0:0:0:0:0::{}\n#DESCRIPTION {}\n".format(max_num, response, response)
    s_type = BqServiceType.MARKER.name
    model, paths = view.get_selection().get_selected_rows()
    itr = model.insert_before(model.get_iter(paths[0]), (None, None, response, None, None, s_type, None, fav_id))
    channels[fav_id] = Channel(None, None, None, response, None, None, None, s_type, *[None] * 7, max_num, fav_id, None)
    bouquets[selected_bouquet].insert(model.get_path(itr)[0], fav_id)


def edit_marker(view, bouquets, selected_bouquet, channels, parent_window):
    """ Edits marker text """
    model, paths = view.get_selection().get_selected_rows()
    itr = model.get_iter(paths[0])
    name, fav_id = model.get(itr, 2, 7)
    response = show_dialog(DialogType.INPUT, parent_window, text=name)
    if response == Gtk.ResponseType.CANCEL:
        return

    bq_services = bouquets[selected_bouquet]
    index = bq_services.index(fav_id)
    old_ch = channels.pop(fav_id, None)
    new_fav_id = "{}::{}\n#DESCRIPTION {}\n".format(fav_id.split("::")[0], response, response)
    model.set(itr, {2: response, 7: new_fav_id})
    channels[new_fav_id] = Channel(*old_ch[0:3], response, *old_ch[4:15], old_ch.data_id, new_fav_id, None)
    bq_services.pop(index)
    bq_services.insert(index, new_fav_id)


# ***************** Movement section *******************#

def move_items(key, view):
    """ Move items in  tree view """
    selection = view.get_selection()
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
                up_itr = model.get_iter(view.get_cursor()[0])
                if up_itr:
                    model.move_before(itr, up_itr)
            elif key == Gdk.KEY_Page_Down or key == Gdk.KEY_KP_Page_Down:
                down_itr = model.get_iter(view.get_cursor()[0])
                if down_itr:
                    model.move_after(itr, down_itr)


if __name__ == "__main__":
    pass

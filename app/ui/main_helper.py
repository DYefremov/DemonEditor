""" This is helper module for main_app_window """
from app.eparser import Channel
from app.eparser.bouquets import BqServiceType
from .dialogs import show_dialog, DialogType
from . import Gtk


def insert_marker(view, bouquets, selected_bouquet, channels, parent_window):
    """" Inserts marker into bouquet services list. """
    response = show_dialog(DialogType.INPUT, parent_window)
    if response == Gtk.ResponseType.CANCEL:
        return

    if not response.strip():
        show_dialog(DialogType.ERROR, parent_window, "The text of marker is empty, please try again!")
        return

    counter = 0
    fav_id = "1:64:{}:0:0:0:0:0:0:0::{}\n#DESCRIPTION {}\n".format(counter, response, response)
    s_type = BqServiceType.MARKER.name
    model, paths = view.get_selection().get_selected_rows()
    itr = model.insert_before(model.get_iter(paths[0]), (None, None, response, None, None, s_type, None, fav_id))
    channels[fav_id] = Channel(None, None, None, response, None, None, None, s_type, *[None] * 7, counter, fav_id, None)
    bouquets[selected_bouquet].insert(model.get_path(itr)[0], fav_id)


def edit_marker(view, bouquets, selected_bouquet, channels,  parent_window):
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


if __name__ == "__main__":
    pass

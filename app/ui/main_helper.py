""" This is helper module for ui """
from enum import Enum

from app.eparser import Channel
from app.eparser.__constants import FLAG
from app.eparser.bouquets import BqServiceType, to_bouquet_id
from . import Gtk, Gdk, HIDE_ICON, LOCKED_ICON
from .dialogs import show_dialog, DialogType


class ViewTarget(Enum):
    """ Used for set target view """
    BOUQUET = 0
    FAV = 1
    SERVICES = 2


# ***************** Markers *******************#

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


# ***************** Movement *******************#

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


# ***************** Edit *******************#

def edit(view, parent_window, target, fav_view=None, service_view=None, channels=None):
    model, paths = view.get_selection().get_selected_rows()

    if not paths:
        return
    elif len(paths) > 1:
        show_dialog(DialogType.ERROR, parent_window, "Please, select only one item!")
        return

    itr = model.get_iter(paths)
    f_id = None
    channel_name = None

    if target is ViewTarget.SERVICES:
        name, fav_id = model.get(itr, 3, 16)
        f_id = fav_id
        response = show_dialog(DialogType.INPUT, parent_window, name)
        if response == Gtk.ResponseType.CANCEL:
            return
        channel_name = response
        model.set_value(itr, 3, response)
        if fav_view is not None:
            for row in fav_view.get_model():
                if row[7] == fav_id:
                    row[2] = response
                    break
    elif target is ViewTarget.FAV:
        name, fav_id = model.get(itr, 2, 7)
        f_id = fav_id
        response = show_dialog(DialogType.INPUT, parent_window, name)
        if response == Gtk.ResponseType.CANCEL:
            return

        channel_name = response
        model.set_value(itr, 2, response)

        if service_view is not None:
            for row in service_view.get_model():
                if row[16] == fav_id:
                    row[3] = response
                    break

    old_ch = channels.get(f_id, None)
    if old_ch:
        channels[f_id] = Channel(*old_ch[0:3], channel_name, *old_ch[4:])


# ***************** Flags *******************#

def set_flags(flag, services_view, fav_view, channels, blacklist):
    """ Updates flags for services. Returns True if any was changed. """
    target = ViewTarget.SERVICES if services_view.is_focus() else ViewTarget.FAV if fav_view.is_focus() else None
    if not target:
        return

    model, paths = None, None

    if target is ViewTarget.SERVICES:
        model, paths = services_view.get_selection().get_selected_rows()
    elif target is ViewTarget.FAV:
        model, paths = fav_view.get_selection().get_selected_rows()

    if not paths:
        return

    if flag is FLAG.HIDE:
        set_hide(channels, model, paths, target)
    elif flag is FLAG.LOCK:
        set_lock(blacklist, channels, model, paths, target, services_model=services_view.get_model())

    return True


def set_lock(blacklist, channels, model, paths, target, services_model):
    col_num = 4 if target is ViewTarget.SERVICES else 3
    locked = has_locked_hide(model, paths, col_num)

    ids = []

    for path in paths:
        itr = model.get_iter(path)
        fav_id = model.get_value(itr, 16 if target is ViewTarget.SERVICES else 7)
        channel = channels.get(fav_id, None)
        if channel:
            bq_id = to_bouquet_id(channel)
            blacklist.discard(bq_id) if locked else blacklist.add(bq_id)
            model.set_value(itr, col_num, None if locked else LOCKED_ICON)
            channels[fav_id] = Channel(*channel[:4], None if locked else LOCKED_ICON, *channel[5:])
            ids.append(fav_id)

    if target is ViewTarget.FAV and ids:
        for ch in services_model:
            if ch[16] in ids:
                ch[4] = None if locked else LOCKED_ICON


def set_hide(channels, model, paths, target):
    if target is ViewTarget.FAV:
        return
    col_num = 5
    hide = has_locked_hide(model, paths, col_num)

    for path in paths:
        itr = model.get_iter(path)
        model.set_value(itr, col_num, None if hide else HIDE_ICON)
        flags = [*model.get_value(itr, 0).split(",")]
        index, flag = None, None
        for i, fl in enumerate(flags):
            if fl.startswith("f:"):
                index = i
                flag = fl
                break

        value = int(flag[2:]) if flag else 0

        if not hide:
            if value in FLAG.hide_values():
                continue  # skip if already hidden
            value += FLAG.HIDE.value
        else:
            if value not in FLAG.hide_values():
                continue  # skip if already allowed to show
            value -= FLAG.HIDE.value

        value = "f:{}".format(value) if value > 10 else "f:0{}".format(value)
        if index is not None:
            flags[index] = value
        else:
            flags.append(value)

        model.set_value(itr, 0, (",".join(reversed(sorted(flags)))))
        fav_id = model.get_value(itr, 16)
        channel = channels.get(fav_id, None)
        if channel:
            channels[fav_id] = Channel(*channel[:5], None if hide else HIDE_ICON, *channel[6:])


def has_locked_hide(model, paths, col_num):
    for path in paths:
        if model.get_value(model.get_iter(path), col_num):
            return True
    return False


# ***************** Location *******************#

def locate_in_services(fav_view, services_view, parent_window):
    """ Locating and scrolling to the service """
    model, paths = fav_view.get_selection().get_selected_rows()

    if not paths:
        return
    elif len(paths) > 1:
        show_dialog(DialogType.ERROR, parent_window, "Please, select only one item!")
        return

    fav_id = model.get_value(model.get_iter(paths[0]), 7)
    for index, row in enumerate(services_view.get_model()):
        if row[16] == fav_id:
            scroll_to(index, services_view)
            break


def scroll_to(index, view):
    """ Scrolling to and selecting  given index(path) """
    view.scroll_to_cell(index, None)
    selection = view.get_selection()
    selection.unselect_all()
    selection.select_path(index)


if __name__ == "__main__":
    pass

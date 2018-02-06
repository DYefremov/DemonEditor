""" This is helper module for ui """
from enum import Enum

import os

import shutil
from gi.repository import GdkPixbuf

from app.eparser import Service
from app.eparser.ecommons import FLAG
from app.eparser.enigma.bouquets import BqServiceType, to_bouquet_id
from . import Gtk, Gdk, HIDE_ICON, LOCKED_ICON
from .dialogs import show_dialog, DialogType, get_chooser_dialog


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
    max_num = max(map(lambda num: int(num.data_id, 18),
                      filter(lambda ch: ch.service_type == BqServiceType.MARKER.name, channels.values())), default=0)
    max_num = '{:x}'.format(max_num + 1)
    fav_id = "1:64:{}:0:0:0:0:0:0:0::{}\n#DESCRIPTION {}\n".format(max_num, response, response)
    s_type = BqServiceType.MARKER.name
    model, paths = view.get_selection().get_selected_rows()
    marker = (None, None, response, None, None, s_type, None, fav_id, None)
    itr = model.insert_before(model.get_iter(paths[0]), marker) if paths else model.insert(0, marker)
    bouquets[selected_bouquet].insert(model.get_path(itr)[0], fav_id)
    channels[fav_id] = Service(None, None, None, response, None, None, None, s_type, *[None] * 9, max_num, fav_id, None)


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
    channels[new_fav_id] = Service(*old_ch[0:3], response, *old_ch[4:17], old_ch.data_id, new_fav_id, None)
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
    model = get_base_model(model)

    if not paths:
        return
    elif len(paths) > 1:
        show_dialog(DialogType.ERROR, parent_window, "Please, select only one item!")
        return

    itr = model.get_iter(paths)
    f_id = None
    channel_name = None

    if target is ViewTarget.SERVICES:
        name, fav_id = model.get(itr, 3, 18)
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
            for row in get_base_model(service_view.get_model()):
                if row[18] == fav_id:
                    row[3] = response
                    break

    old_ch = channels.get(f_id, None)
    if old_ch:
        channels[f_id] = Service(*old_ch[0:3], channel_name, *old_ch[4:])


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

    model = get_base_model(model)

    if flag is FLAG.HIDE:
        if target is ViewTarget.SERVICES:
            set_hide(channels, model, paths)
        else:
            fav_ids = [model.get_value(model.get_iter(path), 7) for path in paths]
            srv_model = get_base_model(services_view.get_model())
            srv_paths = [row.path for row in srv_model if row[18] in fav_ids]
            set_hide(channels, srv_model, srv_paths)
    elif flag is FLAG.LOCK:
        set_lock(blacklist, channels, model, paths, target, services_model=get_base_model(services_view.get_model()))

    return True


def set_lock(blacklist, channels, model, paths, target, services_model):
    col_num = 4 if target is ViewTarget.SERVICES else 3
    locked = has_locked_hide(model, paths, col_num)

    ids = []

    for path in paths:
        itr = model.get_iter(path)
        fav_id = model.get_value(itr, 18 if target is ViewTarget.SERVICES else 7)
        channel = channels.get(fav_id, None)
        if channel:
            bq_id = to_bouquet_id(channel)
            if not bq_id:
                continue
            blacklist.discard(bq_id) if locked else blacklist.add(bq_id)
            model.set_value(itr, col_num, None if locked else LOCKED_ICON)
            channels[fav_id] = Service(*channel[:4], None if locked else LOCKED_ICON, *channel[5:])
            ids.append(fav_id)

    if target is ViewTarget.FAV and ids:
        for ch in services_model:
            if ch[18] in ids:
                ch[4] = None if locked else LOCKED_ICON


def set_hide(channels, model, paths):
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

        if value == 0 and index is not None:
            del flags[index]
        else:
            value = "f:{}".format(value) if value > 10 else "f:0{}".format(value)
            if index is not None:
                flags[index] = value
            else:
                flags.append(value)

        model.set_value(itr, 0, (",".join(reversed(sorted(flags)))))
        fav_id = model.get_value(itr, 18)
        channel = channels.get(fav_id, None)
        if channel:
            channels[fav_id] = Service(*channel[:5], None if hide else HIDE_ICON, *channel[6:])


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
        if row[18] == fav_id:
            scroll_to(index, services_view)
            break


def scroll_to(index, view, paths=None):
    """ Scrolling to and selecting  given index(path) """
    if paths is not None:
        view.expand_row(paths[0], 0)
    view.scroll_to_cell(index, None)
    selection = view.get_selection()
    selection.unselect_all()
    selection.select_path(index)


# ***************** Picons *********************#

def update_picons(path, picons, model):
    if not os.path.exists(path):
        return

    for file in os.listdir(path):
        picons[file] = get_picon_pixbuf(path + file)

    for r in model:
        model.set_value(model.get_iter(r.path), 8, picons.get(r[9], None))


def assign_picon(target, srv_view, fav_view, transient, picons, options, services):
    view = srv_view if target is ViewTarget.SERVICES else fav_view
    model, paths = view.get_selection().get_selected_rows()
    if not is_only_one_item_selected(paths, transient):
        return

    response = get_chooser_dialog(transient, options, "*.png", "png files")
    if response == Gtk.ResponseType.CANCEL:
        return

    if not str(response).endswith(".png"):
        show_dialog(DialogType.ERROR, transient, text="No png file is selected!")
        return

    picon_pos = 8
    model = get_base_model(model)
    itr = model.get_iter(paths)
    fav_id = model.get_value(itr, 18 if target is ViewTarget.SERVICES else 7)
    picon_id = services.get(fav_id)[9]

    if picon_id:
        picon_file = options.get("picons_dir_path") + picon_id
        if os.path.isfile(response):
            shutil.copy(response, picon_file)
            picon = get_picon_pixbuf(picon_file)
            picons[picon_id] = picon
            model.set_value(itr, picon_pos, picon)
            if target is ViewTarget.SERVICES:
                set_picon(fav_id, fav_view.get_model(), picon, 7, picon_pos)
            else:
                set_picon(fav_id, get_base_model(srv_view.get_model()), picon, 18, picon_pos)


def set_picon(fav_id, model, picon, fav_id_pos, picon_pos):
    for row in model:
        if row[fav_id_pos] == fav_id:
            row[picon_pos] = picon
            break


def remove_picon(target, srv_view, fav_view, picons, options):
    view = srv_view if target is ViewTarget.SERVICES else fav_view
    model, paths = view.get_selection().get_selected_rows()
    model = get_base_model(model)

    fav_ids = []
    picon_ids = []
    picon_pos = 8  # picon position is equal for services and fav

    for path in paths:
        itr = model.get_iter(path)
        model.set_value(itr, picon_pos, None)
        if target is ViewTarget.SERVICES:
            fav_ids.append(model.get_value(itr, 18))
            picon_ids.append(model.get_value(itr, 9))
        else:
            fav_ids.append(model.get_value(itr, 7))

    def remove(md, path, itr):
        if md.get_value(itr, 7 if target is ViewTarget.SERVICES else 18) in fav_ids:
            md.set_value(itr, picon_pos, None)
            if target is ViewTarget.FAV:
                picon_ids.append(md.get_value(itr, 9))

    fav_view.get_model().foreach(remove) if target is ViewTarget.SERVICES else get_base_model(
        srv_view.get_model()).foreach(remove)

    pions_path = options.get("picons_dir_path")
    backup_path = options.get("data_dir_path") + "backup/picons/"
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)

    for p_id in picon_ids:
        picons[p_id] = None
        src = pions_path + p_id
        if os.path.isfile(src):
            shutil.move(src, backup_path + p_id)


def copy_picon_reference(target, view, services, clipboard, transient):
    """ Copying picon id to clipboard """
    model, paths = view.get_selection().get_selected_rows()
    if not is_only_one_item_selected(paths, transient):
        return

    if target is ViewTarget.SERVICES:
        picon_id = model.get_value(model.get_iter(paths), 9)
        if picon_id:
            clipboard.set_text(picon_id.rstrip(".png"), -1)
        else:
            show_dialog(DialogType.ERROR, transient, "No reference is present!")
    elif target is ViewTarget.FAV:
        fav_id = model.get_value(model.get_iter(paths), 7)
        srv = services.get(fav_id, None)
        if srv and srv.picon_id:
            clipboard.set_text(srv.picon_id.rstrip(".png"), -1)
        else:
            show_dialog(DialogType.ERROR, transient, "No reference is present!")


def is_only_one_item_selected(paths, transient):
    if len(paths) > 1:
        show_dialog(DialogType.ERROR, transient, "Please, select only one item!")
        return False

    if not paths:
        show_dialog(DialogType.ERROR, transient, "No selected item!")
        return False

    return True


def get_picon_pixbuf(path):
    return GdkPixbuf.Pixbuf.new_from_file_at_scale(filename=path, width=32, height=32, preserve_aspect_ratio=True)


# ***************** Search *********************#

def search(text, srv_view, fav_view, bqs_view, services, bouquets):
    for view in srv_view, fav_view:
        model = get_base_model(view.get_model())
        selection = view.get_selection()
        selection.unselect_all()
        if not text:
            continue
        paths = []
        text = text.upper()
        for r in model:
            if text in str(r[:]).upper():
                path = r.path
                selection.select_path(r.path)
                paths.append(path)

        if paths:
            view.scroll_to_cell(paths[0], None)


# ***************** Others *********************#


def update_entry_data(entry, dialog, options):
    """ Updates value in text entry from chooser dialog """
    response = show_dialog(dialog_type=DialogType.CHOOSER, transient=dialog, options=options)
    if response not in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
        entry.set_text(response)
        return response
    return False


def get_base_model(model):
    """ Returns base tree model if has wrappers ("TreeModelSort" and "TreeModelFilter") """
    if type(model) is Gtk.TreeModelSort:
        return model.get_model().get_model()
    return model


if __name__ == "__main__":
    pass

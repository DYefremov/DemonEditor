# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2023 Dmitriy Yefremov
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Author: Dmitriy Yefremov
#


""" Helper module for the GUI. """

__all__ = ("insert_marker", "move_items", "rename", "ViewTarget", "set_flags", "locate_in_services",
           "scroll_to", "get_base_model", "get_base_paths", "copy_reference", "assign_picons", "remove_picon",
           "is_only_one_item_selected", "gen_bouquets", "BqGenType", "get_selection", "get_service_reference",
           "get_model_data", "remove_all_unused_picons", "get_picon_pixbuf", "get_base_itrs", "get_iptv_url",
           "get_iptv_data", "update_entry_data", "append_text_to_tview", "on_popup_menu", "get_picon_file_name",
           "update_toggle_model", "update_popup_filter_model", "update_filter_sat_positions", "get_pos_num")

import os
import re
import shutil
import unicodedata
from functools import lru_cache
from itertools import groupby
from pathlib import Path
from urllib.parse import unquote

from gi.repository import GdkPixbuf, GLib, Gio

from app.eparser import Service
from app.eparser.ecommons import Flag, BouquetService, Bouquet, BqType
from app.eparser.enigma.bouquets import BqServiceType, to_bouquet_id
from app.settings import SettingsType, SEP, IS_WIN, IS_DARWIN, IS_LINUX
from .dialogs import show_dialog, DialogType, translate
from .uicommons import ViewTarget, BqGenType, Gtk, Gdk, HIDE_ICON, LOCKED_ICON, KeyboardKey, Column


# ***************** Markers *******************#

def insert_marker(view, bouquets, selected_bouquet, services, parent_window, m_type=BqServiceType.MARKER):
    """" Inserts marker into bouquet services list. """
    fav_id, text = "1:832:D:0:0:0:0:0:0:0:\n", None

    if m_type is BqServiceType.MARKER:
        response = show_dialog(DialogType.INPUT, parent_window)
        if response == Gtk.ResponseType.CANCEL:
            return

        if not response.strip():
            show_dialog(DialogType.ERROR, parent_window, "The text of marker is empty, please try again!")
            return

        fav_id = f"1:64:0:0:0:0:0:0:0:0::{response}\n#DESCRIPTION {response}\n"
        text = response

    s_type = m_type.name
    model, paths = view.get_selection().get_selected_rows()
    marker = (None, None, text, None, None, s_type, None, fav_id, None, None, None)
    itr = model.insert_before(model.get_iter(paths[0]), marker) if paths else model.insert(0, marker)
    bouquets[selected_bouquet].insert(model.get_path(itr)[0], fav_id)
    services[fav_id] = Service(None, None, None, text, None, None, None, s_type, *[None] * 9, 0, fav_id, None)


# ***************** Movement *******************#

def move_items(key, view: Gtk.TreeView):
    """ Move items in the tree view """
    selection = view.get_selection()
    model, paths = selection.get_selected_rows()
    if not paths:
        return

    is_tree_store = type(model) is Gtk.TreeStore
    mod_length = len(model)
    if not is_tree_store and mod_length == len(paths):
        return

    cursor_path = view.get_cursor()[0]
    max_path = Gtk.TreePath.new_from_indices((mod_length,))
    min_path = Gtk.TreePath.new_from_indices((0,))

    if is_tree_store:
        is_tree_store = False
        parent_paths = list(filter(lambda p: p.get_depth() == 1, paths))
        if parent_paths:
            paths = parent_paths
            min_path = model.get_path(model.get_iter_first())
            view.collapse_all()
            if mod_length == len(paths):
                return
        else:
            if not is_some_level(paths):
                return
            parent_itr = model.iter_parent(model.get_iter(paths[0]))
            parent_index = model.get_path(parent_itr)
            children_num = model.iter_n_children(parent_itr)
            if key in (KeyboardKey.PAGE_DOWN, KeyboardKey.END, KeyboardKey.END_KP, KeyboardKey.PAGE_DOWN_KP):
                children_num -= 1
            min_path = Gtk.TreePath.new_from_string(f"{parent_index}:{0}")
            max_path = Gtk.TreePath.new_from_string(f"{parent_index}:{children_num}")
            is_tree_store = True

    if key is KeyboardKey.UP:
        top_path = Gtk.TreePath(paths[0])
        set_cursor(top_path, paths, selection, view)
        top_path.prev()
        move_up(top_path, model, paths)
    elif key is KeyboardKey.DOWN:
        down_path = Gtk.TreePath(paths[-1])
        set_cursor(down_path, paths, selection, view)
        down_path.next()
        if down_path < max_path:
            move_down(down_path, model, paths)
        else:
            max_path.prev()
            move_down(max_path, model, paths)
    elif key in (KeyboardKey.PAGE_UP, KeyboardKey.HOME, KeyboardKey.PAGE_UP_KP, KeyboardKey.HOME_KP):
        move_up(min_path if is_tree_store else cursor_path, model, paths)
    elif key in (KeyboardKey.PAGE_DOWN, KeyboardKey.END, KeyboardKey.END_KP, KeyboardKey.PAGE_DOWN_KP):
        move_down(max_path if is_tree_store else cursor_path, model, paths)


def move_up(top_path, model, paths):
    top_iter = model.get_iter(top_path)
    for path in paths:
        itr = model.get_iter(path)
        model.move_before(itr, top_iter)
        top_path.next()
        top_iter = model.get_iter(top_path)


def move_down(down_path, model, paths):
    top_iter = model.get_iter(down_path)
    for path in reversed(paths):
        itr = model.get_iter(path)
        model.move_after(itr, top_iter)
        down_path.prev()
        top_iter = model.get_iter(down_path)


def is_some_level(paths):
    for i in range(1, len(paths)):
        prev = paths[i - 1]
        current = paths[i]
        if len(prev) != len(current) or (len(prev) == 2 and len(current) == 2 and prev[0] != current[0]):
            return
    return True


def set_cursor(dest_path, paths, selection, view):
    view.set_cursor(dest_path, view.get_column(0), False)
    for p in paths:
        selection.select_path(p)


# ***************** Rename *******************#

def rename(view, parent_window, target, fav_view=None, service_view=None, services=None):
    selection = get_selection(view, parent_window)
    if not selection:
        return

    model, paths = selection
    itr = model.get_iter(paths)
    f_id, srv_name, srv_type = None, None, None

    if target is ViewTarget.SERVICES:
        name, fav_id = model.get(itr, Column.SRV_SERVICE, Column.SRV_FAV_ID)
        f_id = fav_id
        response = show_dialog(DialogType.INPUT, parent_window, name)
        if response == Gtk.ResponseType.CANCEL:
            return
        srv_name = response
        model.set_value(itr, Column.SRV_SERVICE, response)
        if fav_view is not None:
            for row in fav_view.get_model():
                if row[Column.FAV_ID] == fav_id:
                    row[Column.FAV_SERVICE] = response
                    break
    elif target is ViewTarget.FAV:
        name, srv_type, fav_id = model.get(itr, Column.FAV_SERVICE, Column.FAV_TYPE, Column.FAV_ID)
        f_id = fav_id
        response = show_dialog(DialogType.INPUT, parent_window, name)
        if response == Gtk.ResponseType.CANCEL:
            return

        srv_name = response
        if not model.get_value(itr, Column.FAV_BACKGROUND):
            model.set_value(itr, Column.FAV_SERVICE, response)

        if service_view is not None:
            for row in get_base_model(service_view.get_model()):
                if row[Column.SRV_FAV_ID] == fav_id:
                    row[Column.SRV_SERVICE] = response
                    break

    old_srv = services.get(f_id, None)
    if old_srv:
        if srv_type == BqServiceType.IPTV.name or srv_type == BqServiceType.MARKER.name:
            l, sep, r = f_id.partition("#DESCRIPTION")
            old_name = old_srv.service.strip()
            new_name = srv_name.strip()
            new_fav_id = "".join((new_name.join(l.rsplit(old_name, 1)), sep, new_name.join(r.rsplit(old_name, 1))))
            services[f_id] = old_srv._replace(service=srv_name, fav_id=new_fav_id)
        else:
            services[f_id] = old_srv._replace(service=srv_name)


def get_selection(view, parent):
    """ Returns (model, paths) if possible """
    model, paths = view.get_selection().get_selected_rows()
    model = get_base_model(model)

    if not paths:
        return
    elif len(paths) > 1:
        show_dialog(DialogType.ERROR, parent, "Please, select only one item!")
        return

    return model, paths


# ***************** Flags *******************#

def set_flags(flag, services_view, fav_view, services, blacklist):
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

    paths = get_base_paths(paths, model)
    model = get_base_model(model)

    if flag is Flag.HIDE:
        if target is ViewTarget.SERVICES:
            set_hide(services, model, paths)
        else:
            fav_ids = [model.get_value(model.get_iter(path), Column.FAV_ID) for path in paths]
            srv_model = get_base_model(services_view.get_model())
            srv_paths = [row.path for row in srv_model if row[Column.SRV_FAV_ID] in fav_ids]
            set_hide(services, srv_model, srv_paths)
    elif flag is Flag.LOCK:
        set_lock(blacklist, services, model, paths, target, services_model=get_base_model(services_view.get_model()))

    update_fav_model(fav_view, services)


def update_fav_model(fav_view, services):
    for row in get_base_model(fav_view.get_model()):
        srv = services.get(row[Column.FAV_ID], None)
        if srv:
            row[Column.FAV_LOCKED], row[Column.FAV_HIDE] = srv.locked, srv.hide


def set_lock(blacklist, services, model, paths, target, services_model):
    col_num = Column.SRV_LOCKED if target is ViewTarget.SERVICES else Column.FAV_LOCKED
    locked = has_locked_hide(model, paths, col_num)

    ids = []
    skip_type = {BqServiceType.MARKER.name, BqServiceType.SPACE.name, BqServiceType.ALT.name}

    for path in paths:
        itr = model.get_iter(path)
        fav_id = model.get_value(itr, Column.SRV_FAV_ID if target is ViewTarget.SERVICES else Column.FAV_ID)
        srv = services.get(fav_id, None)
        if srv and srv.service_type not in skip_type:
            bq_id = srv.data_id if srv.service_type == BqServiceType.IPTV.name else to_bouquet_id(srv)
            if not bq_id:
                continue
            blacklist.discard(bq_id) if locked else blacklist.add(bq_id)
            model.set_value(itr, col_num, None if locked else LOCKED_ICON)
            services[fav_id] = srv._replace(locked=None if locked else LOCKED_ICON)
            ids.append(fav_id)

    if target is ViewTarget.FAV and ids:
        gen = update_services_model(ids, locked, services_model)
        GLib.idle_add(lambda: next(gen, False))


def update_services_model(ids, locked, services_model):
    for srv in services_model:
        if srv[Column.SRV_FAV_ID] in ids:
            srv[Column.SRV_LOCKED] = None if locked else LOCKED_ICON
        yield True


def set_hide(services, model, paths):
    col_num = Column.SRV_HIDE
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
            if Flag.is_hide(value):
                continue  # skip if already hidden
            value += Flag.HIDE.value
        else:
            if not Flag.is_hide(value):
                continue  # skip if already allowed to show
            value -= Flag.HIDE.value

        if value == 0 and index is not None:
            del flags[index]
        else:
            value = "f:{:02d}".format(value)
            if index is not None:
                flags[index] = value
            else:
                flags.append(value)

        model.set_value(itr, 0, (",".join(reversed(sorted(flags)))))
        fav_id = model.get_value(itr, Column.SRV_FAV_ID)
        srv = services.get(fav_id, None)
        if srv:
            services[fav_id] = srv._replace(hide=None if hide else HIDE_ICON)


def has_locked_hide(model, paths, col_num):
    for path in paths:
        if model.get_value(model.get_iter(path), col_num):
            return True
    return False


# ***************** Location *******************#

def locate_in_services(fav_view, services_view, column, parent_window):
    """ Locating and scrolling to the service """
    model, paths = fav_view.get_selection().get_selected_rows()

    if not paths:
        return
    elif len(paths) > 1:
        show_dialog(DialogType.ERROR, parent_window, "Please, select only one item!")
        return

    fav_id = model.get_value(model.get_iter(paths[0]), Column.FAV_ID)
    for index, row in enumerate(services_view.get_model()):
        if row[column] == fav_id:
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


# ***************** Picons ********************* #

def get_picon_dialog(transient, title, button_text, multiple=True):
    """ Returns a copy dialog with a preview of images [picons -> *.png]. """
    dialog = Gtk.FileChooserNative.new(title, transient, Gtk.FileChooserAction.OPEN, button_text)
    dialog.set_select_multiple(multiple)
    dialog.set_modal(True)
    # Filter.
    file_filter = Gtk.FileFilter()
    file_filter.set_name("*.png")
    file_filter.add_pattern("*.png")
    file_filter.add_mime_type("image/png") if IS_DARWIN else None
    dialog.add_filter(file_filter)

    if IS_LINUX:
        preview_image = Gtk.Image(margin_right=10)
        dialog.set_preview_widget(preview_image)

        def update_preview_widget(dlg):
            path = dialog.get_preview_filename()
            if not path:
                return

            pix = get_picon_pixbuf(path, 220)
            preview_image.set_from_pixbuf(pix)
            dlg.set_preview_widget_active(bool(pix))

        dialog.connect("update-preview", update_preview_widget)

    return dialog


def assign_picons(target, srv_view, fav_view, transient, picons, settings, services, src_path=None, dst_path=None):
    """ Assigning  picons and returns picons files list. """
    view = srv_view if target is ViewTarget.SERVICES else fav_view
    model, paths = view.get_selection().get_selected_rows()
    picons_files = []

    if not src_path:
        dialog = get_picon_dialog(transient, translate("Picon selection"), translate("Open"), False)
        if dialog.run() in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT) or not dialog.get_filenames():
            return picons_files

        src_path = dialog.get_filenames()[0]

    if IS_WIN:
        src_path = src_path.lstrip("/")
        dst_path = dst_path.lstrip("/") if dst_path else dst_path

    if not str(src_path).endswith(".png") or not os.path.isfile(src_path):
        show_dialog(DialogType.ERROR, transient, text="No png file is selected!")
        return picons_files

    p_pos = Column.SRV_PICON
    col_num = Column.SRV_FAV_ID if target is ViewTarget.SERVICES else Column.FAV_ID
    itrs = [model.get_iter(p) for p in paths]

    if target is ViewTarget.SERVICES:
        f_model = model.get_model()
        itrs = [f_model.convert_iter_to_child_iter(model.convert_iter_to_child_iter(itr)) for itr in itrs]
        model = get_base_model(model)

    for itr in itrs:
        fav_id = model.get_value(itr, col_num)
        picon_id = services.get(fav_id)[Column.SRV_PICON_ID]

        if picon_id:
            picons_path = dst_path or settings.profile_picons_path
            os.makedirs(os.path.dirname(picons_path), exist_ok=True)
            picon_file = picons_path + picon_id
            try:
                shutil.copy(src_path, picon_file)
            except shutil.SameFileError:
                pass  # NOP
            else:
                picons_files.append(picon_file)
                picon = get_picon_pixbuf(picon_file, settings.list_picon_size)
                picons[picon_id] = picon
                model.set_value(itr, p_pos, picon)
                if target is ViewTarget.SERVICES:
                    set_picon(fav_id, fav_view.get_model(), picon, Column.FAV_ID, p_pos)
                else:
                    set_picon(fav_id, get_base_model(srv_view.get_model()), picon, Column.SRV_FAV_ID, p_pos)

    return picons_files


def set_picon(fav_id, model, picon, fav_id_pos, picon_pos):
    for row in model:
        if row[fav_id_pos] == fav_id:
            row[picon_pos] = picon
            return True
    return True


def remove_picon(target, srv_view, fav_view, picons, settings):
    view = srv_view if target is ViewTarget.SERVICES else fav_view
    model, paths = view.get_selection().get_selected_rows()

    fav_ids = []
    picon_ids = []
    picon_pos = Column.SRV_PICON  # picon position is equal for services and fav

    itrs = [model.get_iter(p) for p in paths]

    if target is ViewTarget.SERVICES:
        f_model = model.get_model()
        itrs = [f_model.convert_iter_to_child_iter(model.convert_iter_to_child_iter(itr)) for itr in itrs]
        model = get_base_model(model)

    for itr in itrs:
        model.set_value(itr, picon_pos, None)
        if target is ViewTarget.SERVICES:
            fav_ids.append(model.get_value(itr, Column.SRV_FAV_ID))
            picon_ids.append(model.get_value(itr, Column.SRV_PICON_ID))
        else:
            srv_type, fav_id = model.get(itr, Column.FAV_TYPE, Column.FAV_ID)
            if srv_type == BqServiceType.IPTV.name:
                picon_ids.append("{}_{}_{}_{}_{}_{}_{}_{}_{}_{}.png".format(*fav_id.split(":")[0:10]).strip())
            else:
                fav_ids.append(fav_id)

    fav_id_column = Column.FAV_ID if target is ViewTarget.SERVICES else Column.SRV_FAV_ID

    def remove(md, path, it):
        if md.get_value(it, fav_id_column) in fav_ids:
            md.set_value(it, picon_pos, None)
            if target is ViewTarget.FAV:
                picon_ids.append(md.get_value(it, Column.SRV_PICON_ID))

    fav_view.get_model().foreach(remove) if target is ViewTarget.SERVICES else get_base_model(
        srv_view.get_model()).foreach(remove)

    remove_picons(settings, picon_ids, picons)


def remove_all_unused_picons(settings, services):
    """ Removes picons from profile picons folder if there are no services for these picons. """
    ids = {s.picon_id for s in services}
    for p in Path(settings.profile_picons_path).glob("*.png"):
        if p.name not in ids and p.is_file():
            p.unlink()


def remove_picons(settings, picon_ids, picons):
    pions_path = settings.profile_picons_path
    backup_path = f"{settings.profile_backup_path}picons{SEP}"
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    for p_id in picon_ids:
        picons[p_id] = None
        src = pions_path + p_id
        if os.path.isfile(src):
            shutil.move(src, backup_path + p_id)


def is_only_one_item_selected(paths, app):
    if len(paths) > 1:
        app.show_error_message("Please, select only one item!")
        return False

    if not paths:
        app.show_error_message("No selected item!")
        return False

    return True


def get_picon_pixbuf(path, size=32):
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width=size, height=size, preserve_aspect_ratio=True)
    except GLib.GError:
        pass  # NOP


def get_pixbuf_from_data(img_data, w=48, h=32):
    if img_data:
        f = Gio.MemoryInputStream.new_from_data(img_data)
        return GdkPixbuf.Pixbuf.new_from_stream_at_scale(f, w, h, True, None)


def get_pixbuf_at_scale(path, width, height, p_ratio):
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width, height, p_ratio)
    except GLib.GError:
        pass


@lru_cache(50)
def get_picon_file_name(service_name):
    """ Returns picon file name by service name. """
    name = unicodedata.normalize("NFKD", service_name).encode("ASCII", errors="ignore").decode(errors="ignore")
    return f"{re.sub('[^a-z0-9]', '', name.replace('&', 'and').replace('+', 'plus').replace('*', 'star').lower())}.png"


# ***************** Bouquets ********************* #

def gen_bouquets(app, gen_type):
    """ Auto-generate and append list of bouquets. """
    model, paths = app.services_view.get_selection().get_selected_rows()
    single_types = {BqGenType.SAT, BqGenType.PACKAGE, BqGenType.TYPE}
    if gen_type in single_types and not is_only_one_item_selected(paths, app):
        return

    index = Column.SRV_TYPE
    if gen_type in (BqGenType.PACKAGE, BqGenType.EACH_PACKAGE):
        index = Column.SRV_PACKAGE
    elif gen_type in (BqGenType.SAT, BqGenType.EACH_SAT):
        index = Column.SRV_POS

    ids = {row[Column.SRV_FAV_ID] for row in model}
    services = [v for k, v in app.current_services.items() if k in ids]

    srv = Service(*model[paths][:Column.SRV_TOOLTIP])
    cond = srv.package if gen_type is BqGenType.PACKAGE else srv.pos if gen_type is BqGenType.SAT else srv.service_type

    if gen_type is BqGenType.TYPE and cond == "Data":
        msg = f"{translate('Selected type:')} '{cond}'\n\n{translate('Are you sure?')}"
        if show_dialog(DialogType.QUESTION, app.app_window, msg) != Gtk.ResponseType.OK:
            return

    def grouper(s):
        data = s[index]
        return data if data else "None"

    services = {k: list(v) for k, v in groupby(sorted(services, key=grouper), key=grouper)}

    bq_view = app.bouquets_view
    bq_type = BqType.TV.value if app.is_enigma else BqType.BOUQUET.value
    bq_index = 0 if app.is_enigma else 1
    bq_root_iter = bq_view.get_model().get_iter(bq_index)

    bq_names = get_bouquets_names(bq_view.get_model())

    if gen_type in single_types:
        if cond in bq_names:
            app.show_error_message("A bouquet with that name exists!")
            return

        bq_services = get_services_type_groups(services.get(cond, []))
        if app.is_enigma:
            if srv.service_type == "Radio":
                bq_index = 1
                bq_type = BqType.RADIO.value
                bq_root_iter = bq_view.get_model().get_iter(bq_index)
                bq_view.expand_row(Gtk.TreePath(bq_index), 1)
                bq_services = bq_services.get("Radio", [])
            else:
                bq_view.expand_row(Gtk.TreePath(bq_index), 0)
                bq_services = bq_services.get("Data" if srv.service_type == "Data" else "TV", [])
        app.append_bouquet(Bouquet(cond, bq_type, get_bouquet_services(bq_services)), bq_root_iter)
    else:
        bq_view.expand_row(Gtk.TreePath(bq_index), 0)
        # We add a bouquet only if the given name is missing [keys - names]!
        if gen_type is BqGenType.EACH_SAT:
            bq_names = sorted(services.keys() - bq_names, key=get_pos_num, reverse=True)
        else:
            bq_names = sorted(services.keys() - bq_names)

        tv_bqs = []
        radio_bqs = []
        for n in bq_names:
            bqs = services.get(n, [])
            # TV and Radio separation.
            bq_grp = get_services_type_groups(bqs)
            tv_bq = bq_grp.get("TV", [])
            tv_bqs.append(Bouquet(n, BqType.TV.value, get_bouquet_services(tv_bq))) if tv_bq else None
            radio_bq = bq_grp.get("Radio", [])
            radio_bqs.append(Bouquet(n, BqType.RADIO.value, get_bouquet_services(radio_bq))) if radio_bq else None

        [app.append_bouquet(b, bq_root_iter) for b in tv_bqs]
        if app.is_enigma:
            bq_root_iter = bq_view.get_model().get_iter(bq_index + 1)
            bq_view.expand_row(Gtk.TreePath(bq_index + 1), 0)
            [app.append_bouquet(b, bq_root_iter) for b in radio_bqs]


def get_bouquet_services(services):
    services.sort(key=lambda s: s.service)
    return [BouquetService(None, BqServiceType.DEFAULT, s.fav_id, 0) for s in services]


def get_bouquets_names(model):
    """ Returns all current bouquets names """
    bouquets_names = set()
    for row in model:
        itr = row.iter
        if model.iter_has_child(itr):
            num_of_children = model.iter_n_children(itr)
            for num in range(num_of_children):
                child_itr = model.iter_nth_child(itr, num)
                bouquets_names.add(model[child_itr][0])
    return bouquets_names


def get_services_type_groups(services):
    """ Returns services grouped by main types [TV, Radio, Data]. -> dict """

    def type_grouper(s):
        s_type = s.service_type

        if s_type == "Data":
            return s_type
        elif s_type == "Radio":
            return s_type
        else:
            return "TV"

    return {k: list(v) for k, v in groupby(sorted(services, key=type_grouper), key=type_grouper)}


# ***************** Others ********************* #

def copy_reference(view, app):
    """ Copying picon id to clipboard. """
    model, paths = view.get_selection().get_selected_rows()
    if not is_only_one_item_selected(paths, app):
        return

    target = app.get_target_view(view)
    clipboard = app._clipboard

    if target is ViewTarget.SERVICES:
        picon_id = model.get_value(model.get_iter(paths), Column.SRV_PICON_ID)
        if picon_id:
            clipboard.set_text(picon_id.rstrip(".png"), -1)
        else:
            app.show_error_message("No reference is present!")
    elif target is ViewTarget.FAV:
        fav_id = model.get_value(model.get_iter(paths), Column.FAV_ID)
        srv = app.current_services.get(fav_id, None)
        if srv and srv.picon_id:
            clipboard.set_text(get_service_reference(srv), -1)
        else:
            app.show_error_message("No reference is present!")

    app.emit("clipboard-changed", clipboard.wait_is_text_available())


def get_service_reference(srv):
    return srv.picon_id.rstrip(".png")


def update_entry_data(entry, dialog, settings):
    """ Updates value in text entry from chooser dialog. """
    response = show_dialog(dialog_type=DialogType.CHOOSER, transient=dialog, settings=settings, create_dir=True)
    if response not in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
        entry.set_text(response)
        return response
    return False


def get_base_model(model):
    """ Returns base tree model if has wrappers [TreeModelSort, TreeModelFilter]. """
    if type(model) is Gtk.TreeModelSort:
        return model.get_model().get_model()
    return model


def get_base_itrs(itrs, model):
    """ Returns base iters from wrapper models. """
    if type(model) is Gtk.TreeModelSort:
        filter_model = model.get_model()
        return [filter_model.convert_iter_to_child_iter(model.convert_iter_to_child_iter(itr)) for itr in itrs]
    return itrs


def get_base_paths(paths, model):
    """ Returns base paths from wrapper models. """
    if type(model) is Gtk.TreeModelSort:
        filter_model = model.get_model()
        return [filter_model.convert_path_to_child_path(model.convert_path_to_child_path(p)) for p in paths]
    return paths


def get_model_data(view):
    """ Returns model name and base model from the given view """
    model = get_base_model(view.get_model())
    model_name = model.get_name() if model else ""
    return model_name, model


def update_toggle_model(model, path, toggle):
    """ Updates the toggle state for the model. """
    active = not toggle.get_active()
    if path == "0":
        model.foreach(lambda m, p, i: m.set_value(i, 1, active))
    else:
        model.set_value(model.get_iter(path), 1, active)
        if active:
            model.set_value(model.get_iter_first(), 1, len({r[0] for r in model if r[1]}) == len(model) - 1)
        else:
            model.set_value(model.get_iter_first(), 1, False)


def update_popup_filter_model(model, elements: set):
    first = model[model.get_iter_first()][:]
    model.clear()
    model.append((first[0], True))
    elements.discard(first[0])


def update_filter_sat_positions(model, sat_positions):
    """ Updates the values for the satellite positions button model. """
    update_popup_filter_model(model, sat_positions)
    list(map(lambda pos: model.append((pos, True)), sorted(sat_positions, key=get_pos_num, reverse=True)))


def get_pos_num(pos):
    """ Returns num [float] representation of satellite position. """
    if not pos:
        return -183.0

    if len(pos) > 1:
        m = -1 if pos[-1] == "W" else 1
        return float(pos[:-1]) * m

    return -181.0 if pos == "T" else -182.0


def append_text_to_tview(char, view):
    """ Appending text and scrolling  to a given line in the text view. """
    buf = view.get_buffer()
    buf.insert_at_cursor(char)
    insert = buf.get_insert()
    view.scroll_to_mark(insert, 0.0, True, 0.0, 1.0)


def get_iptv_url(row, s_type, column=Column.FAV_ID):
    """ Returns url from iptv type row """
    data = row[column].split(":" if s_type is SettingsType.ENIGMA_2 else "::")
    if s_type is SettingsType.ENIGMA_2:
        data = list(filter(lambda x: "http" in x, data))
    if data:
        url = data[0]
        return unquote(url) if s_type is SettingsType.ENIGMA_2 else url


def get_iptv_data(fav_id):
    """ Returns the reference and URL as a tuple from the fav_id. """
    data, sep, desc = fav_id.partition("#DESCRIPTION")
    data = data.split(":")
    if len(data) < 11:
        return None, desc
    return ":".join(data[:10]), unquote(data[10].strip())


def on_popup_menu(menu, event):
    """ Shows popup menu for the view """
    if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
        menu.popup(None, None, None, None, event.button, event.time)


if __name__ == "__main__":
    pass

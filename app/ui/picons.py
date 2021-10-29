# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2021 Dmitriy Yefremov
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


import os
import re
import shutil
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse, unquote

from gi.repository import GLib, GdkPixbuf, Gio

from app.commons import run_idle, run_task, run_with_delay, log
from app.connections import upload_data, DownloadType, download_data, remove_picons
from app.settings import SettingsType, Settings, SEP, IS_LINUX, IS_DARWIN
from app.tools.picons import (PiconsParser, parse_providers, Provider, convert_to, download_picon, PiconsCzDownloader,
                              PiconsError)
from app.tools.satellites import SatellitesParser, SatelliteSource
from .dialogs import show_dialog, DialogType, get_message, get_builder, get_chooser_dialog
from .main_helper import (update_entry_data, append_text_to_tview, scroll_to, on_popup_menu, get_base_model, set_picon,
                          get_picon_pixbuf)
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, TV_ICON, Column, KeyboardKey, Page


class PiconManager(Gtk.Box):
    class DownloadSource(Enum):
        LYNG_SAT = "lyngsat"
        PICON_CZ = "piconcz"

    def __init__(self, app, settings, picon_ids, sat_positions, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._app = app
        self._app.connect("page-changed", self.update_picons_dest)
        self._app.connect("filter-toggled", self.on_app_filter_toggled)
        self._app.connect("profile-changed", self.on_profile_changed)
        self._app.fav_view.connect("row-activated", self.on_fav_changed)
        self._picon_ids = picon_ids
        self._sat_positions = sat_positions
        self._BASE_URL = "www.lyngsat.com/packages/"
        self._PATTERN = re.compile(r"^https://www\.lyngsat\.com/[\w-]+\.html$")
        self._POS_PATTERN = re.compile(r"^\d+\.\d+[EW]?$")
        self._current_process = None
        self._terminate = False
        self._is_downloading = False
        self._filter_binding = None
        self._services = None
        self._current_picon_info = None
        self._filter_cache = {}
        # Downloader
        self._sats = None
        self._sat_names = None
        self._download_src = self.DownloadSource.PICON_CZ
        self._picon_cz_downloader = None

        handlers = {"on_tool_switched": self.on_tool_switched,
                    "on_add": self.on_add,
                    "on_extract": self.on_extract,
                    "on_receive": self.on_receive,
                    "on_cancel": self.on_cancel,
                    "on_send": self.on_send,
                    "on_download": self.on_download,
                    "on_remove": self.on_remove,
                    "on_picons_dir_open": self.on_picons_dir_open,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_url_changed": self.on_url_changed,
                    "on_picons_filter_changed": self.on_picons_filter_changed,
                    "on_position_edited": self.on_position_edited,
                    "on_convert": self.on_convert,
                    "on_picons_view_drag_data_get": self.on_picons_view_drag_data_get,
                    "on_picons_view_drag_drop": self.on_picons_view_drag_drop,
                    "on_picons_view_drag_data_received": self.on_picons_view_drag_data_received,
                    "on_picons_view_drag_end": self.on_picons_view_drag_end,
                    "on_picon_info_image_drag_data_received": self.on_picon_info_image_drag_data_received,
                    "on_send_button_drag_data_received": self.on_send_button_drag_data_received,
                    "on_download_button_drag_data_received": self.on_download_button_drag_data_received,
                    "on_remove_button_drag_data_received": self.on_remove_button_drag_data_received,
                    "on_selective_send": self.on_selective_send,
                    "on_selective_download": self.on_selective_download,
                    "on_selective_remove": self.on_selective_remove,
                    "on_local_remove": self.on_local_remove,
                    "on_download_source_changed": self.on_download_source_changed,
                    "on_satellites_view_realize": self.on_satellites_view_realize,
                    "on_satellite_filter_toggled": self.on_satellite_filter_toggled,
                    "on_providers_view_query_tooltip": self.on_providers_view_query_tooltip,
                    "on_satellite_selection": self.on_satellite_selection,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_fiter_srcs_toggled": self.on_fiter_srcs_toggled,
                    "on_picon_activated": self.on_picon_activated,
                    "on_view_query_tooltip": self.on_view_query_tooltip,
                    "on_tree_view_key_press": self.on_tree_view_key_press,
                    "on_popup_menu": on_popup_menu}

        builder = get_builder(UI_RESOURCES_PATH + "picons.glade", handlers)

        self._app_window = app.get_active_window()
        self._stack = builder.get_object("stack")
        self._picons_src_view = builder.get_object("picons_src_view")
        self._picons_dest_view = builder.get_object("picons_dest_view")
        self._providers_view = builder.get_object("providers_view")
        self._satellites_view = builder.get_object("satellites_view")
        self._picons_src_filter_model = builder.get_object("picons_src_filter_model")
        self._picons_src_filter_model.set_visible_func(self.picons_src_filter_function)
        self._picons_dst_filter_model = builder.get_object("picons_dst_filter_model")
        self._picons_dst_filter_model.set_visible_func(self.picons_dst_filter_function)
        self._src_filter_button = builder.get_object("src_filter_button")
        self._dst_filter_button = builder.get_object("dst_filter_button")
        self._picons_filter_entry = builder.get_object("picons_filter_entry")
        self._current_path_label = builder.get_object("current_path_label")
        self._download_source_button = builder.get_object("download_source_button")
        self._receive_button = builder.get_object("receive_button")
        self._convert_button = builder.get_object("convert_button")
        self._enigma2_path_button = builder.get_object("enigma2_path_button")
        self._save_to_button = builder.get_object("save_to_button")
        self._send_button = builder.get_object("send_button")
        self._download_button = builder.get_object("download_button")
        self._remove_button = builder.get_object("remove_button")
        self._cancel_button = builder.get_object("cancel_button")
        self._enigma2_radio_button = builder.get_object("enigma2_radio_button")
        self._neutrino_mp_radio_button = builder.get_object("neutrino_mp_radio_button")
        self._resize_no_radio_button = builder.get_object("resize_no_radio_button")
        self._resize_220_132_radio_button = builder.get_object("resize_220_132_radio_button")
        self._resize_100_60_radio_button = builder.get_object("resize_100_60_radio_button")
        self._satellite_label = builder.get_object("satellite_label")
        self._src_link_button = builder.get_object("src_link_button")
        self._satellite_filter_switch = builder.get_object("satellite_filter_switch")
        self._bouquet_filter_switch = builder.get_object("bouquet_filter_switch")
        self._providers_header_box = builder.get_object("providers_header_box")
        self._header_download_box = builder.get_object("header_download_box")
        self._satellite_label.bind_property("visible", builder.get_object("loading_data_label"), "visible", 4)
        self._satellite_label.bind_property("visible", builder.get_object("loading_data_spinner"), "visible", 4)
        self._satellite_label.bind_property("visible", self._download_source_button, "sensitive")
        self._satellite_label.bind_property("visible", self._satellites_view, "sensitive")
        self._cancel_button.bind_property("visible", self._header_download_box, "visible", 4)
        self._convert_button.bind_property("visible", self._header_download_box, "visible", 4)
        self._download_source_button.bind_property("visible", self._receive_button, "visible")
        # Info.
        self._dst_count_label = builder.get_object("dst_count_label")
        self._info_check_button = builder.get_object("info_check_button")
        self._picon_info_image = builder.get_object("picon_info_image")
        self._picon_info_label = builder.get_object("picon_info_label")
        self._info_view = builder.get_object("info_view")
        self._info_bar = builder.get_object("info_bar")
        self._info_bar.bind_property("visible", builder.get_object("info_bar_frame"), "visible")
        self._info_bar.connect("response", lambda b, r: b.set_visible(False))
        # Filter.
        self._filter_bar = builder.get_object("filter_bar")
        self._auto_filter_switch = builder.get_object("auto_filter_switch")
        self._filter_button = builder.get_object("filter_button")
        self._filter_button.bind_property("active", self._filter_bar, "visible")
        self._filter_button.bind_property("active", self._src_filter_button, "visible")
        self._filter_button.bind_property("active", self._dst_filter_button, "visible")
        self._filter_button.bind_property("visible", self._info_check_button, "visible")
        self._filter_button.bind_property("visible", self._send_button, "visible")
        self._filter_button.bind_property("visible", self._download_button, "visible")
        self._filter_button.bind_property("visible", self._remove_button, "visible")
        self._src_button = builder.get_object("src_button")
        self._src_button.bind_property("active", builder.get_object("explorer_dst_label"), "visible")
        self._src_button.bind_property("active", builder.get_object("src_picon_box_frame"), "visible")
        self._filter_button.bind_property("visible", self._src_button, "visible")
        self._info_check_button.bind_property("active", builder.get_object("explorer_info_box_frame"), "visible")
        # Header buttons. -> Used instead stack switcher.
        self._manager_button = builder.get_object("manager_button")
        self._manager_button.bind_property("active", builder.get_object("manager_label"), "visible")
        self._downloader_button = builder.get_object("downloader_button")
        self._downloader_button.bind_property("active", builder.get_object("downloader_label"), "visible")
        self._converter_button = builder.get_object("converter_button")
        self._converter_button.bind_property("active", builder.get_object("converter_label"), "visible")
        self._manager_button.bind_property("active", builder.get_object("add_menu_button"), "visible")
        # Init drag-and-drop
        self.init_drag_and_drop()
        # Settings
        self._settings = settings
        self._s_type = settings.setting_type
        self._current_path_label.set_text(self._settings.profile_picons_path)

        self.pack_start(builder.get_object("main_frame"), True, True, 0)
        self.show()

        if not len(self._picon_ids) and self._s_type is SettingsType.ENIGMA_2:
            message = get_message("To automatically set the identifiers for picons,\n"
                                  "first load the required services list into the main application window.")
            self.show_info_message(message, Gtk.MessageType.WARNING)
            self._satellite_label.show()

    def on_tool_switched(self, button):
        if not button.get_active():
            return True

        is_explorer = button is self._manager_button
        is_downloader = button is self._downloader_button
        is_converter = button is self._converter_button

        name = "explorer"
        if is_downloader:
            name = "downloader"
        elif is_converter:
            name = "converter"

        self._stack.set_visible_child_name(name)

        self._convert_button.set_visible(is_converter)
        self._download_source_button.set_visible(is_downloader)
        self._filter_button.set_visible(is_explorer)
        if is_explorer:
            self.update_picons_data(self._picons_dest_view)

    def on_open(self):
        """ Opens picons from local path [in src view]. """
        response = show_dialog(DialogType.CHOOSER, self._app.app_window, settings=self._settings, title="Open folder")
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        self._src_button.set_active(True)
        self.update_picons_data(self._picons_src_view, response)

    def update_picons_dest(self, app, page):
        if page is Page.PICONS:
            self._services = {s.picon_id: s for s in self._app.current_services.values() if s.picon_id}
            self.update_picons_data(self._picons_dest_view)

    def on_profile_changed(self, app, data):
        self._current_path_label.set_text(self._settings.profile_picons_path)
        self.update_picons_dest(app, self._app.page)

    def update_picons_data(self, view, path=None):
        if view is self._picons_dest_view:
            self.update_picon_info()

        gen = self.update_picons(path or self._settings.profile_picons_path, view)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def update_picons(self, path, view):
        p_model = view.get_model()
        model = get_base_model(p_model)
        factor = self._app.DEL_FACTOR

        for index, itr in enumerate([row.iter for row in model]):
            model.remove(itr)
            if index % factor == 0:
                yield True

        self._dst_count_label.set_text("0")
        if not os.path.isdir(path):
            return

        for index, file in enumerate(os.listdir(path)):
            if self._terminate:
                return

            p_path = f"{path}{SEP}{file}"
            p = self.get_pixbuf_at_scale(p_path, 72, 48, True)
            if p:
                model.append((p, file, p_path))

            if index % factor == 0:
                self._dst_count_label.set_text(str(len(model)))
                yield True

        self._dst_count_label.set_text(str(len(model)))
        yield True

    def update_picons_from_file(self, view, uri):
        """ Adds picons in the view on dragging from file system. """
        path = Path(urlparse(unquote(uri)).path.strip())
        f_path = str(path.resolve())
        if not f_path:
            return

        model = get_base_model(view.get_model())

        if path.is_file():
            p = self.get_pixbuf_at_scale(f_path, 72, 48, True)
            if p:
                model.append((p, path.name, f_path))
        elif path.is_dir():
            self.update_picons_data(view, f_path)

    def get_pixbuf_at_scale(self, path, width, height, p_ratio):
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width, height, p_ratio)
        except GLib.GError:
            pass

    # ***************** Drag-and-drop ********************* #

    def init_drag_and_drop(self):
        self._picons_src_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self._picons_src_view.drag_source_add_uri_targets()

        self._picons_dest_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self._picons_dest_view.drag_source_add_uri_targets()

        self._picons_src_view.enable_model_drag_dest([], Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._picons_src_view.drag_dest_add_text_targets()

        self._picons_dest_view.enable_model_drag_dest([], Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._picons_dest_view.drag_dest_add_text_targets()

        self._picon_info_image.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self._picon_info_image.drag_dest_add_uri_targets()

        self._send_button.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self._send_button.drag_dest_add_uri_targets()

        self._download_button.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self._download_button.drag_dest_add_uri_targets()

        self._remove_button.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self._remove_button.drag_dest_add_uri_targets()

    def on_picons_view_drag_data_get(self, view, drag_context, data, info, time):
        model, path = view.get_selection().get_selected_rows()
        if path:
            data.set_uris([Path(model[path][-1]).as_uri(),
                           Path(self._settings.profile_picons_path).as_uri()])

    def on_picons_view_drag_drop(self, view, drag_context, x, y, time):
        view.stop_emission_by_name("drag_drop")
        targets = drag_context.list_targets()
        view.drag_get_data(drag_context, targets[-1] if targets else Gdk.atom_intern("text/plain", False), time)

    def on_picons_view_drag_data_received(self, view, drag_context, x, y, data, info, time):
        view.stop_emission_by_name("drag_data_received")
        txt = data.get_text()
        if not txt:
            return

        if txt.startswith("file://"):
            self.update_picons_from_file(view, txt)
            return

        itr_str, sep, src = txt.partition("::::")
        if src == self._app.BQ_MODEL_NAME:
            return

        path, pos = view.get_dest_row_at_pos(x, y) or (None, None)
        if not path:
            return

        model = view.get_model()
        if src == self._app.FAV_MODEL_NAME:
            target_view = self._app.fav_view
            c_id = Column.FAV_ID
        else:
            target_view = self._app.services_view
            c_id = Column.SRV_FAV_ID

        t_mod = target_view.get_model()
        dest_path = self._settings.profile_picons_path
        self.update_picons_dest_view(self._app.on_assign_picon(target_view, model[path][-1], dest_path))
        self.show_assign_info([t_mod.get_value(t_mod.get_iter_from_string(itr), c_id) for itr in itr_str.split(",")])

    @run_idle
    def update_picons_dest_view(self, picons):
        """ Update destination view on adding/changing picons. """
        if picons:
            dest_model = get_base_model(self._picons_dest_view.get_model())
            paths = {r[1]: r.iter for r in dest_model}

            for p_path in picons:
                p = self.get_pixbuf_at_scale(p_path, 72, 48, True)
                if p:
                    p_name = Path(p_path).name
                    itr = paths.get(p_name, None)
                    if itr:
                        dest_model.set_value(itr, 0, p)
                    else:
                        itr = dest_model.append((p, p_name, p_path))
                    scroll_to(dest_model.get_path(itr), self._picons_dest_view)

            self._dst_count_label.set_text(str(len(dest_model)))

    @run_idle
    def show_assign_info(self, fav_ids):
        self._info_bar.show()
        self._info_view.get_buffer().set_text("")
        for i in fav_ids:
            srv = self._app.current_services.get(i, None)
            if srv:
                info = self._app.get_hint_for_srv_list(srv)
                self.append_output(f"Picon assignment for the service:\n{info}\n{' * ' * 30}\n")

    def on_picons_view_drag_end(self, view, drag_context):
        self.update_picons_dest_view(self._app.picons_buffer)

    def on_picon_info_image_drag_data_received(self, img, drag_context, x, y, data, info, time):
        if not self._current_picon_info:
            self.show_info_message("No selected item!", Gtk.MessageType.ERROR)
            return

        uris = data.get_uris()
        if len(uris) == 2:
            name, fav_id = self._current_picon_info
            src = urlparse(unquote(uris[0])).path
            dst = f"{urlparse(unquote(uris[1])).path}{SEP}{name}"
            if src != dst:
                shutil.copy(src, dst)
                for row in get_base_model(self._picons_dest_view.get_model()):
                    if name == row[1]:
                        row[0] = self.get_pixbuf_at_scale(row[-1], 72, 48, True)
                        img.set_from_pixbuf(self.get_pixbuf_at_scale(row[-1], 100, 60, True))

                gen = self.update_picon_in_lists(dst, fav_id)
                GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_send_button_drag_data_received(self, button, drag_context, x, y, data, info, time):
        path = self.get_path_from_uris(data)
        if path:
            self.on_send(files_filter={path.name}, path=path.parent)

    def on_download_button_drag_data_received(self, button, drag_context, x, y, data, info, time):
        path = self.get_path_from_uris(data)
        if path:
            self.on_download(files_filter={path.name})

    def on_remove_button_drag_data_received(self, button, drag_context, x, y, data, info, time):
        path = self.get_path_from_uris(data)
        if path:
            self.on_remove(files_filter={path.name})

    def get_path_from_uris(self, data):
        uris = data.get_uris()
        if len(uris) == 2:
            return Path(urlparse(unquote(uris[0])).path).resolve()

    def update_picon_in_lists(self, dst, fav_id):
        picon = get_picon_pixbuf(dst)
        p_pos = Column.SRV_PICON
        yield set_picon(fav_id, get_base_model(self._app.services_view.get_model()), picon, Column.SRV_FAV_ID, p_pos)
        yield set_picon(fav_id, get_base_model(self._app.fav_view.get_model()), picon, Column.FAV_ID, p_pos)

    # ************************ Add/Extract ******************************** #

    def on_add(self, item):
        """ Adds (copies) picons from an external folder to the profile picons folder. """
        dialog = self.get_copy_dialog()
        if dialog.run() in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        self.copy_picons_file(dialog.get_filenames())

    def get_copy_dialog(self):
        """ Returns a copy dialog with a preview of images [picons -> *.png]. """
        dialog = Gtk.FileChooserNative.new(get_message("Add picons"), self._app_window,
                                           Gtk.FileChooserAction.OPEN, get_message("Add"))
        dialog.set_select_multiple(True)
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

    def on_extract(self, item):
        """ Extracts picons from an archives to the profile picons folder. """
        file_filter = None
        if IS_DARWIN:
            file_filter = Gtk.FileFilter()
            file_filter.set_name("*.zip, *.gz")
            file_filter.add_mime_type("application/zip")
            file_filter.add_mime_type("application/gzip")

        response = get_chooser_dialog(self._app_window, self._settings, "*.zip, *.gz files",
                                      ("*.zip", "*.gz"), "Extract picons", file_filter)
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        arch_path = self._app.get_archive_path(response)
        if arch_path:
            self.copy_picons_file(Path(arch_path.name).glob("*.png"), arch_path.cleanup)

    def copy_picons_file(self, files, callback=None):
        """ Copies files to the profile picons folder. """
        picon_path = self._settings.profile_picons_path
        os.makedirs(os.path.dirname(picon_path), exist_ok=True)

        try:
            picons = [shutil.copy(p, picon_path) for p in files]
        except shutil.SameFileError as e:
            log(e)
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            self.update_picons_dest_view(picons)
            self._app.update_picons()
        finally:
            if callback:
                callback()

    # ******************** Download/Upload/Remove ************************* #

    def on_selective_send(self, view):
        path = self.get_selected_path(view)
        if path:
            self.on_send(files_filter={path.name}, path=path.parent)

    def on_selective_download(self, view):
        path = self.get_selected_path(view)
        if path:
            self.on_download(files_filter={path.name})

    def on_selective_remove(self, view):
        path = self.get_selected_path(view)
        if path:
            self.on_remove(files_filter={path.name})

    def on_local_remove(self, view):
        model, paths = view.get_selection().get_selected_rows()
        if paths and show_dialog(DialogType.QUESTION, self._app_window) == Gtk.ResponseType.OK:
            itr = model.get_iter(paths.pop())
            p_path = Path(model.get_value(itr, 2)).resolve()
            if p_path.is_file():
                p_path.unlink()
                base_model = get_base_model(model)
                filter_model = model.get_model()
                itr = filter_model.convert_iter_to_child_iter(model.convert_iter_to_child_iter(itr))
                base_model.remove(itr)

        if view is self._picons_dest_view:
            self._dst_count_label.set_text(str(len(model)))

    def on_send(self, item=None, files_filter=None, path=None):
        dest_path = path or self._settings.profile_picons_path
        settings = Settings(self._settings.settings)
        settings.profile_picons_path = f"{dest_path}{SEP}"
        self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
        self.run_func(lambda: upload_data(settings=settings,
                                          download_type=DownloadType.PICONS,
                                          callback=self.append_output,
                                          done_callback=lambda: self.show_info_message(get_message("Done!"),
                                                                                       Gtk.MessageType.INFO),
                                          files_filter=files_filter))

    def on_download(self, item=None, files_filter=None, path=None):
        path = path or self._settings.profile_picons_path
        settings = Settings(self._settings.settings)
        settings.profile_picons_path = path + SEP
        self.run_func(lambda: download_data(settings=settings,
                                            download_type=DownloadType.PICONS,
                                            callback=self.append_output,
                                            files_filter=files_filter), True)

    def on_remove(self, item=None, files_filter=None):
        if show_dialog(DialogType.QUESTION, self._app_window) == Gtk.ResponseType.CANCEL:
            return

        self.run_func(lambda: remove_picons(settings=self._settings,
                                            callback=self.append_output,
                                            done_callback=lambda: self.show_info_message(get_message("Done!"),
                                                                                         Gtk.MessageType.INFO),
                                            files_filter=files_filter))

    def get_selected_path(self, view):
        model, paths = view.get_selection().get_selected_rows()
        if paths:
            return Path(model[paths.pop()][-1]).resolve()

    # ******************** Downloader ************************* #

    def on_download_source_changed(self, button):
        self._download_src = self.DownloadSource(button.get_active_id())
        self.set_providers_header()
        self._providers_header_box.set_sensitive(self._download_src is self.DownloadSource.PICON_CZ)
        GLib.idle_add(self._providers_view.get_model().clear)
        self.init_satellites(self._satellites_view)

    def on_satellites_view_realize(self, view):
        self.set_providers_header()
        self.get_satellites(view)

    def on_satellite_filter_toggled(self, button, state):
        self.init_satellites(self._satellites_view)

    def on_providers_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        if self._download_src is self.DownloadSource.LYNG_SAT:
            return False

        dest = view.get_dest_row_at_pos(x, y)
        if not dest:
            return False

        path, pos = dest
        model = view.get_model()
        itr = model.get_iter(path)
        logo_url = model.get_value(itr, 5)
        if logo_url:
            pix_data = self._picon_cz_downloader.get_logo_data(logo_url)
            if pix_data:
                pix = self.get_pixbuf(pix_data)
                model.set_value(itr, 0, pix if pix else TV_ICON)
                size = self._settings.tooltip_logo_size
                tooltip.set_icon(self.get_pixbuf(pix_data, size, size))
            else:
                self.update_logo_data(itr, model, logo_url)
        tooltip.set_text(model.get_value(itr, 1))
        view.set_tooltip_row(tooltip, path)
        return True

    @run_task
    def update_logo_data(self, itr, model, url):
        pix_data = self._picon_cz_downloader.get_provider_logo(url)
        if pix_data:
            pix = self.get_pixbuf(pix_data)
            GLib.idle_add(model.set_value, itr, 0, pix if pix else TV_ICON)

    @run_idle
    def set_providers_header(self):
        if self._download_src is self.DownloadSource.PICON_CZ:
            link = "https://picon.cz"
            tooltip = f"{link} (by Chocholoušek)"
        elif self._download_src is self.DownloadSource.LYNG_SAT:
            link = "https://www.lyngsat.com"
            tooltip = f"{get_message('Providers')} [{link}]"
        else:
            link = ""
            tooltip = ""

        self._src_link_button.set_uri(link)
        self._src_link_button.set_label(link)
        self._src_link_button.set_tooltip_text(tooltip)

    @run_task
    def get_satellites(self, view):
        self._sats = SatellitesParser().get_satellites_list(SatelliteSource.LYNGSAT)
        if not self._sats:
            self.show_info_message("Getting satellites list error!", Gtk.MessageType.ERROR)

        self._sat_names = {s[1]: s[0] for s in self._sats}  # position -> satellite name
        self._picon_cz_downloader = PiconsCzDownloader(self._picon_ids, self.append_output)
        self.init_satellites(view)

    @run_task
    def init_satellites(self, view):
        sats = self._sats
        if self._download_src is self.DownloadSource.PICON_CZ:
            if not self._picon_cz_downloader:
                return
            try:
                self._picon_cz_downloader.init()
            except PiconsError as e:
                self.show_info_message(str(e), Gtk.MessageType.ERROR)
            else:
                providers = self._picon_cz_downloader.providers
                sats = ((self._sat_names.get(p, p), p, None, p, False) for p in providers)
        gen = self.append_satellites(view.get_model(), sats)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def append_satellites(self, model, sats):
        is_filter = self._satellite_filter_switch.get_active()
        if model:
            model.clear()

        try:
            for sat in sorted(sats):
                pos = sat[1]
                name = f"{sat[0]} ({pos})"
                if is_filter and pos not in self._sat_positions:
                    continue
                if not model:
                    return
                yield model.append((name, sat[3], pos))
        finally:
            self._satellite_label.show()

    def on_satellite_selection(self, view, path, column):
        model = self._providers_view.get_model()
        model.clear()
        self._satellite_label.set_visible(False)
        self.get_providers(view.get_model()[path][1], model)

    @run_task
    def get_providers(self, url, model):
        if self._download_src is self.DownloadSource.LYNG_SAT:
            providers = parse_providers(url)
        elif self._download_src is self.DownloadSource.PICON_CZ:
            providers = self._picon_cz_downloader.get_sat_providers(url)
        else:
            return

        self.append_providers(providers or [], model)

    @run_idle
    def append_providers(self, providers, model):
        if self._download_src is self.DownloadSource.LYNG_SAT:
            for p in providers:
                model.append(p._replace(logo=self.get_pixbuf(p.logo) if p.logo else TV_ICON))
        elif self._download_src is self.DownloadSource.PICON_CZ:
            for p in providers:
                logo_data = self._picon_cz_downloader.get_logo_data(p.ssid)
                model.append(p._replace(logo=self.get_pixbuf(logo_data) if logo_data else TV_ICON))

        self.update_receive_button_state()
        GLib.idle_add(self._satellite_label.set_visible, True)

    def get_pixbuf(self, img_data, w=48, h=32):
        if img_data:
            f = Gio.MemoryInputStream.new_from_data(img_data)
            return GdkPixbuf.Pixbuf.new_from_stream_at_scale(f, w, h, True, None)

    def on_receive(self, item):
        if self._is_downloading:
            self._app.show_error_message("The task is already running!")
            return

        providers = self.get_selected_providers()

        if self._download_src is self.DownloadSource.PICON_CZ and len(providers) > 1:
            self._app.show_error_message("Please, select only one item!")
            return

        self._cancel_button.show()
        self.start_download(providers)

    @run_task
    def start_download(self, providers):
        self._is_downloading = True
        GLib.idle_add(self._info_bar.set_visible, True)

        for prv in providers:
            if self._download_src is self.DownloadSource.LYNG_SAT and not self._POS_PATTERN.match(prv[2]):
                self.show_info_message(
                    get_message("Specify the correct position value for the provider!"), Gtk.MessageType.ERROR)
                scroll_to(prv.path, self._providers_view)
                return

        try:
            picons_path = self._current_path_label.get_text()
            os.makedirs(os.path.dirname(picons_path), exist_ok=True)
            self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
            providers = (Provider(*p) for p in providers)

            if self._download_src is self.DownloadSource.LYNG_SAT:
                self.get_picons_for_lyngsat(picons_path, providers)
            elif self._download_src is self.DownloadSource.PICON_CZ:
                self.get_picons_for_picon_cz(picons_path, providers)

            if not self._is_downloading:
                return

            if not self._resize_no_radio_button.get_active():
                self.resize(picons_path)
        finally:
            self._app.update_picons()
            GLib.idle_add(self._cancel_button.hide)
            self._is_downloading = False

    def get_picons_for_lyngsat(self, path, providers):
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            picons = []
            # Getting links to picons.
            futures = {executor.submit(self.process_provider, p, path): p for p in providers}
            for future in concurrent.futures.as_completed(futures):
                if not self._is_downloading:
                    executor.shutdown()
                    return

                pic = future.result()
                if pic:
                    picons.extend(pic)
            # Getting picon images.
            futures = {executor.submit(download_picon, *pic, self.append_output): pic for pic in picons}
            done, not_done = concurrent.futures.wait(futures, timeout=0)
            while self._is_downloading and not_done:
                done, not_done = concurrent.futures.wait(not_done, timeout=5)

            for future in not_done:
                future.cancel()
            concurrent.futures.wait(not_done)
            self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO)

    def get_picons_for_picon_cz(self, path, providers):
        p_ids = None
        if self._bouquet_filter_switch.get_active():
            p_ids = self.get_bouquet_picon_ids()
            if not p_ids:
                return

        try:
            # We download it sequentially.
            for p in providers:
                self._picon_cz_downloader.download(p, path, p_ids)
        except PiconsError as e:
            self.append_output(f"Error: {str(e)}\n")
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO)

    def get_bouquet_picon_ids(self):
        """ Returns picon ids for selected bouquet or None. """
        bq_selected = self._app.check_bouquet_selection()
        if not bq_selected:
            return

        model, paths = self._app.bouquets_view.get_selection().get_selected_rows()
        if len(paths) > 1:
            self._app.show_error_message("Please, select only one bouquet!")
            return

        fav_bouquet = self._app.current_bouquets[bq_selected]
        services = self._app.current_services
        return {services.get(fav_id).picon_id for fav_id in fav_bouquet}

    def process_provider(self, prv, picons_path):
        self.append_output(f"Getting links to picons for: {prv.name}.\n")
        return PiconsParser.parse(prv, picons_path, self._picon_ids, self.get_picons_format())

    @run_idle
    def append_output(self, char):
        append_text_to_tview(char, self._info_view)

    @run_task
    def resize(self, path):
        self.show_info_message(get_message("Resizing..."), Gtk.MessageType.INFO)

        try:
            from pathlib import Path
            from PIL import Image
        except ImportError as e:
            self.show_info_message(f"{get_message('Conversion error.')} {e}", Gtk.MessageType.ERROR)
        else:
            res = (220, 132) if self._resize_220_132_radio_button.get_active() else (100, 60)

            for img_file in Path(path).glob("*.png"):
                img = Image.open(img_file)
                img = img.resize(res, Image.ANTIALIAS)
                img.save(img_file, "PNG", optimize=True)

            self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO)

    def on_cancel(self, item=None):
        if self._is_downloading and show_dialog(DialogType.QUESTION, self._app_window) == Gtk.ResponseType.CANCEL:
            return True

        self.terminate_task()

    @run_task
    def terminate_task(self):
        self._terminate = True
        self._is_downloading = False
        self.show_info_message(get_message("The task is canceled!"), Gtk.MessageType.WARNING)

    def on_close(self, window, event):
        if self.on_cancel():
            return True

        self._terminate = True
        self._is_downloading = False
        self._app.update_picons()
        GLib.idle_add(self._app_window.destroy)

    @run_task
    def run_func(self, func, update=False):
        try:
            GLib.idle_add(self._info_bar.set_visible, True)
            GLib.idle_add(self._header_download_box.set_sensitive, False)
            func()
        except OSError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        finally:
            GLib.idle_add(self._header_download_box.set_sensitive, True)
            if update:
                self.update_picons_data(self._picons_dest_view)

    def show_info_message(self, text, message_type):
        self._app.show_info_message(text, message_type)

    def on_picons_dir_open(self, entry, icon, event_button):
        update_entry_data(entry, self._app_window, settings=self._settings)

    @run_idle
    def on_selected_toggled(self, toggle, path):
        model = self._providers_view.get_model()
        model.set_value(model.get_iter(path), 7, not toggle.get_active())
        self.update_receive_button_state()

    def on_select_all(self, view):
        self.update_selection(view, True)

    def on_unselect_all(self, view):
        self.update_selection(view, False)

    def update_selection(self, view, select):
        view.get_model().foreach(lambda mod, path, itr: mod.set_value(itr, 7, select))
        self.update_receive_button_state()

    # *********************** Filter **************************** #

    def on_app_filter_toggled(self, app, value):
        if app.page is Page.PICONS:
            self._filter_button.set_active(not self._filter_button.get_active())

    def on_fav_changed(self, view, path, column):
        if self._app.page is Page.PICONS and self._auto_filter_switch.get_active():
            model = view.get_model()
            self._picons_filter_entry.set_text(model.get_value(model.get_iter(path), Column.FAV_SERVICE))

    def on_filter_toggled(self, button):
        active = self._filter_button.get_active()
        if not active:
            self._picons_filter_entry.set_text("")

    def on_fiter_srcs_toggled(self, filter_model):
        """ Activates re-filtering for model when filter check-button has toggled. """
        GLib.idle_add(filter_model.refilter, priority=GLib.PRIORITY_LOW)

    @run_with_delay(0.5)
    def on_picons_filter_changed(self, entry):
        txt = entry.get_text().upper()
        self._filter_cache.clear()
        for s in self._app.current_services.values():
            self._filter_cache[s.picon_id] = txt in s.service.upper()

        GLib.idle_add(self._picons_src_filter_model.refilter, priority=GLib.PRIORITY_LOW)
        GLib.idle_add(self._picons_dst_filter_model.refilter, priority=GLib.PRIORITY_LOW)

    def picons_src_filter_function(self, model, itr, data):
        return self.filter_function(itr, model, self._src_filter_button.get_active())

    def picons_dst_filter_function(self, model, itr, data):
        return self.filter_function(itr, model, self._dst_filter_button.get_active())

    def filter_function(self, itr, model, active):
        """ Main filtering function. """
        if any((not active, model is None, model == "None")):
            return True

        t = model.get_value(itr, 1)
        if not t:
            return True

        txt = self._picons_filter_entry.get_text().upper()
        return txt in t.upper() or self._filter_cache.get(t, False)

    def on_picon_activated(self, view):
        if self._info_check_button.get_active():
            model, path = view.get_selection().get_selected_rows()
            if not path:
                return

            row = model[path][:]
            name, path = row[1], row[-1]
            srv = self._services.get(row[1], None)
            self.update_picon_info(name, path, srv)

    def update_picon_info(self, name=None, path=None, srv=None):
        self._picon_info_image.set_from_pixbuf(self.get_pixbuf_at_scale(path, 100, 60, True) if path else None)
        self._picon_info_label.set_text(self.get_service_info(srv))
        self._current_picon_info = (name, srv.fav_id) if srv else None

    def get_service_info(self, srv):
        """ Returns short info about the service. """
        if not srv:
            return ""

        if srv.service_type == "IPTV":
            return self._app.get_hint_for_srv_list(srv)

        header, ref = self._app.get_hint_header_info(srv)
        return "{}  {}: {}\n{}: {}  {}: {}\n{}".format(header.rstrip(), get_message("Package"), srv.package,
                                                       get_message("System"), srv.system, get_message("Freq"), srv.freq,
                                                       ref)

    def on_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        dest = view.get_dest_row_at_pos(x, y)
        if not dest:
            return False

        path, pos = dest
        model = view.get_model()
        row = model[path][:]
        tooltip.set_icon(get_picon_pixbuf(row[-1], size=self._settings.tooltip_logo_size))
        tooltip.set_text(row[1])
        view.set_tooltip_row(tooltip, path)

        return True

    def on_tree_view_key_press(self, view, event):
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        if key is KeyboardKey.DELETE:
            self.on_local_remove(view)

    def on_url_changed(self, entry):
        suit = self._PATTERN.search(entry.get_text())
        entry.set_name("GtkEntry" if suit else "digit-entry")
        self._download_source_button.set_sensitive(suit if suit else False)

    def on_position_edited(self, render, path, value):
        model = self._providers_view.get_model()
        model.set_value(model.get_iter(path), 2, value)

    @run_idle
    def on_convert(self, item):
        if show_dialog(DialogType.QUESTION, self._app_window) == Gtk.ResponseType.CANCEL:
            return

        picons_path = self._enigma2_path_button.get_filename()
        save_path = self._save_to_button.get_filename()
        if not picons_path or not save_path:
            self._app.show_error_message("Select paths!")
            return

        self._info_bar.set_visible(True)
        convert_to(src_path=picons_path,
                   dest_path=save_path,
                   s_type=SettingsType.ENIGMA_2,
                   callback=self.append_output,
                   done_callback=lambda: self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO))

    @run_idle
    def update_receive_button_state(self):
        try:
            self._receive_button.set_sensitive(len(self.get_selected_providers()) > 0)
        except TypeError:
            pass  # NOP

    def get_selected_providers(self):
        """ returns selected providers """
        return [r for r in self._providers_view.get_model() if r[7]]

    @run_idle
    def show_dialog(self, message, dialog_type):
        show_dialog(dialog_type, self._app_window, message)

    def get_picons_format(self):
        picon_format = SettingsType.ENIGMA_2

        if self._neutrino_mp_radio_button.get_active():
            picon_format = SettingsType.NEUTRINO_MP

        return picon_format


if __name__ == "__main__":
    pass

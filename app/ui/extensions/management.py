# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2023 Dmitriy Yefremov
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
import pkgutil
import shutil
from enum import IntEnum
from pathlib import Path

import requests
from gi.repository import Gtk, Gdk, GLib, Pango

from app.commons import log, run_task, run_idle
from app.ui.dialogs import translate
from app.ui.uicommons import HeaderBar

EXT_URL = "https://api.github.com/repos/DYefremov/demoneditor-extensions/contents/extensions/"
EXT_LIST_FILE = "https://raw.githubusercontent.com/DYefremov/demoneditor-extensions/main/extensions/extension-list"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux i686; rv:112.0) Gecko/20100101 Firefox/112.0",
           "Accept": "application/json"}


class ExtensionManager(Gtk.Window):
    class Column(IntEnum):
        TITLE = 0
        DESC = 1
        STATUS = 2
        NAME = 3
        URL = 4
        PATH = 5

    def __init__(self, app, **kwargs):
        super().__init__(title=translate("Extensions"), icon_name="demon-editor", application=app,
                         transient_for=app.app_window, destroy_with_parent=True,
                         window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
                         default_width=560, default_height=320, modal=True, **kwargs)

        self._app = app
        self._ext_path = f"{self._app.app_settings.default_data_path}tools{os.sep}extensions"

        margin = {"margin_start": 5, "margin_end": 5, "margin_top": 5, "margin_bottom": 5}
        # Title, Description, Status, Name, URL, Path.
        self._model = Gtk.ListStore.new((str, str, bool, str, str, object))
        self._model.connect("row-deleted", self.on_model_changed)
        self._model.connect("row-inserted", self.on_model_changed)
        self._view = Gtk.TreeView(activate_on_single_click=True, enable_grid_lines=Gtk.TreeViewGridLines.BOTH)
        self._view.set_model(self._model)
        self._view.set_tooltip_column(self.Column.DESC)
        # Title
        renderer = Gtk.CellRendererText(xalign=0.05, ellipsize=Pango.EllipsizeMode.END)
        column = Gtk.TreeViewColumn(title=translate("Title"), cell_renderer=renderer, text=self.Column.TITLE)
        column.set_alignment(0.5)
        column.set_min_width(170)
        column.set_resizable(True)
        self._view.append_column(column)
        # Description
        renderer = Gtk.CellRendererText(xalign=0.05, ellipsize=Pango.EllipsizeMode.END)
        column = Gtk.TreeViewColumn(title=translate("Description"), cell_renderer=renderer, text=self.Column.DESC)
        column.set_resizable(True)
        column.set_expand(True)
        self._view.append_column(column)
        # Status
        renderer = Gtk.CellRendererToggle(xalign=0.5)
        column = Gtk.TreeViewColumn(title=translate("Installed"), cell_renderer=renderer, active=self.Column.STATUS)
        column.set_alignment(0.5)
        column.set_fixed_width(100)
        self._view.append_column(column)

        main_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.VERTICAL)
        frame = Gtk.Frame(shadow_type=Gtk.ShadowType.IN, **margin)
        data_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.VERTICAL, **margin)
        # Status bar.
        status_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.HORIZONTAL, margin_start=5, margin_end=5)
        count_icon = Gtk.Image.new_from_icon_name("document-properties", Gtk.IconSize.SMALL_TOOLBAR)
        status_box.pack_start(count_icon, False, False, 0)
        self._count_label = Gtk.Label(label="0", width_chars=4, xalign=0)
        status_box.pack_start(self._count_label, False, False, 0)
        status_box.show_all()
        load_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.HORIZONTAL, margin_end=10, no_show_all=True)
        load_box.pack_start(Gtk.Label(label=translate("Loading data..."), visible=True), False, False, 0)
        self._load_spinner = Gtk.Spinner(visible=True)
        self._load_spinner.bind_property("active", load_box, "visible")
        load_box.pack_end(self._load_spinner, False, False, 0)
        status_box.pack_end(load_box, False, False, 0)

        data_box.pack_end(status_box, False, True, 0)
        scrolled = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN)
        scrolled.add(self._view)
        data_box.pack_start(scrolled, True, True, 0)
        frame.add(data_box)
        self.add(main_box)

        # Popup menu.
        menu = Gtk.Menu()
        item = Gtk.ImageMenuItem.new_from_stock("gtk-goto-bottom")
        item.set_label(translate("Download"))
        item.connect("activate", self.on_download)
        menu.append(item)
        item = Gtk.ImageMenuItem.new_from_stock("gtk-remove")
        item.set_label(translate("Remove"))
        item.connect("activate", self.on_remove)
        menu.append(item)
        menu.show_all()
        self._view.connect("button-press-event", self.on_view_popup_menu, menu)

        # Header and toolbar.
        download_button = Gtk.Button.new_from_icon_name("go-bottom-symbolic", Gtk.IconSize.BUTTON)
        download_button.set_label(translate("Download"))
        download_button.set_always_show_image(True)
        download_button.connect("clicked", self.on_download)
        remove_button = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
        remove_button.set_label(translate("Remove"))
        remove_button.set_always_show_image(True)
        remove_button.connect("clicked", self.on_remove)

        if app.app_settings.use_header_bar:
            header = HeaderBar()
            header.pack_start(download_button)
            header.pack_start(remove_button)

            self.set_titlebar(header)
            header.show_all()
        else:
            toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            toolbar.get_style_context().add_class("primary-toolbar")
            button_box = Gtk.Box(spacing=2, orientation=Gtk.Orientation.HORIZONTAL, **margin)
            button_box.pack_start(download_button, False, False, 0)
            button_box.pack_start(remove_button, False, False, 0)
            toolbar.pack_start(button_box, True, True, 0)
            main_box.pack_start(toolbar, False, False, 0)

        main_box.pack_start(frame, True, True, 0)
        main_box.show_all()

        ws_property = "extension_manager_window_size"
        window_size = self._app.app_settings.get(ws_property, None)
        if window_size:
            self.resize(*window_size)

        self.connect("delete-event", lambda w, e: self._app.app_settings.add(ws_property, w.get_size()))

        self._load_spinner.start()
        self.update()

    def get_installed(self):
        ext_paths = [f"{os.path.dirname(__file__)}{os.sep}", self._ext_path, "extensions"]

        return {name: Path(importer.find_module(name).path).parent for importer, name, is_package in
                pkgutil.iter_modules(ext_paths) if is_package}

    @run_task
    def update(self):
        installed = self.get_installed()
        extensions = []
        with requests.get(url=EXT_LIST_FILE, stream=True) as resp:
            if resp.status_code == 200:
                try:
                    for e, d in resp.json().items():
                        path = installed.get(e)
                        url = f"{EXT_URL}{d.get('ref', '')}"
                        desc = d.get("description", "")
                        extensions.append((d.get('label'), desc, True if path else None, e, url, path))
                except ValueError as e:
                    log(f"{self.__class__.__name__} [update] error: {e}")
            else:
                log(f"{self.__class__.__name__} [update] error: {resp.reason}")

        self.update_data(extensions)

    @run_idle
    def update_data(self, data):
        self._model.clear()
        [self._model.append(e) for e in data]
        self._load_spinner.stop()

    def on_remove(self, item):
        model, paths = self._view.get_selection().get_selected_rows()
        if not paths:
            return

        path = model[paths][-1]
        if path:
            try:
                shutil.rmtree(path)
            except OSError as e:
                log(f"{self.__class__.__name__} [remove] error: {e}")
            else:
                model[paths][self.Column.PATH] = None
                model[paths][self.Column.STATUS] = None
                msg = translate('Restart the program to apply all changes.')
                self._app.show_info_message(msg, Gtk.MessageType.WARNING)

    @run_task
    def on_download(self, item):
        model, paths = self._view.get_selection().get_selected_rows()
        if not paths:
            return

        url = model[paths][self.Column.URL]
        if not url:
            return

        GLib.idle_add(self._load_spinner.start)
        urls = {}
        with requests.get(url=url, headers=HEADERS, stream=True) as resp:
            if resp.status_code == 200:
                try:
                    for f in resp.json():
                        url = f.get("download_url", None)
                        if url:
                            urls[url] = f.get("name", None)
                except ValueError as e:
                    log(f"{self.__class__.__name__} [download] error: {e}")
            else:
                log(f"{self.__class__.__name__} [download] error: {resp.reason}")

        if urls:
            path = f"{self._ext_path}{os.sep}{model[paths][self.Column.NAME]}{os.sep}"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if all((self.download_file(u, f"{path}{n}") for u, n in urls.items())):
                itr = model.get_iter(paths)
                GLib.idle_add(model.set_value, itr, self.Column.STATUS, True)
                GLib.idle_add(model.set_value, itr, self.Column.PATH, path)
                msg = translate('Restart the program to apply all changes.')
                self._app.show_info_message(msg, Gtk.MessageType.WARNING)

        GLib.idle_add(self._load_spinner.stop)

    def download_file(self, url, path):
        with requests.get(url=url, headers=HEADERS, stream=True) as resp:
            if resp.status_code == 200:
                with open(path, mode="bw") as f:
                    for data in resp.iter_content(chunk_size=1024):
                        f.write(data)
                return True

    def on_model_changed(self, model, path, itr=None):
        self._count_label.set_text(str(len(model)))

    def on_view_popup_menu(self, view, event, menu):
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
            menu.popup(None, None, None, None, event.button, event.time)
            return True
        return False


if __name__ == "__main__":
    pass

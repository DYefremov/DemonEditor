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

import requests

from app.commons import log, run_task, run_idle
from gi.repository import Gtk, GLib

from app.ui.dialogs import get_message
from app.ui.uicommons import HeaderBar

EXT_URL = "https://api.github.com/repos/DYefremov/demoneditor-extensions/contents/extensions"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux i686; rv:112.0) Gecko/20100101 Firefox/112.0",
           "Accept": "application/json"}


class ExtensionManager(Gtk.Window):

    def __init__(self, app, **kwargs):
        super().__init__(title=get_message("Extensions"), icon_name="demon-editor", application=app,
                         transient_for=app.app_window, destroy_with_parent=True,
                         window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
                         default_width=560, default_height=320, modal=True, **kwargs)

        self._app = app

        titles = (get_message("Title"), get_message("Description"), get_message("Status"))
        margin = {"margin_start": 5, "margin_end": 5, "margin_top": 5, "margin_bottom": 5}

        self._model = Gtk.ListStore.new((str, str, str, str))
        self._model.connect("row-deleted", self.on_model_changed)
        self._model.connect("row-inserted", self.on_model_changed)
        self._view = Gtk.TreeView(activate_on_single_click=True, enable_grid_lines=Gtk.TreeViewGridLines.BOTH)
        self._view.set_model(self._model)

        for i, t in enumerate(titles):
            renderer = Gtk.CellRendererText(xalign=0.05)
            column = Gtk.TreeViewColumn(title=t, cell_renderer=renderer, text=i)
            column.set_resizable(True)
            column.set_expand(True)
            column.set_alignment(0.5)
            column.set_min_width(50)
            self._view.append_column(column)

        main_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.VERTICAL)
        frame = Gtk.Frame(shadow_type=Gtk.ShadowType.IN, **margin)
        data_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.VERTICAL, **margin)
        # Status bar.
        status_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.HORIZONTAL, margin_start=5, margin_left=5)
        count_icon = Gtk.Image.new_from_icon_name("document-properties", Gtk.IconSize.SMALL_TOOLBAR)
        status_box.pack_start(count_icon, False, False, 0)
        self._count_label = Gtk.Label(label="0", width_chars=4, xalign=0)
        status_box.pack_start(self._count_label, False, False, 0)

        data_box.pack_end(status_box, False, True, 0)
        data_box.pack_start(self._view, True, True, 0)
        frame.add(data_box)
        self.add(main_box)

        # Header and toolbar.
        download_button = Gtk.Button.new_from_icon_name("go-bottom-symbolic", Gtk.IconSize.BUTTON)
        download_button.set_tooltip_text(get_message("Download"))
        remove_button = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
        remove_button.set_tooltip_text(get_message("Remove"))

        if app.app_settings.use_header_bar:
            header = HeaderBar()
            header.pack_start(download_button)
            header.pack_start(remove_button)

            self.set_titlebar(header)
            header.show_all()
        else:
            toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            toolbar.get_style_context().add_class("primary-toolbar")
            button_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.HORIZONTAL, **margin)
            button_box.pack_start(download_button, False, False, 0)
            button_box.pack_start(remove_button, False, False, 0)
            toolbar.pack_start(button_box, True, True, 0)
            main_box.pack_start(toolbar, False, False, 0)

        main_box.pack_start(frame, True, True, 0)
        main_box.show_all()

        self.update()

    def get_installed(self):
        ext_path = f"{self._app.app_settings.default_data_path}tools{os.sep}extensions"
        ext_paths = [f"{os.path.dirname(__file__)}{os.sep}", ext_path, "extensions"]

        return {name for importer, name, is_package in pkgutil.iter_modules(ext_paths) if is_package}

    @run_task
    def update(self):
        installed = self.get_installed()
        extensions = []
        with requests.get(url=EXT_URL, headers=HEADERS, stream=True) as resp:
            if resp.status_code == 200:
                try:
                    for f in resp.json():
                        if f.get("type") == "dir":
                            name = f.get("name")
                            extensions.append((name, None, "Installed" if name in installed else None, None))
                except ValueError as e:
                    log(f"ExtensionManager [update] error: {e}")
            else:
                log(f"ExtensionManager [update] error: {resp.reason}")

        self.update_data(extensions)

    @run_idle
    def update_data(self, data):
        self._model.clear()
        [self._model.append(e) for e in data]

    def on_model_changed(self, model, path, itr=None):
        self._count_label.set_text(str(len(model)))


if __name__ == "__main__":
    pass

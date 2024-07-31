# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2024 Dmitriy Yefremov
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
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from enum import Enum
from pathlib import Path

from app.commons import run_idle, get_size_from_bytes
from app.settings import SettingsType, SEP
from app.ui.dialogs import show_dialog, DialogType, get_builder
from app.ui.main_helper import append_text_to_tview, show_info_bar_message
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, KeyboardKey, MOD_MASK, HeaderBar

KEEP_DATA = {"satellites.xml",
             "terrestrial.xml",
             "cables.xml",
             "whitelist",
             "whitelist_streamrelay"}


class RestoreType(Enum):
    BOUQUETS = 0
    ALL = 1


class BackupDialog:
    def __init__(self, transient, settings, callback):
        handlers = {"on_restore_bouquets": self.on_restore_bouquets,
                    "on_restore_all": self.on_restore_all,
                    "on_remove": self.on_remove,
                    "on_view_popup_menu": self.on_view_popup_menu,
                    "on_info_button_toggled": self.on_info_button_toggled,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_cursor_changed": self.on_cursor_changed,
                    "on_resize": self.on_resize,
                    "on_key_release": self.on_key_release}

        builder = get_builder(UI_RESOURCES_PATH + "backup_dialog.glade", handlers)

        self._settings = settings
        self._s_type = settings.setting_type
        self._data_path = self._settings.profile_data_path
        self._backup_path = self._settings.profile_backup_path or f"{self._data_path}backup{os.sep}"
        self._open_data_callback = callback
        self._dialog_window = builder.get_object("dialog_window")
        self._dialog_window.set_transient_for(transient)
        self._model = builder.get_object("main_list_store")
        self._main_view = builder.get_object("main_view")
        self._text_view = builder.get_object("text_view")
        self._info_check_button = builder.get_object("info_check_button")
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("message_label")
        self._file_count_label = builder.get_object("file_count_label")

        if self._settings.use_header_bar:
            header_bar = HeaderBar()
            self._dialog_window.set_titlebar(header_bar)

            button_box = builder.get_object("main_button_box")
            button_box.set_margin_top(0)
            button_box.set_margin_bottom(0)
            button_box.set_margin_left(0)
            button_box.reparent(header_bar)

            ch_button = builder.get_object("info_check_button")
            ch_button.set_margin_right(0)
            h_bar = builder.get_object("header_bar")
            h_bar.remove(ch_button)
            h_bar.set_visible(False)
            header_bar.pack_end(ch_button)

        # Setting the last size of the dialog window if it was saved
        window_size = self._settings.get("backup_tool_window_size")
        if window_size:
            self._dialog_window.resize(*window_size)

        self.init_data()

    def show(self):
        self._dialog_window.show()

    @run_idle
    def init_data(self):
        if os.path.isdir(self._backup_path):
            for file in filter(lambda x: x.endswith(".zip"), os.listdir(self._backup_path)):
                p = Path(os.path.join(self._backup_path, file))
                if p.is_file():
                    self._model.append((p.stem, get_size_from_bytes(p.stat().st_size)))
        else:
            os.makedirs(os.path.dirname(self._backup_path), exist_ok=True)

        self._file_count_label.set_text(str(len(self._model)))

    def on_restore_bouquets(self, item):
        self.restore(RestoreType.BOUQUETS)

    def on_restore_all(self, item):
        self.restore(RestoreType.ALL)

    def on_remove(self, item):
        model, paths = self._main_view.get_selection().get_selected_rows()
        if not paths:
            show_dialog(DialogType.ERROR, self._dialog_window, "No selected item!")
            return

        if show_dialog(DialogType.QUESTION, self._dialog_window) == Gtk.ResponseType.CANCEL:
            return

        itrs_to_delete = []
        try:
            for itr in map(model.get_iter, paths):
                file_name = model.get_value(itr, 0)
                os.remove(f"{self._backup_path}{file_name}.zip")
                itrs_to_delete.append(itr)
        except FileNotFoundError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            list(map(model.remove, itrs_to_delete))

        self._file_count_label.set_text(str(len(self._model)))

    def on_view_popup_menu(self, menu, event):
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
            menu.popup(None, None, None, None, event.button, event.time)

    def on_info_button_toggled(self, button):
        if button.get_active():
            self.on_cursor_changed(self._main_view)

    @run_idle
    def show_info_message(self, text, message_type):
        show_info_bar_message(self._info_bar, self._message_label, text, message_type)

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    def on_cursor_changed(self, view):
        if not self._info_check_button.get_active():
            return

        model, paths = view.get_selection().get_selected_rows()
        if paths:
            try:
                file_name = self._backup_path + model.get_value(model.get_iter(paths[0]), 0) + ".zip"
                created = time.ctime(os.path.getctime(file_name))
                self._text_view.get_buffer().set_text(
                    f"Created: {created}\n********** Files: **********\n")
                with zipfile.ZipFile(file_name) as zip_file:
                    for name in zip_file.namelist():
                        append_text_to_tview(name + "\n", self._text_view)
            except FileNotFoundError as e:
                self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            self._text_view.get_buffer().set_text("")

    def restore(self, restore_type):
        model, paths = self._main_view.get_selection().get_selected_rows()
        if not paths:
            show_dialog(DialogType.ERROR, self._dialog_window, "No selected item!")
            return

        if len(paths) > 1:
            show_dialog(DialogType.ERROR, self._dialog_window, "Please, select only one item!")
            return

        if show_dialog(DialogType.QUESTION, self._dialog_window) == Gtk.ResponseType.CANCEL:
            return

        file_name = model.get_value(model.get_iter(paths[0]), 0)
        full_file_name = f"{self._backup_path}{file_name}.zip"

        try:
            if restore_type is RestoreType.ALL:
                clear_data_path(self._data_path)
                shutil.unpack_archive(full_file_name, self._data_path)
            elif restore_type is RestoreType.BOUQUETS:
                tmp_dir = tempfile.gettempdir() + SEP + file_name
                cond = (".tv", ".radio") if self._s_type is SettingsType.ENIGMA_2 else "bouquets.xml"
                shutil.unpack_archive(full_file_name, tmp_dir)
                for file in filter(lambda f: f.endswith(cond), os.listdir(self._data_path)):
                    os.remove(os.path.join(self._data_path, file))
                for file in filter(lambda f: f.endswith(cond), os.listdir(tmp_dir)):
                    shutil.move(os.path.join(tmp_dir, file), self._data_path + file)
                shutil.rmtree(tmp_dir)
        except FileNotFoundError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            self.show_info_message("Done!", Gtk.MessageType.INFO)
            self._open_data_callback(self._data_path)

    def on_resize(self, window):
        if self._settings:
            self._settings.add("backup_tool_window_size", window.get_size())

    def on_key_release(self, view, event):
        """  Handling  keystrokes  """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return
        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK

        if key is KeyboardKey.DELETE:
            self.on_remove(view)
        elif ctrl and key is KeyboardKey.E:
            self.restore(RestoreType.ALL)
        elif ctrl and key is KeyboardKey.R:
            self.restore(RestoreType.BOUQUETS)


def backup_data(path, backup_path, move=True, keep=None):
    """ Creating data backup from a folder at the specified path

        Returns full path to the compressed file.
    """
    keep = keep or KEEP_DATA
    backup_path = f"{backup_path}{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}{SEP}"
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Backup files in data dir.
    for file in filter(lambda f: os.path.isfile(os.path.join(path, f)), os.listdir(path)):
        src, dst = os.path.join(path, file), backup_path + file
        shutil.move(src, dst) if move and file not in keep else shutil.copy(src, dst)
    # Compressing to zip and delete remaining files.
    zip_file = shutil.make_archive(backup_path.rstrip(SEP), "zip", backup_path)
    shutil.rmtree(backup_path)

    return zip_file


def restore_data(src, dst):
    """ Unpacks backup data. """
    clear_data_path(dst)
    shutil.unpack_archive(src, dst)


def clear_data_path(path):
    """ Clearing data at the specified path excluding *.xml file. """
    for file in filter(lambda f: f not in KEEP_DATA and os.path.isfile(os.path.join(path, f)), os.listdir(path)):
        os.remove(os.path.join(path, file))


if __name__ == "__main__":
    pass

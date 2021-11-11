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

from gi.repository import GLib

from app.commons import run_idle, run_task, log
from app.connections import download_data, DownloadType, upload_data
from app.settings import SettingsType
from app.ui.backup import backup_data, restore_data
from app.ui.main_helper import append_text_to_tview
from app.ui.settings_dialog import SettingsDialog
from .dialogs import show_dialog, DialogType, get_message, get_builder
from .uicommons import Gtk, UI_RESOURCES_PATH


class DownloadDialog:
    def __init__(self, transient, settings, open_data_callback, update_settings_callback):
        self._s_type = settings.setting_type
        self._settings = settings
        self._open_data_callback = open_data_callback
        self._update_settings_callback = update_settings_callback

        handlers = {"on_receive": self.on_receive,
                    "on_send": self.on_send,
                    "on_settings": self.on_settings,
                    "on_profile_changed": self.on_profile_changed,
                    "on_use_http_state_set": self.on_use_http_state_set,
                    "on_remove_unused_bouquets_toggled": self.on_remove_unused_bouquets_toggled,
                    "on_info_bar_close": self.on_info_bar_close}

        builder = get_builder(UI_RESOURCES_PATH + "download_dialog.glade", handlers)

        self._dialog_window = builder.get_object("download_dialog_window")
        self._dialog_window.set_transient_for(transient)
        self._host_entry = builder.get_object("host_entry")
        self._data_path_entry = builder.get_object("data_path_entry")
        self._remove_unused_check_button = builder.get_object("remove_unused_check_button")
        self._all_radio_button = builder.get_object("all_radio_button")
        self._bouquets_radio_button = builder.get_object("bouquets_radio_button")
        self._satellites_radio_button = builder.get_object("satellites_radio_button")
        self._webtv_radio_button = builder.get_object("webtv_radio_button")
        self._use_http_switch = builder.get_object("use_http_switch")
        self._http_radio_button = builder.get_object("http_radio_button")
        self._profile_combo_box = builder.get_object("profile_combo_box")
        # Info.
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")
        self._text_view = builder.get_object("text_view")
        self._log_bar = builder.get_object("log_bar")
        self._log_bar.bind_property("visible", builder.get_object("log_bar_frame"), "visible")
        self._log_bar.connect("response", lambda b, r: b.set_visible(False))

        self.init_settings()

    def show(self):
        self._dialog_window.show()

    def init_settings(self):
        self.update_profiles()
        self.init_ui_settings()

    def init_ui_settings(self):
        self._host_entry.set_text(self._settings.host)
        self._data_path_entry.set_text(self._settings.profile_data_path)
        is_enigma = self._s_type is SettingsType.ENIGMA_2
        self._webtv_radio_button.set_visible(not is_enigma)
        self._use_http_switch.set_active(self._settings.use_http)
        self._remove_unused_check_button.set_active(self._settings.remove_unused_bouquets)

    def update_profiles(self):
        self._profile_combo_box.remove_all()
        for p in self._settings.profiles:
            self._profile_combo_box.append(p, p)
        self._profile_combo_box.set_active_id(self._settings.current_profile)

    @run_idle
    def on_receive(self, item):
        self.download(True, self.get_download_type())

    @run_idle
    def on_send(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog_window) != Gtk.ResponseType.CANCEL:
            self.download(False, self.get_download_type())

    def get_download_type(self):
        download_type = DownloadType.ALL
        if self._bouquets_radio_button.get_active():
            download_type = DownloadType.BOUQUETS
        elif self._satellites_radio_button.get_active():
            download_type = DownloadType.SATELLITES
        elif self._webtv_radio_button.get_active():
            download_type = DownloadType.WEBTV
        return download_type

    def destroy(self):
        self._dialog_window.destroy()

    def on_settings(self, item):
        dialog = SettingsDialog(self._dialog_window, self._settings)
        dialog.show()
        if dialog.is_updated():
            self._s_type = self._settings.setting_type
            self.update_profiles()
            gen = self._update_settings_callback()
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_profile_changed(self, box):
        active = box.get_active_text()
        if active in self._settings.profiles:
            self._settings.current_profile = active
            self._profile_combo_box.set_active_id(active)
            self._s_type = self._settings.setting_type
            self.init_ui_settings()

    def on_use_http_state_set(self, button, state):
        self._settings.use_http = state

    def on_remove_unused_bouquets_toggled(self, button):
        self._settings.remove_unused_bouquets = button.get_active()

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_task
    def download(self, download, d_type):
        """ Download/upload data from/to receiver """
        GLib.idle_add(self._log_bar.set_visible, True)
        self.clear_output()
        backup, backup_src, data_path = self._settings.backup_before_downloading, None, None

        try:
            if download:
                if backup and d_type is not DownloadType.SATELLITES:
                    data_path = self._settings.profile_data_path or self._data_path_entry.get_text()
                    os.makedirs(os.path.dirname(data_path), exist_ok=True)
                    backup_path = self._settings.profile_backup_path or self._settings.default_backup_path
                    backup_src = backup_data(data_path, backup_path, d_type is DownloadType.ALL)

                download_data(settings=self._settings, download_type=d_type, callback=self.append_output)
            else:
                self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
                upload_data(settings=self._settings,
                            download_type=d_type,
                            remove_unused=self._remove_unused_check_button.get_active(),
                            callback=self.append_output,
                            done_callback=lambda: self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO),
                            use_http=self._use_http_switch.get_active())
        except Exception as e:
            msg = "Downloading data error: {}"
            log(msg.format(e), debug=self._settings.debug_mode, fmt_message=msg)
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
            if all((download, backup, data_path)):
                restore_data(backup_src, data_path)
        else:
            if download and d_type is not DownloadType.SATELLITES:
                GLib.idle_add(self._open_data_callback)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    @run_idle
    def append_output(self, text):
        append_text_to_tview(text, self._text_view)

    @run_idle
    def clear_output(self):
        self._text_view.get_buffer().set_text("")


if __name__ == "__main__":
    pass

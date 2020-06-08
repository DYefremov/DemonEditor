import os

from gi.repository import GLib

from app.commons import run_idle, run_task, log
from app.connections import download_data, DownloadType, upload_data
from app.settings import SettingsType
from app.ui.backup import backup_data, restore_data
from app.ui.main_helper import append_text_to_tview
from app.ui.settings_dialog import show_settings_dialog
from .dialogs import show_dialog, DialogType, get_message
from .uicommons import Gtk, UI_RESOURCES_PATH


class DownloadDialog:
    def __init__(self, transient, settings, open_data_callback, update_settings_callback):
        self._s_type = settings.setting_type
        self._settings = settings
        self._open_data_callback = open_data_callback
        self._update_settings_callback = update_settings_callback

        handlers = {"on_receive": self.on_receive,
                    "on_send": self.on_send,
                    "on_settings_button": self.on_settings_button,
                    "on_settings": self.on_settings,
                    "on_profile_changed": self.on_profile_changed,
                    "on_info_bar_close": self.on_info_bar_close}

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "download_dialog.glade")
        builder.connect_signals(handlers)

        self._current_property = "FTP"
        self._dialog_window = builder.get_object("download_dialog_window")
        self._dialog_window.set_transient_for(transient)
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")
        self._text_view = builder.get_object("text_view")
        self._expander = builder.get_object("expander")
        self._host_entry = builder.get_object("host_entry")
        self._data_path_entry = builder.get_object("data_path_entry")
        self._remove_unused_check_button = builder.get_object("remove_unused_check_button")
        self._all_radio_button = builder.get_object("all_radio_button")
        self._bouquets_radio_button = builder.get_object("bouquets_radio_button")
        self._satellites_radio_button = builder.get_object("satellites_radio_button")
        self._webtv_radio_button = builder.get_object("webtv_radio_button")
        self._login_entry = builder.get_object("login_entry")
        self._password_entry = builder.get_object("password_entry")
        self._host_entry = builder.get_object("host_entry")
        self._port_entry = builder.get_object("port_entry")
        self._timeout_entry = builder.get_object("timeout_entry")
        self._settings_buttons_box = builder.get_object("settings_buttons_box")
        self._use_http_switch = builder.get_object("use_http_switch")
        self._http_radio_button = builder.get_object("http_radio_button")
        self._use_http_box = builder.get_object("use_http_box")
        self._profile_combo_box = builder.get_object("profile_combo_box")

        self.init_settings()

    def show(self):
        self._dialog_window.show()

    def init_settings(self):
        self.update_profiles()
        self.init_ui_settings()

    @run_idle
    def init_ui_settings(self):
        self._host_entry.set_text(self._settings.host)
        self._data_path_entry.set_text(self._settings.data_local_path)
        is_enigma = self._s_type is SettingsType.ENIGMA_2
        self._webtv_radio_button.set_visible(not is_enigma)
        self._http_radio_button.set_visible(is_enigma)
        self._use_http_box.set_visible(is_enigma)
        self._use_http_switch.set_active(is_enigma)

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

    def on_settings_button(self, button):
        if button.get_active():
            label = button.get_label()
            if label == "Telnet":
                self._login_entry.set_text(self._settings.telnet_user)
                self._password_entry.set_text(self._settings.telnet_password)
                self._port_entry.set_text(self._settings.telnet_port)
                self._timeout_entry.set_text(str(self._settings.telnet_timeout))
            elif label == "HTTP":
                self._login_entry.set_text(self._settings.http_user)
                self._password_entry.set_text(self._settings.http_password)
                self._port_entry.set_text(self._settings.http_port)
                self._timeout_entry.set_text(str(self._settings.http_timeout))
            elif label == "FTP":
                self._login_entry.set_text(self._settings.user)
                self._password_entry.set_text(self._settings.password)
                self._port_entry.set_text(self._settings.port)
                self._timeout_entry.set_text("")
            self._current_property = label

    def on_settings(self, item):
        response = show_settings_dialog(self._dialog_window, self._settings)
        if response != Gtk.ResponseType.CANCEL:
            self._s_type = self._settings.setting_type
            self.update_profiles()
            gen = self._update_settings_callback()
            GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

            for button in self._settings_buttons_box.get_children():
                if button.get_active():
                    self.on_settings_button(button)
                    break

    def on_profile_changed(self, box):
        active = box.get_active_text()
        if active in self._settings.profiles:
            self._settings.current_profile = active
            self._profile_combo_box.set_active_id(active)
            self._s_type = self._settings.setting_type
            self.init_ui_settings()

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_task
    def download(self, download, d_type):
        """ Download/upload data from/to receiver """
        self._expander.set_expanded(True)
        self.clear_output()
        backup, backup_src, data_path = self._settings.backup_before_downloading, None, None

        try:
            if download:
                if backup and d_type is not DownloadType.SATELLITES:
                    data_path = self._settings.data_local_path or self._data_path_entry.get_text()
                    os.makedirs(os.path.dirname(data_path), exist_ok=True)
                    backup_path = self._settings.backup_local_path or data_path + "backup/"
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
            from traceback import format_exc
            log("Downloading data error: {}".format(format_exc()))
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

from gi.repository import GLib

from app.commons import run_idle, run_task
from app.connections import download_data, DownloadType, upload_data
from app.properties import Profile, get_config
from app.ui.main_helper import append_text_to_tview
from app.ui.settings_dialog import show_settings_dialog
from .uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN
from .dialogs import show_dialog, DialogType, get_message


class DownloadDialog:
    def __init__(self, transient, properties, open_data_callback, profile=Profile.ENIGMA_2):
        self._profile_properties = properties.get(profile.value)
        self._properties = properties
        self._open_data_callback = open_data_callback
        self._profile = profile

        handlers = {"on_receive": self.on_receive,
                    "on_send": self.on_send,
                    "on_settings_button": self.on_settings_button,
                    "on_preferences": self.on_preferences,
                    "on_info_bar_close": self.on_info_bar_close}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
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
        self._settings_buttons_box = builder.get_object("settings_buttons_box")
        self.init_properties()

        if profile is Profile.NEUTRINO_MP:
            self._webtv_radio_button.set_visible(True)
            builder.get_object("http_radio_button").set_visible(False)
            builder.get_object("use_http_box").set_visible(False)

    def show(self):
        self._dialog_window.show()

    def init_properties(self):
        self._host_entry.set_text(self._profile_properties["host"])
        self._data_path_entry.set_text(self._profile_properties["data_dir_path"])

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
            download_type = DownloadType.WEB_TV
        return download_type

    def destroy(self):
        self._dialog_window.destroy()

    def on_settings_button(self, button):
        if button.get_active():
            label = button.get_label()
            if label == "Telnet":
                self._login_entry.set_text(self._profile_properties.get("telnet_user", ""))
                self._password_entry.set_text(self._profile_properties.get("telnet_password", ""))
                self._port_entry.set_text(self._profile_properties.get("telnet_port", ""))
            elif label == "HTTP":
                self._login_entry.set_text(self._profile_properties.get("http_user", "root"))
                self._password_entry.set_text(self._profile_properties.get("http_password", ""))
                self._port_entry.set_text(self._profile_properties.get("http_port", ""))
            elif label == "FTP":
                self._login_entry.set_text(self._profile_properties.get("user", ""))
                self._password_entry.set_text(self._profile_properties.get("password", ""))
                self._port_entry.set_text(self._profile_properties.get("port", ""))
            self._current_property = label

    def on_preferences(self, item):
        show_settings_dialog(self._dialog_window, self._properties)
        self._profile_properties = get_config().get(self._profile.value)

        for button in self._settings_buttons_box.get_children():
            if button.get_active():
                self.on_settings_button(button)
                self.init_properties()
                break

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_task
    def download(self, download, d_type):
        """ Download/upload data from/to receiver """
        try:
            self._expander.set_expanded(True)
            self.clear_output()

            if download:
                download_data(properties=self._profile_properties, download_type=d_type, callback=self.append_output)
            else:
                self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
                upload_data(properties=self._profile_properties,
                            download_type=d_type,
                            remove_unused=self._remove_unused_check_button.get_active(),
                            profile=self._profile,
                            callback=self.append_output,
                            done_callback=lambda: self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO))
        except Exception as e:
            message = str(getattr(e, "message", str(e)))
            self.show_info_message(message, Gtk.MessageType.ERROR)
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

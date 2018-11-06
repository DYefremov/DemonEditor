import socket
from enum import Enum
from ftplib import error_perm, FTP
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.dom.minidom import parse

from app.commons import run_task, run_idle
from app.connections import test_telnet
from app.properties import write_config, Profile, get_default_settings
from .uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN
from .main_helper import update_entry_data


def show_settings_dialog(transient, options):
    return SettingsDialog(transient, options).show()


class Property(Enum):
    FTP = "ftp"
    HTTP = "http"
    TELNET = "telnet"


class SettingsDialog:

    def __init__(self, transient, options):
        handlers = {"on_data_dir_field_icon_press": self.on_data_dir_field_icon_press,
                    "on_picons_dir_field_icon_press": self.on_picons_dir_field_icon_press,
                    "on_profile_changed": self.on_profile_changed,
                    "on_reset": self.on_reset,
                    "apply_settings": self.apply_settings,
                    "on_connection_test": self.on_connection_test,
                    "on_info_bar_close": self.on_info_bar_close}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_from_file(UI_RESOURCES_PATH + "settings_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("settings_dialog")
        self._dialog.set_transient_for(transient)
        self._host_field = builder.get_object("host_field")
        self._port_field = builder.get_object("port_field")
        self._login_field = builder.get_object("login_field")
        self._password_field = builder.get_object("password_field")
        self._http_login_field = builder.get_object("http_login_field")
        self._http_password_field = builder.get_object("http_password_field")
        self._http_port_field = builder.get_object("http_port_field")
        self._telnet_login_field = builder.get_object("telnet_login_field")
        self._telnet_password_field = builder.get_object("telnet_password_field")
        self._telnet_port_field = builder.get_object("telnet_port_field")
        self._telnet_timeout_spin_button = builder.get_object("telnet_timeout_spin_button")
        self._services_field = builder.get_object("services_field")
        self._user_bouquet_field = builder.get_object("user_bouquet_field")
        self._satellites_xml_field = builder.get_object("satellites_xml_field")
        self._data_dir_field = builder.get_object("data_dir_field")
        self._picons_field = builder.get_object("picons_field")
        self._picons_dir_field = builder.get_object("picons_dir_field")
        self._enigma_radio_button = builder.get_object("enigma_radio_button")
        self._neutrino_radio_button = builder.get_object("neutrino_radio_button")
        self._support_ver5_check_button = builder.get_object("support_ver5_check_button")
        self._settings_stack = builder.get_object("settings_stack")
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")
        self._test_spinner = builder.get_object("test_spinner")
        self._options = options
        self._active_profile = options.get("profile")
        self.set_settings()
        profile = Profile(self._active_profile)
        self._neutrino_radio_button.set_active(profile is Profile.NEUTRINO_MP)
        self._support_ver5_check_button.set_sensitive(profile is not Profile.NEUTRINO_MP)
        self._settings_stack.get_child_by_name(Property.HTTP.value).set_visible(profile is not Profile.NEUTRINO_MP)

    def show(self):
        response = self._dialog.run()
        if response == Gtk.ResponseType.OK:
            self.apply_settings()
        self._dialog.destroy()

        return response

    def on_data_dir_field_icon_press(self, entry, icon, event_button):
        update_entry_data(entry, self._dialog, self._options.get(self._options.get("profile")))

    def on_picons_dir_field_icon_press(self, entry, icon, event_button):
        update_entry_data(entry, self._dialog, self._options.get(self._options.get("profile")))

    def on_profile_changed(self, item):
        profile = Profile.ENIGMA_2 if self._enigma_radio_button.get_active() else Profile.NEUTRINO_MP
        self._settings_stack.get_child_by_name(Property.HTTP.value).set_visible(profile is not Profile.NEUTRINO_MP)
        self.set_profile(profile)
        self._support_ver5_check_button.set_sensitive(profile is Profile.ENIGMA_2)

    def set_profile(self, profile):
        self._active_profile = profile.value
        self.set_settings()

    def on_reset(self, item):
        def_settings = get_default_settings()
        for key in def_settings:
            current = self._options.get(key)
            if type(current) is str:
                continue
            default = def_settings.get(key)
            for k in default:
                current[k] = default.get(k)
        self.set_settings()

    def set_settings(self):
        options = self._options.get(self._active_profile)
        self._host_field.set_text(options.get("host", ""))
        self._port_field.set_text(options.get("port", ""))
        self._login_field.set_text(options.get("user", ""))
        self._password_field.set_text(options.get("password", ""))
        self._http_login_field.set_text(options.get("http_user", ""))
        self._http_password_field.set_text(options.get("http_password", ""))
        self._http_port_field.set_text(options.get("http_port", "80"))
        self._telnet_login_field.set_text(options.get("telnet_user", ""))
        self._telnet_password_field.set_text(options.get("telnet_password", ""))
        self._telnet_port_field.set_text(options.get("telnet_port", ""))
        self._telnet_timeout_spin_button.set_value(options.get("telnet_timeout", 5))
        self._services_field.set_text(options.get("services_path", ""))
        self._user_bouquet_field.set_text(options.get("user_bouquet_path", ""))
        self._satellites_xml_field.set_text(options.get("satellites_xml_path", ""))
        self._picons_field.set_text(options.get("picons_path", ""))
        self._data_dir_field.set_text(options.get("data_dir_path", ""))
        self._picons_dir_field.set_text(options.get("picons_dir_path", ""))
        if Profile(self._active_profile) is Profile.ENIGMA_2:
            self._support_ver5_check_button.set_active(options.get("v5_support", False))

    def apply_settings(self, item=None):
        profile = Profile.ENIGMA_2 if self._enigma_radio_button.get_active() else Profile.NEUTRINO_MP
        self._active_profile = profile.value
        self._options["profile"] = self._active_profile
        options = self._options.get(self._active_profile)
        options["host"] = self._host_field.get_text()
        options["port"] = self._port_field.get_text()
        options["user"] = self._login_field.get_text()
        options["password"] = self._password_field.get_text()
        options["http_user"] = self._http_login_field.get_text()
        options["http_password"] = self._http_password_field.get_text()
        options["http_port"] = self._http_port_field.get_text()
        options["telnet_user"] = self._telnet_login_field.get_text()
        options["telnet_password"] = self._telnet_password_field.get_text()
        options["telnet_port"] = self._telnet_port_field.get_text()
        options["telnet_timeout"] = int(self._telnet_timeout_spin_button.get_value())
        options["services_path"] = self._services_field.get_text()
        options["user_bouquet_path"] = self._user_bouquet_field.get_text()
        options["satellites_xml_path"] = self._satellites_xml_field.get_text()
        options["picons_path"] = self._picons_field.get_text()
        options["data_dir_path"] = self._data_dir_field.get_text()
        options["picons_dir_path"] = self._picons_dir_field.get_text()
        if profile is Profile.ENIGMA_2:
            options["v5_support"] = self._support_ver5_check_button.get_active()
        write_config(self._options)

    @run_task
    def on_connection_test(self, item):
        if self._test_spinner.get_state() is Gtk.StateType.ACTIVE:
            return
        self.show_spinner(True)
        current_property = Property(self._settings_stack.get_visible_child_name())
        if current_property is Property.HTTP:
            self.test_http()
        elif current_property is Property.TELNET:
            self.test_telnet()
        elif current_property is Property.FTP:
            self.test_ftp()

    def test_http(self):
        user, password = self._http_login_field.get_text(), self._http_password_field.get_text()
        try:
            params = urlencode({"text": "Connection test", "type": 2, "timeout": 5})
            with urlopen("http://{}/web/message?%s".format(self._host_field.get_text()) % params, timeout=5) as f:
                dom = parse(f)
                for elem in dom.getElementsByTagName("e2simplexmlresult"):
                    for ch in elem.childNodes:
                        if ch.nodeType == ch.ELEMENT_NODE:
                            msg = "".join(t.nodeValue for t in ch.childNodes if t.nodeType == t.TEXT_NODE)
                            self.show_info_message(msg, Gtk.MessageType.INFO)
        except (URLError, HTTPError) as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        finally:
            self.show_spinner(False)

    def test_telnet(self):
        timeout = int(self._telnet_timeout_spin_button.get_value())
        host, port = self._host_field.get_text(), self._telnet_port_field.get_text()
        user, password = self._telnet_login_field.get_text(), self._telnet_password_field.get_text()
        try:
            gen = test_telnet(host, port, user, password, timeout)
            res = next(gen)
            print(res)
            res = next(gen)
            self.show_info_message(str(res), Gtk.MessageType.INFO)
            self.show_spinner(False)
        except (socket.timeout, OSError) as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
            self.show_spinner(False)

    def test_ftp(self):
        host, port = self._host_field.get_text(), self._port_field.get_text()
        user, password = self._login_field.get_text(), self._password_field.get_text()
        try:
            with FTP(host=host, user=user, passwd=password, timeout=5) as ftp:
                self.show_info_message("OK.  {}".format(ftp.getwelcome()), Gtk.MessageType.INFO)
        except (error_perm, ConnectionRefusedError, OSError) as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        finally:
            self.show_spinner(False)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    @run_idle
    def show_spinner(self, show):
        self._test_spinner.start() if show else self._test_spinner.stop()
        self._test_spinner.set_state(Gtk.StateType.ACTIVE if show else Gtk.StateType.NORMAL)

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)


if __name__ == "__main__":
    pass

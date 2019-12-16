import json
import os
from pprint import pformat
from textwrap import dedent
from enum import Enum
from pathlib import Path

CONFIG_PATH = str(Path.home()) + "/.config/demon-editor/"
CONFIG_FILE = CONFIG_PATH + "config.json"
DATA_PATH = "data/"


class Profile(Enum):
    """ Profiles for settings """
    ENIGMA_2 = "0"
    NEUTRINO_MP = "1"


class Settings:
    __INSTANCE = None

    def __init__(self):
        self._config = get_config()
        self._current_profile = Profile(self._config.get("profile"))
        self._current_profile_options = self._config.get(self._current_profile.value)

    def __str__(self):
        return dedent("""        Current profile: {}
        Current profile options:
        {}
        Full config:
        {}
        """).format(self._current_profile,
                    pformat(self._current_profile_options),
                    pformat(self._config))

    @classmethod
    def get_instance(cls):
        if not cls.__INSTANCE:
            cls.__INSTANCE = Settings()
        return cls.__INSTANCE

    def save(self):
        write_config(self._config)

    def reset(self, force_write=False):
        def_settings = get_default_settings()
        for p in Profile:
            current = self._config.get(p.value)
            default = def_settings.get(p.value)
            for k in default:
                current[k] = default.get(k)

        if force_write:
            write_config(get_default_settings())

    def add(self, name, value):
        """ Adds extra options """
        self._config[name] = value

    def get(self, name):
        """ Returns extra options """
        return self._config.get(name, None)

    def get_default(self, name):
        """ Returns default value of the option """
        return get_default_settings().get(self._current_profile.value).get(name)

    @property
    def presets(self):
        raise NotImplementedError

    @presets.setter
    def presets(self, name):
        raise NotImplementedError

    @property
    def profile(self):
        return self._current_profile

    @profile.setter
    def profile(self, prf):
        self._current_profile = prf
        self._config["profile"] = prf.value
        self._current_profile_options = self._config.get(prf.value)

    @property
    def host(self):
        return self._current_profile_options.get("host", self.get_default("host"))

    @host.setter
    def host(self, value):
        self._current_profile_options["host"] = value

    @property
    def port(self):
        return self._current_profile_options.get("port", self.get_default("port"))

    @port.setter
    def port(self, value):
        self._current_profile_options["port"] = value

    @property
    def user(self):
        return self._current_profile_options.get("user", self.get_default("user"))

    @user.setter
    def user(self, value):
        self._current_profile_options["user"] = value

    @property
    def password(self):
        return self._current_profile_options.get("password", self.get_default("password"))

    @password.setter
    def password(self, value):
        self._current_profile_options["password"] = value

    @property
    def http_user(self):
        return self._current_profile_options.get("http_user", self.get_default("http_user"))

    @http_user.setter
    def http_user(self, value):
        self._current_profile_options["http_user"] = value

    @property
    def http_password(self):
        return self._current_profile_options.get("http_password", self.get_default("http_password"))

    @http_password.setter
    def http_password(self, value):
        self._current_profile_options["http_password"] = value

    @property
    def http_port(self):
        return self._current_profile_options.get("http_port", self.get_default("http_port"))

    @http_port.setter
    def http_port(self, value):
        self._current_profile_options["http_port"] = value

    @property
    def http_timeout(self):
        return self._current_profile_options.get("http_timeout", self.get_default("http_timeout"))

    @http_timeout.setter
    def http_timeout(self, value):
        self._current_profile_options["http_timeout"] = value

    @property
    def telnet_user(self):
        return self._current_profile_options.get("telnet_user", self.get_default("telnet_user"))

    @telnet_user.setter
    def telnet_user(self, value):
        self._current_profile_options["telnet_user"] = value

    @property
    def telnet_password(self):
        return self._current_profile_options.get("telnet_password", self.get_default("telnet_password"))

    @telnet_password.setter
    def telnet_password(self, value):
        self._current_profile_options["telnet_password"] = value

    @property
    def telnet_port(self):
        return self._current_profile_options.get("telnet_port", self.get_default("telnet_port"))

    @telnet_port.setter
    def telnet_port(self, value):
        self._current_profile_options["telnet_port"] = value

    @property
    def telnet_timeout(self):
        return self._current_profile_options.get("telnet_timeout", self.get_default("telnet_timeout"))

    @telnet_timeout.setter
    def telnet_timeout(self, value):
        self._current_profile_options["telnet_timeout"] = value

    @property
    def services_path(self):
        return self._current_profile_options.get("services_path", self.get_default("services_path"))

    @services_path.setter
    def services_path(self, value):
        self._current_profile_options["services_path"] = value

    @property
    def user_bouquet_path(self):
        return self._current_profile_options.get("user_bouquet_path", self.get_default("user_bouquet_path"))

    @user_bouquet_path.setter
    def user_bouquet_path(self, value):
        self._current_profile_options["user_bouquet_path"] = value

    @property
    def satellites_xml_path(self):
        return self._current_profile_options.get("satellites_xml_path", self.get_default("satellites_xml_path"))

    @satellites_xml_path.setter
    def satellites_xml_path(self, value):
        self._current_profile_options["satellites_xml_path"] = value

    @property
    def data_dir_path(self):
        return self._current_profile_options.get("data_dir_path", self.get_default("data_dir_path"))

    @data_dir_path.setter
    def data_dir_path(self, value):
        self._current_profile_options["data_dir_path"] = value

    @property
    def picons_path(self):
        return self._current_profile_options.get("picons_path", self.get_default("picons_path"))

    @picons_path.setter
    def picons_path(self, value):
        self._current_profile_options["picons_path"] = value

    @property
    def picons_dir_path(self):
        return self._current_profile_options.get("picons_dir_path", self.get_default("picons_dir_path"))

    @picons_dir_path.setter
    def picons_dir_path(self, value):
        self._current_profile_options["picons_dir_path"] = value

    @property
    def backup_dir_path(self):
        return self._current_profile_options.get("backup_dir_path", self.get_default("backup_dir_path"))

    @backup_dir_path.setter
    def backup_dir_path(self, value):
        self._current_profile_options["backup_dir_path"] = value

    @property
    def backup_before_save(self):
        return self._current_profile_options.get("backup_before_save", self.get_default("backup_before_save"))

    @backup_before_save.setter
    def backup_before_save(self, value):
        self._current_profile_options["backup_before_save"] = value

    @property
    def backup_before_downloading(self):
        return self._current_profile_options.get("backup_before_downloading",
                                                 self.get_default("backup_before_downloading"))

    @backup_before_downloading.setter
    def backup_before_downloading(self, value):
        self._current_profile_options["backup_before_downloading"] = value

    @property
    def v5_support(self):
        return self._current_profile_options.get("v5_support", self.get_default("v5_support"))

    @v5_support.setter
    def v5_support(self, value):
        self._current_profile_options["v5_support"] = value

    @property
    def http_api_support(self):
        return self._current_profile_options.get("http_api_support", self.get_default("http_api_support"))

    @http_api_support.setter
    def http_api_support(self, value):
        self._current_profile_options["http_api_support"] = value

    @property
    def enable_yt_dl(self):
        return self._current_profile_options.get("enable_yt_dl", self.get_default("enable_yt_dl"))

    @enable_yt_dl.setter
    def enable_yt_dl(self, value):
        self._current_profile_options["enable_yt_dl"] = value

    @property
    def enable_send_to(self):
        return self._current_profile_options.get("enable_send_to", self.get_default("enable_send_to"))

    @enable_send_to.setter
    def enable_send_to(self, value):
        self._current_profile_options["enable_send_to"] = value

    @property
    def use_colors(self):
        return self._current_profile_options.get("use_colors", self.get_default("use_colors"))

    @use_colors.setter
    def use_colors(self, value):
        self._current_profile_options["use_colors"] = value

    @property
    def new_color(self):
        return self._current_profile_options.get("new_color", self.get_default("new_color"))

    @new_color.setter
    def new_color(self, value):
        self._current_profile_options["new_color"] = value

    @property
    def extra_color(self):
        return self._current_profile_options.get("extra_color", self.get_default("extra_color"))

    @extra_color.setter
    def extra_color(self, value):
        self._current_profile_options["extra_color"] = value

    @property
    def fav_click_mode(self):
        return self._current_profile_options.get("fav_click_mode", self.get_default("fav_click_mode"))

    @fav_click_mode.setter
    def fav_click_mode(self, value):
        self._current_profile_options["fav_click_mode"] = value


def get_config():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)  # create dir if not exist
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)

    if not os.path.isfile(CONFIG_FILE) or os.stat(CONFIG_FILE).st_size == 0:
        write_config(get_default_settings())

    with open(CONFIG_FILE, "r") as config_file:
        return json.load(config_file)


def write_config(config):
    with open(CONFIG_FILE, "w") as config_file:
        json.dump(config, config_file, indent="    ")


def get_default_settings():
    return {
        Profile.ENIGMA_2.value: {
            "host": "127.0.0.1", "port": "21", "user": "root", "password": "root",
            "http_user": "root", "http_password": "", "http_port": "80", "http_timeout": 5,
            "telnet_user": "root", "telnet_password": "", "telnet_port": "23", "telnet_timeout": 5,
            "services_path": "/etc/enigma2/", "user_bouquet_path": "/etc/enigma2/",
            "satellites_xml_path": "/etc/tuxbox/", "data_dir_path": DATA_PATH + "enigma2/",
            "picons_path": "/usr/share/enigma2/picon", "picons_dir_path": DATA_PATH + "enigma2/picons/",
            "backup_dir_path": DATA_PATH + "enigma2/backup/",
            "backup_before_save": True, "backup_before_downloading": True,
            "v5_support": False, "http_api_support": False, "enable_yt_dl": False, "enable_send_to": False,
            "use_colors": True, "new_color": "rgb(255,230,204)", "extra_color": "rgb(179,230,204)",
            "fav_click_mode": 0},
        Profile.NEUTRINO_MP.value: {
            "host": "127.0.0.1", "port": "21", "user": "root", "password": "root",
            "http_user": "", "http_password": "", "http_port": "80", "http_timeout": 2,
            "telnet_user": "root", "telnet_password": "", "telnet_port": "23", "telnet_timeout": 1,
            "services_path": "/var/tuxbox/config/zapit/", "user_bouquet_path": "/var/tuxbox/config/zapit/",
            "satellites_xml_path": "/var/tuxbox/config/", "data_dir_path": DATA_PATH + "neutrino/",
            "picons_path": "/usr/share/tuxbox/neutrino/icons/logo/", "picons_dir_path": DATA_PATH + "neutrino/picons/",
            "backup_dir_path": DATA_PATH + "neutrino/backup/",
            "backup_before_save": True, "backup_before_downloading": True,
            "fav_click_mode": 0},
        "profile": Profile.ENIGMA_2.value}


if __name__ == "__main__":
    pass

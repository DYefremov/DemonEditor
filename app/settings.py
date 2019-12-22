import json
import os
from pprint import pformat
from textwrap import dedent
from enum import Enum, IntEnum
from pathlib import Path

CONFIG_PATH = str(Path.home()) + "/.config/demon-editor/"
CONFIG_FILE = CONFIG_PATH + "config.json"
DATA_PATH = "data/"


class Defaults(Enum):
    """ Default program settings """
    DEFAULT_PROFILE = "default"
    BACKUP_BEFORE_DOWNLOADING = True
    BACKUP_BEFORE_SAVE = True
    V5_SUPPORT = False
    HTTP_API_SUPPORT = False
    ENABLE_YT_DL = False
    ENABLE_SEND_TO = False
    USE_COLORS = True
    NEW_COLOR = "rgb(255,230,204)"
    EXTRA_COLOR = "rgb(179,230,204)"
    FAV_CLICK_MODE = 0


def get_default_settings():
    return {
        "version": 1,
        "default_profile": Defaults.DEFAULT_PROFILE.value,
        "profiles": {"default": SettingsType.ENIGMA_2.get_default_settings()},
        "v5_support": Defaults.V5_SUPPORT.value,
        "http_api_support": Defaults.HTTP_API_SUPPORT.value,
        "enable_yt_dl": Defaults.ENABLE_YT_DL.value,
        "enable_send_to": Defaults.ENABLE_SEND_TO.value,
        "use_colors": Defaults.USE_COLORS.value,
        "new_color": Defaults.NEW_COLOR.value,
        "extra_color": Defaults.EXTRA_COLOR.value,
        "fav_click_mode": Defaults.FAV_CLICK_MODE.value
    }


class SettingsType(IntEnum):
    """ Profiles for settings """
    ENIGMA_2 = 0
    NEUTRINO_MP = 1

    def get_default_settings(self):
        """ Returns default settings for current type """
        if self is self.ENIGMA_2:
            return {"setting_type": self,
                    "host": "127.0.0.1", "port": "21", "user": "root", "password": "root", "timeout": 5,
                    "http_user": "root", "http_password": "", "http_port": "80", "http_timeout": 5,
                    "telnet_user": "root", "telnet_password": "", "telnet_port": "23", "telnet_timeout": 5,
                    "services_path": "/etc/enigma2/", "user_bouquet_path": "/etc/enigma2/",
                    "satellites_xml_path": "/etc/tuxbox/", "data_local_path": DATA_PATH + "enigma2/",
                    "picons_path": "/usr/share/enigma2/picon",
                    "picons_local_path": DATA_PATH + "enigma2/picons/",
                    "backup_local_path": DATA_PATH + "enigma2/backup/"}
        elif self is self.NEUTRINO_MP:
            return {"setting_type": self,
                    "host": "127.0.0.1", "port": "21", "user": "root", "password": "root", "timeout": 5,
                    "http_user": "", "http_password": "", "http_port": "80", "http_timeout": 2,
                    "telnet_user": "root", "telnet_password": "", "telnet_port": "23", "telnet_timeout": 1,
                    "services_path": "/var/tuxbox/config/zapit/", "user_bouquet_path": "/var/tuxbox/config/zapit/",
                    "satellites_xml_path": "/var/tuxbox/config/", "data_local_path": DATA_PATH + "neutrino/",
                    "picons_path": "/usr/share/tuxbox/neutrino/icons/logo/",
                    "picons_local_path": DATA_PATH + "neutrino/picons/",
                    "backup_local_path": DATA_PATH + "neutrino/backup/"}


class SettingsException(Exception):
    pass


class Settings:
    __INSTANCE = None
    __VERSION = 1

    def __init__(self):
        settings = get_settings()

        if self.__VERSION > settings.get("version", 0):
            write_settings(get_default_settings())
            raise SettingsException("Outdated version of the settings format!")

        self._settings = settings
        self._current_profile = self._settings.get("default_profile", "default")
        self._profiles = self._settings.get("profiles", {"default": SettingsType.ENIGMA_2.get_default_settings()})
        self._cp_settings = self._profiles.get(self._current_profile)  # Current profile settings

    def __str__(self):
        return dedent("""        Current profile: {}
        Current profile options:
        {}
        Full config:
        {}
        """).format(self._current_profile,
                    pformat(self._cp_settings),
                    pformat(self._settings))

    @classmethod
    def get_instance(cls):
        if not cls.__INSTANCE:
            cls.__INSTANCE = Settings()
        return cls.__INSTANCE

    def save(self):
        write_settings(self._settings)

    def reset(self, force_write=False):
        for k, v in self.setting_type.get_default_settings().items():
            self._cp_settings[k] = v

        if force_write:
            self.save()

    def get_default(self, p_name):
        """ Returns default value for current settings type """
        return self.setting_type.get_default_settings().get(p_name)

    def add(self, name, value):
        """ Adds extra options """
        self._settings[name] = value

    def get(self, name):
        """ Returns extra options or None """
        return self._settings.get(name, None)

    @property
    def profiles(self):
        return self._profiles

    @profiles.setter
    def profiles(self, ps):
        self._profiles = ps
        self._settings["profiles"] = self._profiles

    @property
    def setting_type(self):
        return SettingsType(self._cp_settings.get("setting_type", SettingsType.ENIGMA_2.value))

    @setting_type.setter
    def setting_type(self, s_type):
        self._cp_settings["setting_type"] = s_type
        for k, v in s_type.get_default_settings().items():
            self._cp_settings[k] = v

    @property
    def host(self):
        return self._cp_settings.get("host", self.get_default("host"))

    @host.setter
    def host(self, value):
        self._cp_settings["host"] = value

    @property
    def port(self):
        return self._cp_settings.get("port", self.get_default("port"))

    @port.setter
    def port(self, value):
        self._cp_settings["port"] = value

    @property
    def user(self):
        return self._cp_settings.get("user", self.get_default("user"))

    @user.setter
    def user(self, value):
        self._cp_settings["user"] = value

    @property
    def password(self):
        return self._cp_settings.get("password", self.get_default("password"))

    @password.setter
    def password(self, value):
        self._cp_settings["password"] = value

    @property
    def http_user(self):
        return self._cp_settings.get("http_user", self.get_default("http_user"))

    @http_user.setter
    def http_user(self, value):
        self._cp_settings["http_user"] = value

    @property
    def http_password(self):
        return self._cp_settings.get("http_password", self.get_default("http_password"))

    @http_password.setter
    def http_password(self, value):
        self._cp_settings["http_password"] = value

    @property
    def http_port(self):
        return self._cp_settings.get("http_port", self.get_default("http_port"))

    @http_port.setter
    def http_port(self, value):
        self._cp_settings["http_port"] = value

    @property
    def http_timeout(self):
        return self._cp_settings.get("http_timeout", self.get_default("http_timeout"))

    @http_timeout.setter
    def http_timeout(self, value):
        self._cp_settings["http_timeout"] = value

    @property
    def telnet_user(self):
        return self._cp_settings.get("telnet_user", self.get_default("telnet_user"))

    @telnet_user.setter
    def telnet_user(self, value):
        self._cp_settings["telnet_user"] = value

    @property
    def telnet_password(self):
        return self._cp_settings.get("telnet_password", self.get_default("telnet_password"))

    @telnet_password.setter
    def telnet_password(self, value):
        self._cp_settings["telnet_password"] = value

    @property
    def telnet_port(self):
        return self._cp_settings.get("telnet_port", self.get_default("telnet_port"))

    @telnet_port.setter
    def telnet_port(self, value):
        self._cp_settings["telnet_port"] = value

    @property
    def telnet_timeout(self):
        return self._cp_settings.get("telnet_timeout", self.get_default("telnet_timeout"))

    @telnet_timeout.setter
    def telnet_timeout(self, value):
        self._cp_settings["telnet_timeout"] = value

    @property
    def services_path(self):
        return self._cp_settings.get("services_path", self.get_default("services_path"))

    @services_path.setter
    def services_path(self, value):
        self._cp_settings["services_path"] = value

    @property
    def user_bouquet_path(self):
        return self._cp_settings.get("user_bouquet_path", self.get_default("user_bouquet_path"))

    @user_bouquet_path.setter
    def user_bouquet_path(self, value):
        self._cp_settings["user_bouquet_path"] = value

    @property
    def satellites_xml_path(self):
        return self._cp_settings.get("satellites_xml_path", self.get_default("satellites_xml_path"))

    @satellites_xml_path.setter
    def satellites_xml_path(self, value):
        self._cp_settings["satellites_xml_path"] = value

    @property
    def data_local_path(self):
        return self._cp_settings.get("data_local_path", self.get_default("data_local_path"))

    @data_local_path.setter
    def data_local_path(self, value):
        self._cp_settings["data_local_path"] = value

    @property
    def picons_path(self):
        return self._cp_settings.get("picons_path", self.get_default("picons_path"))

    @picons_path.setter
    def picons_path(self, value):
        self._cp_settings["picons_path"] = value

    @property
    def picons_local_path(self):
        return self._cp_settings.get("picons_local_path", self.get_default("picons_local_path"))

    @picons_local_path.setter
    def picons_local_path(self, value):
        self._cp_settings["picons_local_path"] = value

    @property
    def backup_local_path(self):
        return self._cp_settings.get("backup_local_path", self.get_default("backup_local_path"))

    @backup_local_path.setter
    def backup_local_path(self, value):
        self._cp_settings["backup_local_path"] = value

    # ***** Program settings *****

    @property
    def backup_before_save(self):
        return self._settings.get("backup_before_save", Defaults.BACKUP_BEFORE_SAVE.value)

    @backup_before_save.setter
    def backup_before_save(self, value):
        self._settings["backup_before_save"] = value

    @property
    def backup_before_downloading(self):
        return self._settings.get("backup_before_downloading", Defaults.BACKUP_BEFORE_DOWNLOADING.value)

    @backup_before_downloading.setter
    def backup_before_downloading(self, value):
        self._settings["backup_before_downloading"] = value

    @property
    def v5_support(self):
        return self._settings.get("v5_support", Defaults.V5_SUPPORT.value)

    @v5_support.setter
    def v5_support(self, value):
        self._settings["v5_support"] = value

    @property
    def http_api_support(self):
        return self._settings.get("http_api_support", Defaults.HTTP_API_SUPPORT.value)

    @http_api_support.setter
    def http_api_support(self, value):
        self._settings["http_api_support"] = value

    @property
    def enable_yt_dl(self):
        return self._settings.get("enable_yt_dl", Defaults.ENABLE_YT_DL.value)

    @enable_yt_dl.setter
    def enable_yt_dl(self, value):
        self._settings["enable_yt_dl"] = value

    @property
    def enable_send_to(self):
        return self._settings.get("enable_send_to", Defaults.ENABLE_SEND_TO.value)

    @enable_send_to.setter
    def enable_send_to(self, value):
        self._settings["enable_send_to"] = value

    @property
    def use_colors(self):
        return self._settings.get("use_colors", Defaults.USE_COLORS.value)

    @use_colors.setter
    def use_colors(self, value):
        self._settings["use_colors"] = value

    @property
    def new_color(self):
        return self._settings.get("new_color", Defaults.NEW_COLOR.value)

    @new_color.setter
    def new_color(self, value):
        self._settings["new_color"] = value

    @property
    def extra_color(self):
        return self._settings.get("extra_color", Defaults.EXTRA_COLOR.value)

    @extra_color.setter
    def extra_color(self, value):
        self._settings["extra_color"] = value

    @property
    def fav_click_mode(self):
        return self._settings.get("fav_click_mode", Defaults.FAV_CLICK_MODE.value)

    @fav_click_mode.setter
    def fav_click_mode(self, value):
        self._settings["fav_click_mode"] = value


def get_settings():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)  # create dir if not exist
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)

    if not os.path.isfile(CONFIG_FILE) or os.stat(CONFIG_FILE).st_size == 0:
        write_settings(get_default_settings())

    with open(CONFIG_FILE, "r") as config_file:
        return json.load(config_file)


def write_settings(config):
    with open(CONFIG_FILE, "w") as config_file:
        json.dump(config, config_file, indent="    ")


if __name__ == "__main__":
    pass

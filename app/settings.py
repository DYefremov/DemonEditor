import copy
import json
import locale
import os
import sys
from enum import Enum, IntEnum
from functools import lru_cache
from pathlib import Path
from pprint import pformat
from textwrap import dedent

HOME_PATH = str(Path.home())
CONFIG_PATH = HOME_PATH + "/.config/demon-editor/"
CONFIG_FILE = CONFIG_PATH + "config.json"
DATA_PATH = HOME_PATH + "/DemonEditor/data/"

IS_DARWIN = sys.platform == "darwin"


class Defaults(Enum):
    """ Default program settings """
    DEFAULT_PROFILE = "default"
    BACKUP_BEFORE_DOWNLOADING = True
    BACKUP_BEFORE_SAVE = True
    V5_SUPPORT = False
    FORCE_BQ_NAMES = False
    HTTP_API_SUPPORT = False
    ENABLE_YT_DL = False
    ENABLE_SEND_TO = False
    USE_COLORS = True
    NEW_COLOR = "rgb(255,230,204)"
    EXTRA_COLOR = "rgb(179,230,204)"
    FAV_CLICK_MODE = 0
    PLAY_STREAMS_MODE = 1 if IS_DARWIN else 0
    PROFILE_FOLDER_DEFAULT = False
    RECORDS_PATH = DATA_PATH + "records/"
    ACTIVATE_TRANSCODING = False
    ACTIVE_TRANSCODING_PRESET = "720p TV/device"


def get_settings():
    if not os.path.isfile(CONFIG_FILE) or os.stat(CONFIG_FILE).st_size == 0:
        write_settings(get_default_settings())

    with open(CONFIG_FILE, "r") as config_file:
        return json.load(config_file)


def get_default_settings(profile_name="default"):
    def_settings = SettingsType.ENIGMA_2.get_default_settings()
    set_local_paths(def_settings, profile_name)

    return {
        "version": 1,
        "default_profile": Defaults.DEFAULT_PROFILE.value,
        "profiles": {profile_name: def_settings},
        "v5_support": Defaults.V5_SUPPORT.value,
        "http_api_support": Defaults.HTTP_API_SUPPORT.value,
        "enable_yt_dl": Defaults.ENABLE_YT_DL.value,
        "enable_send_to": Defaults.ENABLE_SEND_TO.value,
        "use_colors": Defaults.USE_COLORS.value,
        "new_color": Defaults.NEW_COLOR.value,
        "extra_color": Defaults.EXTRA_COLOR.value,
        "fav_click_mode": Defaults.FAV_CLICK_MODE.value,
        "profile_folder_is_default": Defaults.PROFILE_FOLDER_DEFAULT.value,
        "records_path": Defaults.RECORDS_PATH.value
    }


def get_default_transcoding_presets():
    return {"720p TV/device": {"vcodec": "h264", "vb": "1500", "width": "1280", "height": "720", "acodec": "mp3",
                               "ab": "192", "channels": "2", "samplerate": "44100", "scodec": "none"},
            "1080p TV/device": {"vcodec": "h264", "vb": "3500", "width": "1920", "height": "1080", "acodec": "mp3",
                                "ab": "192", "channels": "2", "samplerate": "44100", "scodec": "none"}}


def write_settings(config):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_FILE, "w") as config_file:
        json.dump(config, config_file, indent="    ")


def set_local_paths(settings, profile_name, data_path=DATA_PATH, use_profile_folder=False):
    settings["data_local_path"] = "{}{}/".format(data_path, profile_name)
    if use_profile_folder:
        settings["picons_local_path"] = "{}{}/{}/".format(data_path, profile_name, "picons")
        settings["backup_local_path"] = "{}{}/{}/".format(data_path, profile_name, "backup")
    else:
        settings["picons_local_path"] = "{}{}/{}/".format(data_path, "picons", profile_name)
        settings["backup_local_path"] = "{}{}/{}/".format(data_path, "backup", profile_name)


class SettingsType(IntEnum):
    """ Profiles for settings """
    ENIGMA_2 = 0
    NEUTRINO_MP = 1

    def get_default_settings(self):
        """ Returns default settings for current type """
        if self is self.ENIGMA_2:
            return {"setting_type": self.value,
                    "host": "127.0.0.1", "port": "21", "user": "root", "password": "root", "timeout": 5,
                    "http_user": "root", "http_password": "", "http_port": "80",
                    "http_timeout": 5, "http_use_ssl": False,
                    "telnet_user": "root", "telnet_password": "", "telnet_port": "23", "telnet_timeout": 5,
                    "services_path": "/etc/enigma2/", "user_bouquet_path": "/etc/enigma2/",
                    "satellites_xml_path": "/etc/tuxbox/", "data_local_path": DATA_PATH + "enigma2/",
                    "picons_path": "/usr/share/enigma2/picon/",
                    "picons_local_path": DATA_PATH + "enigma2/picons/",
                    "backup_local_path": DATA_PATH + "enigma2/backup/"}
        elif self is self.NEUTRINO_MP:
            return {"setting_type": self,
                    "host": "127.0.0.1", "port": "21", "user": "root", "password": "root", "timeout": 5,
                    "http_user": "", "http_password": "", "http_port": "80", "http_timeout": 2, "http_use_ssl": False,
                    "telnet_user": "root", "telnet_password": "", "telnet_port": "23", "telnet_timeout": 1,
                    "services_path": "/var/tuxbox/config/zapit/", "user_bouquet_path": "/var/tuxbox/config/zapit/",
                    "satellites_xml_path": "/var/tuxbox/config/", "data_local_path": DATA_PATH + "neutrino/",
                    "picons_path": "/usr/share/tuxbox/neutrino/icons/logo/",
                    "picons_local_path": DATA_PATH + "neutrino/picons/",
                    "backup_local_path": DATA_PATH + "neutrino/backup/"}


class SettingsException(Exception):
    pass


class SettingsReadException(SettingsException):
    pass


class PlayStreamsMode(IntEnum):
    """ Behavior mode when opening streams. """
    BUILT_IN = 0
    VLC = 1
    M3U = 2


class Settings:
    __INSTANCE = None
    __VERSION = 1

    def __init__(self, ext_settings=None):
        try:
            settings = ext_settings or get_settings()
        except PermissionError as e:
            raise SettingsReadException(e)

        if self.__VERSION > settings.get("version", 0):
            raise SettingsException("Outdated version of the settings format!")

        self._settings = settings
        self._current_profile = self._settings.get("default_profile", "default")
        self._profiles = self._settings.get("profiles", {"default": SettingsType.ENIGMA_2.get_default_settings()})
        self._cp_settings = self._profiles.get(self._current_profile, None)  # Current profile settings
        if not self._cp_settings:
            raise SettingsException("Error reading settings [current profile].")

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

        def_path = self.default_data_path
        def_path += "enigma2/" if self.setting_type is SettingsType.ENIGMA_2 else "neutrino/"
        set_local_paths(self._cp_settings, self._current_profile, def_path, self.profile_folder_is_default)

        if force_write:
            self.save()

    @staticmethod
    def reset_to_default():
        write_settings(get_default_settings())

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
    def settings(self):
        """ Returns copy of the current settings! """
        return copy.deepcopy(self._settings)

    @settings.setter
    def settings(self, value):
        """ Sets copy of the settings! """
        self._settings = copy.deepcopy(value)

    @property
    def current_profile(self):
        return self._current_profile

    @current_profile.setter
    def current_profile(self, value):
        self._current_profile = value
        self._cp_settings = self._profiles.get(self._current_profile)

    @property
    def default_profile(self):
        return self._settings.get("default_profile", "default")

    @default_profile.setter
    def default_profile(self, value):
        self._settings["default_profile"] = value

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
        self._cp_settings["setting_type"] = s_type.value

    # ******* Network ******** #

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
    def http_use_ssl(self):
        return self._cp_settings.get("http_use_ssl", self.get_default("http_use_ssl"))

    @http_use_ssl.setter
    def http_use_ssl(self, value):
        self._cp_settings["http_use_ssl"] = value

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
    def picons_path(self):
        return self._cp_settings.get("picons_path", self.get_default("picons_path"))

    @picons_path.setter
    def picons_path(self, value):
        self._cp_settings["picons_path"] = value

    # ***** Local paths ***** #

    @property
    def profile_folder_is_default(self):
        return self._settings.get("profile_folder_is_default", Defaults.PROFILE_FOLDER_DEFAULT.value)

    @profile_folder_is_default.setter
    def profile_folder_is_default(self, value):
        self._settings["profile_folder_is_default"] = value

    @property
    def default_data_path(self):
        return self._settings.get("default_data_path", DATA_PATH)

    @default_data_path.setter
    def default_data_path(self, value):
        self._settings["default_data_path"] = value

    @property
    def data_local_path(self):
        return self._cp_settings.get("data_local_path", self.get_default("data_local_path"))

    @data_local_path.setter
    def data_local_path(self, value):
        self._cp_settings["data_local_path"] = value

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

    @property
    def records_path(self):
        return self._settings.get("records_path", Defaults.RECORDS_PATH.value)

    @records_path.setter
    def records_path(self, value):
        self._settings["records_path"] = value

    # ******** Streaming ********* #

    @property
    def activate_transcoding(self):
        return self._settings.get("activate_transcoding", Defaults.ACTIVATE_TRANSCODING.value)

    @activate_transcoding.setter
    def activate_transcoding(self, value):
        self._settings["activate_transcoding"] = value

    @property
    def active_preset(self):
        return self._settings.get("active_preset", Defaults.ACTIVE_TRANSCODING_PRESET.value)

    @active_preset.setter
    def active_preset(self, value):
        self._settings["active_preset"] = value

    @property
    def transcoding_presets(self):
        return self._settings.get("transcoding_presets", get_default_transcoding_presets())

    @transcoding_presets.setter
    def transcoding_presets(self, value):
        self._settings["transcoding_presets"] = value

    @property
    def play_streams_mode(self):
        return PlayStreamsMode(self._settings.get("play_streams_mode", Defaults.PLAY_STREAMS_MODE.value))

    @play_streams_mode.setter
    def play_streams_mode(self, value):
        self._settings["play_streams_mode"] = value

    # *********** EPG ************ #

    @property
    def epg_options(self):
        """ Options used by the EPG dialog. """
        return self._cp_settings.get("epg_options", None)

    @epg_options.setter
    def epg_options(self, value):
        self._cp_settings["epg_options"] = value

    # ***** Program settings ***** #

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
    def force_bq_names(self):
        return self._settings.get("force_bq_names", Defaults.FORCE_BQ_NAMES.value)

    @force_bq_names.setter
    def force_bq_names(self, value):
        self._settings["force_bq_names"] = value

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
    def enable_yt_dl_update(self):
        return self._settings.get("enable_yt_dl_update", Defaults.ENABLE_YT_DL.value)

    @enable_yt_dl_update.setter
    def enable_yt_dl_update(self, value):
        self._settings["enable_yt_dl_update"] = value

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

    @property
    def language(self):
        return self._settings.get("language", locale.getlocale()[0] or "en_US")

    @language.setter
    def language(self, value):
        self._settings["language"] = value

    @property
    def load_last_config(self):
        return self._settings.get("load_last_config", False)

    @load_last_config.setter
    def load_last_config(self, value):
        self._settings["load_last_config"] = value

    @property
    def show_srv_hints(self):
        """ Show short info as hints in the main services list. """
        return self._settings.get("show_srv_hints", True)

    @show_srv_hints.setter
    def show_srv_hints(self, value):
        self._settings["show_srv_hints"] = value

    @property
    def show_bq_hints(self):
        """ Show detailed info as hints in the bouquet list. """
        return self._settings.get("show_bq_hints", True)

    @show_bq_hints.setter
    def show_bq_hints(self, value):
        self._settings["show_bq_hints"] = value

    # *********** Appearance *********** #

    @property
    def is_themes_support(self):
        return self._settings.get("is_themes_support", False)

    @is_themes_support.setter
    def is_themes_support(self, value):
        self._settings["is_themes_support"] = value

    @property
    def theme(self):
        return self._settings.get("theme", "Default")

    @theme.setter
    def theme(self, value):
        self._settings["theme"] = value

    @property
    @lru_cache(1)
    def themes_path(self):
        return "{}/.themes/".format(HOME_PATH)

    @property
    def icon_theme(self):
        return self._settings.get("icon_theme", "Adwaita")

    @icon_theme.setter
    def icon_theme(self, value):
        self._settings["icon_theme"] = value

    @property
    @lru_cache(1)
    def icon_themes_path(self):
        return "{}/.icons/".format(HOME_PATH)

    @property
    def is_darwin(self):
        return IS_DARWIN

    # *********** Download dialog *********** #

    @property
    def use_http(self):
        return self._settings.get("use_http", True)

    @use_http.setter
    def use_http(self, value):
        self._settings["use_http"] = value

    @property
    def remove_unused_bouquets(self):
        return self._settings.get("remove_unused_bouquets", True)

    @remove_unused_bouquets.setter
    def remove_unused_bouquets(self, value):
        self._settings["remove_unused_bouquets"] = value

    # **************** Debug **************** #

    @property
    def debug_mode(self):
        return self._settings.get("debug_mode", False)

    @debug_mode.setter
    def debug_mode(self, value):
        self._settings["debug_mode"] = value

    # **************** Experimental **************** #

    @property
    def is_enable_experimental(self):
        """ Allows experimental functionality. """
        return self._settings.get("enable_experimental", False)

    @is_enable_experimental.setter
    def is_enable_experimental(self, value):
        self._settings["enable_experimental"] = value


if __name__ == "__main__":
    pass

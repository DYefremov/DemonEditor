# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2022 Dmitriy Yefremov
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

SEP = os.sep
HOME_PATH = str(Path.home())
CONFIG_PATH = HOME_PATH + "{}.config{}demon-editor{}".format(SEP, SEP, SEP)
CONFIG_FILE = CONFIG_PATH + "config.json"
DATA_PATH = HOME_PATH + "{}DemonEditor{}".format(SEP, SEP)
GTK_PATH = os.environ.get("GTK_PATH", None)

IS_DARWIN = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
IS_LINUX = sys.platform == "linux"


class Defaults(Enum):
    """ Default program settings """
    USER = "root"
    PASSWORD = ""
    HOST = "127.0.0.1"
    FTP_PORT = "21"
    HTTP_PORT = "80"
    TELNET_PORT = "23"
    HTTP_USE_SSL = False
    # Enigma2.
    BOX_SERVICES_PATH = "/etc/enigma2/"
    BOX_SATELLITE_PATH = "/etc/tuxbox/"
    BOX_PICON_PATH = "/usr/share/enigma2/picon/"
    BOX_PICON_PATHS = ("/usr/share/enigma2/picon/",
                       "/media/hdd/picon/",
                       "/media/usb/picon/",
                       "/media/mmc/picon/",
                       "/media/cf/picon/")
    # Neutrino.
    NEUTRINO_BOX_SERVICES_PATH = "/var/tuxbox/config/zapit/"
    NEUTRINO_BOX_SATELLITE_PATH = "/var/tuxbox/config/"
    NEUTRINO_BOX_PICON_PATH = "/usr/share/tuxbox/neutrino/icons/logo/"
    NEUTRINO_BOX_PICON_PATHS = ("/usr/share/tuxbox/neutrino/icons/logo/",)
    # Paths.
    BACKUP_PATH = "{}backup{}".format(DATA_PATH, SEP)
    PICON_PATH = "{}picons{}".format(DATA_PATH, SEP)

    DEFAULT_PROFILE = "default"
    BACKUP_BEFORE_DOWNLOADING = True
    BACKUP_BEFORE_SAVE = True
    V5_SUPPORT = False
    FORCE_BQ_NAMES = False
    HTTP_API_SUPPORT = True
    ENABLE_YT_DL = False
    ENABLE_SEND_TO = False
    USE_COLORS = True
    NEW_COLOR = "rgb(255,230,204)"
    EXTRA_COLOR = "rgb(179,230,204)"
    TOOLTIP_LOGO_SIZE = 96
    LIST_PICON_SIZE = 32
    FAV_CLICK_MODE = 0
    PLAY_STREAMS_MODE = 1 if IS_DARWIN else 0
    STREAM_LIB = "mpv" if IS_WIN else "vlc"
    MAIN_LIST_PLAYBACK = False
    PROFILE_FOLDER_DEFAULT = False
    RECORDS_PATH = DATA_PATH + "records{}".format(SEP)
    ACTIVATE_TRANSCODING = False
    ACTIVE_TRANSCODING_PRESET = "720p TV{}device".format(SEP)


class SettingsType(IntEnum):
    """ Profiles for settings """
    ENIGMA_2 = 0
    NEUTRINO_MP = 1

    def get_default_settings(self):
        """ Returns default settings for current type. """
        if self is self.ENIGMA_2:
            srv_path = Defaults.BOX_SERVICES_PATH.value
            sat_path = Defaults.BOX_SATELLITE_PATH.value
            picons_path = Defaults.BOX_PICON_PATH.value
            http_timeout = 5
            telnet_timeout = 5
        else:
            srv_path = Defaults.NEUTRINO_BOX_SERVICES_PATH.value
            sat_path = Defaults.NEUTRINO_BOX_SATELLITE_PATH.value
            picons_path = Defaults.NEUTRINO_BOX_PICON_PATH.value
            http_timeout = 2
            telnet_timeout = 1

        return {"setting_type": self.value,
                "host": Defaults.HOST.value,
                "port": Defaults.FTP_PORT.value,
                "timeout": 5,
                "user": Defaults.USER.value,
                "password": Defaults.PASSWORD.value,
                "http_port": Defaults.HTTP_PORT.value,
                "http_timeout": http_timeout,
                "http_use_ssl": Defaults.HTTP_USE_SSL.value,
                "telnet_port": Defaults.TELNET_PORT.value,
                "telnet_timeout": telnet_timeout,
                "services_path": srv_path,
                "user_bouquet_path": srv_path,
                "satellites_xml_path": sat_path,
                "picons_path": picons_path}


class SettingsException(Exception):
    pass


class SettingsReadException(SettingsException):
    pass


class PlayStreamsMode(IntEnum):
    """ Behavior mode when opening streams. """
    BUILT_IN = 0
    WINDOW = 1
    M3U = 2


class Settings:
    __INSTANCE = None
    __VERSION = 2

    def __init__(self, ext_settings=None):
        try:
            settings = ext_settings or self.get_settings()
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
        self.write_settings(self._settings)

    def reset(self, force_write=False):
        for k, v in self.setting_type.get_default_settings().items():
            self._cp_settings[k] = v

        if force_write:
            self.save()

    @staticmethod
    def reset_to_default():
        Settings.write_settings(Settings.get_default_settings())

    def get_default(self, p_name):
        """ Returns default value for current settings type """
        return self.setting_type.get_default_settings().get(p_name)

    def add(self, name, value):
        """ Adds extra options """
        self._settings[name] = value

    def get(self, name, default=None):
        """ Returns extra options or None """
        return self._settings.get(name, default)

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
    def current_profile_settings(self):
        return self._cp_settings

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

    @property
    def picons_paths(self):
        if self.setting_type is SettingsType.NEUTRINO_MP:
            return self._settings.get("neutrino_picon_paths", Defaults.NEUTRINO_BOX_PICON_PATHS.value)
        else:
            return self._settings.get("picon_paths", Defaults.BOX_PICON_PATHS.value)

    @picons_paths.setter
    def picons_paths(self, value):
        if self.setting_type is SettingsType.NEUTRINO_MP:
            self._settings["neutrino_picon_paths"] = value
        else:
            self._settings["picon_paths"] = value

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
    def default_backup_path(self):
        return self._settings.get("default_backup_path", Defaults.BACKUP_PATH.value)

    @default_backup_path.setter
    def default_backup_path(self, value):
        self._settings["default_backup_path"] = value

    @property
    def default_picon_path(self):
        return self._settings.get("default_picon_path", Defaults.PICON_PATH.value)

    @default_picon_path.setter
    def default_picon_path(self, value):
        self._settings["default_picon_path"] = value

    @property
    def profile_data_path(self):
        return f"{self.default_data_path}data{SEP}{self._current_profile}{SEP}"

    @profile_data_path.setter
    def profile_data_path(self, value):
        self._cp_settings["profile_data_path"] = value

    @property
    def profile_picons_path(self):
        if self.profile_folder_is_default:
            return f"{self.profile_data_path}picons{SEP}"
        return f"{self.default_picon_path}{self._current_profile}{SEP}"

    @profile_picons_path.setter
    def profile_picons_path(self, value):
        self._cp_settings["profile_picons_path"] = value

    @property
    def profile_backup_path(self):
        if self.profile_folder_is_default:
            return f"{self.profile_data_path}backup{SEP}"
        return f"{self.default_backup_path}{self._current_profile}{SEP}"

    @profile_backup_path.setter
    def profile_backup_path(self, value):
        self._cp_settings["profile_backup_path"] = value

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
        return self._settings.get("transcoding_presets", self.get_default_transcoding_presets())

    @transcoding_presets.setter
    def transcoding_presets(self, value):
        self._settings["transcoding_presets"] = value

    @property
    def play_streams_mode(self):
        return PlayStreamsMode(self._settings.get("play_streams_mode", Defaults.PLAY_STREAMS_MODE.value))

    @play_streams_mode.setter
    def play_streams_mode(self, value):
        self._settings["play_streams_mode"] = value

    @property
    def stream_lib(self):
        return self._settings.get("stream_lib", Defaults.STREAM_LIB.value)

    @stream_lib.setter
    def stream_lib(self, value):
        self._settings["stream_lib"] = value

    @property
    def fav_click_mode(self):
        return self._settings.get("fav_click_mode", Defaults.FAV_CLICK_MODE.value)

    @fav_click_mode.setter
    def fav_click_mode(self, value):
        self._settings["fav_click_mode"] = value

    @property
    def main_list_playback(self):
        return self._settings.get("main_list_playback", Defaults.MAIN_LIST_PLAYBACK.value)

    @main_list_playback.setter
    def main_list_playback(self, value):
        self._settings["main_list_playback"] = value

    # *********** EPG ************ #

    @property
    def epg_options(self):
        """ Options used by the EPG dialog. """
        return self._cp_settings.get("epg_options", None)

    @epg_options.setter
    def epg_options(self, value):
        self._cp_settings["epg_options"] = value

    # *********** FTP ************ #

    @property
    def ftp_bookmarks(self):
        return self._cp_settings.get("ftp_bookmarks", [])

    @ftp_bookmarks.setter
    def ftp_bookmarks(self, value):
        self._cp_settings["ftp_bookmarks"] = value

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
    def list_font(self):
        return self._settings.get("list_font", "")

    @list_font.setter
    def list_font(self, value):
        self._settings["list_font"] = value

    @property
    def list_picon_size(self):
        return self._settings.get("list_picon_size", Defaults.LIST_PICON_SIZE.value)

    @list_picon_size.setter
    def list_picon_size(self, value):
        self._settings["list_picon_size"] = value

    @property
    def tooltip_logo_size(self):
        return self._settings.get("tooltip_logo_size", Defaults.TOOLTIP_LOGO_SIZE.value)

    @tooltip_logo_size.setter
    def tooltip_logo_size(self, value):
        self._settings["tooltip_logo_size"] = value

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
    def dark_mode(self):
        if IS_DARWIN:
            import subprocess

            cmd = ["defaults", "read", "-g", "AppleInterfaceStyle"]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
            return "Dark" in str(p[0])

        return self._settings.get("dark_mode", False)

    @dark_mode.setter
    def dark_mode(self, value):
        self._settings["dark_mode"] = value

    @property
    def display_picons(self):
        return self._settings.get("display_picons", True)

    @display_picons.setter
    def display_picons(self, value):
        self._settings["display_picons"] = value

    @property
    def alternate_layout(self):
        return self._settings.get("alternate_layout", IS_DARWIN)

    @alternate_layout.setter
    def alternate_layout(self, value):
        self._settings["alternate_layout"] = value

    @property
    def bq_details_first(self):
        return self._settings.get("bq_details_first", False)

    @bq_details_first.setter
    def bq_details_first(self, value):
        self._settings["bq_details_first"] = value

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
        return f"{HOME_PATH}{SEP}.themes{SEP}"

    @property
    def icon_theme(self):
        return self._settings.get("icon_theme", "Adwaita")

    @icon_theme.setter
    def icon_theme(self, value):
        self._settings["icon_theme"] = value

    @property
    @lru_cache(1)
    def icon_themes_path(self):
        return f"{HOME_PATH}{SEP}.icons{SEP}"

    @property
    def is_darwin(self):
        return IS_DARWIN

    @property
    def force_external_themes(self):
        return self._settings.get("force_external_themes", False)

    @force_external_themes.setter
    def force_external_themes(self, value):
        self._settings["force_external_themes"] = value

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

    # **************** Get-Set settings **************** #

    @staticmethod
    def get_settings():
        if not os.path.isfile(CONFIG_FILE) or os.stat(CONFIG_FILE).st_size == 0:
            Settings.write_settings(Settings.get_default_settings())

        with open(CONFIG_FILE, "r", encoding="utf-8") as config_file:
            try:
                return json.load(config_file)
            except ValueError as e:
                raise SettingsReadException(e)

    @staticmethod
    def get_default_settings(profile_name="default"):
        def_settings = SettingsType.ENIGMA_2.get_default_settings()

        return {
            "version": Settings.__VERSION,
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

    @staticmethod
    def get_default_transcoding_presets():
        return {"720p TV/device": {"vcodec": "h264", "vb": "1500", "width": "1280", "height": "720", "acodec": "mp3",
                                   "ab": "192", "channels": "2", "samplerate": "44100", "scodec": "none"},
                "1080p TV/device": {"vcodec": "h264", "vb": "3500", "width": "1920", "height": "1080", "acodec": "mp3",
                                    "ab": "192", "channels": "2", "samplerate": "44100", "scodec": "none"}}

    @staticmethod
    def write_settings(config):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as config_file:
            json.dump(config, config_file, indent="    ")


if __name__ == "__main__":
    pass

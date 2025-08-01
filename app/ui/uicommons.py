# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2025 Dmitriy Yefremov
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


import locale
import os
from enum import Enum, IntEnum
from functools import lru_cache

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from app.settings import Settings, SettingsException, IS_DARWIN, IS_LINUX, GTK_PATH

# Setting mod mask for keyboard depending on platform
MOD_MASK = Gdk.ModifierType.MOD2_MASK if IS_DARWIN else Gdk.ModifierType.CONTROL_MASK
# Paths.
BASE_PATH = "app/ui/"
EX_PATH = "/usr/share/demoneditor/app/ui/" if IS_LINUX else "ui/"
# Path to *.glade files.
UI_RESOURCES_PATH = BASE_PATH if os.path.exists(BASE_PATH) else EX_PATH
# Translation.
LANG_PATH = UI_RESOURCES_PATH + "lang"
TEXT_DOMAIN = "demon-editor"

NOTIFY_IS_INIT = False
APP_FONT = None

try:
    settings = Settings.get_instance()
except SettingsException:
    pass
else:
    os.environ["LANGUAGE"] = settings.language
    st = Gtk.Settings().get_default()
    APP_FONT = st.get_property("gtk-font-name")
    st.set_property("gtk-application-prefer-dark-theme", settings.dark_mode)

    if settings.is_themes_support:
        st.set_property("gtk-theme-name", settings.theme)
        st.set_property("gtk-icon-theme-name", settings.icon_theme)
    else:
        if not IS_LINUX:
            if IS_DARWIN:
                s_path = f"{GTK_PATH + '/' + UI_RESOURCES_PATH if GTK_PATH else UI_RESOURCES_PATH}mac_style.css"
            else:
                s_path = f"{UI_RESOURCES_PATH}win_style.css"

            style_provider = Gtk.CssProvider()
            style_provider.load_from_path(s_path)
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), style_provider,
                                                     Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

if IS_LINUX:
    if UI_RESOURCES_PATH == BASE_PATH:
        locale.bindtextdomain(TEXT_DOMAIN, LANG_PATH)
    # Init notify
    try:
        gi.require_version("Notify", "0.7")
        from gi.repository import Notify
    except (ImportError, ValueError):
        pass  # NOP
    else:
        NOTIFY_IS_INIT = Notify.init("DemonEditor")
elif IS_DARWIN:
    import gettext

    if GTK_PATH:
        LANG_PATH = GTK_PATH + "/share/locale"
    gettext.bindtextdomain(TEXT_DOMAIN, LANG_PATH)
    # For launching from the bundle.
    if os.getcwd() == "/" and GTK_PATH:
        os.chdir(GTK_PATH)
else:
    locale.setlocale(locale.LC_NUMERIC, "C")

# Icons.
theme = Gtk.IconTheme.get_default()
theme.append_search_path(UI_RESOURCES_PATH + "icons")


def get_icon(name, size, default=None):
    try:
        return theme.load_icon(name, size, 0) if theme.lookup_icon(name, size, 0) else default
    except GLib.Error:
        return default


_IMAGE_MISSING = get_icon("image-missing", 16)
CODED_ICON = get_icon("emblem-readonly", 16, _IMAGE_MISSING)
LOCKED_ICON = get_icon("changes-prevent-symbolic", 16, _IMAGE_MISSING)
HIDE_ICON = get_icon("go-jump", 16, _IMAGE_MISSING)
TV_ICON = get_icon("tv-symbolic", 16, _IMAGE_MISSING)
IPTV_ICON = get_icon("emblem-shared", 16, _IMAGE_MISSING)
LINK_ICON = get_icon("emblem-symbolic-link", 16, _IMAGE_MISSING)
FOLDER_ICON = get_icon("folder-symbolic" if IS_DARWIN else "folder", 16, _IMAGE_MISSING)
EPG_ICON = get_icon("gtk-index", 16, _IMAGE_MISSING)
DEFAULT_ICON = get_icon("emblem-default", 16, get_icon("emblem-default-symbolic", 16, _IMAGE_MISSING))


@lru_cache(maxsize=1)
def get_yt_icon(icon_name, size=24):
    """ Getting  YouTube icon.

        If the icon is not found in the icon themes, the "Info" icon is returned by default!
    """
    default_theme = Gtk.IconTheme.get_default()
    if default_theme.has_icon(icon_name):
        return default_theme.load_icon(icon_name, size, 0)

    n_theme = Gtk.IconTheme.new()
    import glob

    for theme_name in map(os.path.basename, filter(os.path.isdir, glob.glob("/usr/share/icons/*"))):
        n_theme.set_custom_theme(theme_name)
        if n_theme.has_icon(icon_name):
            return n_theme.load_icon(icon_name, size, 0)

    return default_theme.load_icon("emblem-important-symbolic", size, 0)


def show_notification(message, timeout=10000, urgency=1):
    """ Shows notification.

        @param message: text to display
        @param timeout: milliseconds
        @param urgency: 0 - low, 1 - normal, 2 - critical
    """
    if IS_DARWIN:
        # Since NSUserNotification has been deprecated, osascript will be used.
        os.system("""osascript -e 'display notification "{}" with title "DemonEditor"'""".format(message))
    elif NOTIFY_IS_INIT:
        notify = Notify.Notification.new("DemonEditor", message, "demon-editor")
        notify.set_urgency(urgency)
        notify.set_timeout(timeout)
        notify.show()


class HeaderBar(Gtk.HeaderBar):
    """ Custom header bar widget. """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_visible(True)
        self.set_show_close_button(True)

        if IS_DARWIN:
            self.set_decoration_layout("close,minimize,maximize")


class Page(Enum):
    """ Main stack widget page. """
    INFO = "info"
    SERVICES = "services"
    SATELLITE = "satellite"
    PICONS = "picons"
    EPG = "epg"
    TIMERS = "timers"
    RECORDINGS = "recordings"
    FTP = "ftp"
    CONTROL = "control"


class ViewTarget(Enum):
    """ Used for set target view. """
    BOUQUET = 0
    FAV = 1
    SERVICES = 2
    IPTV = 3
    ALT = 4


class BqGenType(Enum):
    """  Bouquet generation type. """
    SAT = 0
    EACH_SAT = 1
    PACKAGE = 2
    EACH_PACKAGE = 3
    TYPE = 4
    EACH_TYPE = 5


class Column(IntEnum):
    """ Column nums in the views """
    # Main view
    SRV_CAS_FLAGS = 0
    SRV_STANDARD = 1
    SRV_CODED = 2
    SRV_SERVICE = 3
    SRV_LOCKED = 4
    SRV_HIDE = 5
    SRV_PACKAGE = 6
    SRV_TYPE = 7
    SRV_PICON = 8
    SRV_PICON_ID = 9
    SRV_SSID = 10
    SRV_FREQ = 11
    SRV_RATE = 12
    SRV_POL = 13
    SRV_FEC = 14
    SRV_SYSTEM = 15
    SRV_POS = 16
    SRV_DATA_ID = 17
    SRV_FAV_ID = 18
    SRV_TRANSPONDER = 19
    SRV_TOOLTIP = 20
    SRV_BACKGROUND = 21
    # FAV view
    FAV_NUM = 0
    FAV_CODED = 1
    FAV_SERVICE = 2
    FAV_LOCKED = 3
    FAV_HIDE = 4
    FAV_TYPE = 5
    FAV_POS = 6
    FAV_ID = 7
    FAV_PICON = 8
    FAV_TOOLTIP = 9
    FAV_BACKGROUND = 10
    # Bouquets view
    BQ_NAME = 0
    BQ_LOCKED = 1
    BQ_HIDDEN = 2
    BQ_TYPE = 3
    # Alternatives view
    ALT_NUM = 0
    ALT_PICON = 1
    ALT_SERVICE = 2
    ALT_TYPE = 3
    ALT_POS = 4
    ALT_FAV_ID = 5
    ALT_ID = 6
    ALT_ITER = 7
    # Recordings view
    REC_SERVICE = 0
    REC_TITLE = 1
    REC_TIME = 2
    REC_LEN = 3
    REC_FILE = 4
    REC_DESC = 5
    # IPTV view
    IPTV_SERVICE = 0
    IPTV_TYPE = 1
    IPTV_PICON = 2
    IPTV_REF = 3
    IPTV_URL = 4
    IPTV_FAV_ID = 5
    IPTV_PICON_ID = 6
    IPTV_TOOLTIP = 7
    # EPG view
    EPG_SERVICE = 0
    EPG_TITLE = 1
    EPG_START = 2
    EPG_END = 3
    EPG_LENGTH = 4
    EPG_DESC = 5
    EPG_DATA = 6

    def __index__(self):
        """ Overridden to get the index in slices directly """
        return self.value


# *************** Keyboard keys *************** #

class BaseKeyboardKey(Enum):
    @classmethod
    def value_exist(cls, value):
        return value in (val.value for val in cls.__members__.values())


if IS_LINUX:
    class KeyboardKey(BaseKeyboardKey):
        """ The raw(hardware) codes [Linux] of the keyboard keys. """
        E = 26
        R = 27
        T = 28
        P = 33
        S = 39
        F = 41
        X = 53
        C = 54
        V = 55
        W = 25
        Z = 52
        INSERT = 118
        HOME = 110
        END = 115
        UP = 111
        DOWN = 116
        PAGE_UP = 112
        PAGE_DOWN = 117
        LEFT = 113
        RIGHT = 114
        F2 = 68
        F4 = 70
        F5 = 71
        F7 = 73
        SPACE = 65
        DELETE = 119
        BACK_SPACE = 22
        RETURN = 36
        CTRL_L = 37
        CTRL_R = 105
        # Laptop codes
        HOME_KP = 79
        END_KP = 87
        PAGE_UP_KP = 81
        PAGE_DOWN_KP = 89

elif IS_DARWIN:
    class KeyboardKey(BaseKeyboardKey):
        """ The raw(hardware) codes [macOS] of the keyboard keys. """
        F = 3
        E = 14
        R = 15
        T = 17
        P = 35
        S = 1
        H = 4
        L = 37
        X = 7
        C = 8
        V = 9
        W = 13
        Z = 6
        INSERT = -1
        HOME = -1
        END = -1
        UP = 126
        DOWN = 125
        PAGE_UP = -1
        PAGE_DOWN = -1
        LEFT = 123
        RIGHT = 123
        F2 = 120
        F4 = 118
        F5 = 96
        F7 = 98
        SPACE = 49
        DELETE = 51
        BACK_SPACE = 76
        RETURN = 36
        CTRL_L = 55
        CTRL_R = 55
        # Laptop codes.
        HOME_KP = -1
        END_KP = -1
        PAGE_UP_KP = -1
        PAGE_DOWN_KP = -1

else:
    class KeyboardKey(BaseKeyboardKey):
        """ The raw(hardware) codes [Windows] of the keyboard keys. """
        E = 69
        R = 82
        T = 84
        P = 80
        S = 83
        F = 70
        X = 88
        C = 67
        V = 86
        W = 87
        Z = 90
        INSERT = 45
        HOME = 36
        END = 35
        UP = 38
        DOWN = 40
        PAGE_UP = 33
        PAGE_DOWN = 34
        LEFT = 37
        RIGHT = 39
        F2 = 113
        F4 = 115
        F5 = 116
        F7 = 118
        SPACE = 32
        DELETE = 46
        BACK_SPACE = 8
        RETURN = 13
        CTRL_L = 17
        CTRL_R = 163
        # Laptop codes.
        HOME_KP = -1
        END_KP = -1
        PAGE_UP_KP = -1
        PAGE_DOWN_KP = -1

# Keys for move in lists. KEY_KP_(NAME) for laptop!
MOVE_KEYS = {KeyboardKey.UP, KeyboardKey.PAGE_UP,
             KeyboardKey.DOWN, KeyboardKey.PAGE_DOWN,
             KeyboardKey.HOME, KeyboardKey.END,
             KeyboardKey.HOME_KP, KeyboardKey.END_KP,
             KeyboardKey.PAGE_UP_KP, KeyboardKey.PAGE_DOWN_KP}

if __name__ == "__main__":
    pass

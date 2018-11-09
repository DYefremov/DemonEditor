import locale
import os

import gi
from enum import Enum

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

# path to *.glade files
UI_RESOURCES_PATH = "app/ui/" if os.path.exists("app/ui/") else "/usr/share/demoneditor/app/ui/"

# translation
TEXT_DOMAIN = "demon-editor"
if UI_RESOURCES_PATH == "app/ui/":
    LANG_DIR = UI_RESOURCES_PATH + "lang"
    locale.bindtextdomain(TEXT_DOMAIN, UI_RESOURCES_PATH + "lang")

theme = Gtk.IconTheme.get_default()
_IMAGE_MISSING = theme.load_icon("image-missing", 16, 0) if theme.lookup_icon("image-missing", 16, 0) else None
CODED_ICON = theme.load_icon("emblem-readonly", 16, 0) if theme.lookup_icon(
    "emblem-readonly", 16, 0) else _IMAGE_MISSING
LOCKED_ICON = theme.load_icon("changes-prevent-symbolic", 16, 0) if theme.lookup_icon(
    "system-lock-screen", 16, 0) else _IMAGE_MISSING
HIDE_ICON = theme.load_icon("go-jump", 16, 0) if theme.lookup_icon("go-jump", 16, 0) else _IMAGE_MISSING
TV_ICON = theme.load_icon("tv-symbolic", 16, 0) if theme.lookup_icon("tv-symbolic", 16, 0) else _IMAGE_MISSING
IPTV_ICON = theme.load_icon("emblem-shared", 16, 0) if theme.load_icon("emblem-shared", 16, 0) else None


class KeyboardKey(Enum):
    """ The raw(hardware) codes of the keyboard keys """
    E = 26
    R = 27
    T = 28
    P = 33
    S = 39
    H = 43
    L = 46
    X = 53
    C = 54
    V = 55
    INSERT = 118
    HOME = 110
    END = 115
    UP = 111
    DOWN = 116
    PAGE_UP = 112
    PAGE_DOWN = 117
    LEFT = 113
    RIGHT = 114
    F2 = 23
    DELETE = 119
    BACK_SPACE = 22
    CTRL_L = 37
    CTRL_R = 105
    # Laptop codes
    HOME_KP = 79
    END_KP = 87
    PAGE_UP_KP = 81
    PAGE_DOWN_KP = 89

    @classmethod
    def value_exist(cls, value):
        return value in (val.value for val in cls.__members__.values())


# Keys for move in lists. KEY_KP_(NAME) for laptop!!!
MOVE_KEYS = (KeyboardKey.UP, KeyboardKey.PAGE_UP, KeyboardKey.DOWN, KeyboardKey.PAGE_DOWN, KeyboardKey.HOME,
             KeyboardKey.END, KeyboardKey.HOME_KP, KeyboardKey.END_KP, KeyboardKey.PAGE_UP_KP, KeyboardKey.PAGE_DOWN_KP)


class ViewTarget(Enum):
    """ Used for set target view """
    BOUQUET = 0
    FAV = 1
    SERVICES = 2


class BqGenType(Enum):
    """  Bouquet generation type """
    SAT = 0
    EACH_SAT = 1
    PACKAGE = 2
    EACH_PACKAGE = 3
    TYPE = 4
    EACH_TYPE = 5


if __name__ == "__main__":
    pass

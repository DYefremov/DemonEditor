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

# Keys for move in lists. KEY_KP_(NAME) for laptop!!!
MOVE_KEYS = (Gdk.KEY_Up, Gdk.KEY_Page_Up, Gdk.KEY_Down, Gdk.KEY_Page_Down, Gdk.KEY_Home, Gdk.KEY_KP_Home, Gdk.KEY_End,
             Gdk.KEY_KP_End, Gdk.KEY_KP_Page_Up, Gdk.KEY_KP_Page_Down)


KEY_MAP = {Gdk.KEY_Cyrillic_es: Gdk.KEY_c, Gdk.KEY_Cyrillic_ES: Gdk.KEY_c,
           Gdk.KEY_Cyrillic_che: Gdk.KEY_x, Gdk.KEY_Cyrillic_CHE: Gdk.KEY_x,
           Gdk.KEY_Cyrillic_em: Gdk.KEY_v, Gdk.KEY_Cyrillic_EM: Gdk.KEY_v,
           Gdk.KEY_Cyrillic_ka: Gdk.KEY_r, Gdk.KEY_Cyrillic_KA: Gdk.KEY_r,
           Gdk.KEY_Cyrillic_u: Gdk.KEY_e, Gdk.KEY_Cyrillic_U: Gdk.KEY_e,
           Gdk.KEY_Cyrillic_de: Gdk.KEY_l, Gdk.KEY_Cyrillic_DE: Gdk.KEY_l,
           Gdk.KEY_Cyrillic_er: Gdk.KEY_h, Gdk.KEY_Cyrillic_ER: Gdk.KEY_h,
           Gdk.KEY_Cyrillic_ze: Gdk.KEY_p, Gdk.KEY_Cyrillic_ZE: Gdk.KEY_p}


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

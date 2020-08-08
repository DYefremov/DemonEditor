import os
from enum import Enum, IntEnum
from functools import lru_cache
from app.settings import Settings, SettingsException, IS_DARWIN

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib

# Setting mod mask for keyboard depending on platform
MOD_MASK = Gdk.ModifierType.MOD2_MASK if IS_DARWIN else Gdk.ModifierType.CONTROL_MASK
# Path to *.glade files
UI_RESOURCES_PATH = "app/ui/" if os.path.exists("app/ui/") else "ui/"
LANG_PATH = UI_RESOURCES_PATH + "lang"
GTK_PATH = os.environ.get("GTK_PATH", None)
NOTIFY_IS_INIT = False
IS_GNOME_SESSION = int(bool(os.environ.get("GNOME_DESKTOP_SESSION_ID")))
# Translation.
TEXT_DOMAIN = "demon-editor"

try:
    settings = Settings.get_instance()
except SettingsException:
    pass
else:
    os.environ["LANGUAGE"] = settings.language
    st = Gtk.Settings().get_default()
    st.set_property("gtk-application-prefer-dark-theme", settings.dark_mode)

    if settings.is_themes_support:
        st.set_property("gtk-theme-name", settings.theme)
        st.set_property("gtk-icon-theme-name", settings.icon_theme)
    else:
        style_provider = Gtk.CssProvider()
        s_path = "{}default_style.css".format(GTK_PATH + "/" + UI_RESOURCES_PATH if GTK_PATH else UI_RESOURCES_PATH)
        style_provider.load_from_path(s_path)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), style_provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

if IS_DARWIN:
    import gettext

    if GTK_PATH:
        LANG_PATH = GTK_PATH + "/share/locale"
    gettext.bindtextdomain(TEXT_DOMAIN, LANG_PATH)
    # For launching from the bundle.
    if os.getcwd() == "/" and GTK_PATH:
        os.chdir(GTK_PATH)
else:
    import locale

    locale.bindtextdomain(TEXT_DOMAIN, LANG_PATH)
    # Init notify
    try:
        gi.require_version("Notify", "0.7")
        from gi.repository import Notify
    except ImportError:
        pass
    else:
        NOTIFY_IS_INIT = Notify.init("DemonEditor")

theme = Gtk.IconTheme.get_default()
theme.append_search_path(GTK_PATH + "/share/icons" if GTK_PATH else UI_RESOURCES_PATH + "icons")


def get_theme_icon(icon_theme, name, size):
    try:
        return icon_theme.load_icon(name, size, 0)
    except GLib.Error:
        pass


_IMAGE_MISSING = get_theme_icon(theme, "image-missing", 16)
CODED_ICON = get_theme_icon(theme, "emblem-readonly", 16) or _IMAGE_MISSING
LOCKED_ICON = get_theme_icon(theme, "changes-prevent-symbolic", 16) or _IMAGE_MISSING
HIDE_ICON = get_theme_icon(theme, "go-jump", 16) or _IMAGE_MISSING
TV_ICON = get_theme_icon(theme, "tv-symbolic", 16) or _IMAGE_MISSING
IPTV_ICON = get_theme_icon(theme, "emblem-shared", 16)
EPG_ICON = get_theme_icon(theme, "gtk-index", 16)
DEFAULT_ICON = get_theme_icon(theme, "emblem-default", 16)


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
        theme.set_custom_theme(theme_name)
        if n_theme.has_icon(icon_name):
            return n_theme.load_icon(icon_name, size, 0)

    if default_theme.lookup_icon(Gtk.STOCK_APPLY, size, 0):
        return default_theme.load_icon(Gtk.STOCK_APPLY, size, 0)


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


class KeyboardKey(Enum):
    """ The raw(hardware) codes of the keyboard keys. """
    F = 3 if IS_DARWIN else 41
    E = 14 if IS_DARWIN else 26
    R = 15 if IS_DARWIN else 27
    T = 17 if IS_DARWIN else 28
    P = 35 if IS_DARWIN else 33
    S = 1 if IS_DARWIN else 39
    H = 4 if IS_DARWIN else 43
    L = 37 if IS_DARWIN else 46
    X = 7 if IS_DARWIN else 53
    C = 8 if IS_DARWIN else 54
    V = 9 if IS_DARWIN else 55
    W = 13 if IS_DARWIN else 25
    Z = 6 if IS_DARWIN else 52
    INSERT = -1 if IS_DARWIN else 118
    HOME = -1 if IS_DARWIN else 110
    END = -1 if IS_DARWIN else 115
    UP = 126 if IS_DARWIN else 111
    DOWN = 125 if IS_DARWIN else 116
    PAGE_UP = -1 if IS_DARWIN else 112
    PAGE_DOWN = -1 if IS_DARWIN else 117
    LEFT = 123 if IS_DARWIN else 113
    RIGHT = 123 if IS_DARWIN else 114
    F2 = 120 if IS_DARWIN else 68
    SPACE = 49 if IS_DARWIN else 65
    DELETE = 51 if IS_DARWIN else 119
    BACK_SPACE = 76 if IS_DARWIN else 22
    CTRL_L = 55 if IS_DARWIN else 37
    CTRL_R = 55 if IS_DARWIN else 105
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


class FavClickMode(IntEnum):
    """ Double click mode on the service in the bouquet(FAV) list. """
    DISABLED = 0
    STREAM = 1
    PLAY = 2
    ZAP = 3
    ZAP_PLAY = 4


class ViewTarget(Enum):
    """ Used for set target view. """
    BOUQUET = 0
    FAV = 1
    SERVICES = 2


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
    # main view
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
    # fav view
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
    # bouquets view
    BQ_NAME = 0
    BQ_LOCKED = 1
    BQ_HIDDEN = 2
    BQ_TYPE = 3

    def __index__(self):
        """ Overridden to get the index in slices directly """
        return self.value


if __name__ == "__main__":
    pass

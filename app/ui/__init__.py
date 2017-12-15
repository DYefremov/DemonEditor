import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

theme = Gtk.IconTheme.get_default()
_IMAGE_MISSING = theme.load_icon("image-missing", 16, 0) if theme.lookup_icon("image-missing", 16, 0) else None
CODED_ICON = theme.load_icon("gtk-dialog-authentication-panel", 16, 0) if theme.lookup_icon(
    "gtk-dialog-authentication-panel", 16, 0) else _IMAGE_MISSING
LOCKED_ICON = theme.load_icon("system-lock-screen", 16, 0) if theme.lookup_icon(
    "system-lock-screen", 16, 0) else _IMAGE_MISSING
HIDE_ICON = theme.load_icon("go-jump", 16, 0) if theme.lookup_icon("go-jump", 16, 0) else _IMAGE_MISSING
TV_ICON = theme.load_icon("tv-symbolic", 16, 0) if theme.lookup_icon("tv-symbolic", 16, 0) else _IMAGE_MISSING

if __name__ == "__main__":
    pass

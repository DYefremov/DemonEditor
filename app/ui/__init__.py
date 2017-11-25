import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

CODED_ICON = Gtk.IconTheme.get_default().load_icon("emblem-readonly", 16, 0)
LOCKED_ICON = Gtk.IconTheme.get_default().load_icon("system-lock-screen", 16, 0)
HIDE_ICON = Gtk.IconTheme.get_default().load_icon("go-jump", 16, 0)
TV_ICON = Gtk.IconTheme.get_default().load_icon("tv-symbolic", 16, 0)

if __name__ == "__main__":
    pass

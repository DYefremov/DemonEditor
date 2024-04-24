# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2023 Dmitriy Yefremov
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

__all__ = ("APP_ID", "APP", "UI_PATH", "Gtk", "Gdk", "Adw", "Gio", "GdkPixbuf", "GLib", "GObject")

import gettext
import locale
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, GdkPixbuf, Adw, GLib, GObject, Gio

from app.settings import Settings, SettingsException, IS_DARWIN, IS_LINUX

APP = "demoneditor"
APP_NAME = "DemonEditor"
APP_ID = f"by.{APP}.{APP_NAME}"
GLib.set_application_name(APP_NAME)

# Paths.
BASE_PATH = "app/ui/"
EX_PATH = f"/usr/share/{APP}/app/ui/" if IS_LINUX else "ui/"
# Path to *.ui files.
UI_PATH = BASE_PATH if os.path.exists(BASE_PATH) else EX_PATH
# Translation.
LOCALE_PATH = f"{UI_PATH}locale"
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
    if not settings.is_themes_support:
        style_provider = Gtk.CssProvider()
        style_provider.load_from_path(f"{UI_PATH}style.css")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), style_provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

if IS_LINUX:
    locale.bindtextdomain(APP, LOCALE_PATH)
elif IS_DARWIN:
    st = Gtk.Settings().get_default()
    st.set_property("gtk-decoration-layout", "close,minimize,maximize")
else:
    locale.setlocale(locale.LC_NUMERIC, "C")

gettext.bindtextdomain(APP, LOCALE_PATH)
gettext.textdomain(APP)
translate = gettext.gettext

if __name__ == "__main__":
    pass

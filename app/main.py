# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2024 Dmitriy Yefremov
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


import sys

from .commons import log, init_logger
from .settings import Settings, IS_DARWIN
from .widgets import ProfileActionRow
from .uicommons import *


@Gtk.Template(filename=f"{UI_PATH}main.ui")
class AppWindow(Adw.ApplicationWindow):
    __gtype_name__ = "AppWindow"

    # Sidebar
    sidebar_header = Gtk.Template.Child()
    add_profile_button = Gtk.Template.Child()
    main_menu_button = Gtk.Template.Child()
    profiles_list = Gtk.Template.Child()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if IS_DARWIN:
            self.sidebar_header.pack_end(self.add_profile_button)
        else:
            self.sidebar_header.pack_start(self.add_profile_button)
            self.sidebar_header.pack_end(self.main_menu_button)

        self.profiles_list.append(ProfileActionRow())


class Application(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
                         **kwargs)
        self.add_main_option("log", ord("l"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "", None)
        self.add_main_option("debug", ord("d"), GLib.OptionFlags.NONE, GLib.OptionArg.STRING, "", None)

        self.settings = Settings.get_instance()
        self.style_manager = Adw.StyleManager().get_default()

        if self.settings.is_themes_support:
            self.style_manager.set_property("gtk-theme-name", self.settings.theme)
            self.style_manager.set_property("gtk-icon-theme-name", self.settings.icon_theme)
        else:
            if self.settings.dark_mode:
                self.style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)

        self.window = None
        self.init_actions()

    def do_activate(self):
        if not self.window:
            self.window = AppWindow(application=self)

        self.window.present()

    def do_command_line(self, command_line):
        """ Processing command line parameters. """
        options = command_line.get_options_dict()
        options = options.end().unpack()

        if "log" in options:
            init_logger()

        if "record" in options:
            log("Starting record of current stream...")
            log("Not implemented yet!")

        if "debug" in options:
            d_op = options.get("debug", "off")
            if d_op == "on":
                self._settings.debug_mode = True
            elif d_op == "off":
                self._settings.debug_mode = False
            else:
                msg = "No valid [on, off] arguments for -d found!"
                log(msg) if "log" in options else print(msg)
                return 1

            log(f"Debug mode is {d_op}.")
            self._settings.save()

        self.activate()
        return 0

    def do_shutdown(self):
        """  Performs shutdown tasks. """
        log("Exiting...")
        Gtk.Application.do_shutdown(self)

    def init_actions(self):
        self.set_action("preferences", self.on_preferences)
        self.set_action("about", self.on_about_app)
        self.set_action("quit", self.on_close_app)

    def set_action(self, name, fun, enabled=True):
        ac = Gio.SimpleAction.new(name, None)
        ac.connect("activate", fun)
        ac.set_enabled(enabled)
        self.add_action(ac)

        return ac

    def on_preferences(self, action, value):
        pass

    def on_about_app(self, action, value):
        pass

    def on_close_app(self, action, value):
        self.quit()


def start_app():
    app = Application()
    app.run(sys.argv)


if __name__ == "__main__":
    pass

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


from enum import Enum
from pyexpat import ExpatError

from gi.repository import GLib

from app.commons import run_idle
from app.connections import DownloadType
from app.eparser import get_satellites, write_satellites, Satellite, Transponder
from app.eparser.satxml import get_terrestrial, get_cable
from .dialogs import SatelliteDialog, TransponderDialog, SatellitesUpdateDialog
from ..dialogs import show_dialog, DialogType, get_chooser_dialog, get_message, get_builder
from ..main_helper import move_items, on_popup_menu
from ..uicommons import Gtk, Gdk, UI_RESOURCES_PATH, MOVE_KEYS, KeyboardKey, MOD_MASK, Page


class SatellitesTool(Gtk.Box):
    """ Class to processing *.xml data. """
    _aggr = [None for x in range(9)]  # aggregate

    class DVB(str, Enum):
        SAT = "satellites"
        TERRESTRIAL = "terrestrial"
        CABLE = "cable"

        def __str__(self):
            return self.value

    def __init__(self, app, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._app = app
        self._app.connect("data-save", self.on_save)
        self._app.connect("data-save-as", self.on_save_as)
        self._app.connect("data-receive", self.on_download)
        self._app.connect("data-send", self.on_upload)

        self._settings = settings
        self._current_sat_path = None
        self._dvb_type = self.DVB.SAT

        handlers = {"on_satellite_view_realize": self.on_satellite_view_realize,
                    "on_terrestrial_view_realize": self.on_terrestrial_view_realize,
                    "on_cable_view_realize": self.on_cable_view_realize,
                    "on_remove": self.on_remove,
                    "on_update": self.on_update,
                    "on_up": self.on_up,
                    "on_down": self.on_down,
                    "on_button_press": self.on_button_press,
                    "on_add": self.on_add,
                    "on_transponder_add": self.on_transponder_add,
                    "on_edit": self.on_edit,
                    "on_key_release": self.on_key_release,
                    "on_visible_page": self.on_visible_page,
                    "on_satellite_selection": self.on_satellite_selection}

        builder = get_builder(f"{UI_RESOURCES_PATH}xml/editor.glade", handlers)

        self._satellite_view = builder.get_object("satellite_view")
        self._terrestrial_view = builder.get_object("terrestrial_view")
        self._cable_view = builder.get_object("cable_view")
        self._sat_tr_view = builder.get_object("sat_tr_view")
        builder.get_object("sat_pos_column").set_cell_data_func(builder.get_object("sat_pos_renderer"),
                                                                self.sat_pos_func)
        self._transponders_stack = builder.get_object("transponders_stack")
        self.pack_start(builder.get_object("main_paned"), True, True, 0)
        self._app.connect("profile-changed", lambda a, m: self.load_satellites_list())
        self.show()

    def on_satellite_view_realize(self, view):
        self.load_satellites_list()

    def on_terrestrial_view_realize(self, view):
        gen = self.on_terrestrial_list_load()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_cable_view_realize(self, view):
        gen = self.on_cable_list_load()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def load_satellites_list(self, path=None):
        gen = self.on_satellites_list_load(path)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_visible_page(self, stack, param):
        self._dvb_type = self.DVB(stack.get_visible_child_name())
        self._transponders_stack.set_visible_child_name(self._dvb_type)

    def on_satellite_selection(self, view):
        model = self._sat_tr_view.get_model()
        model.clear()

        self._current_sat_path, column = view.get_cursor()
        if self._current_sat_path:
            list(map(model.append, view.get_model()[self._current_sat_path][-1]))

    def on_up(self, item):
        move_items(KeyboardKey.UP, self._satellite_view)

    def on_down(self, item):
        move_items(KeyboardKey.DOWN, self._satellite_view)

    def on_button_press(self, menu, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.on_edit(self._satellite_view if self._satellite_view.is_focus() else self._sat_tr_view)
        else:
            on_popup_menu(menu, event)

    def on_key_release(self, view, event):
        """  Handling  keystrokes  """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return
        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK

        if key is KeyboardKey.DELETE:
            self.on_remove(view)
        elif key is KeyboardKey.INSERT:
            pass
        elif ctrl and key is KeyboardKey.E:
            self.on_edit(view)
        elif ctrl and key is KeyboardKey.S:
            self.on_satellite()
        elif ctrl and key is KeyboardKey.T:
            self.on_transponder()
        elif ctrl and key in MOVE_KEYS:
            move_items(key, self._satellite_view)
        elif key is KeyboardKey.LEFT or key is KeyboardKey.RIGHT:
            view.do_unselect_all(view)

    def on_satellites_list_load(self, path=None):
        """ Load satellites data into model """
        path = path or self._settings.profile_data_path + "satellites.xml"
        yield from self.load_data(self._satellite_view, get_satellites, path)

    def on_terrestrial_list_load(self, path=None):
        path = path or self._settings.profile_data_path + "terrestrial.xml"
        yield from self.load_data(self._terrestrial_view, get_terrestrial, path)

    def on_cable_list_load(self, path=None):
        path = path or self._settings.profile_data_path + "cables.xml"
        yield from self.load_data(self._cable_view, get_cable, path)

    def load_data(self, view, func, path):
        model = view.get_model()
        model.clear()

        try:
            data = func(path)
            yield True
        except FileNotFoundError as e:
            msg = get_message("Please, download files from receiver or setup your path for read data!")
            self._app.show_error_message(f"{e}\n{msg}")
        except ExpatError as e:
            msg = f"The file [{path}] is not formatted correctly or contains invalid characters! Cause: {e}"
            self._app.show_error_message(msg)
        else:
            for d in data:
                yield model.append(d)

    def on_add(self, item):
        """ Common adding. """
        if self._dvb_type is self.DVB.SAT:
            self.on_edit(self._satellite_view, force=True)
        else:
            self._app.show_error_message("Not implemented yet!")

    def on_satellite_add(self, item):
        self.on_satellite()

    def on_transponder_add(self, item):
        if self._dvb_type is self.DVB.SAT:
            self.on_transponder()
        else:
            self._app.show_error_message("Not implemented yet!")

    def on_edit(self, view, force=False):
        """ Common edit """
        paths = self.check_selection(view, "Please, select only one item!")
        if not paths:
            return

        model = view.get_model()
        row = model[paths][:]
        itr = model.get_iter(paths)

        if self._dvb_type is self.DVB.SAT:
            if view is self._satellite_view:
                self.on_satellite(None if force else Satellite(*row), itr)
            elif view is self._sat_tr_view:
                self.on_transponder(None if force else Transponder(*row), itr)
        else:
            self._app.show_error_message("Not implemented yet!")

    def on_satellite(self, satellite=None, edited_itr=None):
        """ Create or edit satellite"""
        sat_dialog = SatelliteDialog(self._app.get_active_window(), satellite)
        sat = sat_dialog.run()
        sat_dialog.destroy()

        if sat:
            model, paths = self._satellite_view.get_selection().get_selected_rows()
            if satellite and edited_itr:
                model.set(edited_itr, {i: v for i, v in enumerate(sat)})
            else:
                if len(model):
                    index = paths[0].get_indices()[0] + 1
                    model.insert(index, sat)
                else:
                    model.append(sat)

    def on_transponder(self, transponder=None, edited_itr=None):
        """ Create or edit transponder """

        paths = self.check_selection(self._satellite_view, "Please, select only one satellite!")
        if paths is None:
            return
        elif len(paths) == 0:
            self._app.show_error_message("No satellite is selected!")
            return

        dialog = TransponderDialog(self._app.get_active_window(), transponder)
        tr = dialog.run()
        dialog.destroy()

        if tr:
            sat_model = self._satellite_view.get_model()
            transponders = sat_model[paths][-1]
            tr_model, tr_paths = self._sat_tr_view.get_selection().get_selected_rows()

            if transponder and edited_itr:
                tr_model.set(edited_itr, {i: v for i, v in enumerate(tr)})
                transponders[tr_model.get_path(edited_itr).get_indices()[0]] = tr
            else:
                index = paths[0].get_indices()[0] + 1
                tr_model.insert(index, tr)
                transponders.insert(index, tr)

    def check_selection(self, view, message):
        """ Checks if any row is selected. Shows error dialog if selected more than one.

            Returns selected path or None.
        """
        model, paths = view.get_selection().get_selected_rows()
        if len(paths) > 1:
            self._app.show_error_message(message)
            return

        return paths

    def on_remove(self, view):
        """ Removes selected satellites and transponders. """
        selection = view.get_selection()
        model, paths = selection.get_selected_rows()

        if self._dvb_type is self.DVB.SAT:
            if view is self._satellite_view:
                list(map(model.remove, [model.get_iter(path) for path in paths]))
            elif view is self._sat_tr_view:
                if self._current_sat_path:
                    trs = self._satellite_view.get_model()[self._current_sat_path][-1]
                    list(map(trs.pop, sorted(map(lambda p: p.get_indices()[0], paths), reverse=True)))
                    list(map(model.remove, [model.get_iter(path) for path in paths]))
                else:
                    self._app.show_error_message("No satellite is selected!")
        else:
            self._app.show_error_message("Not implemented yet!")

    def sat_pos_func(self, column, renderer, model, itr, data):
        """ Converts and sets the satellite position value to a readable format. """
        pos = int(model.get_value(itr, 2))
        renderer.set_property("text", f"{abs(pos / 10):0.1f}{'W' if pos < 0 else 'E'}")

    @run_idle
    def on_open(self):
        response = get_chooser_dialog(self._app.app_window, self._settings, "satellites.xml", ("*.xml",))
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        if not str(response).endswith("satellites.xml"):
            self._app.show_error_message("No satellites.xml file is selected!")
            return

        self.load_satellites_list(response)

    @run_idle
    def on_save(self, app, page):
        if page is Page.SATELLITE and show_dialog(DialogType.QUESTION, self._app.app_window) == Gtk.ResponseType.OK:
            if self._dvb_type is self.DVB.SAT:
                write_satellites((Satellite(*r) for r in self._satellite_view.get_model()),
                                 self._settings.profile_data_path + "satellites.xml")
            else:
                self._app.show_error_message("Not implemented yet!")

    def on_save_as(self, app, page):
        show_dialog(DialogType.ERROR, transient=self._app.app_window, text="Not implemented yet!")

    def on_download(self, app, page):
        if page is Page.SATELLITE:
            self._app.on_download_data(DownloadType.SATELLITES)

    def on_upload(self, app, page):
        if page is Page.SATELLITE:
            self._app.upload_data(DownloadType.SATELLITES)

    @run_idle
    def on_update(self, item):
        SatellitesUpdateDialog(self._app.get_active_window(), self._settings, self._satellite_view.get_model()).show()


if __name__ == "__main__":
    pass

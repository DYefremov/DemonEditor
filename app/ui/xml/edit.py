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


from enum import Enum
from pyexpat import ExpatError

from gi.repository import GLib

from app.commons import run_idle
from app.connections import DownloadType
from app.eparser import get_satellites, write_satellites, Satellite, Transponder
from app.eparser.ecommons import (POLARIZATION, FEC, SYSTEM, MODULATION, T_SYSTEM, BANDWIDTH, CONSTELLATION, T_FEC,
                                  GUARD_INTERVAL, TRANSMISSION_MODE, HIERARCHY, Inversion, FEC_DEFAULT, C_MODULATION,
                                  Terrestrial, Cable, CableTransponder, TerTransponder)
from app.eparser.satxml import get_terrestrial, get_cable, write_terrestrial, write_cable, get_pos_str
from .dialogs import (SatelliteDialog, SatellitesUpdateDialog, TerrestrialDialog, CableDialog, SatTransponderDialog,
                      CableTransponderDialog, TerTransponderDialog)
from ..dialogs import show_dialog, DialogType, get_chooser_dialog, translate, get_builder
from ..main_helper import move_items, on_popup_menu, scroll_to
from ..uicommons import Gtk, Gdk, UI_RESOURCES_PATH, MOVE_KEYS, KeyboardKey, MOD_MASK, Page


class SatellitesTool(Gtk.Box):
    """ Class to processing *.xml data. """

    class DVB(str, Enum):
        SAT = "satellites"
        TERRESTRIAL = "terrestrial"
        CABLE = "cable"

        def __str__(self):
            return self.value

    def __init__(self, app, settings, **kwargs):
        super().__init__(**kwargs)

        self._app = app
        self._app.connect("data-save", self.on_save)
        self._app.connect("data-save-as", self.on_save_as)
        self._app.connect("data-receive", self.on_download)
        self._app.connect("data-send", self.on_upload)

        self._settings = settings
        self._current_sat_path = None
        self._current_ter_path = None
        self._current_cable_path = None
        self._dvb_type = self.DVB.SAT

        handlers = {"on_satellite_view_realize": self.on_satellite_view_realize,
                    "on_terrestrial_view_realize": self.on_terrestrial_view_realize,
                    "on_cable_view_realize": self.on_cable_view_realize,
                    "on_update": self.on_update,
                    "on_up": self.on_up,
                    "on_down": self.on_down,
                    "on_button_press": self.on_button_press,
                    "on_tr_button_press": self.on_tr_button_press,
                    "on_add": self.on_add,
                    "on_edit": self.on_edit,
                    "on_remove": self.on_remove,
                    "on_transponder_add": self.on_transponder_add,
                    "on_transponder_edit": self.on_transponder_edit,
                    "on_transponder_remove": self.on_transponder_remove,
                    "on_key_press": self.on_key_press,
                    "on_tr_key_press": self.on_tr_key_press,
                    "on_visible_page": self.on_visible_page,
                    "on_satellite_selection": self.on_satellite_selection,
                    "on_terrestrial_selection": self.on_terrestrial_selection,
                    "on_cable_selection": self.on_cable_selection,
                    "on_sat_model_changed": self.on_sat_model_changed,
                    "on_sat_tr_model_changed": self.on_sat_tr_model_changed,
                    "on_ter_model_changed": self.on_ter_model_changed,
                    "on_ter_tr_model_changed": self.on_ter_tr_model_changed,
                    "on_cable_model_changed": self.on_cable_model_changed,
                    "on_cable_tr_model_changed": self.on_cable_tr_model_changed}

        builder = get_builder(f"{UI_RESOURCES_PATH}xml/editor.glade", handlers)

        self._satellite_view = builder.get_object("satellite_view")
        self._terrestrial_view = builder.get_object("terrestrial_view")
        self._cable_view = builder.get_object("cable_view")
        self._sat_tr_view = builder.get_object("sat_tr_view")
        self._ter_tr_view = builder.get_object("ter_tr_view")
        self._cable_tr_view = builder.get_object("cable_tr_view")

        self._sat_count_label = builder.get_object("sat_count_label")
        self._sat_tr_count_label = builder.get_object("sat_tr_count_label")
        self._ter_count_label = builder.get_object("ter_count_label")
        self._ter_tr_count_label = builder.get_object("ter_tr_count_label")
        self._cable_count_label = builder.get_object("cable_count_label")
        self._cable_tr_count_label = builder.get_object("cable_tr_count_label")

        self._transponders_stack = builder.get_object("transponders_stack")
        self._add_header_button = builder.get_object("add_header_button")
        self._update_header_button = builder.get_object("update_header_button")
        self.pack_start(builder.get_object("main_paned"), True, True, 0)
        self._app.connect("profile-changed", self.on_profile_changed)
        # Custom renderers.
        renderer = builder.get_object("sat_pos_renderer")
        builder.get_object("sat_pos_column").set_cell_data_func(renderer, self.sat_pos_func)
        # Satellite.
        renderer = builder.get_object("sat_pol_renderer")
        builder.get_object("pol_column").set_cell_data_func(renderer, self.sat_pol_func)
        renderer = builder.get_object("sat_fec_renderer")
        builder.get_object("fec_column").set_cell_data_func(renderer, self.sat_fec_func)
        renderer = builder.get_object("sat_sys_renderer")
        builder.get_object("sys_column").set_cell_data_func(renderer, self.sat_sys_func)
        renderer = builder.get_object("sat_mod_renderer")
        builder.get_object("mod_column").set_cell_data_func(renderer, self.sat_mod_func)
        # Terrestrial.
        renderer = builder.get_object("ter_system_renderer")
        builder.get_object("ter_system_column").set_cell_data_func(renderer, self.ter_sys_func)
        renderer = builder.get_object("ter_bandwidth_renderer")
        builder.get_object("ter_bandwidth_column").set_cell_data_func(renderer, self.ter_bandwidth_func)
        renderer = builder.get_object("ter_constellation_renderer")
        builder.get_object("ter_constellation_column").set_cell_data_func(renderer, self.ter_constellation_func)
        renderer = builder.get_object("ter_rate_hp_renderer")
        builder.get_object("ter_rate_hp_column").set_cell_data_func(renderer, self.ter_fec_hp_func)
        renderer = builder.get_object("ter_rate_lp_renderer")
        builder.get_object("ter_rate_lp_column").set_cell_data_func(renderer, self.ter_fec_lp_func)
        renderer = builder.get_object("ter_guard_renderer")
        builder.get_object("ter_guard_column").set_cell_data_func(renderer, self.ter_guard_func)
        renderer = builder.get_object("ter_tr_mode_renderer")
        builder.get_object("ter_tr_mode_column").set_cell_data_func(renderer, self.ter_transmission_func)
        renderer = builder.get_object("ter_hierarchy_renderer")
        builder.get_object("ter_hierarchy_column").set_cell_data_func(renderer, self.ter_hierarchy_func)
        renderer = builder.get_object("ter_inversion_renderer")
        builder.get_object("ter_inversion_column").set_cell_data_func(renderer, self.ter_inversion_func)
        # Cable.
        renderer = builder.get_object("cable_fec_renderer")
        builder.get_object("cable_fec_column").set_cell_data_func(renderer, self.cable_fec_func)
        renderer = builder.get_object("cable_mod_renderer")
        builder.get_object("cable_mod_column").set_cell_data_func(renderer, self.cable_mod_func)

        self.show()

    # ******************** Custom renderers ******************** #

    def sat_pos_func(self, column, renderer, model, itr, data):
        """ Converts and sets the satellite position value to a readable format. """
        renderer.set_property("text", get_pos_str(int(model.get_value(itr, 2))))

    def sat_pol_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", POLARIZATION.get(model.get_value(itr, 2), None))

    def sat_fec_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", FEC.get(model.get_value(itr, 3), None))

    def sat_sys_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", SYSTEM.get(model.get_value(itr, 4), None))

    def sat_mod_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", MODULATION.get(model.get_value(itr, 5), None))

    def ter_sys_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", T_SYSTEM.get(model.get_value(itr, 1), None))

    def ter_bandwidth_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", BANDWIDTH.get(model.get_value(itr, 2), None))

    def ter_constellation_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", CONSTELLATION.get(model.get_value(itr, 3), None))

    def ter_fec_hp_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", T_FEC.get(model.get_value(itr, 4), None))

    def ter_fec_lp_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", T_FEC.get(model.get_value(itr, 5), None))

    def ter_guard_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", GUARD_INTERVAL.get(model.get_value(itr, 6), None))

    def ter_transmission_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", TRANSMISSION_MODE.get(model.get_value(itr, 7), None))

    def ter_hierarchy_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", HIERARCHY.get(model.get_value(itr, 8), None))

    def ter_inversion_func(self, column, renderer, model, itr, data):
        value = model.get_value(itr, 9)
        if value:
            value = Inversion(value).name
        renderer.set_property("text", value)

    def cable_fec_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", FEC_DEFAULT.get(model.get_value(itr, 2), None))

    def cable_mod_func(self, column, renderer, model, itr, data):
        renderer.set_property("text", C_MODULATION.get(model.get_value(itr, 3), None))

    def on_satellite_view_realize(self, view):
        self.load_satellites_list()

    def on_terrestrial_view_realize(self, view):
        self.load_terrestrial_list()

    def on_cable_view_realize(self, view):
        self.load_cable_list()

    def load_satellites_list(self, path=None):
        gen = self.on_satellites_list_load(path)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def load_terrestrial_list(self, path=None):
        gen = self.on_terrestrial_list_load(path)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def load_cable_list(self, path=None):
        gen = self.on_cable_list_load(path)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_visible_page(self, stack, param):
        self._dvb_type = self.DVB(stack.get_visible_child_name())
        self._transponders_stack.set_visible_child_name(self._dvb_type)
        self._update_header_button.set_sensitive(self._dvb_type is self.DVB.SAT)

        if self._dvb_type is self.DVB.SAT:
            self._app.on_info_bar_close()

        else:
            self._app.show_info_message("EXPERIMENTAL!", Gtk.MessageType.WARNING)

    def on_satellite_selection(self, view):
        model = self._sat_tr_view.get_model()
        model.clear()

        self._current_sat_path, column = view.get_cursor()
        if self._current_sat_path:
            sat_model = view.get_model()
            list(map(model.append, sat_model[self._current_sat_path][-1]))

    def on_terrestrial_selection(self, view):
        model = self._ter_tr_view.get_model()
        model.clear()

        self._current_ter_path, column = view.get_cursor()
        if self._current_ter_path:
            ter_model = view.get_model()
            list(map(model.append, ter_model[self._current_ter_path][-1]))

    def on_cable_selection(self, view):
        model = self._cable_tr_view.get_model()
        model.clear()

        self._current_cable_path, column = view.get_cursor()
        if self._current_cable_path:
            cable_model = view.get_model()
            list(map(model.append, cable_model[self._current_cable_path][-1]))

    def on_sat_model_changed(self, model, path, itr=None):
        self._sat_count_label.set_text(str(len(model)))

    def on_sat_tr_model_changed(self, model, path, itr=None):
        self._sat_tr_count_label.set_text(str(len(model)))

    def on_ter_model_changed(self, model, path, itr=None):
        self._ter_count_label.set_text(str(len(model)))

    def on_ter_tr_model_changed(self, model, path, itr=None):
        self._ter_tr_count_label.set_text(str(len(model)))

    def on_cable_model_changed(self, model, path, itr=None):
        self._cable_count_label.set_text(str(len(model)))

    def on_cable_tr_model_changed(self, model, path, itr=None):
        self._cable_tr_count_label.set_text(str(len(model)))

    def on_up(self, item):
        move_items(KeyboardKey.UP, self._satellite_view)

    def on_down(self, item):
        move_items(KeyboardKey.DOWN, self._satellite_view)

    def on_button_press(self, menu, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.on_edit()
        else:
            on_popup_menu(menu, event)

    def on_tr_button_press(self, menu, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.on_transponder_edit()
        else:
            on_popup_menu(menu, event)

    def on_key_press(self, view, event):
        """ Handling  keystrokes. """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK

        if key is KeyboardKey.DELETE:
            self.on_remove(view)
        elif key is KeyboardKey.INSERT:
            self.on_edit(force=True)
        elif ctrl and key is KeyboardKey.E:
            self.on_edit()
        elif ctrl and key in MOVE_KEYS:
            move_items(key, view)
        elif key is KeyboardKey.LEFT or key is KeyboardKey.RIGHT:
            view.do_unselect_all(view)

    def on_tr_key_press(self, view, event):
        """ Handling  transponder view keystrokes. """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK

        if key is KeyboardKey.DELETE:
            self.on_transponder_remove()
        elif key is KeyboardKey.INSERT:
            self.on_transponder_edit(force=True)
        elif ctrl and key is KeyboardKey.E:
            self.on_transponder_edit()
        elif ctrl and key in MOVE_KEYS:
            move_items(key, view)
        elif key is KeyboardKey.LEFT or key is KeyboardKey.RIGHT:
            view.do_unselect_all(view)

    def on_satellites_list_load(self, path=None):
        """ Load satellites data into model """
        path = path or f"{self._settings.profile_data_path}satellites.xml"
        yield from self.load_data(self._satellite_view, get_satellites, path)

    def on_terrestrial_list_load(self, path=None):
        path = path or f"{self._settings.profile_data_path}terrestrial.xml"
        yield from self.load_data(self._terrestrial_view, get_terrestrial, path)

    def on_cable_list_load(self, path=None):
        path = path or f"{self._settings.profile_data_path}cables.xml"
        yield from self.load_data(self._cable_view, get_cable, path)

    def load_data(self, view, func, path):
        model = view.get_model()
        model.clear()

        try:
            data = func(path)
            yield True
        except FileNotFoundError as e:
            msg = translate("Please, download files from receiver or setup your path for read data!")
            self._app.show_error_message(f"{e}\n{msg}")
        except ExpatError as e:
            msg = f"The file [{path}] is not formatted correctly or contains invalid characters! Cause: {e}"
            self._app.show_error_message(msg)
        else:
            for d in data:
                yield model.append(d)

    def on_add(self, item):
        """ Common adding. """
        self.on_edit(item, force=True)

    def on_transponder_add(self, item):
        self.on_transponder_edit(force=True)

    def on_edit(self, item=None, force=False):
        self.on_data_edit(self.get_active_dvb_view(), force)

    def on_transponder_edit(self, item=None, force=False):
        self.on_data_edit(self.get_active_transponder_view(), force)

    def on_data_edit(self, view, force=False):
        """ Common edit. """
        if force:
            model, paths = view.get_selection().get_selected_rows()
        else:
            paths = self.check_selection(view, "Please, select only one item!")
            if not paths:
                return

        model = view.get_model()
        row = model[paths][:] if paths else None
        itr = model.get_iter(paths) if paths else None

        if view is self._satellite_view:
            self.on_dvb_data_edit(SatelliteDialog, "Satellite", view, None if force else Satellite(*row), itr)
        elif view is self._terrestrial_view:
            self.on_dvb_data_edit(TerrestrialDialog, "Region", view, None if force else Terrestrial(*row), itr)
        elif view is self._cable_view:
            self.on_dvb_data_edit(CableDialog, "Provider", view, None if force else Cable(*row), itr)
        elif view is self._sat_tr_view:
            data = None if force else Transponder(*row)
            self.on_transponder_data_edit(SatTransponderDialog, "Transponder", view, self._satellite_view, data, itr)
        elif view is self._ter_tr_view:
            data = None if force else TerTransponder(*row)
            self.on_transponder_data_edit(TerTransponderDialog, "Transponder", view, self._terrestrial_view, data, itr)
        elif view is self._cable_tr_view:
            data = None if force else CableTransponder(*row)
            self.on_transponder_data_edit(CableTransponderDialog, "Transponder", view, self._cable_view, data, itr)
        else:
            self._app.show_error_message("Not implemented yet!")

    def on_dvb_data_edit(self, dialog, title, view, data=None, edited_itr=None):
        """ Creates or edits DVB data. """
        dialog = dialog(self._app.get_active_window(), title, data)
        if dialog.run() == Gtk.ResponseType.OK:
            dvb_data = dialog.data
            if dvb_data:
                model, paths = view.get_selection().get_selected_rows()
                if data and edited_itr:
                    model.set(edited_itr, {i: v for i, v in enumerate(dvb_data)})
                else:
                    if paths:
                        index = paths[0].get_indices()[0] + 1
                        model.insert(index, dvb_data)
                    else:
                        model.append(dvb_data)
                        scroll_to(len(model) - 1, view)
        dialog.destroy()

    def on_transponder_data_edit(self, dialog, title, view, src_view, data=None, edited_itr=None):
        """ Creates or edits transponder data. """
        paths = self.check_selection(src_view, "Please, select only one item!")
        if paths is None:
            return
        elif len(paths) == 0:
            self._app.show_error_message("No source selected!")
            return

        dialog = dialog(self._app.app_window, title, data)
        if dialog.run() == Gtk.ResponseType.OK:
            tr = dialog.data
            if tr:
                src_model = src_view.get_model()
                transponders = src_model[paths][-1]
                tr_model, tr_paths = view.get_selection().get_selected_rows()

                if data and edited_itr:
                    tr_model.set(edited_itr, {i: v for i, v in enumerate(tr)})
                    transponders[tr_model.get_path(edited_itr).get_indices()[0]] = tr
                else:
                    index = paths[0].get_indices()[0] + 1
                    tr_model.insert(index, tr)
                    transponders.insert(index, tr)
        dialog.destroy()

    def check_selection(self, view, message):
        """ Checks if any row is selected. Shows error dialog if selected more than one.

            Returns selected path or None.
        """
        model, paths = view.get_selection().get_selected_rows()
        if len(paths) > 1:
            self._app.show_error_message(message)
            return

        return paths

    def on_remove(self, view=None):
        """ Removes selected satellites and transponders. """
        view = self.get_active_dvb_view()
        selection = view.get_selection()
        model, paths = selection.get_selected_rows()
        list(map(model.remove, [model.get_iter(path) for path in paths]))

    def on_transponder_remove(self, item=None):
        view = self.get_active_transponder_view()
        trs = None
        if view is self._sat_tr_view:
            if self._current_sat_path:
                trs = self._satellite_view.get_model()[self._current_sat_path][-1]
            else:
                self._app.show_error_message("No satellite is selected!")
        elif view is self._ter_tr_view:
            if self._current_ter_path:
                trs = self._terrestrial_view.get_model()[self._current_ter_path][-1]
            else:
                self._app.show_error_message("No terrestrial is selected!")
        elif view is self._cable_tr_view:
            if self._current_cable_path:
                trs = self._cable_view.get_model()[self._current_cable_path][-1]
            else:
                self._app.show_error_message("No cable is selected!")

        if trs:
            model, paths = view.get_selection().get_selected_rows()
            list(map(trs.pop, sorted(map(lambda p: p.get_indices()[0], paths), reverse=True)))
            list(map(model.remove, [model.get_iter(path) for path in paths]))

    def get_active_dvb_view(self):
        if self._dvb_type is self.DVB.SAT:
            return self._satellite_view
        elif self._dvb_type is self.DVB.TERRESTRIAL:
            return self._terrestrial_view
        return self._cable_view

    def get_active_transponder_view(self):
        if self._dvb_type is self.DVB.SAT:
            return self._sat_tr_view
        elif self._dvb_type is self.DVB.TERRESTRIAL:
            return self._ter_tr_view
        return self._cable_tr_view

    @run_idle
    def on_open(self):
        xml_file = "satellites.xml"
        if self._dvb_type is self.DVB.TERRESTRIAL:
            xml_file = "terrestrial.xml"
        elif self._dvb_type is self.DVB.CABLE:
            xml_file = "cables.xml"

        response = get_chooser_dialog(self._app.app_window, self._settings, xml_file, ("*.xml",))
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        if not str(response).endswith(xml_file):
            self._app.show_error_message(f"No {xml_file} file is selected!")
            return

        if self._dvb_type is self.DVB.SAT:
            self.load_satellites_list(response)
        elif self._dvb_type is self.DVB.TERRESTRIAL:
            self.load_terrestrial_list(response)
        else:
            self.load_cable_list(response)

    @run_idle
    def on_profile_changed(self, app, profile):
        self.load_satellites_list()
        self.load_terrestrial_list()
        self.load_cable_list()

    @run_idle
    def on_save(self, app, page):
        if page is Page.SATELLITE and show_dialog(DialogType.QUESTION, self._app.app_window) == Gtk.ResponseType.OK:
            if self._dvb_type is self.DVB.SAT:
                write_satellites((Satellite(*r) for r in self._satellite_view.get_model()),
                                 f"{self._settings.profile_data_path}satellites.xml")
            elif self._dvb_type is self.DVB.TERRESTRIAL:
                write_terrestrial((Terrestrial(*r) for r in self._terrestrial_view.get_model()),
                                  f"{self._settings.profile_data_path}terrestrial.xml")
            else:
                write_cable((Cable(*r) for r in self._cable_view.get_model()),
                            f"{self._settings.profile_data_path}cables.xml")

    def on_save_as(self, app, page):
        self._app.show_error_message("Not implemented yet!")

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

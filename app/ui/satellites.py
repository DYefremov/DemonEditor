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


import concurrent.futures
import re
import time
from math import fabs
from pyexpat import ExpatError

from gi.repository import GLib

from app.commons import run_idle, run_task, log
from app.eparser import get_satellites, write_satellites, Satellite, Transponder
from app.eparser.ecommons import PLS_MODE, get_key_by_value
from app.tools.satellites import SatellitesParser, SatelliteSource, ServicesParser
from .dialogs import show_dialog, DialogType, get_chooser_dialog, get_message, get_builder
from .main_helper import move_items, append_text_to_tview, get_base_model, on_popup_menu
from .search import SearchProvider
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, MOVE_KEYS, KeyboardKey, MOD_MASK

_UI_PATH = UI_RESOURCES_PATH + "satellites.glade"


class SatellitesTool(Gtk.Box):
    _aggr = [None for x in range(9)]  # aggregate

    def __init__(self, app, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._app = app
        self._settings = settings
        self._current_sat_path = None

        handlers = {"on_remove": self.on_remove,
                    "on_update": self.on_update,
                    "on_up": self.on_up,
                    "on_down": self.on_down,
                    "on_button_press": self.on_button_press,
                    "on_satellite_add": self.on_satellite_add,
                    "on_transponder_add": self.on_transponder_add,
                    "on_edit": self.on_edit,
                    "on_key_release": self.on_key_release,
                    "on_satellite_selection": self.on_satellite_selection}

        builder = get_builder(_UI_PATH, handlers, use_str=True,
                              objects=("satellite_editor_box", "satellite_view_model", "transponder_view_model",
                                       "satellite_popup_menu", "transponder_popup_menu", "left_header_menu",
                                       "popup_menu_add_image", "popup_menu_add_image_2"))

        self._satellite_view = builder.get_object("satellite_view")
        self._transponder_view = builder.get_object("transponder_view")
        builder.get_object("sat_pos_column").set_cell_data_func(builder.get_object("sat_pos_renderer"),
                                                                self.sat_pos_func)

        self._stores = {3: builder.get_object("pol_store"),
                        4: builder.get_object("fec_store"),
                        5: builder.get_object("system_store"),
                        6: builder.get_object("mod_store")}

        self.pack_start(builder.get_object("satellite_editor_box"), True, True, 0)
        self._app.connect("profile-changed", lambda a, m: self.load_satellites_list())
        self.show()
        self.load_satellites_list()

    def load_satellites_list(self, path=None):
        gen = self.on_satellites_list_load(path)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    @run_idle
    def on_open(self):
        response = get_chooser_dialog(self._app.app_window, self._settings, "satellites.xml", ("*.xml",))
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        if not str(response).endswith("satellites.xml"):
            self._app.show_error_message("No satellites.xml file is selected!")
            return

        self.load_satellites_list(response)

    def on_satellite_selection(self, view):
        model = self._transponder_view.get_model()
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
            self.on_edit(self._satellite_view if self._satellite_view.is_focus() else self._transponder_view)
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
        model = self._satellite_view.get_model()
        model.clear()

        try:
            path = path or self._settings.profile_data_path + "satellites.xml"
            satellites = get_satellites(path)
            yield True
        except FileNotFoundError as e:
            msg = get_message("Please, download files from receiver or setup your path for read data!")
            self._app.show_error_message(f"{e}\n{msg}")
        except ExpatError as e:
            msg = f"The file [{path}] is not formatted correctly or contains invalid characters! Cause: {e}"
            self._app.show_error_message(msg)
        else:
            for sat in satellites:
                yield model.append(sat)

    def on_add(self, view):
        """ Common adding """
        self.on_edit(view, force=True)

    def on_satellite_add(self, item):
        self.on_satellite()

    def on_transponder_add(self, item):
        self.on_transponder()

    def on_edit(self, view, force=False):
        """ Common edit """
        paths = self.check_selection(view, "Please, select only one item!")
        if not paths:
            return

        model = view.get_model()
        row = model[paths][:]
        itr = model.get_iter(paths)

        if view is self._satellite_view:
            self.on_satellite(None if force else Satellite(*row), itr)
        elif view is self._transponder_view:
            self.on_transponder(None if force else Transponder(*row), itr)

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
            tr_model, tr_paths = self._transponder_view.get_selection().get_selected_rows()

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

        if view is self._satellite_view:
            list(map(model.remove, [model.get_iter(path) for path in paths]))
        elif view is self._transponder_view:
            if self._current_sat_path:
                trs = self._satellite_view.get_model()[self._current_sat_path][-1]
                list(map(trs.pop, sorted(map(lambda p: p.get_indices()[0], paths), reverse=True)))
                list(map(model.remove, [model.get_iter(path) for path in paths]))
            else:
                self._app.show_error_message("No satellite is selected!")

    def sat_pos_func(self, column, renderer, model, itr, data):
        """ Converts and sets the satellite position value to a readable format. """
        pos = int(model.get_value(itr, 2))
        renderer.set_property("text", f"{abs(pos / 10):0.1f}{'W' if pos < 0 else 'E'}")

    @run_idle
    def on_save(self):
        if show_dialog(DialogType.QUESTION, self._app.app_window) == Gtk.ResponseType.CANCEL:
            return

        write_satellites((Satellite(*r) for r in self._satellite_view.get_model()),
                         self._settings.profile_data_path + "satellites.xml")

    def on_save_as(self):
        show_dialog(DialogType.ERROR, transient=self._app.app_window, text="Not implemented yet!")

    @run_idle
    def on_update(self, item):
        SatellitesUpdateDialog(self._app.get_active_window(), self._settings, self._satellite_view.get_model()).show()


# ***************** Transponder dialog *******************#

class TransponderDialog:
    """ Shows dialog for adding or edit transponder """

    def __init__(self, transient, transponder: Transponder = None):

        handlers = {"on_entry_changed": self.on_entry_changed}
        objects = ("transponder_dialog", "pol_store", "fec_store", "mod_store", "system_store", "pls_mode_store")
        builder = get_builder(_UI_PATH, handlers, use_str=True, objects=objects)

        self._dialog = builder.get_object("transponder_dialog")
        self._dialog.set_transient_for(transient)
        self._freq_entry = builder.get_object("freq_entry")
        self._rate_entry = builder.get_object("rate_entry")
        self._pol_box = builder.get_object("pol_box")
        self._fec_box = builder.get_object("fec_box")
        self._sys_box = builder.get_object("sys_box")
        self._mod_box = builder.get_object("mod_box")
        self._pls_mode_box = builder.get_object("pls_mode_box")
        self._pls_code_entry = builder.get_object("pls_code_entry")
        self._is_id_entry = builder.get_object("is_id_entry")
        self._t2mi_plp_id_entry = builder.get_object("t2mi_plp_id_entry")
        # pattern for frequency and rate entries (only digits)
        self._pattern = re.compile(r"\D")
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._freq_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                                     Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._rate_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                                     Gtk.STYLE_PROVIDER_PRIORITY_USER)
        if transponder:
            self.init_transponder(transponder)

    def run(self):
        while self._dialog.run() != Gtk.ResponseType.CANCEL:
            tr = self.to_transponder()
            if self.is_accept(tr):
                return tr
            show_dialog(DialogType.ERROR, self._dialog, "Please check your parameters and try again.")

    def destroy(self):
        self._dialog.destroy()

    def init_transponder(self, transponder):
        self._freq_entry.set_text(transponder.frequency)
        self._rate_entry.set_text(transponder.symbol_rate)
        self._pol_box.set_active_id(transponder.polarization)
        self._fec_box.set_active_id(transponder.fec_inner)
        self._sys_box.set_active_id(transponder.system)
        self._mod_box.set_active_id(transponder.modulation)
        self._pls_mode_box.set_active_id(PLS_MODE.get(transponder.pls_mode, None))
        self._is_id_entry.set_text(transponder.is_id if transponder.is_id else "")
        self._pls_code_entry.set_text(transponder.pls_code if transponder.pls_code else "")
        self._t2mi_plp_id_entry.set_text(transponder.t2mi_plp_id if transponder.t2mi_plp_id else "")

    def to_transponder(self):
        return Transponder(frequency=self._freq_entry.get_text(),
                           symbol_rate=self._rate_entry.get_text(),
                           polarization=self._pol_box.get_active_id(),
                           fec_inner=self._fec_box.get_active_id(),
                           system=self._sys_box.get_active_id(),
                           modulation=self._mod_box.get_active_id(),
                           pls_mode=get_key_by_value(PLS_MODE, self._pls_mode_box.get_active_id()),
                           pls_code=self._pls_code_entry.get_text(),
                           is_id=self._is_id_entry.get_text(),
                           t2mi_plp_id=self._t2mi_plp_id_entry.get_text())

    def on_entry_changed(self, entry):
        entry.set_name("digit-entry" if self._pattern.search(entry.get_text()) else "GtkEntry")

    def is_accept(self, tr):
        if self._pattern.search(tr.frequency) or not tr.frequency:
            return False
        elif self._pattern.search(tr.symbol_rate) or not tr.symbol_rate:
            return False
        elif None in (tr.polarization, tr.fec_inner, tr.system, tr.modulation):
            return False
        elif self._pattern.search(tr.pls_code) or self._pattern.search(tr.is_id):
            return False
        elif self._pattern.search(tr.t2mi_plp_id):
            return False

        return True


# ***************** Satellite dialog *******************#

class SatelliteDialog:
    """ Shows dialog for adding or edit satellite """

    def __init__(self, transient, satellite=None):
        builder = get_builder(_UI_PATH, use_str=True, objects=("satellite_dialog", "side_store", "pos_adjustment"))

        self._dialog = builder.get_object("satellite_dialog")
        self._dialog.set_transient_for(transient)
        self._sat_name = builder.get_object("sat_name_entry")
        self._sat_position = builder.get_object("sat_position_button")
        self._side = builder.get_object("side_box")
        self._transponders = satellite.transponders if satellite else []

        if satellite:
            self._sat_name.set_text(satellite.name)
            pos = satellite.position
            pos = float(f"{pos[:-1]}.{pos[-1:]}")
            self._sat_position.set_value(fabs(pos))
            self._side.set_active(0 if pos >= 0 else 1)  # E or W

    def run(self):
        if self._dialog.run() == Gtk.ResponseType.CANCEL:
            return

        return self.to_satellite()

    def destroy(self):
        self._dialog.destroy()

    def to_satellite(self):
        name = self._sat_name.get_text()
        pos = round(self._sat_position.get_value(), 1)
        side = self._side.get_active()
        pos = "{}{}{}".format("-" if side == 1 else "", *str(pos).split("."))

        return Satellite(name=name, flags="0", position=pos, transponders=self._transponders)


# ********************** Update dialogs ************************ #

class UpdateDialog:
    """ Base dialog for update satellites, transponders and services from the web."""

    def __init__(self, transient, settings, title=None):
        handlers = {"on_update_satellites_list": self.on_update_satellites_list,
                    "on_receive_data": self.on_receive_data,
                    "on_cancel_receive": self.on_cancel_receive,
                    "on_satellite_toggled": self.on_satellite_toggled,
                    "on_satellite_changed": self.on_satellite_changed,
                    "on_transponder_toggled": self.on_transponder_toggled,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_find_toggled": self.on_find_toggled,
                    "on_popup_menu": on_popup_menu,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_filter": self.on_filter,
                    "on_quit": self.on_quit}

        self._settings = settings
        self._download_task = False
        self._parser = None
        self._size_name = f"{'_'.join(re.findall('[A-Z][^A-Z]*', self.__class__.__name__))}_window_size".lower()

        builder = get_builder(UI_RESOURCES_PATH + "satellites.glade", handlers,
                              objects=("satellites_update_window", "update_source_store", "update_sat_list_store",
                                       "update_sat_list_model_filter", "update_sat_list_model_sort", "side_store",
                                       "pos_adjustment", "pos_adjustment2", "satellites_update_popup_menu",
                                       "remove_selection_image", "sat_update_cancel_image", "sat_receive_image",
                                       "sat_update_image", "update_transponder_store", "update_service_store"))

        self._window = builder.get_object("satellites_update_window")
        self._window.set_transient_for(transient)
        if title:
            self._window.set_title(title)

        self._transponder_paned = builder.get_object("sat_update_tr_paned")
        self._sat_view = builder.get_object("sat_update_tree_view")
        self._transponder_view = builder.get_object("sat_update_tr_view")
        self._service_view = builder.get_object("sat_update_srv_view")
        self._source_box = builder.get_object("source_combo_box")
        self._text_view = builder.get_object("text_view")
        self._receive_button = builder.get_object("receive_data_button")
        self._sat_update_info_bar = builder.get_object("sat_update_info_bar")
        self._info_bar_message_label = builder.get_object("info_bar_message_label")
        self._satellites_count_label = builder.get_object("satellites_count_label")
        self._transponders_count_label = builder.get_object("transponders_count_label")
        self._services_count_label = builder.get_object("services_count_label")
        self._receive_button.bind_property("visible", builder.get_object("cancel_data_button"), "visible", 4)
        update_button = builder.get_object("sat_update_button")
        self._sat_view.bind_property("sensitive", update_button, "sensitive")
        self._sat_view.bind_property("sensitive", self._source_box, "sensitive")
        self._sat_view.bind_property("sensitive", self._source_box, "sensitive")
        self._sat_view.bind_property("sensitive", self._receive_button, "sensitive")
        self._receive_button.bind_property("visible", update_button, "visible")
        # Filter
        self._filter_bar = builder.get_object("sat_update_filter_bar")
        self._from_pos_button = builder.get_object("from_pos_button")
        self._to_pos_button = builder.get_object("to_pos_button")
        self._filter_from_combo_box = builder.get_object("filter_from_combo_box")
        self._filter_to_combo_box = builder.get_object("filter_to_combo_box")
        self._filter_model = builder.get_object("update_sat_list_model_filter")
        self._filter_model.set_visible_func(self.filter_function)
        self._filter_positions = (0, 0)
        self._filter_bar.bind_property("search-mode-enabled", self._filter_bar, "visible")
        # Log.
        self._log_frame = builder.get_object("log_frame")
        builder.get_object("log_info_bar").connect("response", lambda b, r: self._log_frame.set_visible(False))
        # Search.
        self._search_bar = builder.get_object("sat_update_search_bar")
        self._search_bar.bind_property("search-mode-enabled", self._search_bar, "visible")
        search_provider = SearchProvider(self._sat_view,
                                         builder.get_object("sat_update_search_entry"),
                                         builder.get_object("sat_update_search_down_button"),
                                         builder.get_object("sat_update_search_up_button"))
        builder.get_object("sat_update_find_button").connect("toggled", search_provider.on_search_toggled)

        window_size = self._settings.get(self._size_name)
        if window_size:
            self._window.resize(*window_size)

    def show(self):
        self._window.show()

    @property
    def is_download(self):
        return self._download_task

    @is_download.setter
    def is_download(self, value):
        self._download_task = value
        self._receive_button.set_visible(not value)

    @run_idle
    def on_update_satellites_list(self, item=None):
        if self.is_download:
            show_dialog(DialogType.ERROR, self._window, "The task is already running!")
            return

        self.clear_data()

        self.is_download = True
        self._sat_view.set_sensitive(False)
        src = self._source_box.get_active()
        if not self._parser:
            self._parser = SatellitesParser()

        self.get_sat_list(src, self.append_satellites)

    def clear_data(self):
        get_base_model(self._sat_view.get_model()).clear()
        self._transponder_view.get_model().clear()
        self._service_view.get_model().clear()
        self._satellites_count_label.set_text("0")
        self._transponders_count_label.set_text("0")
        self._services_count_label.set_text("0")

    @run_task
    def get_sat_list(self, src, callback):
        sat_src = SatelliteSource.LYNGSAT
        if src == 1:
            sat_src = SatelliteSource.KINGOFSAT
        elif src == 2:
            sat_src = SatelliteSource.FLYSAT

        sats = self._parser.get_satellites_list(sat_src)
        callback(sats)
        self.is_download = False

    @run_idle
    def append_satellites(self, sats):
        model = get_base_model(self._sat_view.get_model())
        for sat in sats:
            model.append(sat)

        self._sat_view.set_sensitive(True)
        self._satellites_count_label.set_text(str(len(model)))

    @run_idle
    def on_receive_data(self, item):
        if self.is_download:
            show_dialog(DialogType.ERROR, self._window, "The task is already running!")
            return

    @run_idle
    def update_log_visibility(self):
        self._log_frame.set_visible(True)
        self._text_view.get_buffer().set_text("", 0)

    def append_output(self):
        @run_idle
        def append(t):
            append_text_to_tview(t, self._text_view)

        while True:
            text = yield
            append(text)

    def on_cancel_receive(self, item=None):
        self._download_task = False

    def on_satellite_changed(self, box):
        self.on_update_satellites_list()

    def on_satellite_toggled(self, toggle, path):
        model = self._sat_view.get_model()
        self.update_state(model, path, not toggle.get_active())
        self.update_receive_button_state(self._filter_model)

    def on_transponder_toggled(self, toggle, path):
        model = self._transponder_view.get_model()
        model.set_value(model.get_iter(path), 2, not toggle.get_active())

    @run_idle
    def update_receive_button_state(self, model):
        self._receive_button.set_sensitive((any(r[4] for r in model)))

    @run_idle
    def show_info_message(self, text, message_type):
        self._sat_update_info_bar.set_visible(True)
        self._sat_update_info_bar.set_message_type(message_type)
        self._info_bar_message_label.set_text(text)

    def on_info_bar_close(self, bar=None, resp=None):
        self._sat_update_info_bar.set_visible(False)

    def on_find_toggled(self, button: Gtk.ToggleToolButton):
        self._search_bar.set_search_mode(button.get_active())

    def on_filter_toggled(self, button: Gtk.ToggleToolButton):
        self._filter_bar.set_search_mode(button.get_active())

    @run_idle
    def on_filter(self, item):
        self._filter_positions = self.get_positions()
        self._filter_model.refilter()

    def filter_function(self, model, itr, data):
        if self._filter_model is None or self._filter_model == "None":
            return True

        from_pos, to_pos = self._filter_positions
        if from_pos == 0 and to_pos == 0:
            return True

        if from_pos > to_pos:
            from_pos, to_pos = to_pos, from_pos

        return from_pos <= float(self._parser.get_position(model.get(itr, 1)[0])) <= to_pos

    def get_positions(self):
        from_pos = round(self._from_pos_button.get_value(), 1) * (-1 if self._filter_from_combo_box.get_active() else 1)
        to_pos = round(self._to_pos_button.get_value(), 1) * (-1 if self._filter_to_combo_box.get_active() else 1)
        return from_pos, to_pos

    def on_select_all(self, view):
        self.update_selection(view, True)

    def on_unselect_all(self, view):
        self.update_selection(view, False)

    def update_selection(self, view, select):
        model = view.get_model()
        view.get_model().foreach(lambda mod, path, itr: self.update_state(model, path, select))
        self.update_receive_button_state(self._filter_model)

    def update_state(self, model, path, select):
        """ Updates checkbox state by given path in the list """
        itr = self._filter_model.convert_iter_to_child_iter(model.convert_iter_to_child_iter(model.get_iter(path)))
        self._filter_model.get_model().set_value(itr, 4, select)

    def on_quit(self, window, event):
        self._settings.add(self._size_name, window.get_size())
        self.is_download = False


class SatellitesUpdateDialog(UpdateDialog):
    """ Dialog for update satellites from the web. """

    def __init__(self, transient, settings, main_model):
        super().__init__(transient=transient, settings=settings)

        self._main_model = main_model
        self._source_box.connect("changed", self.on_update_satellites_list)

    @run_idle
    def on_receive_data(self, item):
        if self.is_download:
            show_dialog(DialogType.ERROR, self._window, "The task is already running!")
            return

        self.receive_satellites()

    @run_task
    def receive_satellites(self):
        self.is_download = True
        self.update_log_visibility()
        model = self._sat_view.get_model()
        start = time.time()

        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
            text = "Processing: {}\n"
            sats = []
            appender = self.append_output()
            next(appender)
            futures = {executor.submit(self._parser.get_satellite, sat[:-1]): sat for sat in [r for r in model if r[4]]}
            for future in concurrent.futures.as_completed(futures):
                if not self.is_download:
                    self.is_download = True
                    executor.shutdown()
                    appender.send("\nCanceled\n")
                    appender.close()
                    self.is_download = False
                    return
                data = future.result()
                appender.send(text.format(data[0]))
                sats.append(data)

            appender.send("-" * 75 + "\n")
            sat_count = len(sats)

            sats = {s[0]: s for s in sats}  # key = name, v = satellite

            for row in self._main_model:
                pos = row[0]
                if pos in sats:
                    sat = sats.pop(pos)
                    appender.send(f"Updating satellite: {row[0]}\n")
                    GLib.idle_add(self._main_model.set, row.iter, {i: v for i, v in enumerate(sat)})

            for p, s in sats.items():
                appender.send(f"Adding satellite: {s.name}\n")
                self.append_satellite(s)

            appender.send("-" * 75 + "\n")
            appender.send(f"Consumed: {time.time() - start:0.0f}s, {sat_count} satellites received.\n")
            appender.close()
            self.is_download = False

    @run_idle
    def append_satellite(self, sat):
        self._main_model.append(sat)


class ServicesUpdateDialog(UpdateDialog):
    """ Dialog for updating services from the web. """

    def __init__(self, transient, settings, callback):
        super().__init__(transient=transient, settings=settings, title="Services update")

        self._callback = callback
        self._satellite_paths = {}
        self._transponders = {}
        self._services = {}
        self._selected_transponders = set()
        self._services_parser = ServicesParser(source=SatelliteSource.LYNGSAT)
        # Transponder view popup menu
        tr_popup_menu = Gtk.Menu()
        select_all_item = Gtk.ImageMenuItem.new_from_stock("gtk-select-all")
        select_all_item.connect("activate", lambda w: self.update_transponder_selection(True))
        tr_popup_menu.append(select_all_item)
        remove_selection_item = Gtk.ImageMenuItem.new_from_stock("gtk-undo")
        remove_selection_item.set_label(get_message("Remove selection"))
        remove_selection_item.connect("activate", lambda w: self.update_transponder_selection(False))
        tr_popup_menu.append(remove_selection_item)
        tr_popup_menu.show_all()

        self._sat_view.connect("row-activated", self.on_activate_satellite)
        self._transponder_view.connect("row-activated", self.on_activate_transponder)
        self._transponder_view.connect("button-press-event", lambda w, e: on_popup_menu(tr_popup_menu, e))
        self._transponder_view.connect("select_all", lambda w: self.update_transponder_selection(True))

        self._transponder_paned.set_visible(True)
        self._source_box.connect("changed", self.on_update_satellites_list)

    @run_idle
    def on_receive_data(self, item):
        if self.is_download:
            show_dialog(DialogType.ERROR, self._window, "The task is already running!")
            return

        self.receive_services()

    @run_task
    def receive_services(self):
        self.is_download = True
        self.update_log_visibility()
        model = self._sat_view.get_model()
        appender = self.append_output()
        next(appender)

        start = time.time()
        non_cached_sats = []
        sat_names = {}
        t_names = {}
        t_urls = set()
        services = []

        for r in (r for r in model if r[-1]):
            if not self.is_download:
                appender.send("\nCanceled\n")
                return

            sat, url = r[0], r[3]
            trs = self._transponders.get(url, None)
            if trs:
                for t in filter(lambda tp: tp.url in self._selected_transponders, trs):
                    t_urls.add(t.url)
                    t_names[t.url] = t.text
            else:
                non_cached_sats.append(url)
                sat_names[url] = sat

        if non_cached_sats:
            with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self._services_parser.get_transponders_links, u): u for u in non_cached_sats}
                for future in concurrent.futures.as_completed(futures):
                    if not self.is_download:
                        appender.send("\nCanceled.\n")
                        self.is_download = False
                        return

                    appender.send(f"Getting transponders for: {sat_names.get(futures[future])}.\n")
                    for t in future.result():
                        t_urls.add(t.url)
                        t_names[t.url] = t.text

                appender.send("-" * 75 + "\n")
                appender.send(f"{len(t_urls)} transponders received.\n\n")

        non_cached_ts = []
        for tr in t_urls:
            srvs = self._services.get(tr)
            services.extend(srvs) if srvs else non_cached_ts.append(tr)

        if non_cached_ts:
            with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self._services_parser.get_transponder_services, u): u for u in non_cached_ts}
                for future in concurrent.futures.as_completed(futures):
                    if not self.is_download:
                        appender.send("\nCanceled.\n")
                        self.is_download = False
                        return

                    appender.send(f"Getting services for: {t_names.get(futures[future], '')}.\n")
                    try:
                        list(map(services.append, future.result()))
                    except ValueError as e:
                        log(f"Getting services error: {e} [{t_names.get(futures[future])}]")

        appender.send("-" * 75 + "\n")
        appender.send(f"Consumed: {time.time() - start:0.0f}s, {len(services)} services received.")

        try:
            from app.eparser.enigma.lamedb import LameDbReader
            # Used for double check!
            reader = LameDbReader(path=None)
            srvs = reader.get_services_list("".join(reader.get_services_lines(services)))
        except ValueError as e:
            log(f"ServicesUpdateDialog [on receive data] error: {e}")
        else:
            self._callback(srvs)

        self.is_download = False

    @run_task
    def get_sat_list(self, src, callback):
        sat_src = SatelliteSource.LYNGSAT
        if src == 1:
            sat_src = SatelliteSource.KINGOFSAT

        self._services_parser.source = sat_src
        sats = self._parser.get_satellites_list(sat_src)
        callback(sats)
        self.is_download = False

    def on_satellite_toggled(self, toggle, path):
        model = self._sat_view.get_model()
        self.update_state(model, path, not toggle.get_active())
        self.update_receive_button_state(self._filter_model)

        url = model.get_value(model.get_iter(path), 3)
        selected = toggle.get_active()
        transponders = self._transponders.get(url, None)

        if transponders:
            for t in transponders:
                self._selected_transponders.add(t.url) if selected else self._selected_transponders.discard(t.url)

    def on_transponder_toggled(self, toggle, path):
        model = self._transponder_view.get_model()
        itr = model.get_iter(path)
        active = not toggle.get_active()
        url = self.update_transponder_state(itr, model, active)

        s_path = self._satellite_paths.get(url, None)
        if s_path:
            self.update_sat_state(model, s_path, active)

    def update_sat_state(self, model, path, active):
        sat_model = self._sat_view.get_model()
        if active:
            self.update_state(sat_model, path, active)
        else:
            self.update_state(sat_model, path, any((r[-1] for r in model)))
        self.update_receive_button_state(self._filter_model)

    def update_transponder_state(self, itr, model, active):
        model.set_value(itr, 2, active)
        url = model.get_value(itr, 1)
        self._selected_transponders.add(url) if active else self._selected_transponders.discard(url)
        return url

    @run_task
    def on_activate_satellite(self, view, path, column):
        GLib.idle_add(self._transponder_view.get_model().clear)
        GLib.idle_add(self._service_view.get_model().clear)

        model = view.get_model()
        itr = model.get_iter(path)
        url, selected = model.get_value(itr, 3), model.get_value(itr, 4)
        transponders = self._transponders.get(url, None)
        if transponders is None:
            GLib.idle_add(view.set_sensitive, False)
            transponders = self._services_parser.get_transponders_links(url)
            self._transponders[url] = transponders

            for t in transponders:
                t_url = t.url
                self._satellite_paths[t_url] = path
                self._selected_transponders.add(t_url) if selected else self._selected_transponders.discard(t_url)

        self.append_transponders(self._transponder_view.get_model(), transponders)

    @run_idle
    def append_transponders(self, model, trs_list):
        model.clear()
        list(map(model.append, [(t.text, t.url, t.url in self._selected_transponders) for t in trs_list]))
        self._sat_view.set_sensitive(True)
        self._transponders_count_label.set_text(str(len(model)))

    @run_task
    def on_activate_transponder(self, view, path, column):
        url = view.get_model()[path][1]
        services = self._services.get(url, None)
        if services is None:
            GLib.idle_add(view.set_sensitive, False)
            services = self._services_parser.get_transponder_services(url)
            self._services[url] = services

        self.append_services(self._service_view.get_model(), services)

    @run_idle
    def append_services(self, model, srv_list):
        model.clear()
        for s in srv_list:
            model.append((None, s.service, s.package, s.service_type, str(s.ssid), None))

        self._transponder_view.set_sensitive(True)
        self._services_count_label.set_text(str(len(model)))

    def update_transponder_selection(self, select):
        m = self._transponder_view.get_model()
        if not len(m):
            return

        s_path = self._satellite_paths.get({self.update_transponder_state(r.iter, m, select) for r in m}.pop(), None)
        if s_path:
            self.update_sat_state(m, s_path, select)


if __name__ == "__main__":
    pass

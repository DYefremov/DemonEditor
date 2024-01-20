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


import concurrent.futures
import os
import re
import time
from collections import OrderedDict
from itertools import groupby
from math import fabs

from gi.repository import GLib

from app.commons import run_idle, run_task, log
from app.eparser import Satellite, Transponder
from app.eparser.ecommons import (PLS_MODE, get_key_by_value, POLARIZATION, FEC, SYSTEM, MODULATION, Terrestrial, Cable,
                                  T_SYSTEM, BANDWIDTH, CONSTELLATION, T_FEC, GUARD_INTERVAL, TRANSMISSION_MODE,
                                  HIERARCHY, Inversion, C_MODULATION, FEC_DEFAULT, TerTransponder, CableTransponder,
                                  Bouquet, BouquetService, BqServiceType, Bouquets, BqType)
from app.eparser.satxml import get_pos_str
from app.settings import Settings, CONFIG_PATH
from app.tools.satellites import SatellitesParser, SatelliteSource, ServicesParser
from ..dialogs import show_dialog, BaseDialog, DialogType, translate, get_builder
from ..main_helper import append_text_to_tview, get_base_model, on_popup_menu, get_services_type_groups
from ..search import SearchProvider
from ..uicommons import Gtk, Gdk, UI_RESOURCES_PATH, HeaderBar

_DIALOGS_UI_PATH = f"{UI_RESOURCES_PATH}xml{os.sep}dialogs.glade"


class DVBDialog(BaseDialog):
    """ Base dialog class for editing DVB (-> *.xml) data. """

    def __init__(self, parent, title, data=None, *args, **kwargs):
        super().__init__(parent=parent, title=title, *args, **kwargs)

        self._viewport = Gtk.Viewport(margin_top=2)
        self._viewport.get_style_context().add_class("view")
        self._frame = Gtk.Frame(margin=5, label_xalign=0.02, shadow_type=Gtk.ShadowType.NONE)
        self._label = Gtk.Label(margin_bottom=2, use_markup=True)
        self._frame.set_label_widget(self._label)
        self._frame.add(self._viewport)
        self.get_content_area().pack_start(self._frame, True, True, 0)

        self._data = data

    @property
    def data(self):
        return self._data

    def set_content(self, widget):
        self._viewport.add(widget)

    def set_label_text(self, text):
        self._label.set_markup(f"<b>{text}</b>")


class TransponderDialog(DVBDialog):
    """ Base transponder dialog class. """

    def __init__(self, parent, title, data=None, *args, **kwargs):
        super().__init__(parent, title, data, *args, **kwargs)
        self.set_label_text(translate("Transponder properties:"))
        # Pattern for digits entries.
        self.digit_pattern = re.compile(r"\D")
        # Style
        self.style_provider = Gtk.CssProvider()
        self.style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")

    def run(self):
        resp = super().run()
        while resp == Gtk.ResponseType.OK:
            if self.is_accept():
                return resp
            show_dialog(DialogType.ERROR, self, "Please check your parameters and try again.")
            resp = super().run()
        return resp

    def is_accept(self):
        return True

    def init_transponder_data(self, data):
        self._data = data

    def to_transponder(self):
        return self.data

    def on_entry_changed(self, entry):
        """ Digit entries handler. """
        entry.set_name("digit-entry" if self.digit_pattern.search(entry.get_text()) else "GtkEntry")

    def set_style_provider(self, widget):
        context = widget.get_style_context()
        context.add_provider_for_screen(Gdk.Screen.get_default(), self.style_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)


class TCDialog(DVBDialog):
    def __init__(self, parent, title=None, data=None, *args, **kwargs):
        super().__init__(parent, title, data, *args, **kwargs)

        self._entry = Gtk.Entry(margin=5)
        self.set_content(self._entry)
        self.set_label_text(translate("Name:"))
        self.show_all()

        if data:
            self._entry.set_text(data.name)


class SatelliteDialog(DVBDialog):
    """ Dialog for adding or edit satellite. """

    def __init__(self, transient, title, satellite=None, *args, **kwargs):
        super().__init__(transient, title, *args, **kwargs)
        builder = get_builder(_DIALOGS_UI_PATH, use_str=True,
                              objects=("sat_dialog_box", "side_store", "pos_adjustment"))

        self.set_content(builder.get_object("sat_dialog_box"))
        self.set_label_text(translate("Satellite properties:"))
        self._sat_name = builder.get_object("sat_name_entry")
        self._sat_position = builder.get_object("sat_position_button")
        self._side = builder.get_object("side_box")
        self._transponders = satellite.transponders if satellite else []
        self.show_all()

        if satellite:
            self._sat_name.set_text(satellite.name)
            pos = satellite.position
            pos = float(f"{pos[:-1]}.{pos[-1:]}")
            self._sat_position.set_value(fabs(pos))
            self._side.set_active(0 if pos >= 0 else 1)  # E or W

    @property
    def data(self):
        return self.to_satellite()

    def to_satellite(self):
        name = self._sat_name.get_text()
        pos = round(self._sat_position.get_value(), 1)
        side = self._side.get_active()
        pos = "{}{}{}".format("-" if side == 1 else "", *str(pos).split("."))

        return Satellite(name=name, flags="0", position=pos, transponders=self._transponders)


class TerrestrialDialog(TCDialog):
    """ Dialog for adding or edit  terrestrial region. """

    @property
    def data(self):
        name = self._entry.get_text()
        return self._data._replace(name=name) if self._data else Terrestrial(name, "5", None, [])


class CableDialog(TCDialog):
    """ Dialog for adding or edit cable provider. """

    @property
    def data(self):
        name = self._entry.get_text()
        return self._data._replace(name=name) if self._data else Cable(name, "true", "9", None, [])


class SatTransponderDialog(TransponderDialog):
    """ Dialog for adding or edit satellite transponder. """

    def __init__(self, transient, title, data=None, *args, **kwargs):
        super().__init__(transient, title, data, *args, **kwargs)

        handlers = {"on_entry_changed": self.on_entry_changed}
        objects = ("sat_tr_box", "pol_store", "fec_store", "mod_store", "system_store", "pls_mode_store")
        builder = get_builder(_DIALOGS_UI_PATH, handlers, use_str=True, objects=objects)

        self.set_content(builder.get_object("sat_tr_box"))
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

        self.set_style_provider(self._freq_entry)
        self.set_style_provider(self._rate_entry)
        self.show_all()

        self.init_transponder_data(data)

    @property
    def data(self):
        return self.to_transponder()

    def init_transponder_data(self, transponder):
        if transponder:
            self._freq_entry.set_text(transponder.frequency)
            self._rate_entry.set_text(transponder.symbol_rate)
            self._pol_box.set_active_id(POLARIZATION.get(transponder.polarization, None))
            self._fec_box.set_active_id(FEC.get(transponder.fec_inner, None))
            self._sys_box.set_active_id(SYSTEM.get(transponder.system, None))
            self._mod_box.set_active_id(MODULATION.get(transponder.modulation, None))
            self._pls_mode_box.set_active_id(PLS_MODE.get(transponder.pls_mode, None))
            self._is_id_entry.set_text(transponder.is_id if transponder.is_id else "")
            self._pls_code_entry.set_text(transponder.pls_code if transponder.pls_code else "")
            self._t2mi_plp_id_entry.set_text(transponder.t2mi_plp_id if transponder.t2mi_plp_id else "")

    def to_transponder(self):
        return Transponder(frequency=self._freq_entry.get_text(),
                           symbol_rate=self._rate_entry.get_text(),
                           polarization=get_key_by_value(POLARIZATION, self._pol_box.get_active_id()),
                           fec_inner=get_key_by_value(FEC, self._fec_box.get_active_id()),
                           system=get_key_by_value(SYSTEM, self._sys_box.get_active_id()),
                           modulation=get_key_by_value(MODULATION, self._mod_box.get_active_id()),
                           pls_mode=get_key_by_value(PLS_MODE, self._pls_mode_box.get_active_id()),
                           pls_code=self._pls_code_entry.get_text(),
                           is_id=self._is_id_entry.get_text(),
                           t2mi_plp_id=self._t2mi_plp_id_entry.get_text())

    def is_accept(self):
        tr = self.to_transponder()
        if self.digit_pattern.search(tr.frequency) or not tr.frequency:
            return False
        elif self.digit_pattern.search(tr.symbol_rate) or not tr.symbol_rate:
            return False
        elif None in (tr.polarization, tr.fec_inner, tr.system, tr.modulation):
            return False
        elif self.digit_pattern.search(tr.pls_code) or self.digit_pattern.search(tr.is_id):
            return False
        elif self.digit_pattern.search(tr.t2mi_plp_id):
            return False

        return True


class TerTransponderDialog(TransponderDialog):
    """ Dialog for adding or edit terrestrial transponder. """

    def __init__(self, transient, title, data=None, *args, **kwargs):
        super().__init__(transient, title, data, *args, **kwargs)

        handlers = {"on_entry_changed": self.on_entry_changed}
        builder = get_builder(_DIALOGS_UI_PATH, handlers, use_str=True, objects=("ter_tr_box",))

        self.set_content(builder.get_object("ter_tr_box"))
        self._freq_entry = builder.get_object("ter_freq_entry")
        self._sys_box = builder.get_object("ter_sys_box")
        self._bandwidth_box = builder.get_object("ter_bandwidth_box")
        self._constellation_box = builder.get_object("ter_constellation_box")
        self._sr_hp_box = builder.get_object("ter_sr_hp_box")
        self._sr_lp_box = builder.get_object("ter_sr_lp_box")
        self._guard_box = builder.get_object("ter_guard_box")
        self._transmission_box = builder.get_object("ter_transmission_box")
        self._hierarchy_box = builder.get_object("ter_hierarchy_box")
        self._inversion_box = builder.get_object("ter_inversion_box")
        self._plp_id_entry = builder.get_object("ter_plp_id_entry")

        self.set_style_provider(self._freq_entry)
        self.set_style_provider(self._plp_id_entry)
        self.show_all()

        self.init_transponder_data(data)

    @property
    def data(self):
        return self.to_transponder()

    def init_transponder_data(self, transponder):
        [self._sys_box.append(k, v) for k, v in T_SYSTEM.items()]
        [self._bandwidth_box.append(k, v) for k, v in BANDWIDTH.items()]
        [self._constellation_box.append(k, v) for k, v in CONSTELLATION.items()]
        [self._sr_hp_box.append(k, v) for k, v in T_FEC.items()]
        [self._sr_lp_box.append(k, v) for k, v in T_FEC.items()]
        [self._guard_box.append(k, v) for k, v in GUARD_INTERVAL.items()]
        [self._transmission_box.append(k, v) for k, v in TRANSMISSION_MODE.items()]
        [self._hierarchy_box.append(k, v) for k, v in HIERARCHY.items()]
        [self._inversion_box.append(k.value, k.name) for k in Inversion]

        if transponder:
            self._freq_entry.set_text(transponder.centre_frequency)
            self._sys_box.set_active_id(transponder.system)
            self._bandwidth_box.set_active_id(transponder.bandwidth)
            self._constellation_box.set_active_id(transponder.constellation)
            self._sr_hp_box.set_active_id(transponder.code_rate_hp)
            self._sr_lp_box.set_active_id(transponder.code_rate_lp)
            self._guard_box.set_active_id(transponder.guard_interval)
            self._transmission_box.set_active_id(transponder.transmission_mode)
            self._hierarchy_box.set_active_id(transponder.hierarchy_information)
            self._inversion_box.set_active_id(transponder.inversion)
            self._plp_id_entry.set_text(transponder.plp_id or "")

    def is_accept(self):
        tr = self.to_transponder()
        if not tr.centre_frequency or self.digit_pattern.search(tr.centre_frequency):
            return False
        elif tr.plp_id and self.digit_pattern.search(tr.plp_id):
            return False
        return True

    def to_transponder(self):
        return TerTransponder(centre_frequency=self._freq_entry.get_text(),
                              system=self._sys_box.get_active_id(),
                              bandwidth=self._bandwidth_box.get_active_id(),
                              constellation=self._constellation_box.get_active_id(),
                              code_rate_hp=self._sr_hp_box.get_active_id(),
                              code_rate_lp=self._sr_lp_box.get_active_id(),
                              guard_interval=self._guard_box.get_active_id(),
                              transmission_mode=self._transmission_box.get_active_id(),
                              hierarchy_information=self._hierarchy_box.get_active_id(),
                              inversion=self._inversion_box.get_active_id(),
                              plp_id=self._plp_id_entry.get_text() or None)


class CableTransponderDialog(TransponderDialog):
    """ Dialog for adding or edit cable transponder. """

    def __init__(self, transient, title, data=None, *args, **kwargs):
        super().__init__(transient, title, data, *args, **kwargs)

        handlers = {"on_entry_changed": self.on_entry_changed}
        builder = get_builder(_DIALOGS_UI_PATH, handlers, use_str=True, objects=("cable_tr_box",))

        self.set_content(builder.get_object("cable_tr_box"))

        self._freq_entry = builder.get_object("cable_freq_entry")
        self._rate_entry = builder.get_object("cable_rate_entry")
        self._fec_box = builder.get_object("cable_fec_box")
        self._mod_box = builder.get_object("cable_mod_box")

        self.set_style_provider(self._freq_entry)
        self.set_style_provider(self._rate_entry)
        self.show_all()

        self.init_transponder_data(data)

    @property
    def data(self):
        return self.to_transponder()

    def init_transponder_data(self, transponder):
        [self._fec_box.append(k, v) for k, v in FEC_DEFAULT.items()]
        [self._mod_box.append(k, v) for k, v in C_MODULATION.items()]

        if transponder:
            self._freq_entry.set_text(transponder.frequency)
            self._rate_entry.set_text(transponder.symbol_rate)
            self._fec_box.set_active_id(transponder.fec_inner)
            self._mod_box.set_active_id(transponder.modulation)

    def is_accept(self):
        tr = self.to_transponder()
        if not tr.frequency or self.digit_pattern.search(tr.frequency):
            return False
        elif not tr.symbol_rate or self.digit_pattern.search(tr.symbol_rate):
            return False
        return True

    def to_transponder(self):
        return CableTransponder(frequency=self._freq_entry.get_text(),
                                symbol_rate=self._rate_entry.get_text(),
                                fec_inner=self._fec_box.get_active_id(),
                                modulation=self._mod_box.get_active_id())


# ********************** Update dialogs ************************ #

class UpdateDialog:
    """ Base dialog for update satellites, transponders and services from the Web."""

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
        self._selected_satellites = set()

        builder = get_builder(f"{UI_RESOURCES_PATH}xml{os.sep}update.glade", handlers)

        self._window = builder.get_object("satellites_update_window")
        self._window.set_transient_for(transient)
        self._window.set_title(title if title else "")

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
        self._sat_view.bind_property("sensitive", self._receive_button, "sensitive")
        self._receive_button.bind_property("visible", update_button, "visible")
        self._left_action_box = builder.get_object("sat_update_left_action_box")
        self._right_action_box = builder.get_object("sat_update_right_action_box")
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
        # Satellite lists init on dialog start.
        self._sat_view.connect("realize", self.on_update_satellites_list)
        # Options.
        self._general_options_box = builder.get_object("general_options_box")
        self._save_sat_selection_switch = builder.get_object("save_sat_selection_switch")
        self._skip_c_band_switch = builder.get_object("skip_c_band_switch")

        if self._settings.use_header_bar:
            header_bar = HeaderBar()
            builder.get_object("sat_update_header").set_visible(False)
            header_box = builder.get_object("satellites_update_header_box")
            header_box.remove(self._source_box)
            header_bar.pack_start(self._source_box)
            header_box.remove(self._left_action_box)
            header_bar.pack_start(self._left_action_box)
            header_box.remove(self._right_action_box)
            header_bar.pack_end(self._right_action_box)
            self._window.set_titlebar(header_bar)

        # Dialog settings.
        self._dialog_name = f"{'_'.join(re.findall('[A-Z][^A-Z]*', self.__class__.__name__))}".lower()
        self._dialog_settings = self._settings.get(self._dialog_name, {})
        self._source_box.set_active(self._dialog_settings.get("source", 1))
        self._save_sat_selection_switch.set_active(self._dialog_settings.get("save_sat_selection", False))
        self._skip_c_band_switch.set_active(self._dialog_settings.get("skip_c_band", False))

        if self._save_sat_selection_switch.get_active():
            self._selected_satellites.update(self.get_selected_satellites())

        window_size = self._dialog_settings.get("window_size", None)
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

        if not self._parser:
            self._parser = SatellitesParser()

        self.get_sat_list(self._source_box.get_active(), self.append_satellites)

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
            itr = model.append(sat)
            model[itr][-1] = sat[-2] in self._selected_satellites

        self._sat_view.set_sensitive(True)
        self._satellites_count_label.set_text(str(len(model)))
        self.update_receive_button_state(self._filter_model)

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

        if self._save_sat_selection_switch.get_active():
            sat = model[path][-2]
            self._selected_satellites.add(sat) if select else self._selected_satellites.discard(sat)

    def on_quit(self, window, event):
        self.save_settings()
        self.is_download = False

    def save_settings(self):
        self._dialog_settings["window_size"] = self._window.get_size()
        self._dialog_settings["source"] = self._source_box.get_active()
        self._dialog_settings["save_sat_selection"] = self._save_sat_selection_switch.get_active()
        self._dialog_settings["skip_c_band"] = self._skip_c_band_switch.get_active()
        self._settings.add(self._dialog_name, self._dialog_settings)
        self.save_selected_satellites()

    def get_selected_satellites(self):
        """ Returns selected satellites set from the last session. """
        c_file = f"{CONFIG_PATH}{self._dialog_name}_satellites"
        return Settings.get_settings(c_file, default_settings=[])

    def save_selected_satellites(self):
        """ Saves current selected satellites to a file. """
        if self._save_sat_selection_switch.get_active():
            c_file = f"{CONFIG_PATH}{self._dialog_name}_satellites"
            Settings.write_settings(list(self._selected_satellites), config_file=c_file)


class SatellitesUpdateDialog(UpdateDialog):
    """ Dialog for update satellites from the Web. """

    def __init__(self, transient, settings, main_model):
        super().__init__(transient=transient, settings=settings)

        self._main_model = main_model
        self._source_box.connect("changed", self.on_update_satellites_list)
        # Options.
        self._merge_sat_switch = Gtk.Switch(active=self._dialog_settings.get("merge_satellites", False))
        self._merge_sat_switch.connect("state-set", lambda b, s: self._dialog_settings.update({"merge_satellites": s}))
        box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(Gtk.Label(translate("Merge satellites by positions")), False, True, 0)
        box.pack_end(self._merge_sat_switch, False, True, 0)
        self._general_options_box.pack_start(box, True, True, 0)
        self._general_options_box.show_all()

        self._skip_c_band_switch.get_parent().set_visible(False)

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
        _len = 75

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

            appender.send("-" * _len + "\n")
            sat_count = len(sats)

            if self._merge_sat_switch.get_active():
                def grouper(sat):
                    try:
                        return int(sat.position)
                    except ValueError:
                        pass
                    return 0

                sat_groups = groupby(sorted(sats, key=grouper, reverse=True), key=grouper)
                sats = {}
                for pos, satellites in sat_groups:
                    satellites = list(satellites)
                    if len(satellites) > 1:
                        position = get_pos_str(pos)
                        appender.send(f"Merging satellites for position: {position}\n")
                        names = []
                        transponders = []
                        for s in satellites:
                            names.append(s.name.lstrip(position).strip().split())
                            transponders.extend(s.transponders)

                        transponders.sort(key=lambda t: int(t.frequency))
                        sat = Satellite(self.get_grouped_satellite_name(names, position), "0", str(pos), transponders)
                        sats[sat.name] = sat
                    else:
                        sat = satellites.pop()
                        sats[sat.name] = sat
                appender.send("-" * _len + "\n")
            else:
                sats = {s.name: s for s in sats}  # key = name, v = satellite

            for row in self._main_model:
                pos = row[0]
                if pos in sats:
                    sat = sats.pop(pos)
                    appender.send(f"Updating satellite: {row[0]}\n")
                    GLib.idle_add(self._main_model.set, row.iter, {i: v for i, v in enumerate(sat)})

            for p, s in sats.items():
                appender.send(f"Adding satellite: {s.name}\n")
                self.append_satellite(s)

            appender.send("-" * _len + "\n")
            appender.send(f"Consumed: {time.time() - start:0.0f}s, {sat_count} satellites received.\n")
            appender.close()
            self.is_download = False

    def get_grouped_satellite_name(self, sat_names, pos):
        """ Forms name for merged satellites. """

        def name_grouper(nd):
            if nd:
                return nd[0]
            return ""

        name_groups = groupby(sorted(sat_names, key=name_grouper), key=name_grouper)
        names = []
        for s, s_names in name_groups:
            tk = set()
            name = s
            for i, n_data in enumerate(s_names):
                if i == 0:
                    name = " ".join(n_data)
                    tk.update(n_data)
                else:
                    for n in n_data:
                        if n in tk:
                            continue
                        name = f"{name}/{n}"
                        tk.add(n)

            names.append(name)

        return f"{pos} {' & '.join(names)}"

    @run_idle
    def append_satellite(self, sat):
        self._main_model.append(sat)


class ServicesUpdateDialog(UpdateDialog):
    """ Dialog for updating services from the Web. """

    def __init__(self, app):
        super().__init__(transient=app.app_window, settings=app.app_settings, title="Services update")

        self._callback = app.on_import_data_from_web
        self._satellite_paths = {}
        self._transponders = {}
        self._services = {}
        self._selected_transponders = set()
        self._services_parser = ServicesParser(source=SatelliteSource.LYNGSAT)
        # Transponder view popup menu.
        tr_popup_menu = Gtk.Menu()
        select_all_item = Gtk.ImageMenuItem.new_from_stock("gtk-select-all")
        select_all_item.connect("activate", lambda w: self.update_transponder_selection(True))
        tr_popup_menu.append(select_all_item)
        remove_selection_item = Gtk.ImageMenuItem.new_from_stock("gtk-undo")
        remove_selection_item.set_label(translate("Remove selection"))
        remove_selection_item.connect("activate", lambda w: self.update_transponder_selection(False))
        tr_popup_menu.append(remove_selection_item)
        tr_popup_menu.show_all()

        self._sat_view.connect("row-activated", self.on_activate_satellite)
        self._transponder_view.connect("row-activated", self.on_activate_transponder)
        self._transponder_view.connect("button-press-event", lambda w, e: on_popup_menu(tr_popup_menu, e))
        self._transponder_view.connect("select_all", lambda w: self.update_transponder_selection(True))

        self._transponder_paned.set_visible(True)
        self._source_box.connect("changed", self.on_update_satellites_list)
        self._source_box.connect("changed", self.on_source_changed)
        # Options for KingOfSat source.
        self._kos_bq_groups_switch = Gtk.Switch(active=self._dialog_settings.get("kos_bq_groups", False))
        self._kos_bq_groups_switch.connect("state-set", lambda b, s: self._dialog_settings.update({"kos_bq_groups": s}))
        self._kos_bq_lang_switch = Gtk.Switch(active=self._dialog_settings.get("kos_bq_lang", False))
        self._kos_bq_lang_switch.connect("state-set", lambda b, s: self._dialog_settings.update({"kos_bq_lang": s}))
        self._kos_options_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.VERTICAL)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5, margin_top=5)
        box.pack_start(Gtk.Label(translate("Create Category bouquets")), False, True, 0)
        box.pack_end(self._kos_bq_groups_switch, False, True, 0)
        self._kos_options_box.add(box)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5, margin_bottom=5)
        box.pack_start(Gtk.Label(translate("Create Regional bouquets")), False, True, 0)
        box.pack_end(self._kos_bq_lang_switch, False, True, 0)
        self._kos_options_box.add(box)
        self._kos_options_box.connect("realize", self.on_source_changed)
        self._general_options_box.pack_start(self._kos_options_box, True, True, 0)
        self._general_options_box.show_all()

    @run_idle
    def on_receive_data(self, item):
        if self.is_download:
            show_dialog(DialogType.ERROR, self._window, "The task is already running!")
            return

        self.receive_services()

    def on_source_changed(self, item):
        is_kos = self._source_box.get_active_id() == SatelliteSource.KINGOFSAT.name
        self._kos_options_box.set_sensitive(is_kos)
        if not is_kos:
            self._kos_bq_groups_switch.set_active(False)
            self._kos_bq_lang_switch.set_active(False)
        self._kos_options_box.set_tooltip_text(None if is_kos else translate("KingOfSat only!"))

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
        services = OrderedDict({s.fav_id: s for s in services}).values()
        appender.send(f"Consumed: {time.time() - start:0.0f}s, {len(services)} services received.")

        try:
            from app.eparser.enigma.lamedb import LameDbReader
            # Used for double check!
            reader = LameDbReader(path=None)
            srvs = reader.get_services_list("".join(reader.get_services_lines(services)))
        except ValueError as e:
            log(f"ServicesUpdateDialog [on receive data] error: {e}")
        else:
            bouquets = None
            if self._source_box.get_active_id() == SatelliteSource.KINGOFSAT.name:
                bouquets = self.get_bouquets([srv._replace(fav_id=srvs[i].fav_id) for i, srv in enumerate(services)])

            def c_filter(s):
                try:
                    return int(s.freq) > 10000
                except ValueError:
                    return False

            self._callback(filter(c_filter, srvs) if self._skip_c_band_switch.get_active() else srvs, bouquets)

        self.is_download = False

    def get_bouquets(self, services):
        type_groups = get_services_type_groups(services)
        tv_bouquets, radio_bouquets = [], []

        tv_services = sorted(type_groups.get("TV", []), key=lambda s: s.service)
        rd_services = sorted(type_groups.get("Radio", []), key=lambda s: s.service)
        no_lb = "No Category"

        if self._kos_bq_groups_switch.get_active():
            self.gen_bouquet_group(tv_services, tv_bouquets, lambda s: s[4] or no_lb)
            self.gen_bouquet_group(rd_services, radio_bouquets, lambda s: s[4] or no_lb, bq_type=BqType.RADIO.value)

        if self._kos_bq_lang_switch.get_active():
            lb = "" if no_lb in {b.name for b in tv_bouquets} else "No Region"
            self.gen_bouquet_group(tv_services, tv_bouquets, lambda s: s[5] or lb)
            lb = "" if no_lb in {b.name for b in radio_bouquets} else "No Region"
            self.gen_bouquet_group(rd_services, radio_bouquets, lambda s: s[5] or lb, bq_type=BqType.RADIO.value)

        return Bouquets("", BqType.TV.value, tv_bouquets), Bouquets("", BqType.RADIO.value, radio_bouquets)

    def gen_bouquet_group(self, services, bouquets, grouper, bq_type=BqType.TV.value):
        """ Generates bouquets depending on <grouper>. """
        s_type = BqServiceType.DEFAULT
        [bouquets.append(Bouquet(name=g[0], type=bq_type,
                                 services=[BouquetService(None, s_type, s.fav_id, 0) for s in g[1]])) for g in
         groupby(sorted(services, key=grouper), key=grouper) if g[0]]

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
        super().on_satellite_toggled(toggle, path)

        model = self._sat_view.get_model()
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

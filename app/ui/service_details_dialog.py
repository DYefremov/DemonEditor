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


import os
import re

from app.commons import run_idle, log
from app.eparser import Service
from app.eparser.ecommons import (MODULATION, Inversion, ROLL_OFF, Pilot, Flag, Pids, POLARIZATION, get_key_by_value,
                                  get_value_by_name, FEC_DEFAULT, PLS_MODE, SERVICE_TYPE, T_MODULATION, C_MODULATION,
                                  TrType, SystemCable, T_SYSTEM, BANDWIDTH, TRANSMISSION_MODE, GUARD_INTERVAL, T_FEC,
                                  HIERARCHY, A_MODULATION)
from app.eparser.neutrino import get_attributes, SP, KSP
from app.settings import SettingsType
from .dialogs import show_dialog, DialogType, Action, get_builder
from .main_helper import get_base_model
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, HIDE_ICON, CODED_ICON, Column

_UI_PATH = UI_RESOURCES_PATH + "service_details_dialog.glade"


class ServiceDetailsDialog:
    _ENIGMA2_DATA_ID = "{:04x}:{:08x}:{:04x}:{:04x}:{}:{}"

    _ENIGMA2_FAV_ID = "{:X}:{:X}:{:X}:{:X}"

    _ENIGMA2_TRANSPONDER_DATA = "{} {}:{}:{}:{}:{}:{}:{}"

    _NEUTRINO_FAV_ID = "{:x}:{:x}:{:x}"

    _DIGIT_ENTRY_ELEMENTS = ("bitstream_entry", "pcm_entry", "video_pid_entry", "pcr_pid_entry", "srv_type_entry",
                             "ac3_pid_entry", "ac3plus_pid_entry", "acc_pid_entry", "he_acc_pid_entry",
                             "teletext_pid_entry", "pls_code_entry", "stream_id_entry", "tr_flag_entry",
                             "audio_pid_entry")
    _NOT_EMPTY_DIGIT_ELEMENTS = ("sid_entry", "freq_entry", "rate_entry", "transponder_id_entry", "network_id_entry",
                                 "namespace_entry", "srv_type_entry")

    _DIGIT_ENTRY_NAME = "digit-entry"

    def __init__(self, app, new_color, action=Action.EDIT):
        handlers = {"on_system_changed": self.on_system_changed,
                    "on_save": self.on_save,
                    "on_create_new": self.on_create_new,
                    "on_tr_edit_toggled": self.on_tr_edit_toggled,
                    "update_reference": self.update_reference,
                    "on_cas_entry_changed": self.on_cas_entry_changed,
                    "on_extra_pids_entry_changed": self.on_extra_pids_entry_changed,
                    "on_digit_entry_changed": self.on_digit_entry_changed,
                    "on_non_empty_entry_changed": self.on_non_empty_entry_changed,
                    "on_cancel": lambda item: self._dialog.destroy()}

        builder = get_builder(_UI_PATH, handlers, use_str=True)
        self._builder = builder
        settings = app.app_settings

        self._dialog = builder.get_object("service_details_dialog")
        self._dialog.set_transient_for(app.app_window)
        self._s_type = settings.setting_type
        self._tr_type = TrType.Satellite
        self._picons_path = settings.profile_picons_path
        self._services_view = app.services_view
        self._fav_view = app.fav_view
        self._action = action
        self._old_service = None
        self._services = app.current_services
        self._bouquets = app.current_bouquets
        self._new_color = new_color
        self._transponder_services_iters = None
        self._current_model = None
        self._current_itr = None
        # Patterns
        self._DIGIT_PATTERN = re.compile("\\D")
        self._NON_EMPTY_PATTERN = re.compile("(?:^[\\s]*$|\\D)")
        self._CAID_PATTERN = re.compile("(?:^[\\s]*$)|(C:[0-9a-fA-F]{1,4})(,C:[0-9a-fA-F]{1,4})*")
        self._PIDS_PATTERN = re.compile("(?:^[\\s]*$)|(c:[0-9]{2}[0-9a-fA-F]{4})(,c:[0-9]{2}[0-9a-fA-F]{4})*")
        # Buttons
        self._apply_button = builder.get_object("apply_button")
        self._create_button = builder.get_object("create_button")
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        # initialization only digit elements
        self._digit_elements = {k: builder.get_object(k) for k in self._DIGIT_ENTRY_ELEMENTS}
        for elem in self._digit_elements.values():
            elem.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                             Gtk.STYLE_PROVIDER_PRIORITY_USER)
        # initialization of non empty elements
        self._non_empty_elements = {k: builder.get_object(k) for k in self._NOT_EMPTY_DIGIT_ELEMENTS}
        for elem in self._non_empty_elements.values():
            elem.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                             Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._sid_entry = self._non_empty_elements.get("sid_entry")
        self._bitstream_entry = self._digit_elements.get("bitstream_entry")
        self._pcm_entry = self._digit_elements.get("pcm_entry")
        self._video_pid_entry = self._digit_elements.get("video_pid_entry")
        self._pcr_pid_entry = self._digit_elements.get("pcr_pid_entry")
        self._audio_pid_entry = self._digit_elements.get("audio_pid_entry")
        self._ac3_pid_entry = self._digit_elements.get("ac3_pid_entry")
        self._ac3plus_pid_entry = self._digit_elements.get("ac3plus_pid_entry")
        self._acc_pid_entry = self._digit_elements.get("acc_pid_entry")
        self._he_acc_pid_entry = self._digit_elements.get("he_acc_pid_entry")
        self._teletext_pid_entry = self._digit_elements.get("teletext_pid_entry")
        self._transponder_id_entry = self._non_empty_elements.get("transponder_id_entry")
        self._network_id_entry = self._non_empty_elements.get("network_id_entry")
        self._freq_entry = self._non_empty_elements.get("freq_entry")
        self._rate_entry = self._non_empty_elements.get("rate_entry")
        self._pls_code_entry = self._digit_elements.get("pls_code_entry")
        self._stream_id_entry = self._digit_elements.get("stream_id_entry")
        self._tr_flag_entry = self._digit_elements.get("tr_flag_entry")
        self._namespace_entry = self._non_empty_elements.get("namespace_entry")
        self._extra_pids_entry = builder.get_object("extra_pids_entry")
        # Service elements
        self._name_entry = builder.get_object("name_entry")
        self._package_entry = builder.get_object("package_entry")
        self._srv_type_entry = self._non_empty_elements.get("srv_type_entry")
        self._service_type_combo_box = builder.get_object("service_type_combo_box")
        self._cas_entry = builder.get_object("cas_entry")
        self._reference_label = builder.get_object("reference_label")
        self._keep_check_button = builder.get_object("keep_check_button")
        self._hide_check_button = builder.get_object("hide_check_button")
        self._use_pids_check_button = builder.get_object("use_pids_check_button")
        self._new_check_button = builder.get_object("new_check_button")
        self._pids_grid = builder.get_object("pids_grid")
        # Transponder elements
        self._sat_pos_button = builder.get_object("sat_pos_button")
        self._pos_side_box = builder.get_object("pos_side_box")
        self._pol_combo_box = builder.get_object("pol_combo_box")
        self._fec_combo_box = builder.get_object("fec_combo_box")
        self._rate_lp_combo_box = builder.get_object("rate_lp_combo_box")
        self._sys_combo_box = builder.get_object("sys_combo_box")
        self._mod_combo_box = builder.get_object("mod_combo_box")
        self._invertion_combo_box = builder.get_object("invertion_combo_box")
        self._rolloff_combo_box = builder.get_object("rolloff_combo_box")
        self._pilot_combo_box = builder.get_object("pilot_combo_box")
        self._pls_mode_combo_box = builder.get_object("pls_mode_combo_box")
        self._tr_edit_switch = builder.get_object("tr_edit_switch")

        self._DVB_S2_ELEMENTS = (self._mod_combo_box, self._rolloff_combo_box, self._pilot_combo_box,
                                 self._pls_mode_combo_box, self._pls_code_entry, self._stream_id_entry)
        self._TRANSPONDER_ELEMENTS = (self._sat_pos_button, self._pol_combo_box, self._invertion_combo_box,
                                      self._sys_combo_box, self._freq_entry, self._transponder_id_entry,
                                      self._network_id_entry, self._namespace_entry, self._fec_combo_box,
                                      self._rate_entry, self._rate_lp_combo_box, self._pos_side_box)

        if self._action is Action.EDIT:
            self.update_data_elements()
        elif self._action is Action.ADD:
            self.init_default_data_elements()

    def show(self):
        self._dialog.show()

    @run_idle
    def init_default_data_elements(self):
        self._apply_button.set_visible(False)
        self._create_button.set_visible(True)
        self._tr_edit_switch.set_sensitive(False)
        self.on_tr_edit_toggled(self._tr_edit_switch.set_active(True), True)
        for elem in self._non_empty_elements.values():
            elem.set_text(" ")
            elem.set_text("")
        self._new_check_button.set_active(True)
        self._service_type_combo_box.set_active(0)
        self._pol_combo_box.set_active(0)
        self._fec_combo_box.set_active(0)
        self._sys_combo_box.set_active(0)
        self._invertion_combo_box.set_active(2)

    def update_data_elements(self):
        model, paths = self._services_view.get_selection().get_selected_rows()
        # Unpacking to search for an iterator for the base model
        filter_model = model.get_model()
        self._current_model = get_base_model(model)
        itr = None
        if not paths:
            # If editing from bouquet list and services list in the filter mode
            fav_model, paths = self._fav_view.get_selection().get_selected_rows()
            fav_id = fav_model[paths][7]
            for row in self._current_model:
                if row[-2] == fav_id:
                    itr = row.iter
                    break
        else:
            itr = model.get_iter(paths)
            itr = filter_model.convert_iter_to_child_iter(model.convert_iter_to_child_iter(itr))

        if not itr:
            return

        srv = Service(*self._current_model[itr][: Column.SRV_TOOLTIP])
        self._old_service = srv
        self._current_itr = itr
        # Service
        self._name_entry.set_text(srv.service)
        self._package_entry.set_text(srv.package)
        self._sid_entry.set_text(str(int(srv.ssid, 16)))
        # Transponder
        self._tr_type = TrType(srv.transponder_type)
        self._freq_entry.set_text(srv.freq)
        self._rate_entry.set_text(srv.rate)
        self.select_active_text(self._pol_combo_box, srv.pol)
        self.select_active_text(self._fec_combo_box, srv.fec)
        self.select_active_text(self._sys_combo_box, srv.system)
        if self._tr_type is TrType.Terrestrial:
            self.update_ui_for_terrestrial()
        elif self._tr_type is TrType.Cable:
            self.update_ui_for_cable()
        elif self._tr_type is TrType.ATSC:
            self.update_ui_for_atsc()
        else:
            self.set_sat_positions(srv.pos)

        if self._s_type is SettingsType.ENIGMA_2:
            self.init_enigma2_service_data(srv)
            self.init_enigma2_transponder_data(srv)
        elif self._s_type is SettingsType.NEUTRINO_MP:
            self.init_neutrino_data(srv)
            self.init_neutrino_ui_elements()

    # ***************** Init Enigma2 data *********************#

    @run_idle
    def init_enigma2_service_data(self, srv):
        """ Service data initialisation """
        flags = srv.flags_cas
        if flags:
            flags = flags.split(",")
            self.init_enigma2_flags(flags)
            self.init_enigma2_pids(flags)
            self.init_enigma2_cas(flags)

    def init_enigma2_flags(self, flags):
        f_flags = list(filter(lambda x: x.startswith("f:"), flags))
        if f_flags:
            value = Flag.parse(f_flags[0])
            self._keep_check_button.set_active(Flag.is_keep(value))
            self._hide_check_button.set_active(Flag.is_hide(value))
            self._use_pids_check_button.set_active(Flag.is_pids(value))
            self._new_check_button.set_active(Flag.is_new(value))

    def init_enigma2_cas(self, flags):
        cas = list(filter(lambda x: x.startswith("C:"), flags))
        if cas:
            self._cas_entry.set_text(",".join(cas))

    def init_enigma2_pids(self, flags):
        pids = list(filter(lambda x: x.startswith("c:"), flags))
        if pids:
            extra_pids = []
            for pid in pids:
                if pid.startswith(Pids.VIDEO.value):
                    self._video_pid_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.AUDIO.value):
                    self._audio_pid_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.TELETEXT.value):
                    self._teletext_pid_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.PCR.value):
                    self._pcr_pid_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.AC3.value):
                    self._ac3_pid_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.VIDEO_TYPE.value):
                    extra_pids.append(pid)
                elif pid.startswith(Pids.AUDIO_CHANNEL.value):
                    extra_pids.append(pid)
                elif pid.startswith(Pids.BIT_STREAM_DELAY.value):
                    self._bitstream_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.PCM_DELAY.value):
                    self._pcm_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.SUBTITLE.value):
                    extra_pids.append(pid)
                else:
                    extra_pids.append(pid)

            self._extra_pids_entry.set_text(",".join(extra_pids))

    def init_enigma2_transponder_data(self, srv):
        """ Transponder data initialisation """
        data = srv.data_id.split(":")
        tr_data = srv.transponder.split(":")
        tr_type = TrType(srv.transponder_type)

        self._namespace_entry.set_text(str(int(data[1], 16)))
        self._transponder_id_entry.set_text(str(int(data[2], 16)))
        self._network_id_entry.set_text(str(int(data[3], 16)))

        if tr_type is TrType.Satellite:
            self.select_active_text(self._invertion_combo_box, Inversion(tr_data[5]).name)
            if srv.system == "DVB-S2":
                self.select_active_text(self._mod_combo_box, MODULATION.get(tr_data[8]))
                self.select_active_text(self._rolloff_combo_box, ROLL_OFF.get(tr_data[9]))
                self.select_active_text(self._pilot_combo_box, Pilot(tr_data[10]).name)
                self._tr_flag_entry.set_text(tr_data[7])
                if len(tr_data) > 12:
                    self._stream_id_entry.set_text(tr_data[11])
                    self._pls_code_entry.set_text(tr_data[12])
                    self.select_active_text(self._pls_mode_combo_box, PLS_MODE.get(tr_data[13]))
        elif tr_type is TrType.Cable:
            self.select_active_text(self._invertion_combo_box, Inversion(tr_data[2]).name)
            self.select_active_text(self._mod_combo_box, C_MODULATION.get(tr_data[3]))
            self.select_active_text(self._fec_combo_box, FEC_DEFAULT.get(tr_data[4]))
            self.select_active_text(self._sys_combo_box, SystemCable(tr_data[5]).name)
        elif tr_type is TrType.Terrestrial:
            self.select_active_text(self._fec_combo_box, T_FEC.get(tr_data[2]))
            self.select_active_text(self._rate_lp_combo_box, T_FEC.get(tr_data[3]))
            # Pol -> Bandwidth
            self.select_active_text(self._pol_combo_box, BANDWIDTH.get(tr_data[1]))
            self.select_active_text(self._mod_combo_box, T_MODULATION.get(tr_data[4]))
            # Transmission Mode -> Roll off
            self.select_active_text(self._rolloff_combo_box, TRANSMISSION_MODE.get(tr_data[5]))
            # GuardInterval -> Pilot
            self.select_active_text(self._pilot_combo_box, GUARD_INTERVAL.get(tr_data[6]))
            # Hierarchy -> Pls Mode
            self.select_active_text(self._pls_mode_combo_box, HIERARCHY.get(tr_data[7]))
            self.select_active_text(self._invertion_combo_box, Inversion(tr_data[8]).name)
            self.select_active_text(self._sys_combo_box, T_SYSTEM.get(tr_data[9]))
        elif tr_type is TrType.ATSC:
            self._sys_combo_box.set_active(0)
            self.select_active_text(self._mod_combo_box, A_MODULATION.get(tr_data[2]))
            self.select_active_text(self._invertion_combo_box, Inversion(tr_data[1]).name)

        # Should be called last to properly initialize the reference
        self._srv_type_entry.set_text(data[4])

    # ***************** Init Neutrino data *********************#

    def init_neutrino_data(self, srv):
        if self._tr_type is not TrType.Satellite:
            return
        tr_data = get_attributes(srv.transponder)
        self._transponder_id_entry.set_text(str(int(tr_data.get("id", "0"), 16)))
        self._network_id_entry.set_text(str(int(tr_data.get("on", "0"), 16)))
        self.select_active_text(self._invertion_combo_box, Inversion(tr_data.get("inv", "2")).name)
        self.select_active_text(self._service_type_combo_box, srv.service_type)
        self.update_reference_entry()

    def init_neutrino_ui_elements(self):
        self._builder.get_object("flags_box").set_visible(False)
        self._builder.get_object("pids_grid").set_visible(False)
        tr_grid = self._builder.get_object("tr_grid")
        tr_grid.remove_column(7)
        tr_grid.set_margin_bottom(5)
        self._builder.get_object("extra_transponder_grid").set_visible(False)
        self._package_entry.set_sensitive(False)

    # ***************** Init Sat positions *********************#

    def set_sat_positions(self, sat_pos):
        """ Sat positions initialisation """
        self._sat_pos_button.set_value(float(sat_pos[:-1]))
        self._pos_side_box.set_active_id(sat_pos[-1:])

    def on_system_changed(self, box):
        if not self._tr_edit_switch.get_active():
            return
        active = box.get_active()
        self.update_dvb_s2_elements(active)

    def update_dvb_s2_elements(self, active):
        for elem in self._DVB_S2_ELEMENTS:
            elem.set_sensitive(active)
        self._pls_code_entry.set_name("GtkEntry")
        self._stream_id_entry.set_name("GtkEntry")

        if active:
            if not self._mod_combo_box.get_active_id():
                self._mod_combo_box.set_active_id(MODULATION["2"])
            if not self._rolloff_combo_box.get_active_id():
                self._rolloff_combo_box.set_active_id(ROLL_OFF["0"])
            if not self._pilot_combo_box.get_active_id():
                self._pilot_combo_box.set_active_id(Pilot.Auto.name)
            if not self._pls_mode_combo_box.get_active_id():
                self._pls_mode_combo_box.set_active_id(PLS_MODE["0"])

    # ***************** Save data *********************#

    def on_save(self, item):
        self.save_data()

    def on_create_new(self, item):
        self.save_data()

    def save_data(self):
        if self._s_type is SettingsType.NEUTRINO_MP and self._tr_type is not TrType.Satellite:
            show_dialog(DialogType.ERROR, transient=self._dialog, text="Not implemented yet!")
            return

        if not self.is_data_correct():
            show_dialog(DialogType.ERROR, self._dialog, "Error. Verify the data!")
            return

        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        if self.on_edit() if self._action is Action.EDIT else self.on_new():
            self._dialog.destroy()

    def on_new(self):
        """ Create new service. """
        service = self.get_service(*self.get_srv_data(), self.get_satellite_transponder_data())
        show_dialog(DialogType.ERROR, transient=self._dialog, text="Not implemented yet!")
        return True

    def on_edit(self):
        """ Edit current service.  """
        fav_id, data_id = self.get_srv_data()
        # Transponder
        transponder = self._old_service.transponder
        if self._tr_edit_switch.get_active():
            try:
                if self._tr_type is TrType.Satellite:
                    transponder = self.get_satellite_transponder_data()
                elif self._tr_type is TrType.Terrestrial:
                    transponder = self.get_terrestrial_transponder_data()
                elif self._tr_type is TrType.Cable:
                    transponder = self.get_cable_transponder_data()
                elif self._tr_type is TrType.ATSC:
                    transponder = self.get_atsc_transponder_data()
            except Exception as e:
                log("Edit service error: {}".format(e))
                show_dialog(DialogType.ERROR, transient=self._dialog, text="Error getting transponder parameters!")
            else:
                if self._transponder_services_iters:
                    self.update_transponder_services(transponder, self.get_sat_position())
        # Service
        service = self.get_service(fav_id, data_id, transponder)
        old_fav_id = self._old_service.fav_id
        if old_fav_id != fav_id:
            if fav_id in self._services:
                msg = "{}\n\n\t{}".format("A similar service is already in this list!", "Are you sure?")
                if show_dialog(DialogType.QUESTION, transient=self._dialog, text=msg) != Gtk.ResponseType.OK:
                    return False
            self.update_bouquets(fav_id, old_fav_id)

        self._services[fav_id] = service

        if self._old_service.picon_id != service.picon_id:
            self.update_picon_name(self._old_service.picon_id, service.picon_id)

        flags = service.flags_cas
        extra_data = {Column.SRV_TOOLTIP: None, Column.SRV_BACKGROUND: None}
        if self._s_type is SettingsType.ENIGMA_2 and flags:
            f_flags = list(filter(lambda x: x.startswith("f:"), flags.split(",")))
            if f_flags and Flag.is_new(Flag.parse(f_flags[0])):
                extra_data[Column.SRV_BACKGROUND] = self._new_color

        self._current_model.set(self._current_itr, extra_data)
        self._current_model.set(self._current_itr, {i: v for i, v in enumerate(service)})
        self.update_fav_view(self._old_service, service)
        self._old_service = service
        return True

    def update_bouquets(self, fav_id, old_fav_id):
        self._services.pop(old_fav_id, None)
        for bq in self._bouquets.values():
            indexes = []
            for i, f_id in enumerate(bq):
                if old_fav_id == f_id:
                    indexes.append(i)
            for i in indexes:
                bq[i] = fav_id

    @run_idle
    def update_fav_view(self, old_service, new_service):
        model = self._fav_view.get_model()
        for row in filter(lambda r: old_service.fav_id == r[7], model):
            itr = row.iter
            if not model.get_value(itr, Column.FAV_BACKGROUND):
                model.set_value(itr, Column.FAV_SERVICE, new_service.service)

            model.set(itr, {Column.FAV_CODED: new_service.coded,
                            Column.FAV_LOCKED: new_service.locked,
                            Column.FAV_HIDE: new_service.hide,
                            Column.FAV_TYPE: new_service.service_type,
                            Column.FAV_POS: new_service.pos,
                            Column.FAV_ID: new_service.fav_id,
                            Column.FAV_PICON: new_service.picon})

    def update_picon_name(self, old_name, new_name):
        if not os.path.isdir(self._picons_path):
            return

        for file_name in os.listdir(self._picons_path):
            if file_name == old_name:
                old_file = os.path.join(self._picons_path, old_name)
                new_file = os.path.join(self._picons_path, new_name)
                os.rename(old_file, new_file)
                break

    # ***************** Service ********************* #

    def get_service(self, fav_id, data_id, transponder):
        freq, rate, pol, fec, system, pos = self.get_transponder_values()
        return Service(flags_cas=self.get_flags(),
                       transponder_type=self._old_service.transponder_type,
                       coded=CODED_ICON if self._cas_entry.get_text() else None,
                       service=self._name_entry.get_text(),
                       locked=self._old_service.locked,
                       hide=HIDE_ICON if self._hide_check_button.get_active() else None,
                       package=self._package_entry.get_text(),
                       service_type=SERVICE_TYPE.get(self._srv_type_entry.get_text(), SERVICE_TYPE["3"]),
                       picon=self._old_service.picon,
                       picon_id=self._reference_label.get_text().replace(":", "_") + ".png",
                       ssid="{:04x}".format(int(self._sid_entry.get_text())),
                       freq=freq,
                       rate=rate,
                       pol=pol,
                       fec=fec,
                       system=system,
                       pos=pos,
                       data_id=data_id,
                       fav_id=fav_id,
                       transponder=transponder)

    def get_flags(self):
        if self._s_type is SettingsType.ENIGMA_2:
            return self.get_enigma2_flags()
        elif self._s_type is SettingsType.NEUTRINO_MP:
            flags = get_attributes(self._old_service.flags_cas)
            flags["position"] = self.get_sat_position()
            return SP.join("{}{}{}".format(k, KSP, v) for k, v in flags.items())

    def get_enigma2_flags(self):
        flags = ["p:{}".format(self._package_entry.get_text())]
        # cas
        cas = self._cas_entry.get_text()
        if cas:
            flags.append(cas)
        # pids
        video_pid = self._video_pid_entry.get_text()
        if video_pid:
            flags.append("{}{:04x}".format(Pids.VIDEO.value, int(video_pid)))
        audio_pid = self._audio_pid_entry.get_text()
        if audio_pid:
            flags.append("{}{:04x}".format(Pids.AUDIO.value, int(audio_pid)))
        teletext_pid = self._teletext_pid_entry.get_text()
        if teletext_pid:
            flags.append("{}{:04x}".format(Pids.TELETEXT.value, int(teletext_pid)))
        pcr_pid = self._pcr_pid_entry.get_text()
        if pcr_pid:
            flags.append("{}{:04x}".format(Pids.PCR.value, int(pcr_pid)))
        ac3_pid = self._ac3_pid_entry.get_text()
        if ac3_pid:
            flags.append("{}{:04x}".format(Pids.AC3.value, int(ac3_pid)))
        bitstream_pid = self._bitstream_entry.get_text()
        if bitstream_pid:
            flags.append("{}{:04x}".format(Pids.BIT_STREAM_DELAY.value, int(bitstream_pid)))
        pcm_pid = self._pcm_entry.get_text()
        if pcm_pid:
            flags.append("{}{:04x}".format(Pids.PCM_DELAY.value, int(pcm_pid)))
        extra_pids = self._extra_pids_entry.get_text()
        if extra_pids:
            flags.append(extra_pids)
        # flags
        f_flags = Flag.KEEP.value if self._keep_check_button.get_active() else 0
        f_flags = f_flags + Flag.HIDE.value if self._hide_check_button.get_active() else f_flags
        f_flags = f_flags + Flag.PIDS.value if self._use_pids_check_button.get_active() else f_flags
        f_flags = f_flags + Flag.NEW.value if self._new_check_button.get_active() else f_flags
        if f_flags:
            flags.append("f:{:02d}".format(f_flags))

        return ",".join(flags)

    def get_srv_data(self):
        ssid = int(self._sid_entry.get_text())
        net_id, tr_id = int(self._network_id_entry.get_text()), int(self._transponder_id_entry.get_text())
        service_type = self._srv_type_entry.get_text()

        if self._s_type is SettingsType.ENIGMA_2:
            namespace = int(self._namespace_entry.get_text())
            data_id = self._ENIGMA2_DATA_ID.format(ssid, namespace, tr_id, net_id, service_type, 0)
            fav_id = self._ENIGMA2_FAV_ID.format(ssid, tr_id, net_id, namespace)
            return fav_id, data_id
        elif self._s_type is SettingsType.NEUTRINO_MP:
            data = get_attributes(self._old_service.data_id)
            data["n"] = self._name_entry.get_text()
            data["t"] = "{:x}".format(int(service_type))
            data["i"] = "{:04x}".format(ssid)
            fav_id = self._NEUTRINO_FAV_ID.format(tr_id, net_id, ssid)
            return fav_id, SP.join("{}{}{}".format(k, KSP, v) for k, v in data.items())

    # ***************** Transponder ********************* #

    def get_transponder_values(self):
        freq = self._freq_entry.get_text()
        fec = self._fec_combo_box.get_active_id()
        system = self._sys_combo_box.get_active_id()
        o_srv = self._old_service

        if self._tr_type is TrType.Satellite or self._s_type is SettingsType.NEUTRINO_MP:
            freq = self._freq_entry.get_text()
            rate = self._rate_entry.get_text()
            pol = self._pol_combo_box.get_active_id()
            pos = "{}{}".format(round(self._sat_pos_button.get_value(), 1), self._pos_side_box.get_active_id())
            return freq, rate, pol, fec, system, pos
        elif self._tr_type in (TrType.Terrestrial, TrType.ATSC):
            return freq, o_srv.rate, o_srv.pol, fec, system, o_srv.pos
        elif self._tr_type is TrType.Cable:
            return freq, self._rate_entry.get_text(), o_srv.pol, fec, o_srv.system, o_srv.pos

    def get_satellite_transponder_data(self):
        sys = self._sys_combo_box.get_active_id()
        freq = "{}000".format(self._freq_entry.get_text())
        rate = "{}000".format(self._rate_entry.get_text())
        pol = self.get_value_from_combobox_id(self._pol_combo_box, POLARIZATION)
        fec = self.get_value_from_combobox_id(self._fec_combo_box, FEC_DEFAULT)
        sat_pos = self.get_sat_position()

        inv = get_value_by_name(Inversion, self._invertion_combo_box.get_active_id())
        srv_sys = "0"  # !!!

        if self._s_type is SettingsType.ENIGMA_2:
            dvb_s_tr = self._ENIGMA2_TRANSPONDER_DATA.format("s", freq, rate, pol, fec, sat_pos, inv, srv_sys)
            if sys == "DVB-S":
                return dvb_s_tr
            if sys == "DVB-S2":
                flag = self._tr_flag_entry.get_text()
                mod = self.get_value_from_combobox_id(self._mod_combo_box, MODULATION)
                roll_off = self.get_value_from_combobox_id(self._rolloff_combo_box, ROLL_OFF)
                pilot = get_value_by_name(Pilot, self._pilot_combo_box.get_active_id())
                pls_mode = self.get_value_from_combobox_id(self._pls_mode_combo_box, PLS_MODE)
                pls_code = self._pls_code_entry.get_text()
                st_id = self._stream_id_entry.get_text()
                pls = ":{}:{}:{}".format(st_id, pls_code, pls_mode) if pls_mode and pls_code and st_id else ""

                return "{}:{}:{}:{}:{}{}".format(dvb_s_tr, flag, mod, roll_off, pilot, pls)
        elif self._s_type is SettingsType.NEUTRINO_MP:
            tr_data = get_attributes(self._old_service.transponder)
            tr_data["frq"] = freq
            tr_data["sr"] = rate
            tr_data["pol"] = pol
            tr_data["fec"] = fec
            tr_data["on"] = "{:04x}".format(int(self._network_id_entry.get_text()))
            tr_data["id"] = "{:04x}".format(int(self._transponder_id_entry.get_text()))
            tr_data["inv"] = inv

            return SP.join("{}{}{}".format(k, KSP, v) for k, v in tr_data.items())

    def get_sat_position(self):
        sat_pos = self._sat_pos_button.get_value() * (-1 if self._pos_side_box.get_active_id() == "W" else 1)
        sat_pos = str(round(sat_pos, 1)).replace(".", "")
        return sat_pos

    def get_terrestrial_transponder_data(self):
        tr_data = re.split("\s|:", self._old_service.transponder)
        # frequency, bandwidth, code rate HP, code rate LP, modulation, transmission mode, guard interval, hierarchy,
        # inversion, system, plp_id
        # Bandwidth -> Pol, Rate HP -> FEC, TransmissionMode -> Roll off, GuardInterval -> Pilot, Hierarchy -> Pls Mode
        tr_data[1] = "{}000".format(self._freq_entry.get_text())
        tr_data[2] = self.get_value_from_combobox_id(self._pol_combo_box, BANDWIDTH)
        tr_data[3] = self.get_value_from_combobox_id(self._fec_combo_box, T_FEC)
        tr_data[4] = self.get_value_from_combobox_id(self._rate_lp_combo_box, T_FEC)
        tr_data[5] = self.get_value_from_combobox_id(self._mod_combo_box, T_MODULATION)
        tr_data[6] = self.get_value_from_combobox_id(self._rolloff_combo_box, TRANSMISSION_MODE)
        tr_data[7] = self.get_value_from_combobox_id(self._pilot_combo_box, GUARD_INTERVAL)
        tr_data[8] = self.get_value_from_combobox_id(self._pls_mode_combo_box, HIERARCHY)
        tr_data[9] = get_value_by_name(Inversion, self._invertion_combo_box.get_active_id())
        tr_data[10] = self.get_value_from_combobox_id(self._sys_combo_box, T_SYSTEM)

        return "{} {}".format(tr_data[0], ":".join(tr_data[1:]))

    def get_cable_transponder_data(self):
        tr_data = re.split("\s|:", self._old_service.transponder)
        # frequency, symbol_rate, modulation, inversion, fec_inner, system;
        tr_data[1] = "{}000".format(self._freq_entry.get_text())
        tr_data[2] = "{}000".format(self._rate_entry.get_text())
        tr_data[3] = get_value_by_name(Inversion, self._invertion_combo_box.get_active_id())
        tr_data[4] = self.get_value_from_combobox_id(self._mod_combo_box, C_MODULATION)
        tr_data[5] = self.get_value_from_combobox_id(self._fec_combo_box, FEC_DEFAULT)
        tr_data[6] = get_value_by_name(SystemCable, self._sys_combo_box.get_active_id())

        return "{} {}".format(tr_data[0], ":".join(tr_data[1:]))

    def get_atsc_transponder_data(self):
        tr_data = re.split("\s|:", self._old_service.transponder)
        # frequency, inversion, modulation, system
        tr_data[1] = "{}000".format(self._freq_entry.get_text())
        tr_data[2] = get_value_by_name(Inversion, self._invertion_combo_box.get_active_id())
        tr_data[3] = self.get_value_from_combobox_id(self._mod_combo_box, A_MODULATION)

        return "{} {}".format(tr_data[0], ":".join(tr_data[1:]))

    def update_transponder_services(self, transponder, sat_pos):
        for itr in self._transponder_services_iters:
            srv = self._current_model[itr][:]
            srv[Column.SRV_FREQ], srv[Column.SRV_RATE], srv[Column.SRV_POL], srv[Column.SRV_FEC], srv[
                Column.SRV_SYSTEM], srv[Column.SRV_POS] = self.get_transponder_values()
            srv[Column.SRV_TRANSPONDER] = transponder

            fav_id = srv[Column.SRV_FAV_ID]
            old_srv = self._services.pop(fav_id, None)
            if not old_srv:
                log("Update transponder services error: No service found for ID {}".format(srv[Column.SRV_FAV_ID]))
                continue

            if self._s_type is SettingsType.NEUTRINO_MP:
                flags = get_attributes(srv[Column.SRV_CAS_FLAGS])
                flags["position"] = sat_pos
                srv[Column.SRV_CAS_FLAGS] = SP.join("{}{}{}".format(k, KSP, v) for k, v in flags.items())

            self._services[fav_id] = Service(*srv[:Column.SRV_TOOLTIP])
            self._current_model.set_row(itr, srv)

    # ***************** Others *********************#

    def select_active_text(self, box, text):
        model = box.get_model()
        for index, row in enumerate(model):
            if row[0] == text:
                box.set_active(index)
                break

    def on_digit_entry_changed(self, entry):
        entry.set_name(self._DIGIT_ENTRY_NAME if self._DIGIT_PATTERN.search(entry.get_text()) else "GtkEntry")

    def on_non_empty_entry_changed(self, entry):
        entry.set_name(self._DIGIT_ENTRY_NAME if self._NON_EMPTY_PATTERN.search(entry.get_text()) else "GtkEntry")

    def on_cas_entry_changed(self, entry):
        entry.set_name("GtkEntry" if self._CAID_PATTERN.fullmatch(entry.get_text()) else self._DIGIT_ENTRY_NAME)

    def on_extra_pids_entry_changed(self, entry):
        entry.set_name("GtkEntry" if self._PIDS_PATTERN.fullmatch(entry.get_text()) else self._DIGIT_ENTRY_NAME)

    def get_value_from_combobox_id(self, box: Gtk.ComboBox, dc: dict):
        cb_id = box.get_active_id()
        return get_key_by_value(dc, cb_id)

    @run_idle
    def on_tr_edit_toggled(self, switch, active):
        if active and self._action is Action.EDIT:
            self._transponder_services_iters = []
            response = TransponderServicesDialog(self._dialog,
                                                 self._services_view,
                                                 self._old_service.transponder,
                                                 self._transponder_services_iters).show()
            if response == Gtk.ResponseType.CANCEL or response == Gtk.ResponseType.DELETE_EVENT:
                switch.set_active(False)
                self._transponder_services_iters = None
                return

        self.update_dvb_s2_elements(active and (self._sys_combo_box.get_active_id() == "DVB-S2"
                                                or self._old_service.transponder_type in "tca"))

        for elem in self._TRANSPONDER_ELEMENTS:
            elem.set_sensitive(active)

    def is_data_correct(self):
        for elem in self._digit_elements.values():
            if elem.get_name() == self._DIGIT_ENTRY_NAME:
                return False
        for elem in self._non_empty_elements.values():
            if elem.get_name() == self._DIGIT_ENTRY_NAME:
                return False
        if self._cas_entry.get_name() == self._DIGIT_ENTRY_NAME:
            return False
        if self._extra_pids_entry.get_name() == self._DIGIT_ENTRY_NAME:
            return False
        return True

    def update_reference(self, entry, event=None):
        if not self.is_data_correct() or (event is None and self._s_type is SettingsType.NEUTRINO_MP):
            return
        self.update_reference_entry()

    def update_reference_entry(self):
        srv_type = int(self._srv_type_entry.get_text())
        ssid = int(self._sid_entry.get_text())
        tid = int(self._transponder_id_entry.get_text())
        nid = int(self._network_id_entry.get_text())
        if self._s_type is SettingsType.ENIGMA_2:
            on_id = int(self._namespace_entry.get_text())
            ref = "1:0:{:X}:{:X}:{:X}:{:X}:{:X}:0:0:0".format(srv_type, ssid, tid, nid, on_id)
            self._reference_label.set_text(ref)
        else:
            self._reference_label.set_text("{:x}{:04x}{:04x}".format(tid, nid, ssid))

    def update_ui_for_terrestrial(self):
        tr_grid = self.get_transponder_grid_for_non_satellite()
        tr_grid.remove_column(1)
        tr_grid.insert_column(1)
        extra_tr_grid = self._builder.get_object("extra_transponder_grid")
        for i in range(4):
            extra_tr_grid.remove_column(6)
        # Bandwidth -> Pol
        pol_label = self._builder.get_object("pol_label")
        pol_label.set_text("Bandwidth")
        tr_grid.attach(pol_label, 1, 0, 1, 1)
        tr_grid.attach(self._pol_combo_box, 1, 1, 1, 1)
        # Rate HP -> FEC
        self._builder.get_object("fec_label").set_text("Rate HP")
        # Rate LP
        tr_grid.insert_column(3)
        rate_lp_label = self._builder.get_object("pls_code_label")
        rate_lp_label.set_text("Rate LP")
        tr_grid.attach(rate_lp_label, 3, 0, 1, 1)
        tr_grid.attach(self._rate_lp_combo_box, 3, 1, 1, 1)
        # Modulation
        tr_grid.insert_column(4)
        extra_tr_grid.remove_column(1)
        tr_grid.attach(self._builder.get_object("mod_label"), 4, 0, 1, 1)
        tr_grid.attach(self._mod_combo_box, 4, 1, 1, 1)
        # TransmissionMode -> Roll off
        rolloff_label = self._builder.get_object("rolloff_label")
        rolloff_label.set_text("T mode")
        # GuardInterval -> Pilot
        pilot_label = self._builder.get_object("pilot_label")
        pilot_label.set_text("Guard Interval")
        # Hierarchy -> Pls Mode
        pls_mode_label = self._builder.get_object("pls_mode_label")
        pls_mode_label.set_text("Hierarchy")
        # Models
        fec_model, modulation_model, sys_model = self.get_models_for_non_satellite()
        pol_model = self._pol_combo_box.get_model()
        roll_off_model = self._rolloff_combo_box.get_model()
        pilot_model = self._pilot_combo_box.get_model()
        pls_model = self._pls_mode_combo_box.get_model()
        # Models clearing
        for m in pol_model, roll_off_model, pilot_model, pls_model:
            m.clear()

        self.init_terrestrial_models((pol_model, modulation_model, roll_off_model, pilot_model, pls_model, sys_model),
                                     (BANDWIDTH, T_MODULATION, TRANSMISSION_MODE, GUARD_INTERVAL, HIERARCHY, T_SYSTEM))

        # Removing the latest FEC elements from the model
        for itr in [fec_model.get_iter(Gtk.TreePath.new_from_string(str(i))) for i in range(7, 11)]:
            fec_model.remove(itr)
        # Extra
        self._namespace_entry.set_max_width_chars(15)
        self._sys_combo_box.set_hexpand(False)

    def init_terrestrial_models(self, models, properties):
        for index, model in enumerate(models):
            for v in properties[index].values():
                model.append((v,))

    def update_ui_for_cable(self):
        tr_grid = self.get_transponder_grid_for_non_satellite()
        tr_box = self._builder.get_object("tr_box")
        # Models
        fec_model, modulation_model, system_model = self.get_models_for_non_satellite()

        extra_tr_grid = self._builder.get_object("extra_transponder_grid")
        for child in extra_tr_grid.get_children():
            extra_tr_grid.remove(child)
        tr_grid.remove(extra_tr_grid)

        tr_grid.insert_column(3)
        tr_grid.insert_column(4)
        tr_grid.insert_column(5)
        # Modulation
        tr_grid.attach(self._builder.get_object("mod_label"), 3, 0, 1, 1)
        tr_grid.attach(self._mod_combo_box, 3, 1, 1, 1)
        for v in C_MODULATION.values():
            modulation_model.append((v,))
        # Inversion
        tr_grid.attach(self._builder.get_object("inversion_label"), 4, 0, 1, 1)
        tr_grid.attach(self._invertion_combo_box, 4, 1, 1, 1)
        # System
        tr_grid.attach(self._builder.get_object("system_label"), 5, 0, 1, 1)
        tr_grid.attach(self._sys_combo_box, 5, 1, 1, 1)
        system_model.append((SystemCable.ANNEX_A.name,))
        system_model.append((SystemCable.ANNEX_C.name,))
        # FEC
        fec_model.append(("None",))
        # Extra
        tr_grid.set_margin_bottom(5)
        self._freq_entry.set_width_chars(10)
        self._freq_entry.set_max_width_chars(10)
        self._rate_entry.set_width_chars(10)
        self._rate_entry.set_max_width_chars(10)
        self._transponder_id_entry.set_max_width_chars(8)
        self._network_id_entry.set_max_width_chars(8)

    def update_ui_for_atsc(self):
        self.update_ui_for_cable()
        tr_grid = self._builder.get_object("tr_grid")
        tr_grid.remove_column(1)
        tr_grid.remove_column(1)
        # Init models
        fec_model, modulation_model, system_model = self.get_models_for_non_satellite()
        system_model.append((TrType.ATSC.name,))
        [modulation_model.append((v,)) for k, v in A_MODULATION.items()]
        # Extra
        self._namespace_entry.set_max_width_chars(25)

    def get_transponder_grid_for_non_satellite(self):
        self._pids_grid.set_visible(False)
        tr_grid = self._builder.get_object("tr_grid")
        tr_grid.remove_column(0)
        tr_grid.remove_column(2)
        return tr_grid

    def get_models_for_non_satellite(self):
        fec_model = self._fec_combo_box.get_model()
        modulation_model = self._mod_combo_box.get_model()
        modulation_model.clear()
        system_model = self._sys_combo_box.get_model()
        system_model.clear()
        return fec_model, modulation_model, system_model


class TransponderServicesDialog:
    def __init__(self, transient, services_view, transponder, tr_iters):
        builder = get_builder(_UI_PATH, use_str=True, objects=("tr_services_dialog", "transponder_services_liststore"))
        self._dialog = builder.get_object("tr_services_dialog")
        self._dialog.set_transient_for(transient)
        self._srv_model = builder.get_object("transponder_services_liststore")
        self.append_services(services_view, transponder, tr_iters)
        builder.get_object("srv_list_dialog_info_bar").connect("response", lambda bar, resp: bar.hide())

    def append_services(self, view, transponder, tr_iters):
        model = view.get_model()
        filter_model = model.get_model()
        for row in model:
            if row[Column.SRV_TRANSPONDER] == transponder:
                self._srv_model.append((row[Column.SRV_SERVICE], row[Column.SRV_PACKAGE], row[Column.SRV_TYPE],
                                        row[Column.SRV_SSID], row[Column.SRV_FREQ], row[Column.SRV_POS]))
                itr = model.get_iter(row.path)
                tr_iters.append(filter_model.convert_iter_to_child_iter(model.convert_iter_to_child_iter(itr)))

    def show(self):
        response = self._dialog.run()
        self._dialog.destroy()
        return response


if __name__ == "__main__":
    pass

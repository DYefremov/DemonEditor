import re
from math import fabs

from app.commons import run_idle
from app.eparser import Service, get_satellites
from app.eparser.ecommons import MODULATION, Inversion, ROLL_OFF, Pilot, Flag, Pids, POLARIZATION, \
    get_key_by_value, get_value_by_name, FEC_DEFAULT, PLS_MODE
from app.properties import Profile
from . import Gtk, Gdk, UI_RESOURCES_PATH, HIDE_ICON, TEXT_DOMAIN
from .dialogs import show_dialog, DialogType, Action
from .main_helper import get_base_model


class ServiceDetailsDialog:
    _ENIGMA2_DATA_ID = "{:04x}:{:08x}:{:04x}:{:04x}:{}:{}"

    _ENIGMA2_FAV_ID = "{:X}:{:X}:{:X}:{:X}"

    _ENIGMA2_TRANSPONDER_DATA = "{} {}:{}:{}:{}:{}:{}:{}"

    _NEUTRINO_FAV_ID = "{:x}:{:x}:{:x}"

    _NEUTRINO_TRANSPONDER_DATA = "{:04x}:{:04x}:{}:{}:{}:{}:{}:{}:{}"

    _DIGIT_ENTRY_ELEMENTS = ("bitstream_entry", "pcm_entry", "video_pid_entry", "pcr_pid_entry", "srv_type_entry",
                             "ac3_pid_entry", "ac3plus_pid_entry", "acc_pid_entry", "he_acc_pid_entry",
                             "teletext_pid_entry", "pls_code_entry", "stream_id_entry", "tr_flag_entry",
                             "audio_pid_entry", "namespace_entry")
    _NOT_EMPTY_DIGIT_ELEMENTS = ("sid_entry", "freq_entry", "rate_entry", "transponder_id_entry", "network_id_entry")

    _DIGIT_ENTRY_NAME = "digit-entry"

    def __init__(self, transient, options, view, services, bouquets, action=Action.EDIT):
        handlers = {"on_system_changed": self.on_system_changed,
                    "on_save": self.on_save,
                    "on_create_new": self.on_create_new,
                    "on_digit_entry_changed": self.on_digit_entry_changed,
                    "on_tr_edit_toggled": self.on_tr_edit_toggled,
                    "on_non_empty_entry_changed": self.on_non_empty_entry_changed}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_from_file(UI_RESOURCES_PATH + "service_details_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("service_details_dialog")
        self._dialog.set_transient_for(transient)
        self._profile = Profile(options["profile"])
        self._satellites_xml_path = options.get(self._profile.value)["data_dir_path"] + "satellites.xml"
        self._services_view = view
        self._action = action
        self._old_service = None
        self._services = services
        self._bouquets = bouquets
        self._transponder_services_iters = None
        self._current_model = None
        self._current_itr = None
        self._DIGIT_PATTERN = re.compile("\D")
        self._NON_EMPTY_PATTERN = re.compile("(?:^[\s]*$|\D)")
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
        self._namespace_entry = self._digit_elements.get("namespace_entry")
        # Service elements
        self._name_entry = builder.get_object("name_entry")
        self._package_entry = builder.get_object("package_entry")
        self._srv_type_entry = builder.get_object("srv_type_entry")
        self._service_type_combo_box = builder.get_object("service_type_combo_box")
        self._cas_entry = builder.get_object("cas_entry")
        self._reference_entry = builder.get_object("reference_entry")
        self._keep_check_button = builder.get_object("keep_check_button")
        self._hide_check_button = builder.get_object("hide_check_button")
        self._use_pids_check_button = builder.get_object("use_pids_check_button")
        self._new_check_button = builder.get_object("new_check_button")
        self._pids_grid = builder.get_object("pids_grid")
        # Transponder elements
        self._sat_pos_button = builder.get_object("sat_pos_button")
        self._pol_combo_box = builder.get_object("pol_combo_box")
        self._fec_combo_box = builder.get_object("fec_combo_box")
        self._sys_combo_box = builder.get_object("sys_combo_box")
        self._mod_combo_box = builder.get_object("mod_combo_box")
        self._invertion_combo_box = builder.get_object("invertion_combo_box")
        self._rolloff_combo_box = builder.get_object("rolloff_combo_box")
        self._pilot_combo_box = builder.get_object("pilot_combo_box")
        self._pls_mode_combo_box = builder.get_object("pls_mode_combo_box")
        self._tr_edit_switch = builder.get_object("tr_edit_switch")
        self._tr_extra_expander = builder.get_object("tr_extra_expander")

        self._DVB_S2_ELEMENTS = (self._mod_combo_box, self._rolloff_combo_box, self._pilot_combo_box,
                                 self._pls_mode_combo_box, self._pls_code_entry, self._stream_id_entry)
        self._TRANSPONDER_ELEMENTS = (self._sat_pos_button, self._pol_combo_box, self._invertion_combo_box,
                                      self._sys_combo_box, self._freq_entry, self._transponder_id_entry,
                                      self._network_id_entry, self._namespace_entry, self._fec_combo_box,
                                      self._rate_entry)

        if self._action is Action.EDIT:
            self.update_data_elements()
        elif self._action is Action.ADD:
            self.init_default_data_elements()

    def show(self):
        response = self._dialog.run()
        if response == Gtk.ResponseType.OK:
            pass
        self._dialog.destroy()

        return response

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
        self._tr_extra_expander.activate()
        self._service_type_combo_box.set_active(0)
        self._pol_combo_box.set_active(0)
        self._fec_combo_box.set_active(0)
        self._sys_combo_box.set_active(0)
        self._invertion_combo_box.set_active(2)

    @run_idle
    def update_data_elements(self):
        model, paths = self._services_view.get_selection().get_selected_rows()
        itr = model.get_iter(paths)
        # Unpacking to search for an iterator for the base model
        filter_model = model.get_model()
        itr = filter_model.convert_iter_to_child_iter(model.convert_iter_to_child_iter(itr))
        self._current_model = get_base_model(model)
        srv = Service(*self._current_model[itr][:])
        self._old_service = srv
        self._current_itr = itr
        # Service
        self._name_entry.set_text(srv.service)
        self._package_entry.set_text(srv.package)
        self.select_active_text(self._service_type_combo_box, srv.service_type)
        self._sid_entry.set_text(str(int(srv.ssid, 16)))
        # Transponder
        self._freq_entry.set_text(srv.freq)
        self._rate_entry.set_text(srv.rate)
        self.select_active_text(self._pol_combo_box, srv.pol)
        self.select_active_text(self._fec_combo_box, srv.fec)
        self.select_active_text(self._sys_combo_box, srv.system)
        self.set_sat_positions(srv.pos)

        if self._profile is Profile.ENIGMA_2:
            self.init_enigma2_service_data(srv)
            self.init_enigma2_transponder_data(srv)
        elif self._profile is Profile.NEUTRINO_MP:
            self.init_neutrino_data(srv)
            self.init_enigma_ui_elements()

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

        self._reference_entry.set_text(srv.picon_id.replace("_", ":").rstrip(".png"))

    def init_enigma2_flags(self, flags):
        f_flags = list(filter(lambda x: x.startswith("f:"), flags))
        if f_flags:
            value = int(f_flags[0][2:])
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
                    pass
                elif pid.startswith(Pids.AUDIO_CHANNEL.value):
                    pass
                elif pid.startswith(Pids.BIT_STREAM_DELAY.value):
                    self._bitstream_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.PCM_DELAY.value):
                    self._pcm_entry.set_text(str(int(pid[4:], 16)))
                elif pid.startswith(Pids.SUBTITLE.value):
                    pass

    @run_idle
    def init_enigma2_transponder_data(self, srv):
        """ Transponder data initialisation """
        data = srv.data_id.split(":")
        tr_data = srv.transponder.split(":")

        if srv.system == "DVB-S2":
            self.select_active_text(self._mod_combo_box, MODULATION.get(tr_data[8]))
            self.select_active_text(self._rolloff_combo_box, ROLL_OFF.get(tr_data[9]))
            self.select_active_text(self._pilot_combo_box, Pilot(tr_data[10]).name)
            self._tr_flag_entry.set_text(tr_data[7])
            if len(tr_data) > 12:
                self._stream_id_entry.set_text(tr_data[11])
                self._pls_code_entry.set_text(tr_data[12])
                self.select_active_text(self._pls_mode_combo_box, PLS_MODE.get(tr_data[13]))

        self._srv_type_entry.set_text(data[4])
        self._namespace_entry.set_text(str(int(data[1], 16)))
        self._transponder_id_entry.set_text(str(int(data[2], 16)))
        self._network_id_entry.set_text(str(int(data[3], 16)))
        self.select_active_text(self._invertion_combo_box, Inversion(tr_data[5]).name)

    # ***************** Init Neutrino data *********************#

    def init_neutrino_data(self, srv):
        srv_data = srv.data_id.split(":")
        tr_data = srv.transponder.split(":")
        self._reference_entry.set_text(srv.picon_id.rstrip(".png"))
        self._transponder_id_entry.set_text(str(int(tr_data[0], 16)))
        self._network_id_entry.set_text(str(int(tr_data[1], 16)))
        self.select_active_text(self._invertion_combo_box, Inversion(tr_data[3]).name)

    def init_enigma_ui_elements(self):
        self._pids_grid.set_sensitive(False)
        self._cas_entry.set_sensitive(False)
        self._keep_check_button.set_sensitive(False)
        self._hide_check_button.set_sensitive(False)
        self._use_pids_check_button.set_sensitive(False)
        self._new_check_button.set_sensitive(False)

    # ***************** Init Sat positions *********************#

    @run_idle
    def set_sat_positions(self, sat_pos):
        """ Sat positions initialisation """
        pos = float(sat_pos)
        self._sat_pos_button.set_value(fabs(pos))

    def get_sat_positions(self, path):
        try:
            return ["{:.1f}".format(float(x.position) / 10) for x in get_satellites(path)]
        except FileNotFoundError:
            return {r[-4] for r in self._current_model}

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

    # ***************** Save data *********************#

    def on_save(self, item):
        self.save_data()

    def on_create_new(self, item):
        self.save_data()

    def save_data(self):
        if not self.is_data_correct():
            show_dialog(DialogType.ERROR, self._dialog, "Error. Verify the data!")
            return

        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self.on_edit() if self._action is Action.EDIT else self.on_new()
        self._dialog.destroy()

    def on_edit(self):
        fav_id, data_id = self.get_srv_data()
        # transponder
        transponder = self._old_service.transponder
        if self._tr_edit_switch.get_active():
            transponder = self.get_transponder_data()
            if self._transponder_services_iters:
                self.update_transponder_services(transponder)
        service = self.get_service(fav_id, data_id, transponder)
        old_fav_id = self._old_service.fav_id
        if old_fav_id != fav_id:
            self._services.pop(old_fav_id, None)
            for bq in self._bouquets.values():
                indexes = []
                for i, f_id in enumerate(bq):
                    if old_fav_id == f_id:
                        indexes.append(i)
                for i in indexes:
                    bq[i] = fav_id
        self._services[fav_id] = service
        self._current_model.set(self._current_itr, {i: v for i, v in enumerate(service)})
        self._old_service = service

    def on_new(self):
        service = self.get_service(*self.get_srv_data(), self.get_transponder_data())
        print(service)
        show_dialog(DialogType.ERROR, transient=self._dialog, text="Not implemented yet!")

    def get_service(self, fav_id, data_id, transponder):
        freq, rate, pol, fec, system, pos = self.get_transponder_values()
        return Service(flags_cas=self.get_flags(),
                       transponder_type="s",
                       coded=self._old_service.coded,
                       service=self._name_entry.get_text(),
                       locked=self._old_service.locked,
                       hide=HIDE_ICON if self._hide_check_button.get_active() else None,
                       package=self._package_entry.get_text(),
                       service_type=self._service_type_combo_box.get_active_id(),
                       picon=self._old_service.picon,
                       picon_id=self._old_service.picon_id,
                       ssid="{:x}".format(int(self._sid_entry.get_text())),
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
        if self._profile is Profile.ENIGMA_2:
            return self.get_enigma2_flags()
        elif self._profile is Profile.NEUTRINO_MP:
            return self._old_service.flags_cas

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

        if self._profile is Profile.ENIGMA_2:
            namespace = int(self._namespace_entry.get_text())
            data_id = self._ENIGMA2_DATA_ID.format(ssid, namespace, tr_id, net_id, service_type, 0)
            fav_id = self._ENIGMA2_FAV_ID.format(ssid, tr_id, net_id, namespace)
            return fav_id, data_id
        elif self._profile is Profile.NEUTRINO_MP:
            fav_id = self._NEUTRINO_FAV_ID.format(tr_id, net_id, ssid)
            return fav_id, self._old_service.data_id

    def get_transponder_values(self):
        freq = self._freq_entry.get_text()
        rate = self._rate_entry.get_text()
        pol = self._pol_combo_box.get_active_id()
        fec = self._fec_combo_box.get_active_id()
        system = self._sys_combo_box.get_active_id()
        pos = str(round(self._sat_pos_button.get_value(), 1))
        return freq, rate, pol, fec, system, pos

    def get_transponder_data(self):
        sys = self._sys_combo_box.get_active_id()
        freq = self._freq_entry.get_text()
        rate = self._rate_entry.get_text()
        pol = self.get_value_from_combobox_id(self._pol_combo_box, POLARIZATION)
        fec = self.get_value_from_combobox_id(self._fec_combo_box, FEC_DEFAULT)
        sat_pos = str(round(self._sat_pos_button.get_value(), 1)).replace(".", "")
        inv = get_value_by_name(Inversion, self._invertion_combo_box.get_active_id())
        srv_sys = "0"  # !!!

        if self._profile is Profile.ENIGMA_2:
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
        elif self._profile is Profile.NEUTRINO_MP:
            on_id, tr_id = int(self._network_id_entry.get_text()), int(self._transponder_id_entry.get_text())
            mod = self.get_value_from_combobox_id(self._mod_combo_box, MODULATION) if sys == "DVB-S2" else None
            srv_sys = None
            return self._NEUTRINO_TRANSPONDER_DATA.format(tr_id, on_id, freq, inv, rate, fec, pol, mod, srv_sys)

    def update_transponder_services(self, transponder):
        for itr in self._transponder_services_iters:
            srv = self._current_model[itr][:]
            srv[-9], srv[-8], srv[-7], srv[-6], srv[-5], srv[-4] = self.get_transponder_values()
            srv[-1] = transponder
            srv = Service(*srv)
            self._services[srv.fav_id] = self._services.pop(srv.fav_id)._replace(transponder=transponder)
            self._current_model.set(itr, {i: v for i, v in enumerate(srv)})

    # ***************** Others *********************#

    def select_active_text(self, box: Gtk.ComboBox, text):
        model = box.get_model()
        for index, row in enumerate(model):
            if row[0] == text:
                box.set_active(index)
                break

    def on_digit_entry_changed(self, entry):
        entry.set_name(self._DIGIT_ENTRY_NAME if self._DIGIT_PATTERN.search(entry.get_text()) else "GtkEntry")

    def on_non_empty_entry_changed(self, entry):
        entry.set_name(self._DIGIT_ENTRY_NAME if self._NON_EMPTY_PATTERN.search(entry.get_text()) else "GtkEntry")

    def get_value_from_combobox_id(self, box: Gtk.ComboBox, dc: dict):
        cb_id = box.get_active_id()
        return get_key_by_value(dc, cb_id)

    @run_idle
    def on_tr_edit_toggled(self, switch: Gtk.Switch, active):

        if active and self._action is Action.EDIT:
            self._transponder_services_iters = []
            response = TransponderServicesDialog(self._dialog,
                                                 self._current_model,
                                                 self._old_service.transponder,
                                                 self._transponder_services_iters).show()
            if response == Gtk.ResponseType.CANCEL or response == -4:
                switch.set_active(False)
                self._transponder_services_iters = None
                return

        self.update_dvb_s2_elements(active and self._sys_combo_box.get_active_id() == "DVB-S2")

        for elem in self._TRANSPONDER_ELEMENTS:
            elem.set_sensitive(active)

    def is_data_correct(self):
        for elem in self._digit_elements.values():
            if elem.get_name() == self._DIGIT_ENTRY_NAME:
                return False
        for elem in self._non_empty_elements.values():
            if elem.get_name() == self._DIGIT_ENTRY_NAME:
                return False
        return True


class TransponderServicesDialog:
    def __init__(self, transient, model, transponder, tr_iters):
        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "service_details_dialog.glade",
                                      ("tr_services_dialog", "transponder_services_liststore"))
        self._dialog = builder.get_object("tr_services_dialog")
        self._dialog.set_transient_for(transient)
        self._srv_model = builder.get_object("transponder_services_liststore")
        self.append_services(model, transponder, tr_iters)

    def append_services(self, model, transponder, tr_iters):
        for row in model:
            if row[-1] == transponder:
                self._srv_model.append((row[3], row[6], row[7], row[10], row[11], row[16]))
                tr_iters.append(model.get_iter(row.path))

    def show(self):
        response = self._dialog.run()
        self._dialog.destroy()
        return response


if __name__ == "__main__":
    pass

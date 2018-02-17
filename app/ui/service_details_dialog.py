from enum import Enum
from functools import lru_cache

from app.commons import run_idle
from app.eparser import Service, get_satellites
from app.eparser.ecommons import MODULATION, Inversion, ROLL_OFF, Pilot
from app.properties import Profile
from . import Gtk, UI_RESOURCES_PATH
from .main_helper import is_only_one_item_selected


class Pids(Enum):
    VIDEO = "c:00"
    AUDIO = "c:01"
    TELETEXT = "c:02"
    PCR = "c:03"
    AC3 = "c:04"
    VIDEO_TYPE = "c:05"
    AUDIO_CHANNEL = "c:06"
    BIT_STREAM_DELAY = "c:07"  # in ms
    PCM_DELAY = "c:08"  # in ms
    SUBTITLE = "c:09"


@lru_cache(maxsize=1)
def get_sat_positions(path):
    return ["{:.1f}".format(float(x.position) / 10) for x in get_satellites(path)]


class ServiceDetailsDialog:
    def __init__(self, transient, options, view):
        handlers = {"on_system_changed": self.on_system_changed}

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "service_details_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("service_details_dialog")
        self._dialog.set_transient_for(transient)
        self._profile = Profile(options["profile"])
        self._satellites_xml_path = options.get(self._profile.value)["data_dir_path"] + "satellites.xml"
        self._services_view = view
        # Service elements
        self._name_entry = builder.get_object("name_entry")
        self._package_entry = builder.get_object("package_entry")
        self._id_entry = builder.get_object("id_entry")
        self._service_type_combo_box = builder.get_object("service_type_combo_box")
        self._cas_entry = builder.get_object("cas_entry")
        self._bitstream_entry = builder.get_object("bitstream_entry")
        self._pcm_entry = builder.get_object("pcm_entry")
        self._reference_entry = builder.get_object("reference_entry")
        self._video_pid_entry = builder.get_object("video_pid_entry")
        self._pcr_pid_entry = builder.get_object("pcr_pid_entry")
        self._audio_pid_entry = builder.get_object("audio_pid_entry")
        self._ac3_pid_entry = builder.get_object("ac3_pid_entry")
        self._ac3plus_pid_entry = builder.get_object("ac3plus_pid_entry")
        self._acc_pid_entry = builder.get_object("acc_pid_entry")
        self._he_acc_pid_entry = builder.get_object("he_acc_pid_entry")
        self._teletext_pid_entry = builder.get_object("teletext_pid_entry")
        self._keep_check_button = builder.get_object("keep_check_button")
        self._hide_check_button = builder.get_object("hide_check_button")
        self._use_pids_check_button = builder.get_object("use_pids_check_button")
        self._new_check_button = builder.get_object("new_check_button")
        # Transponder elements
        self._sat_pos_combo_box = builder.get_object("sat_pos_combo_box")
        self._transponder_id_entry = builder.get_object("transponder_id_entry")
        self._network_id_entry = builder.get_object("network_id_entry")
        self._freq_entry = builder.get_object("freq_entry")
        self._rate_entry = builder.get_object("rate_entry")
        self._pol_combo_box = builder.get_object("pol_combo_box")
        self._fec_combo_box = builder.get_object("fec_combo_box")
        self._sys_combo_box = builder.get_object("sys_combo_box")
        self._mod_combo_box = builder.get_object("mod_combo_box")
        self._invertion_combo_box = builder.get_object("invertion_combo_box")
        self._rolloff_combo_box = builder.get_object("rolloff_combo_box")
        self._pilot_combo_box = builder.get_object("pilot_combo_box")
        self._pls_mode_combo_box = builder.get_object("pls_mode_combo_box")
        self._pls_code_entry = builder.get_object("pls_code_entry")
        self._stream_id_entry = builder.get_object("stream_id_entry")
        self._flags_entry = builder.get_object("flags_entry")
        self._namespace_entry = builder.get_object("namespace_entry")
        self._DVB_S2_ELEMENTS = (self._mod_combo_box, self._rolloff_combo_box, self._pilot_combo_box,
                                 self._pls_mode_combo_box, self._pls_code_entry, self._stream_id_entry)
        self.update_data_elements()

    @run_idle
    def update_data_elements(self):
        model, paths = self._services_view.get_selection().get_selected_rows()
        if is_only_one_item_selected(paths, self._dialog):
            srv = Service(*model[paths][:])
            # Service
            self._name_entry.set_text(srv.service)
            self._package_entry.set_text(srv.package)
            self.select_active_text(self._service_type_combo_box, srv.service_type)
            self._id_entry.set_text(str(int(srv.ssid, 16)))
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

    @run_idle
    def init_enigma2_service_data(self, srv):
        """ Service data initialisation """
        flags = srv.flags_cas.split(",")

        cas = list(filter(lambda x: x.startswith("C:"), flags))
        if cas:
            self._cas_entry.set_text(",".join(cas))

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

        self._reference_entry.set_text(srv.picon_id.replace("_", ":").rstrip(".png"))

    @run_idle
    def init_enigma2_transponder_data(self, srv):
        """ Transponder data initialisation """
        data = srv.data_id.split(":")
        tr_data = srv.transponder.split(":")

        if srv.system == "DVB-S2":
            self.select_active_text(self._mod_combo_box, MODULATION.get(tr_data[8]))
            self.select_active_text(self._rolloff_combo_box, ROLL_OFF.get(tr_data[9]))
            self.select_active_text(self._pilot_combo_box, Pilot(tr_data[10]).name)

        self._namespace_entry.set_text(str(int(data[1], 16)))
        self._transponder_id_entry.set_text(str(int(data[2], 16)))
        self._network_id_entry.set_text(str(int(data[3], 16)))
        self.select_active_text(self._invertion_combo_box, Inversion(tr_data[5]).name)
        self._flags_entry.set_text(tr_data[6])

    def select_active_text(self, box: Gtk.ComboBox, text):
        model = box.get_model()
        for index, row in enumerate(model):
            if row[0] == text:
                box.set_active(index)
                break

    @run_idle
    def set_sat_positions(self, sat_pos):
        model = self._sat_pos_combo_box.get_model()
        positions = get_sat_positions(self._satellites_xml_path)
        for pos in positions:
            model.append((pos,))
        self.select_active_text(self._sat_pos_combo_box, sat_pos)

    def on_system_changed(self, box):
        for elem in self._DVB_S2_ELEMENTS:
            elem.set_sensitive(box.get_active())

    def show(self):
        response = self._dialog.run()
        if response == Gtk.ResponseType.OK:
            pass
        self._dialog.destroy()

        return response


if __name__ == "__main__":
    dialog = ServiceDetailsDialog()
    dialog.show()

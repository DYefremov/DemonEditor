from .main_helper import get_base_model
from . import Gtk

from app.properties import Profile
from .dialogs import get_dialog_from_xml, DialogType, Action


class IptvDialog:
    def __init__(self, transient, view=None, services=None, bouquets=None, profile=Profile.ENIGMA_2, action=Action.ADD):
        builder, dialog = get_dialog_from_xml(DialogType.IPTV, transient)
        self._dialog = dialog
        self._dialog.set_transient_for(transient)
        self._name_entry = builder.get_object("name_entry")
        self._description_entry = builder.get_object("description_entry")
        self._url_entry = builder.get_object("url_entry")
        self._reference_entry = builder.get_object("reference_entry")
        self._srv_type_entry = builder.get_object("srv_type_entry")
        self._sid_entry = builder.get_object("sid_entry")
        self._tr_id_entry = builder.get_object("tr_id_entry")
        self._net_id_entry = builder.get_object("net_id_entry")
        self._namespace_entry = builder.get_object("namespace_entry")
        self._stream_type_combobox = builder.get_object("stream_type_combobox")
        self._add_button = builder.get_object("iptv_dialog_add_button")
        self._save_button = builder.get_object("iptv_dialog_save_button")
        self._stream_type_combobox = builder.get_object("stream_type_combobox")
        self._action = action
        self._profile = profile

        if self._action is Action.ADD:
            self._save_button.set_visible(False)
            self._add_button.set_visible(True)
        elif self._action is Action.EDIT:
            model, paths = view.get_selection().get_selected_rows()
            self.init_data(get_base_model(model)[paths][:])

    def show(self):
        response = self._dialog.run()
        if response == Gtk.ResponseType.OK:
            self.save()
        self._dialog.hide()

    def save(self):
        print(self._action)

    def init_data(self, srv):
        name, fav_id = srv[2], srv[7]
        self._name_entry.set_text(name)
        if self._profile is Profile.ENIGMA_2:
            data, sep, desc = fav_id.partition("#DESCRIPTION:")
            self._description_entry.set_text(desc.strip())
            data = data.split(":")
            if len(data) < 12:
                return
            self._srv_type_entry.set_text(data[2])
            self._sid_entry.set_text(data[3])
            self._tr_id_entry.set_text(data[4])
            self._net_id_entry.set_text(data[5])
            self._namespace_entry.set_text(data[6])
            self._url_entry.set_text(data[10].replace("%3a", ":"))
            self._update_reference_entry()

    def _update_reference_entry(self):
        if self._profile is Profile.ENIGMA_2:
            self._reference_entry.set_text("{}:0:{}:{}:{}:{}:{}:0:0:0".format(self.get_type(),
                                                                              self._srv_type_entry.get_text(),
                                                                              self._sid_entry.get_text(),
                                                                              self._tr_id_entry.get_text(),
                                                                              self._net_id_entry.get_text(),
                                                                              self._namespace_entry.get_text()))

    def get_type(self):
        return 1


if __name__ == "__main__":
    pass

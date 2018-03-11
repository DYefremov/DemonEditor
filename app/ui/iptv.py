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
        self._action = action

        if self._action is Action.ADD:
            self._save_button.set_visible(False)
            self._add_button.set_visible(True)
        elif self._action is Action.EDIT:
            model, paths = view.get_selection().get_selected_rows()
            model = get_base_model(model)
            row = model[paths][:]
            self._name_entry.set_text(row[2])

    def show(self):
        response = self._dialog.run()
        if response == Gtk.ResponseType.OK:
            self.save()
        self._dialog.destroy()

    def save(self):
        print(self._action)


if __name__ == "__main__":
    pass

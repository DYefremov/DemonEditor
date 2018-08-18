import re

from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.commons import run_idle, run_task
from app.eparser.ecommons import BqServiceType, Service
from app.eparser.iptv import NEUTRINO_FAV_ID_FORMAT, StreamType, ENIGMA2_FAV_ID_FORMAT
from app.properties import Profile
from .uicommons import Gtk, Gdk, TEXT_DOMAIN, UI_RESOURCES_PATH, IPTV_ICON
from .dialogs import Action, show_dialog, DialogType
from .main_helper import get_base_model, get_iptv_url


class IptvDialog:
    _DIGIT_ENTRY_NAME = "digit-entry"
    _ENIGMA2_REFERENCE = "{}:0:{}:{:X}:{:X}:{:X}:{:X}:0:0:0"

    def __init__(self, transient, view, services, bouquet, profile=Profile.ENIGMA_2, action=Action.ADD):
        handlers = {"on_entry_changed": self.on_entry_changed,
                    "on_url_changed": self.on_url_changed,
                    "on_save": self.on_save,
                    "on_stream_type_changed": self.on_stream_type_changed}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "dialogs.glade", ("iptv_dialog", "stream_type_liststore"))
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("iptv_dialog")
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
        self._bouquet = bouquet
        self._services = services
        self._model, self._paths = view.get_selection().get_selected_rows()
        self._PATTERN = re.compile("(?:^[\s]*$|\D)")
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        for el in (self._srv_type_entry, self._sid_entry, self._tr_id_entry, self._net_id_entry, self._namespace_entry):
            el.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                           Gtk.STYLE_PROVIDER_PRIORITY_USER)
        if profile is Profile.NEUTRINO_MP:
            builder.get_object("iptv_data_box").set_visible(False)
            builder.get_object("iptv_type_label").set_visible(False)
            builder.get_object("reference_entry").set_visible(False)
            builder.get_object("iptv_reference_label").set_visible(False)
            self._stream_type_combobox.set_visible(False)
        else:
            self._description_entry.set_visible(False)
            builder.get_object("iptv_description_label").set_visible(False)

        if self._action is Action.ADD:
            self._save_button.set_visible(False)
            self._add_button.set_visible(True)
            if self._profile is Profile.ENIGMA_2:
                self._update_reference_entry()
        elif self._action is Action.EDIT:
            self._current_srv = get_base_model(self._model)[self._paths][:]
            self.init_data(self._current_srv)

    def show(self):
        self._dialog.run()
        self._dialog.destroy()

    def on_save(self, item):
        if not self.is_data_correct():
            show_dialog(DialogType.ERROR, self._dialog, "Error. Verify the data!")
            return

        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self.save_enigma2_data() if self._profile is Profile.ENIGMA_2 else self.save_neutrino_data()
        self._dialog.destroy()

    def init_data(self, srv):
        name, fav_id = srv[2], srv[7]
        self._name_entry.set_text(name)
        self.init_enigma2_data(fav_id) if self._profile is Profile.ENIGMA_2 else self.init_neutrino_data(fav_id)

    def init_enigma2_data(self, fav_id):
        data, sep, desc = fav_id.partition("#DESCRIPTION:")
        self._description_entry.set_text(desc.strip())
        data = data.split(":")
        if len(data) < 12:
            return
        self._stream_type_combobox.set_active(0 if StreamType(data[0].strip()) is StreamType.DVB_TS else 1)
        self._srv_type_entry.set_text(data[2])
        self._sid_entry.set_text(str(int(data[3], 16)))
        self._tr_id_entry.set_text(str(int(data[4], 16)))
        self._net_id_entry.set_text(str(int(data[5], 16)))
        self._namespace_entry.set_text(str(int(data[6], 16)))
        self._url_entry.set_text(data[10].replace("%3a", ":"))
        self._update_reference_entry()

    def init_neutrino_data(self, fav_id):
        data = fav_id.split("::")
        self._url_entry.set_text(data[0])
        self._description_entry.set_text(data[1])

    def _update_reference_entry(self):
        if self._profile is Profile.ENIGMA_2:
            self._reference_entry.set_text(self._ENIGMA2_REFERENCE.format(self.get_type(),
                                                                          self._srv_type_entry.get_text(),
                                                                          int(self._sid_entry.get_text()),
                                                                          int(self._tr_id_entry.get_text()),
                                                                          int(self._net_id_entry.get_text()),
                                                                          int(self._namespace_entry.get_text())))

    def get_type(self):
        return 1 if self._stream_type_combobox.get_active() == 0 else 4097

    def on_entry_changed(self, entry):
        if self._PATTERN.search(entry.get_text()):
            entry.set_name(self._DIGIT_ENTRY_NAME)
        else:
            entry.set_name("GtkEntry")
            self._update_reference_entry()

    def on_url_changed(self, entry):
        url = urlparse(entry.get_text())
        entry.set_name("GtkEntry" if all([url.scheme, url.netloc, url.path]) else self._DIGIT_ENTRY_NAME)

    def on_stream_type_changed(self, item):
        self._update_reference_entry()

    def save_enigma2_data(self):
        name = self._name_entry.get_text().strip()
        fav_id = ENIGMA2_FAV_ID_FORMAT.format(self.get_type(),
                                              self._srv_type_entry.get_text(),
                                              int(self._sid_entry.get_text()),
                                              int(self._tr_id_entry.get_text()),
                                              int(self._net_id_entry.get_text()),
                                              int(self._namespace_entry.get_text()),
                                              self._url_entry.get_text().replace(":", "%3a"),
                                              name, name)
        self.update_bouquet_data(name, fav_id)

    def save_neutrino_data(self):
        if self._action is Action.EDIT:
            id_data = self._current_srv[7].split("::")
        else:
            id_data = ["", "", "0", None, None, None, None, "", "", "1"]
        id_data[0] = self._url_entry.get_text()
        id_data[1] = self._description_entry.get_text()
        self.update_bouquet_data(self._name_entry.get_text(), NEUTRINO_FAV_ID_FORMAT.format(*id_data))
        self._dialog.destroy()

    def update_bouquet_data(self, name, fav_id):
        if self._action is Action.EDIT:
            old_srv = self._services.pop(self._current_srv[7])
            self._services[fav_id] = old_srv._replace(service=name, fav_id=fav_id)
            self._bouquet[self._paths[0][0]] = fav_id
            self._model.set(self._model.get_iter(self._paths), {2: name, 7: fav_id})
        else:
            aggr = [None] * 10
            s_type = BqServiceType.IPTV.name
            srv = (None, None, name, None, None, s_type, None, fav_id, None)
            itr = self._model.insert_after(self._model.get_iter(self._paths[0]),
                                           srv) if self._paths else self._model.insert(0, srv)
            self._model.set_value(itr, 1, IPTV_ICON)
            self._bouquet.insert(self._model.get_path(itr)[0], fav_id)
            self._services[fav_id] = Service(None, None, IPTV_ICON, name, *aggr[0:3], s_type, *aggr, fav_id, None)

    def is_data_correct(self):
        for elem in (self._srv_type_entry, self._sid_entry, self._tr_id_entry, self._net_id_entry,
                     self._namespace_entry, self._url_entry):
            if elem.get_name() == self._DIGIT_ENTRY_NAME:
                return False
        return True


class SearchUnavailableDialog:

    def __init__(self, transient, model, fav_bouquet, iptv_rows, profile):
        handlers = {"on_search_unavailable_close": self.on_close}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "dialogs.glade", ("search_unavailable_streams_dialog",))
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("search_unavailable_streams_dialog")
        self._dialog.set_transient_for(transient)
        self._model = model
        self._counter_label = builder.get_object("streams_rows_counter_label")
        self._level_bar = builder.get_object("unavailable_streams_level_bar")
        self._bouquet = fav_bouquet
        self._profile = profile
        self._iptv_rows = iptv_rows
        self._counter = -1
        self._max_rows = len(self._iptv_rows)
        self._level_bar.set_max_value(self._max_rows)
        self._download_task = True
        self._to_delete = []

        self.update_process()
        self.do_search()

    @run_task
    def do_search(self):
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self.get_unavailable, row): row for row in self._iptv_rows}
            for future in concurrent.futures.as_completed(futures):
                if not self._download_task:
                    executor.shutdown()
                    return
                future.result()
            self._download_task = False
        self.on_close()

    def get_unavailable(self, row):
        if not self._download_task:
            return
        req = Request(get_iptv_url(row, self._profile))
        try:
            self.update_bar()
            urlopen(req, timeout=2)
        except Exception:
            self._to_delete.append(self._model.get_iter(row.path))
            self.update_process()

    @run_idle
    def update_bar(self):
        self._max_rows -= 1
        self._level_bar.set_value(self._max_rows)

    @run_idle
    def update_process(self):
        self._counter += 1
        self._counter_label.set_text(str(self._counter))

    def show(self):
        response = self._dialog.run()
        self._dialog.destroy()

        return self._to_delete if response not in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT) else False

    @run_idle
    def on_close(self, item=None, event=None):
        if self._download_task and show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return
        self._download_task = False
        self._dialog.destroy()


class IptvListConfigurationDialog:

    def __init__(self, transient):
        handlers = {}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "dialogs.glade", ("iptv_list_configuration_dialog",))
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("iptv_list_configuration_dialog")
        self._dialog.set_transient_for(transient)

    def show(self):
        response = self._dialog.run()
        self._dialog.destroy()


if __name__ == "__main__":
    pass

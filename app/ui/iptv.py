import re
import urllib
from urllib.error import HTTPError

from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.commons import run_idle, run_task
from app.eparser.ecommons import BqServiceType, Service
from app.eparser.iptv import NEUTRINO_FAV_ID_FORMAT, StreamType, ENIGMA2_FAV_ID_FORMAT
from app.properties import Profile
from .uicommons import Gtk, Gdk, TEXT_DOMAIN, UI_RESOURCES_PATH, IPTV_ICON, Column
from .dialogs import Action, show_dialog, DialogType
from .main_helper import get_base_model, get_iptv_url

_DIGIT_ENTRY_NAME = "digit-entry"
_ENIGMA2_REFERENCE = "{}:0:{}:{:X}:{:X}:{:X}:{:X}:0:0:0"
_PATTERN = re.compile("(?:^[\s]*$|\D)")


def is_data_correct(elems):
    for elem in elems:
        if elem.get_name() == _DIGIT_ENTRY_NAME:
            return False
    return True


def get_stream_type(box):
    active = box.get_active()
    if active == 0:
        return StreamType.DVB_TS.value
    elif active == 1:
        return StreamType.NONE_TS.value
    elif active == 2:
        return StreamType.NONE_REC_1.value
    return StreamType.NONE_REC_2.value


class IptvDialog:

    def __init__(self, transient, view, services, bouquet, profile=Profile.ENIGMA_2, action=Action.ADD):
        handlers = {"on_response": self.on_response,
                    "on_entry_changed": self.on_entry_changed,
                    "on_url_changed": self.on_url_changed,
                    "on_save": self.on_save,
                    "on_stream_type_changed": self.on_stream_type_changed}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "iptv.glade", ("iptv_dialog", "stream_type_liststore"))
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
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._digit_elems = (self._srv_type_entry, self._sid_entry, self._tr_id_entry, self._net_id_entry,
                             self._namespace_entry)
        for el in self._digit_elems:
            el.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                           Gtk.STYLE_PROVIDER_PRIORITY_USER)
        if profile is Profile.NEUTRINO_MP:
            builder.get_object("iptv_dialog_ts_data_frame").set_visible(False)
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

    def on_response(self, dialog, response):
        if response == Gtk.ResponseType.CANCEL:
            self._dialog.destroy()

    def on_save(self, item):
        self.on_url_changed(self._url_entry)
        if not is_data_correct(self._digit_elems) or self._url_entry.get_name() == _DIGIT_ENTRY_NAME:
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
        data, sep, desc = fav_id.partition("#DESCRIPTION")
        self._description_entry.set_text(desc.strip())
        data = data.split(":")
        if len(data) < 11:
            return

        s_type = data[0].strip()
        try:
            stream_type = StreamType(s_type)
            if stream_type is StreamType.DVB_TS:
                self._stream_type_combobox.set_active(0)
            elif stream_type is StreamType.NONE_TS:
                self._stream_type_combobox.set_active(1)
            elif stream_type is StreamType.NONE_REC_1:
                self._stream_type_combobox.set_active(2)
            elif stream_type is StreamType.NONE_REC_2:
                self._stream_type_combobox.set_active(3)
        except ValueError:
            show_dialog(DialogType.ERROR, "Unknown stream type {}".format(s_type))

        self._srv_type_entry.set_text(data[2])
        self._sid_entry.set_text(str(int(data[3], 16)))
        self._tr_id_entry.set_text(str(int(data[4], 16)))
        self._net_id_entry.set_text(str(int(data[5], 16)))
        self._namespace_entry.set_text(str(int(data[6], 16)))
        self._url_entry.set_text(urllib.request.unquote(data[10].strip()))
        self._update_reference_entry()

    def init_neutrino_data(self, fav_id):
        data = fav_id.split("::")
        self._url_entry.set_text(data[0])
        self._description_entry.set_text(data[1])

    def _update_reference_entry(self):
        if self._profile is Profile.ENIGMA_2:
            self._reference_entry.set_text(_ENIGMA2_REFERENCE.format(self.get_type(),
                                                                     self._srv_type_entry.get_text(),
                                                                     int(self._sid_entry.get_text()),
                                                                     int(self._tr_id_entry.get_text()),
                                                                     int(self._net_id_entry.get_text()),
                                                                     int(self._namespace_entry.get_text())))

    def get_type(self):
        return get_stream_type(self._stream_type_combobox)

    def on_entry_changed(self, entry):
        if _PATTERN.search(entry.get_text()):
            entry.set_name(_DIGIT_ENTRY_NAME)
        else:
            entry.set_name("GtkEntry")
            self._update_reference_entry()

    def on_url_changed(self, entry):
        url = urlparse(entry.get_text())
        entry.set_name("GtkEntry" if all([url.scheme, url.netloc, url.path]) else _DIGIT_ENTRY_NAME)

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
                                              urllib.request.quote(self._url_entry.get_text()),
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
            self._model.set(self._model.get_iter(self._paths), {Column.FAV_SERVICE: name, Column.FAV_ID: fav_id})
        else:
            aggr = [None] * 10
            s_type = BqServiceType.IPTV.name
            srv = (None, None, name, None, None, s_type, None, fav_id, *aggr[0:3])
            itr = self._model.insert_after(self._model.get_iter(self._paths[0]),
                                           srv) if self._paths else self._model.insert(0, srv)
            self._model.set_value(itr, 1, IPTV_ICON)
            self._bouquet.insert(self._model.get_path(itr)[0], fav_id)
            self._services[fav_id] = Service(None, None, IPTV_ICON, name, *aggr[0:3], s_type, *aggr, fav_id, None)


class SearchUnavailableDialog:

    def __init__(self, transient, model, fav_bouquet, iptv_rows, profile):
        handlers = {"on_response": self.on_response}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "iptv.glade", ("search_unavailable_streams_dialog",))
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

        self.update_counter()
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
        try:
            req = Request(get_iptv_url(row, self._profile))
            self.update_bar()
            urlopen(req, timeout=2)
        except HTTPError as e:
            if e.code != 403:
                self.append_data(row)
        except Exception:
            self.append_data(row)

    def append_data(self, row):
        self._to_delete.append(self._model.get_iter(row.path))
        self.update_counter()

    @run_idle
    def update_bar(self):
        self._max_rows -= 1
        self._level_bar.set_value(self._max_rows)

    @run_idle
    def update_counter(self):
        self._counter += 1
        self._counter_label.set_text(str(self._counter))

    def show(self):
        response = self._dialog.run()

        return self._to_delete if response not in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT) else False

    def on_response(self, dialog, response):
        if response == Gtk.ResponseType.CANCEL:
            self.on_close()

    @run_idle
    def on_close(self):
        if self._download_task and show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return
        self._download_task = False
        self._dialog.destroy()


class IptvListConfigurationDialog:

    def __init__(self, transient, services, iptv_rows, bouquet, profile):
        handlers = {"on_apply": self.on_apply,
                    "on_response": self.on_response,
                    "on_stream_type_default_togged": self.on_stream_type_default_togged,
                    "on_stream_type_changed": self.on_stream_type_changed,
                    "on_default_type_toggled": self.on_default_type_toggled,
                    "on_auto_sid_toggled": self.on_auto_sid_toggled,
                    "on_default_tid_toggled": self.on_default_tid_toggled,
                    "on_default_nid_toggled": self.on_default_nid_toggled,
                    "on_default_namespace_toggled": self.on_default_namespace_toggled,
                    "on_reset_to_default": self.on_reset_to_default,
                    "on_entry_changed": self.on_entry_changed,
                    "on_info_bar_close": self.on_info_bar_close}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "iptv.glade",
                                      ("iptv_list_configuration_dialog", "stream_type_liststore"))
        builder.connect_signals(handlers)

        self._rows = iptv_rows
        self._services = services
        self._bouquet = bouquet
        self._profile = profile

        self._dialog = builder.get_object("iptv_list_configuration_dialog")
        self._dialog.set_transient_for(transient)
        self._info_bar = builder.get_object("list_configuration_info_bar")
        self._reference_label = builder.get_object("reference_label")
        self._stream_type_check_button = builder.get_object("stream_type_default_check_button")
        self._type_check_button = builder.get_object("type_default_check_button")
        self._sid_auto_check_button = builder.get_object("sid_auto_check_button")
        self._tid_check_button = builder.get_object("tid_default_check_button")
        self._nid_check_button = builder.get_object("nid_default_check_button")
        self._namespace_check_button = builder.get_object("namespace_default_check_button")
        self._stream_type_combobox = builder.get_object("stream_type_list_combobox")
        self._list_srv_type_entry = builder.get_object("list_srv_type_entry")
        self._list_sid_entry = builder.get_object("list_sid_entry")
        self._list_tid_entry = builder.get_object("list_tid_entry")
        self._list_nid_entry = builder.get_object("list_nid_entry")
        self._list_namespace_entry = builder.get_object("list_namespace_entry")
        self._reset_to_default_switch = builder.get_object("reset_to_default_lists_switch")
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._digit_elems = (self._list_srv_type_entry, self._list_sid_entry, self._list_tid_entry,
                             self._list_nid_entry, self._list_namespace_entry)
        for el in self._digit_elems:
            el.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                           Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def show(self):
        self._dialog.run()

    def on_response(self, dialog, response):
        if response == Gtk.ResponseType.CANCEL:
            self._dialog.destroy()

    def on_stream_type_changed(self, box):
        self.update_reference()

    def on_stream_type_default_togged(self, button):
        if button.get_active():
            self._stream_type_combobox.set_active(1)
        self._stream_type_combobox.set_sensitive(not button.get_active())

    def on_default_type_toggled(self, button):
        if button.get_active():
            self._list_srv_type_entry.set_text("1")
        self._list_srv_type_entry.set_sensitive(not button.get_active())

    def on_auto_sid_toggled(self, button):
        if button.get_active():
            self._list_sid_entry.set_text("0")
        self._list_sid_entry.set_sensitive(not button.get_active())

    def on_default_tid_toggled(self, button):
        if button.get_active():
            self._list_tid_entry.set_text("0")
        self._list_tid_entry.set_sensitive(not button.get_active())

    def on_default_nid_toggled(self, button):
        if button.get_active():
            self._list_nid_entry.set_text("0")
        self._list_nid_entry.set_sensitive(not button.get_active())

    def on_default_namespace_toggled(self, button):
        if button.get_active():
            self._list_namespace_entry.set_text("0")
        self._list_namespace_entry.set_sensitive(not button.get_active())

    @run_idle
    def on_reset_to_default(self, item, active):
        item.set_sensitive(not active)
        self._stream_type_combobox.set_active(1)
        self._list_srv_type_entry.set_text("1")
        for el in (self._list_sid_entry, self._list_nid_entry, self._list_tid_entry, self._list_namespace_entry):
            el.set_text("0")
        for el in (self._stream_type_check_button, self._type_check_button, self._sid_auto_check_button,
                   self._tid_check_button, self._nid_check_button, self._namespace_check_button):
            el.set_active(True)

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_idle
    def on_apply(self, item):
        if not is_data_correct(self._digit_elems):
            show_dialog(DialogType.ERROR, self._dialog, "Error. Verify the data!")
            return

        if len(self._bouquet) != len(self._rows):
            return

        if self._profile is Profile.ENIGMA_2:
            reset = self._reset_to_default_switch.get_active()
            type_default = self._type_check_button.get_active()
            tid_default = self._tid_check_button.get_active()
            sid_auto = self._sid_auto_check_button.get_active()
            nid_default = self._nid_check_button.get_active()
            namespace_default = self._namespace_check_button.get_active()

            for index, row in enumerate(self._rows):
                fav_id = row[7]
                data, sep, desc = fav_id.partition("http")
                data = data.split(":")

                if reset:
                    data[0] = StreamType.NONE_TS.value
                    data[2], data[3], data[4], data[5], data[6] = "10000"
                else:
                    data[0] = get_stream_type(self._stream_type_combobox)
                    data[2] = "1" if type_default else self._list_srv_type_entry.get_text()
                    data[3] = "{:X}".format(index) if sid_auto else "0"
                    data[4] = "0" if tid_default else "{:X}".format(int(self._list_tid_entry.get_text()))
                    data[5] = "0" if nid_default else "{:X}".format(int(self._list_nid_entry.get_text()))
                    data[6] = "0" if namespace_default else "{:X}".format(int(self._list_namespace_entry.get_text()))

                data = ":".join(data)
                new_fav_id = "{}{}{}".format(data, sep, desc)
                row[7] = new_fav_id
                self._bouquet[index] = new_fav_id
                srv = self._services.pop(fav_id, None)
                self._services[new_fav_id] = srv._replace(fav_id=new_fav_id)

            self._info_bar.set_visible(True)

    @run_idle
    def update_reference(self):
        if is_data_correct(self._digit_elems):
            stream_type = get_stream_type(self._stream_type_combobox)
            self._reference_label.set_text(
                _ENIGMA2_REFERENCE.format(stream_type, *[int(elem.get_text()) for elem in self._digit_elems]))

    def on_entry_changed(self, entry):
        if _PATTERN.search(entry.get_text()):
            entry.set_name(_DIGIT_ENTRY_NAME)
        else:
            entry.set_name("GtkEntry")
            self.update_reference()


if __name__ == "__main__":
    pass

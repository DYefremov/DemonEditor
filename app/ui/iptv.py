import concurrent.futures
import glob
import os
import re
import urllib
from functools import lru_cache
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from gi.repository import GLib

from app.commons import run_idle, run_task, log
from app.eparser.ecommons import BqServiceType, Service
from app.eparser.iptv import NEUTRINO_FAV_ID_FORMAT, StreamType, ENIGMA2_FAV_ID_FORMAT, get_fav_id, MARKER_FORMAT
from app.settings import SettingsType
from app.tools.yt import YouTube, PlayListParser
from .dialogs import Action, show_dialog, DialogType, get_dialogs_string, get_message
from .main_helper import get_base_model, get_iptv_url, on_popup_menu
from .uicommons import Gtk, Gdk, TEXT_DOMAIN, UI_RESOURCES_PATH, IPTV_ICON, Column, IS_GNOME_SESSION, KeyboardKey

_DIGIT_ENTRY_NAME = "digit-entry"
_ENIGMA2_REFERENCE = "{}:0:{}:{:X}:{:X}:{:X}:{:X}:0:0:0"
_PATTERN = re.compile("(?:^[\\s]*$|\\D)")
_UI_PATH = UI_RESOURCES_PATH + "iptv.glade"


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


@lru_cache(maxsize=1)
def get_yt_icon(icon_name, size=24):
    """ Getting  YouTube icon. If the icon is not found in the icon themes, the "Info" icon is returned by default! """
    default_theme = Gtk.IconTheme.get_default()
    if default_theme.has_icon(icon_name):
        return default_theme.load_icon(icon_name, size, 0)

    theme = Gtk.IconTheme.new()
    for theme_name in map(os.path.basename, filter(os.path.isdir, glob.glob("/usr/share/icons/*"))):
        theme.set_custom_theme(theme_name)
        if theme.has_icon(icon_name):
            return theme.load_icon(icon_name, size, 0)

    return default_theme.load_icon("info", size, 0)


class IptvDialog:

    def __init__(self, transient, view, services, bouquet, profile=SettingsType.ENIGMA_2, action=Action.ADD):
        handlers = {"on_response": self.on_response,
                    "on_entry_changed": self.on_entry_changed,
                    "on_url_changed": self.on_url_changed,
                    "on_save": self.on_save,
                    "on_stream_type_changed": self.on_stream_type_changed,
                    "on_yt_quality_changed": self.on_yt_quality_changed,
                    "on_info_bar_close": self.on_info_bar_close}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_string(get_dialogs_string(_UI_PATH).format(use_header=IS_GNOME_SESSION),
                                        ("iptv_dialog", "stream_type_liststore", "yt_quality_liststore"))
        builder.connect_signals(handlers)

        self._action = action
        self._profile = profile
        self._bouquet = bouquet
        self._services = services
        self._yt_links = None

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
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")
        self._yt_quality_box = builder.get_object("yt_iptv_quality_combobox")
        self._model, self._paths = view.get_selection().get_selected_rows()
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._digit_elems = (self._srv_type_entry, self._sid_entry, self._tr_id_entry, self._net_id_entry,
                             self._namespace_entry)
        for el in self._digit_elems:
            el.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                           Gtk.STYLE_PROVIDER_PRIORITY_USER)
        if profile is SettingsType.NEUTRINO_MP:
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
            if self._profile is SettingsType.ENIGMA_2:
                self._update_reference_entry()
                self._stream_type_combobox.set_active(1)
        elif self._action is Action.EDIT:
            self._current_srv = get_base_model(self._model)[self._paths][:]
            self.init_data(self._current_srv)

    def show(self):
        self._dialog.run()

    def on_response(self, dialog, response):
        if response == Gtk.ResponseType.CANCEL:
            self._dialog.destroy()

    def on_save(self, item):
        if self._action is Action.ADD:
            self.on_url_changed(self._url_entry)

        if not is_data_correct(self._digit_elems) or self._url_entry.get_name() == _DIGIT_ENTRY_NAME:
            self.show_info_message(get_message("Error. Verify the data!"), Gtk.MessageType.ERROR)
            return

        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self.save_enigma2_data() if self._profile is SettingsType.ENIGMA_2 else self.save_neutrino_data()
        self._dialog.destroy()

    def init_data(self, srv):
        name, fav_id = srv[2], srv[7]
        self._name_entry.set_text(name)
        self.init_enigma2_data(fav_id) if self._profile is SettingsType.ENIGMA_2 else self.init_neutrino_data(fav_id)

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
            self.show_info_message("Unknown stream type {}".format(s_type), Gtk.MessageType.ERROR)

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
        if self._profile is SettingsType.ENIGMA_2:
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
        url_str = entry.get_text()
        url = urlparse(url_str)
        entry.set_name("GtkEntry" if all([url.scheme, url.netloc, url.path]) else _DIGIT_ENTRY_NAME)

        yt_id = YouTube.get_yt_id(url_str)
        if yt_id:
            entry.set_icon_from_pixbuf(Gtk.EntryIconPosition.SECONDARY, get_yt_icon("youtube", 32))
            text = "Found a link to the YouTube resource!\nTry to get a direct link to the video?"
            if show_dialog(DialogType.QUESTION, self._dialog, text=text) == Gtk.ResponseType.OK:
                entry.set_sensitive(False)
                gen = self.set_yt_url(entry, yt_id)
                GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
        elif YouTube.is_yt_video_link(url_str):
            entry.set_icon_from_pixbuf(Gtk.EntryIconPosition.SECONDARY, get_yt_icon("youtube", 32))
        else:
            entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)
            self._yt_quality_box.set_visible(False)

    def set_yt_url(self, entry, video_id):
        try:
            links, title = YouTube.get_yt_link(video_id)
        except urllib.error.URLError as e:
            self.show_info_message(get_message("Getting link error:") + (str(e)), Gtk.MessageType.ERROR)
            return
        else:
            if self._action is Action.ADD:
                self._name_entry.set_text(title)

            if links:
                if len(links) > 1:
                    self._yt_quality_box.set_visible(True)
                entry.set_text(links[sorted(links, key=lambda x: int(x.rstrip("p")), reverse=True)[0]])
                self._yt_links = links
            else:
                msg = get_message("Getting link error:") + " No link received for id: {}".format(video_id)
                self.show_info_message(msg, Gtk.MessageType.ERROR)
        finally:
            entry.set_sensitive(True)
        yield True

    def on_stream_type_changed(self, item):
        self._update_reference_entry()

    def on_yt_quality_changed(self, box):
        model = box.get_model()
        active = model.get_value(box.get_active_iter(), 0)
        if self._yt_links and active in self._yt_links:
            self._url_entry.set_text(self._yt_links[active])

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

    @run_idle
    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)


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

    def __init__(self, transient, services, iptv_rows, bouquet, fav_model, profile):
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
        builder.add_objects_from_string(get_dialogs_string(_UI_PATH).format(use_header=IS_GNOME_SESSION),
                                        ("iptv_list_configuration_dialog", "stream_type_liststore"))
        builder.connect_signals(handlers)

        self._rows = iptv_rows
        self._services = services
        self._bouquet = bouquet
        self._fav_model = fav_model
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

        if self._profile is SettingsType.ENIGMA_2:
            reset = self._reset_to_default_switch.get_active()
            type_default = self._type_check_button.get_active()
            tid_default = self._tid_check_button.get_active()
            sid_auto = self._sid_auto_check_button.get_active()
            nid_default = self._nid_check_button.get_active()
            namespace_default = self._namespace_check_button.get_active()

            stream_type = StreamType.NONE_TS.value if reset else get_stream_type(self._stream_type_combobox)
            srv_type = "1" if type_default else self._list_srv_type_entry.get_text()
            tid = "0" if tid_default else "{:X}".format(int(self._list_tid_entry.get_text()))
            nid = "0" if nid_default else "{:X}".format(int(self._list_nid_entry.get_text()))
            namespace = "0" if namespace_default else "{:X}".format(int(self._list_namespace_entry.get_text()))

            for index, row in enumerate(self._rows):
                fav_id = row[Column.FAV_ID]
                data, sep, desc = fav_id.partition("http")
                data = data.split(":")

                if reset:
                    data[2], data[3], data[4], data[5], data[6] = "10000"
                else:
                    data[0], data[2], data[4], data[5], data[6] = stream_type, srv_type, tid, nid, namespace
                    data[3] = "{:X}".format(index) if sid_auto else "0"

                data = ":".join(data)
                new_fav_id = "{}{}{}".format(data, sep, desc)
                row[Column.FAV_ID] = new_fav_id
                srv = self._services.pop(fav_id, None)

                if srv:
                    self._services[new_fav_id] = srv._replace(fav_id=new_fav_id)

            self._bouquet.clear()
            list(map(lambda r: self._bouquet.append(r[Column.FAV_ID]), self._fav_model))

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


class YtListImportDialog:
    def __init__(self, transient, profile, appender):
        handlers = {"on_import": self.on_import,
                    "on_receive": self.on_receive,
                    "on_yt_url_entry_changed": self.on_url_entry_changed,
                    "on_yt_info_bar_close": self.on_info_bar_close,
                    "on_popup_menu": on_popup_menu,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_key_press": self.on_key_press,
                    "on_close": self.on_close}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_string(get_dialogs_string(_UI_PATH).format(use_header=IS_GNOME_SESSION),
                                        ("yt_import_dialog_window", "yt_liststore", "yt_quality_liststore",
                                         "yt_popup_menu", "remove_selection_image"))
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("yt_import_dialog_window")
        self._dialog.set_transient_for(transient)
        self._list_view_scrolled_window = builder.get_object("yt_list_view_scrolled_window")
        self._model = builder.get_object("yt_liststore")
        self._progress_bar = builder.get_object("yt_progress_bar")
        self._info_bar_box = builder.get_object("yt_info_bar_box")
        self._message_label = builder.get_object("yt_info_bar_message_label")
        self._info_bar = builder.get_object("yt_info_bar")
        self._yt_count_label = builder.get_object("yt_count_label")
        self._url_entry = builder.get_object("yt_url_entry")
        self._receive_button = builder.get_object("yt_receive_button")
        self._import_button = builder.get_object("yt_import_button")
        self._quality_box = builder.get_object("yt_quality_combobox")
        self._quality_model = builder.get_object("yt_quality_liststore")
        self._import_button.bind_property("visible", self._quality_box, "visible")
        self._import_button.bind_property("sensitive", self._quality_box, "sensitive")
        self._receive_button.bind_property("sensitive", self._import_button, "sensitive")
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._url_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                                    Gtk.STYLE_PROVIDER_PRIORITY_USER)

        self.appender = appender
        self._profile = profile
        self._download_task = False
        self._yt_list_id = None
        self._yt_list_title = None

    def show(self):
        self._dialog.show()

    @run_task
    def on_import(self, item):
        self.on_info_bar_close()
        self.update_active_elements(False)
        self._download_task = True

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                done_links = {}
                rows = list(filter(lambda r: r[2], self._model))
                futures = {executor.submit(YouTube.get_yt_link, r[1]): r for r in rows}
                size = len(futures)
                counter = 0

                for future in concurrent.futures.as_completed(futures):
                    if not self._download_task:
                        executor.shutdown()
                        return

                    done_links[futures[future]] = future.result()
                    counter += 1
                    self.update_progress_bar(counter / size)
        except Exception as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            if self._download_task:
                self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO)
                self.append_services([done_links[r] for r in rows])
        finally:
            self._download_task = False
            self.update_active_elements(True)

    def on_receive(self, item):
        self.show_invisible_elements()
        self.update_active_elements(False)
        self._model.clear()
        self._yt_count_label.set_text("0")
        self.on_info_bar_close()
        self.update_refs_list()

    @run_task
    def update_refs_list(self):
        if self._yt_list_id:
            try:
                self._yt_list_title, links = PlayListParser.get_yt_playlist(self._yt_list_id)
            except Exception as e:
                self.show_info_message(str(e), Gtk.MessageType.ERROR)
                return
            else:
                gen = self.update_links(links)
                GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)
            finally:
                self.update_active_elements(True)

    def update_links(self, links):
        for l in links:
            yield self._model.append((l[0], l[1], True, None))

        size = len(self._model)
        self._yt_count_label.set_text(str(size))
        self._import_button.set_visible(size)
        yield True

    @run_idle
    def append_services(self, links):
        aggr = [None] * 9
        srvs = []

        if self._yt_list_title:
            title = self._yt_list_title
            fav_id = MARKER_FORMAT.format(0, title, title)
            mk = Service(None, None, None, title, *aggr[0:3], BqServiceType.MARKER.name, *aggr, 0, fav_id, None)
            srvs.append(mk)

        act = self._quality_model.get_value(self._quality_box.get_active_iter(), 0)
        for link in links:
            lnk, title = link
            if not lnk:
                continue
            ln = lnk.get(act) if act in lnk else lnk[sorted(lnk, key=lambda x: int(x.rstrip("p")), reverse=True)[0]]
            fav_id = get_fav_id(ln, title, self._profile)
            srv = Service(None, None, IPTV_ICON, title, *aggr[0:3], BqServiceType.IPTV.name, *aggr, None, fav_id, None)
            srvs.append(srv)
        self.appender(srvs)

    @run_idle
    def update_active_elements(self, sensitive):
        self._url_entry.set_sensitive(sensitive)
        self._receive_button.set_sensitive(sensitive)

    def show_invisible_elements(self):
        self._list_view_scrolled_window.set_visible(True)
        self._info_bar_box.set_visible(True)
        self._dialog.set_resizable(True)

    def on_url_entry_changed(self, entry):
        url_str = entry.get_text()
        yt_id = YouTube.get_yt_list_id(url_str)
        entry.set_name("GtkEntry" if yt_id else _DIGIT_ENTRY_NAME)
        self._receive_button.set_sensitive(bool(yt_id))
        self._import_button.set_sensitive(bool(yt_id))
        self._yt_list_id = yt_id

        if yt_id:
            entry.set_icon_from_pixbuf(Gtk.EntryIconPosition.SECONDARY, get_yt_icon("youtube", 32))
        else:
            entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, None)

    @run_idle
    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_idle
    def update_progress_bar(self, value):
        self._progress_bar.set_visible(value < 1)
        self._progress_bar.set_fraction(value)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    def on_selected_toggled(self, toggle, path):
        self._model.set_value(self._model.get_iter(path), 2, not toggle.get_active())

    def on_select_all(self, view):
        self.update_selection(view, True)

    def on_unselect_all(self, view):
        self.update_selection(view, False)

    def update_selection(self, view, select):
        view.get_model().foreach(lambda mod, path, itr: mod.set_value(itr, 2, select))

    def on_key_press(self, view, event):
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return
        key = KeyboardKey(key_code)

        if key is KeyboardKey.SPACE:
            path, column = view.get_cursor()
            itr = self._model.get_iter(path)
            selected = self._model.get_value(itr, 2)
            self._model.set_value(itr, 2, not selected)

    def on_close(self, window, event):
        if self._download_task and show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return True
        self._download_task = False


if __name__ == "__main__":
    pass

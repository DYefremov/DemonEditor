# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2021 Dmitriy Yefremov
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


import gzip
import locale
import os
import re
import shutil
import urllib.request
from enum import Enum
from urllib.error import HTTPError, URLError

from gi.repository import GLib

from app.commons import run_idle, run_task
from app.connections import download_data, DownloadType
from app.eparser.ecommons import BouquetService, BqServiceType
from app.settings import SEP
from app.tools.epg import EPG, ChannelsParser
from app.ui.dialogs import get_message, show_dialog, DialogType, get_builder
from .main_helper import on_popup_menu, update_entry_data
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, Column, EPG_ICON, KeyboardKey


class RefsSource(Enum):
    SERVICES = 0
    XML = 1


class EpgDialog:

    def __init__(self, transient, settings, services, bouquet, fav_model, bouquet_name):

        handlers = {"on_close_dialog": self.on_close_dialog,
                    "on_apply": self.on_apply,
                    "on_update": self.on_update,
                    "on_save_to_xml": self.on_save_to_xml,
                    "on_auto_configuration": self.on_auto_configuration,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_filter_changed": self.on_filter_changed,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_popup_menu": on_popup_menu,
                    "on_bouquet_popup_menu": self.on_bouquet_popup_menu,
                    "on_copy_ref": self.on_copy_ref,
                    "on_assign_ref": self.on_assign_ref,
                    "on_reset": self.on_reset,
                    "on_list_reset": self.on_list_reset,
                    "on_drag_begin": self.on_drag_begin,
                    "on_drag_data_get": self.on_drag_data_get,
                    "on_drag_data_received": self.on_drag_data_received,
                    "on_resize": self.on_resize,
                    "on_names_source_changed": self.on_names_source_changed,
                    "on_options_save": self.on_options_save,
                    "on_use_web_source_switch": self.on_use_web_source_switch,
                    "on_enable_filtering_switch": self.on_enable_filtering_switch,
                    "on_update_on_start_switch": self.on_update_on_start_switch,
                    "on_field_icon_press": self.on_field_icon_press,
                    "on_key_release": self.on_key_release}

        self._services = {}
        self._ex_services = services
        self._ex_fav_model = fav_model
        self._settings = settings
        self._bouquet = bouquet
        self._bouquet_name = bouquet_name
        self._current_ref = []
        self._enable_dat_filter = False
        self._use_web_source = False
        self._update_epg_data_on_start = False
        self._refs_source = RefsSource.SERVICES
        self._show_tooltips = True
        self._download_xml_is_active = False

        builder = get_builder(UI_RESOURCES_PATH + "epg_dialog.glade", handlers)

        self._dialog = builder.get_object("epg_dialog_window")
        self._dialog.set_transient_for(transient)
        self._source_view = builder.get_object("source_view")
        self._bouquet_view = builder.get_object("bouquet_view")
        self._bouquet_model = builder.get_object("bouquet_list_store")
        self._services_model = builder.get_object("services_list_store")
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")
        self._assign_ref_popup_item = builder.get_object("bouquet_assign_ref_popup_item")
        self._left_header_box = builder.get_object("left_header_box")
        self._xml_download_progress_bar = builder.get_object("xml_download_progress_bar")
        # Filter
        self._filter_bar = builder.get_object("filter_bar")
        self._filter_entry = builder.get_object("filter_entry")
        self._services_filter_model = builder.get_object("services_filter_model")
        self._services_filter_model.set_visible_func(self.services_filter_function)
        # Info
        self._source_count_label = builder.get_object("source_count_label")
        self._source_info_label = builder.get_object("source_info_label")
        self._bouquet_count_label = builder.get_object("bouquet_count_label")
        self._bouquet_epg_count_label = builder.get_object("bouquet_epg_count_label")
        # Options
        self._xml_radiobutton = builder.get_object("xml_radiobutton")
        self._xml_chooser_button = builder.get_object("xml_chooser_button")
        self._names_source_box = builder.get_object("names_source_box")
        self._web_source_box = builder.get_object("web_source_box")
        self._use_web_source_switch = builder.get_object("use_web_source_switch")
        self._url_to_xml_entry = builder.get_object("url_to_xml_entry")
        self._enable_filtering_switch = builder.get_object("enable_filtering_switch")
        self._epg_dat_path_entry = builder.get_object("epg_dat_path_entry")
        self._epg_dat_stb_path_entry = builder.get_object("epg_dat_stb_path_entry")
        self._update_on_start_switch = builder.get_object("update_on_start_switch")
        self._epg_dat_source_box = builder.get_object("epg_dat_source_box")
        # Setting the last size of the dialog window
        window_size = self._settings.get("epg_tool_window_size")
        if window_size:
            self._dialog.resize(*window_size)

        self.init_drag_and_drop()
        self.on_update()

    def show(self):
        self._dialog.show()

    def on_close_dialog(self, window, event):
        self._download_xml_is_active = False

    @run_idle
    def on_apply(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self._bouquet.clear()
        list(map(self._bouquet.append, [r[Column.FAV_ID] for r in self._bouquet_model]))
        for index, row in enumerate(self._ex_fav_model):
            fav_id = self._bouquet[index]
            row[Column.FAV_ID] = fav_id
            if row[Column.FAV_TYPE] == BqServiceType.IPTV.name:
                old_fav_id = self._services[fav_id]
                srv = self._ex_services.pop(old_fav_id, None)
                if srv:
                    self._ex_services[fav_id] = srv._replace(fav_id=fav_id)
        self._dialog.destroy()

    @run_idle
    def on_update(self, item=None):
        self.clear_data()
        self.init_options()
        gen = self.init_data()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def clear_data(self):
        self._services_model.clear()
        self._bouquet_model.clear()
        self._services.clear()
        self._source_info_label.set_text("")
        self._bouquet_epg_count_label.set_text("")
        self.on_info_bar_close()

    def init_data(self):
        gen = self.init_bouquet_data()
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

        refs = None
        if self._enable_dat_filter:
            if self._update_epg_data_on_start:
                try:
                    self.download_epg_from_stb()
                except OSError as e:
                    self.show_info_message("Download epg.dat file error: {}".format(e), Gtk.MessageType.ERROR)
                    return
            yield True

            try:
                refs = EPG.get_epg_refs(self._epg_dat_path_entry.get_text() + "epg.dat")
            except FileNotFoundError as e:
                self.show_info_message("Read data error: {}".format(e), Gtk.MessageType.ERROR)
                return
            yield True

        if self._refs_source is RefsSource.SERVICES:
            self.init_lamedb_source(refs)
        elif self._refs_source is RefsSource.XML:
            xml_gen = self.init_xml_source(refs)
            try:
                yield from xml_gen
            except ValueError as e:
                self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            self.show_info_message("Unknown names source!", Gtk.MessageType.ERROR)
        yield True

    def init_bouquet_data(self):
        for r in self._ex_fav_model:
            row = [*r[:]]
            fav_id = r[Column.FAV_ID]
            self._services[fav_id] = self._ex_services[fav_id].fav_id
            yield self._bouquet_model.append(row)
        self._bouquet_count_label.set_text(str(len(self._bouquet_model)))
        yield True

    def init_lamedb_source(self, refs):
        srvs = {k[:k.rfind(":")]: v for k, v in self._ex_services.items()}
        s_types = (BqServiceType.MARKER.value, BqServiceType.IPTV.value)
        filtered = filter(None, [srvs.get(ref) for ref in refs]) if refs else filter(
            lambda s: s.service_type not in s_types, self._ex_services.values())
        list(map(self._services_model.append, map(lambda s: (s.service, s.fav_id), filtered)))
        self.update_source_count_info()

    def init_xml_source(self, refs):
        path = self._epg_dat_path_entry.get_text() if self._use_web_source else self._xml_chooser_button.get_filename()
        if not path:
            self.show_info_message("The path to the xml file is not set!", Gtk.MessageType.ERROR)
            return

        if self._use_web_source:
            #  Downloading gzipped xml file that contains services names with references from the web.
            self._download_xml_is_active = True
            self.update_active_header_elements(False)
            url = self._url_to_xml_entry.get_text()

            try:
                with urllib.request.urlopen(url, timeout=2) as fp:
                    headers = fp.info()
                    content_type = headers.get("Content-Type", "")

                    if content_type != "application/gzip":
                        self._download_xml_is_active = False
                        raise ValueError("{} {} {}".format(get_message("Download XML file error."),
                                                           get_message("Unsupported file type:"),
                                                           content_type))

                    file_name = os.path.basename(url)
                    data_path = self._epg_dat_path_entry.get_text()

                    with open(data_path + file_name, "wb") as tfp:
                        bs = 1024 * 8
                        size = -1
                        read = 0
                        b_num = 0
                        if "content-length" in headers:
                            size = int(headers["Content-Length"])

                        while self._download_xml_is_active:
                            block = fp.read(bs)
                            if not block:
                                break
                            read += len(block)
                            tfp.write(block)
                            b_num += 1
                            self.update_download_progress(b_num * bs / size)
                            yield True

                        path = tfp.name.rstrip(".gz")
            except (HTTPError, URLError) as e:
                raise ValueError("{} {}".format(get_message("Download XML file error."), e))
            else:
                try:
                    with open(path, "wb") as f_out:
                        with gzip.open(tfp.name, "rb") as f:
                            shutil.copyfileobj(f, f_out)
                    os.remove(tfp.name)
                except Exception as e:
                    raise ValueError("{} {}".format(get_message("Unpacking data error."), e))
            finally:
                self._download_xml_is_active = False
                self.update_active_header_elements(True)

        try:
            s_refs, info = ChannelsParser.get_refs_from_xml(path)
            yield True
        except Exception as e:
            raise ValueError("{} {}".format(get_message("XML parsing error:"), e))
        else:
            if refs:
                s_refs = filter(lambda x: x.num in refs, s_refs)
            list(map(lambda s: self._services_model.append((s.name, s.data)), s_refs))
            self.update_source_info(info)
            self.update_source_count_info()
            yield True

    def on_key_release(self, view, event):
        """  Handling  keystrokes  """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return
        key = KeyboardKey(key_code)
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK

        if ctrl and key is KeyboardKey.C:
            self.on_copy_ref()
        elif ctrl and key is KeyboardKey.V:
            self.on_assign_ref()

    @run_idle
    def on_save_to_xml(self, item):
        response = show_dialog(DialogType.CHOOSER, self._dialog, settings=self._settings)
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        services = []
        iptv_types = (BqServiceType.IPTV.value, BqServiceType.MARKER.value)
        for r in self._bouquet_model:
            srv_type = r[Column.FAV_TYPE]
            if srv_type in iptv_types:
                srv = BouquetService(name=r[Column.FAV_SERVICE],
                                     type=BqServiceType(srv_type),
                                     data=r[Column.FAV_ID],
                                     num=r[Column.FAV_NUM])
                services.append(srv)

        ChannelsParser.write_refs_to_xml("{}{}.xml".format(response, self._bouquet_name), services)
        self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO)

    @run_idle
    def on_auto_configuration(self, item):
        """ Simple mapping of services by name. """
        use_cyrillic = locale.getdefaultlocale()[0] in ("ru_RU", "be_BY", "uk_UA", "sr_RS")
        tr = None
        if use_cyrillic:
            # may be not entirely correct
            symbols = (u"АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯІÏҐЎЈЂЉЊЋЏTB",
                       u"ABVGDEEJZIJKLMNOPRSTUFHZCSS_Y_EUAIEGUEDLNCJTV")
            tr = {ord(k): ord(v) for k, v in zip(*symbols)}

        source = {}
        for row in self._services_model:
            name = re.sub("\\W+", "", str(row[0])).upper()
            name = name.translate(tr) if use_cyrillic else name
            source[name] = row[1]

        success_count = 0
        not_founded = {}

        for r in self._bouquet_model:
            if r[Column.FAV_TYPE] != BqServiceType.IPTV.value:
                continue
            name = re.sub("\\W+", "", str(r[Column.FAV_SERVICE])).upper()
            if use_cyrillic:
                name = name.translate(tr)
            ref = source.get(name, None)  # Not [pop], because the list may contain duplicates or similar names!
            if ref:
                self.assign_data(r, ref, True)
                success_count += 1
            else:
                not_founded[name] = r
        # Additional attempt to search in the remaining elements
        for n in not_founded:
            for k in source:
                if k.startswith(n):
                    self.assign_data(not_founded[n], source[k], True)
                    success_count += 1
                    break

        self.update_epg_count()
        self.show_info_message("{} {} {}".format(get_message("Done!"),
                                                 get_message("Count of successfully configured services:"),
                                                 success_count), Gtk.MessageType.INFO)

    def assign_data(self, row, ref, show_error=False):
        if row[Column.FAV_TYPE] != BqServiceType.IPTV.value:
            if not show_error:
                self.show_info_message(get_message("Not allowed in this context!"), Gtk.MessageType.ERROR)
            return

        fav_id = row[Column.FAV_ID]
        fav_id_data = fav_id.split(":")
        fav_id_data[3:7] = ref.split(":")
        new_fav_id = ":".join(fav_id_data)
        service = self._services.pop(fav_id, None)
        if service:
            self._services[new_fav_id] = service
            row[Column.FAV_ID] = new_fav_id
            row[Column.FAV_LOCKED] = EPG_ICON
            row[Column.FAV_TOOLTIP] = ":".join(fav_id_data[:10]) if self._show_tooltips else None

    def on_filter_toggled(self, button: Gtk.ToggleButton):
        self._filter_bar.set_search_mode(button.get_active())

    def on_filter_changed(self, entry):
        self._services_filter_model.refilter()

    def services_filter_function(self, model, itr, data):
        txt = self._filter_entry.get_text().upper()
        return model is None or model == "None" or txt in model.get_value(itr, 0).upper()

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    def on_copy_ref(self, item=None):
        model, paths = self._source_view.get_selection().get_selected_rows()
        self._current_ref.clear()
        if paths:
            self._current_ref.append(model[paths][1])

    def on_assign_ref(self, item=None):
        if self._current_ref:
            model, paths = self._bouquet_view.get_selection().get_selected_rows()
            self.assign_data(model[paths], self._current_ref.pop())
            self.update_epg_count()

    @run_idle
    def on_reset(self, item):
        model, paths = self._bouquet_view.get_selection().get_selected_rows()
        if paths:
            row = self._bouquet_model[paths]
            self.reset_row_data(row)
            self.update_epg_count()

    @run_idle
    def on_list_reset(self, item):
        list(map(self.reset_row_data, self._bouquet_model))
        self.update_epg_count()

    def reset_row_data(self, row):
        default_fav_id = self._services.pop(row[Column.FAV_ID], None)
        if default_fav_id:
            self._services[default_fav_id] = default_fav_id
            row[Column.FAV_ID], row[Column.FAV_LOCKED], row[Column.FAV_TOOLTIP] = default_fav_id, None, None

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    @run_idle
    def update_source_info(self, info):
        lines = info.split("\n")
        self._source_info_label.set_text(lines[0] if lines else "")
        self._source_view.set_tooltip_text(info)

    @run_idle
    def update_source_count_info(self):
        source_count = len(self._services_model)
        self._source_count_label.set_text(str(source_count))
        if self._enable_dat_filter and source_count == 0:
            msg = get_message("Current epg.dat file does not contains references for the services of this bouquet!")
            self.show_info_message(msg, Gtk.MessageType.WARNING)

    @run_idle
    def update_epg_count(self):
        count = len(list((filter(None, [r[Column.FAV_LOCKED] for r in self._bouquet_model]))))
        self._bouquet_epg_count_label.set_text(str(count))

    @run_idle
    def update_active_header_elements(self, state):
        self._left_header_box.set_sensitive(state)
        self._xml_download_progress_bar.set_visible(not state)
        self._source_info_label.set_text("" if state else "Downloading XML:")

    @run_idle
    def update_download_progress(self, value):
        self._xml_download_progress_bar.set_fraction(value)

    def on_bouquet_popup_menu(self, menu, event):
        self._assign_ref_popup_item.set_sensitive(self._current_ref)
        on_popup_menu(menu, event)

    # ***************** Drag-and-drop *********************#

    def init_drag_and_drop(self):
        """ Enable drag-and-drop """
        target = []
        self._source_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, target, Gdk.DragAction.COPY)
        self._source_view.drag_source_add_text_targets()
        self._bouquet_view.enable_model_drag_dest(target, Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._bouquet_view.drag_dest_add_text_targets()

    def on_drag_begin(self, view, context):
        """ Selects a row under the cursor in the view at the dragging beginning. """
        selection = view.get_selection()
        if selection.count_selected_rows() > 1:
            view.do_toggle_cursor_row(view)

    def on_drag_data_get(self, view: Gtk.TreeView, drag_context, data, info, time):
        model, paths = view.get_selection().get_selected_rows()
        if paths:
            val = model.get_value(model.get_iter(paths), 1)
            data.set_text(val, -1)

    def on_drag_data_received(self, view: Gtk.TreeView, drag_context, x, y, data, info, time):
        path, pos = view.get_dest_row_at_pos(x, y)
        model = view.get_model()
        self.assign_data(model[path], data.get_text())
        self.update_epg_count()
        return False

    # ***************** Options *********************#

    def init_options(self):
        epg_dat_path = "{}epg{}".format(self._settings.profile_data_path, SEP)
        self._epg_dat_path_entry.set_text(epg_dat_path)
        default_epg_data_stb_path = "/etc/enigma2"
        epg_options = self._settings.epg_options
        if epg_options:
            self._refs_source = RefsSource.XML if epg_options.get("xml_source", False) else RefsSource.SERVICES
            self._xml_radiobutton.set_active(self._refs_source is RefsSource.XML)
            self._use_web_source = epg_options.get("use_web_source", False)
            self._use_web_source_switch.set_active(self._use_web_source)
            self._url_to_xml_entry.set_text(epg_options.get("url_to_xml", ""))
            self._enable_dat_filter = epg_options.get("enable_filtering", False)
            self._enable_filtering_switch.set_active(self._enable_dat_filter)
            epg_dat_path = epg_options.get("epg_dat_path", epg_dat_path)
            self._epg_dat_path_entry.set_text(epg_dat_path)
            self._epg_dat_stb_path_entry.set_text(epg_options.get("epg_dat_stb_path", default_epg_data_stb_path))
            self._update_epg_data_on_start = epg_options.get("epg_data_update_on_start", False)
            self._update_on_start_switch.set_active(self._update_epg_data_on_start)
            local_xml_path = epg_options.get("local_path_to_xml", None)
            if local_xml_path:
                self._xml_chooser_button.set_filename(local_xml_path)
        os.makedirs(os.path.dirname(self._epg_dat_path_entry.get_text()), exist_ok=True)

    def on_options_save(self, item=None):
        self._settings.epg_options = {"xml_source": self._xml_radiobutton.get_active(),
                                      "use_web_source": self._use_web_source_switch.get_active(),
                                      "local_path_to_xml": self._xml_chooser_button.get_filename(),
                                      "url_to_xml": self._url_to_xml_entry.get_text(),
                                      "enable_filtering": self._enable_filtering_switch.get_active(),
                                      "epg_dat_path": self._epg_dat_path_entry.get_text(),
                                      "epg_dat_stb_path": self._epg_dat_stb_path_entry.get_text(),
                                      "epg_data_update_on_start": self._update_on_start_switch.get_active()}

    def on_resize(self, window):
        if self._settings:
            self._settings.add("epg_tool_window_size", window.get_size())

    def on_names_source_changed(self, button):
        self._refs_source = RefsSource.XML if button.get_active() else RefsSource.SERVICES
        self._names_source_box.set_sensitive(button.get_active())

    def on_enable_filtering_switch(self, switch, state):
        self._epg_dat_source_box.set_sensitive(state)
        self._update_on_start_switch.set_active(False if not state else self._update_epg_data_on_start)

    def on_update_on_start_switch(self, switch, state):
        pass

    def on_use_web_source_switch(self, switch, state):
        self._web_source_box.set_sensitive(state)
        self._xml_chooser_button.set_sensitive(not state)

    def on_field_icon_press(self, entry, icon, event_button):
        update_entry_data(entry, self._dialog, self._settings)

    # ***************** Downloads *********************#

    @run_task
    def download_epg_from_stb(self):
        """ Download the epg.dat file via ftp from the receiver. """
        download_data(settings=self._settings, download_type=DownloadType.EPG, callback=print)


if __name__ == "__main__":
    pass

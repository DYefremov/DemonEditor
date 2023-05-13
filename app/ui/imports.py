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


from collections import defaultdict
from contextlib import suppress
from pathlib import Path

from app.commons import run_idle, log
from app.eparser import get_bouquets, get_services, BouquetsReader
from app.eparser.ecommons import BqType, BqServiceType, Bouquet
from app.eparser.neutrino.bouquets import parse_webtv, parse_bouquets as get_neutrino_bouquets
from app.settings import SettingsType, IS_DARWIN, SEP
from app.ui.dialogs import show_dialog, DialogType, get_chooser_dialog, translate, get_builder
from app.ui.main_helper import on_popup_menu, get_iptv_data
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, KeyboardKey, Column, Page, HeaderBar


def import_bouquet(app, model, path, appender, file_path=None):
    """ Import of single bouquet """
    itr = model.get_iter(path)
    bq_type = BqType(model.get(itr, Column.BQ_TYPE)[0])
    pattern, f_pattern = None, None
    settings = app.app_settings
    transient = app.app_window
    services = app.current_services
    profile = settings.setting_type

    if profile is SettingsType.ENIGMA_2:
        pattern = f".{bq_type.value}"
        f_pattern = f"{'' if IS_DARWIN else 'userbouquet.'}*{pattern}"
    elif profile is SettingsType.NEUTRINO_MP:
        pattern = "webtv.xml" if bq_type is BqType.WEBTV else "bouquets.xml"
        f_pattern = "bouquets.xml"
        if bq_type is BqType.TV:
            f_pattern = "ubouquets.xml"
        elif bq_type is BqType.WEBTV:
            f_pattern = "webtv.xml"

    file_path = file_path or get_chooser_dialog(transient, settings, "bouquet files", (f_pattern,))
    if file_path == Gtk.ResponseType.CANCEL:
        return

    if not str(file_path).endswith(pattern):
        show_dialog(DialogType.ERROR, transient, text="No bouquet file is selected!")
        return

    if profile is SettingsType.ENIGMA_2:
        if IS_DARWIN and file_path.rfind("userbouquet.") < 0:
            show_dialog(DialogType.ERROR, transient, text="Not allowed in this context!")
            return

        bq = get_enigma2_bouquet(file_path)
        imported = list(filter(lambda x: x.data in services or x.type is BqServiceType.IPTV, bq.services))

        if len(imported) == 0:
            show_dialog(DialogType.ERROR, transient, text="The main list does not contain services for this bouquet!")
            return

        if model.iter_n_children(itr):
            appender(bq, itr)
        else:
            p_itr = model.iter_parent(itr)
            appender(bq, p_itr) if p_itr else appender(bq, itr)
    elif profile is SettingsType.NEUTRINO_MP:
        if bq_type is BqType.WEBTV:
            bqs = parse_webtv(file_path, "WEBTV", bq_type.value)
        else:
            bqs = get_neutrino_bouquets(file_path, "", bq_type.value)
        file_path = f"{Path(file_path).parent}{SEP}"
        ImportDialog(app, file_path, lambda b, s: appender(b), (bqs,)).show()


def get_enigma2_bouquet(path):
    path, sep, f_name = path.rpartition("userbouquet.")
    name, sep, suf = f_name.rpartition(".")
    bq = BouquetsReader.get_bouquet(path, name, suf)
    bouquet = Bouquet(name=bq[0], type=BqType(suf).value, services=bq[1], locked=None, hidden=None)
    return bouquet


class ImportDialog:
    def __init__(self, app, path, appender, bouquets=None):
        handlers = {"on_import": self.on_import,
                    "on_cursor_changed": self.on_cursor_changed,
                    "on_service_changed": self.on_service_changed,
                    "on_bq_selected_toggled": self.on_bq_selected_toggled,
                    "on_sat_selected_toggled": self.on_sat_selected_toggled,
                    "on_service_selected_toggled": self.on_service_selected_toggled,
                    "on_services_model_changed": self.on_services_model_changed,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_sat_view_realize": self.on_sat_view_realize,
                    "on_services_view_realize": self.on_services_view_realize,
                    "on_popup_menu": on_popup_menu,
                    "on_resize": self.on_resize,
                    "on_main_paned_realize": self.on_main_paned_realize,
                    "on_visible_page": self.on_visible_page,
                    "on_bouquets_only_switch": self.on_bouquets_only_switch,
                    "on_key_press": self.on_key_press}

        builder = get_builder(f"{UI_RESOURCES_PATH}imports.glade", handlers)

        self._app = app
        self._services = {}
        self._bq_services = {}
        self._sat_services = defaultdict(list)
        self._ids = self._app.current_services.keys()
        self._skip_import = defaultdict(set)
        self._append = appender
        self._profile = app.app_settings.setting_type
        self._settings = app.app_settings
        self._bouquets = bouquets
        self._current_bq = None
        self._current_sat = None
        self._existing_srv_background = None
        self._page = Page.SERVICES

        self._dialog_window = builder.get_object("dialog_window")
        self._dialog_window.set_transient_for(app.app_window)
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("message_label")
        # Options.
        self._replace_existing_switch = builder.get_object("replace_existing_switch")
        self._bouquets_only_switch = builder.get_object("bouquets_only_switch")
        self._bouquets_settings_box = builder.get_object("bouquets_settings_box")
        # Bouquets page.
        self._bq_model = builder.get_object("bq_list_store")
        self._bq_view = builder.get_object("bq_view")
        self._services_view = builder.get_object("services_view")
        self._services_model = builder.get_object("services_list_store")
        self._bouquets_count_label = builder.get_object("bouquets_count_label")
        self._services_count_label = builder.get_object("services_count_label")
        self._service_info_label = builder.get_object("service_info_label")
        self._service_exists_frame = builder.get_object("service_exists_frame")
        # Satellites page.
        self._sat_view = builder.get_object("sat_view")
        self._sat_model = builder.get_object("sat_list_store")
        self._sat_count_label = builder.get_object("sat_count_label")

        if self._settings.use_header_bar:
            actions_box = builder.get_object("actions_box")
            builder.get_object("toolbar_box").set_visible(False)
            header_bar = HeaderBar()
            stack_switcher = builder.get_object("stack_switcher")
            actions_box.remove(stack_switcher)
            header_bar.set_custom_title(stack_switcher)
            button = builder.get_object("import_button")
            actions_box.remove(button)
            header_bar.pack_start(button)
            extra_box = builder.get_object("extra_header_box")
            actions_box.remove(extra_box)
            header_bar.pack_end(extra_box)

            self._dialog_window.set_titlebar(header_bar)

        window_size = self._settings.get("import_dialog_window_size")
        if window_size:
            self._dialog_window.resize(*window_size)

        self.init_data(path)

    def show(self):
        self._dialog_window.show()

    @run_idle
    def init_data(self, path):
        self._bq_model.clear()
        self._services_model.clear()
        try:
            if not self._bouquets:
                log("Import [init data]: getting bouquets...")
                self._bouquets = get_bouquets(path, self._profile)
            for bqs in self._bouquets:
                for bq in bqs.bouquets:
                    self._bq_model.append((bq.name, bq.type, True))
                    self._bq_services[(bq.name, bq.type)] = bq.services
                self._bouquets_count_label.set_text(str(len(self._bq_model)))

            if self._profile is SettingsType.ENIGMA_2:
                services = get_services(path, self._profile, 5 if self._settings.v5_support else 4)
            elif self._profile is SettingsType.NEUTRINO_MP:
                services = get_services(path, self._profile, 0)
            else:
                self.show_info_message("Setting format not supported!", Gtk.MessageType.ERROR)
                return

            for srv in services:
                self._services[srv.fav_id] = srv
        except FileNotFoundError as e:
            log(f"Import error [init data]: {e}")
            self.show_info_message(str(e), Gtk.MessageType.ERROR)

    def on_import(self, item):
        if self._page is Page.SERVICES:
            if not any(r[-1] for r in self._bq_model):
                self.show_info_message(translate("No selected item!"), Gtk.MessageType.ERROR)
                return

            if not self._bouquets or show_dialog(DialogType.QUESTION, self._dialog_window) != Gtk.ResponseType.OK:
                return

            self.import_bouquets_data()
        else:
            self.import_satellites_data()

    @run_idle
    def import_bouquets_data(self):
        """ Importing data into models. """
        if not self._bouquets:
            return

        log("Importing data...")
        services = set()
        to_delete = set()
        for row in self._bq_model:
            bq = (row[0], row[1])
            if row[-1]:
                skip = self._skip_import[bq]
                for bq_srv in self._bq_services.get(bq, []):
                    srv = self._services.get(bq_srv.data, None)
                    if srv and srv.fav_id not in skip:
                        services.add(srv)
            else:
                to_delete.add(bq)
        bqs_to_delete = []
        for bqs in self._bouquets:
            for bq in bqs.bouquets:
                if (bq.name, bq.type) in to_delete:
                    bqs_to_delete.append(bq)
                else:
                    skip = self._skip_import[(bq.name, bq.type)]
                    bq_services = [srv for srv in bq.services if srv.data not in skip]
                    bq.services.clear()
                    bq.services.extend(bq_services)
        for bqs in self._bouquets:
            bq = bqs.bouquets
            for b in bqs_to_delete:
                with suppress(ValueError):
                    bq.remove(b)

        if self._bouquets_only_switch.get_active():
            services = ()
        else:
            services = list(filter(lambda s: s.fav_id not in self._ids, services))

        self._append(self._bouquets, services)

        if self._replace_existing_switch.get_active():
            self._app.emit("services_update", {s.fav_id: s for s in filter(lambda s: s.fav_id in self._ids, services)})

        self._dialog_window.destroy()

    def import_satellites_data(self):
        if show_dialog(DialogType.QUESTION, self._dialog_window) != Gtk.ResponseType.OK:
            return

        replace_existing = self._replace_existing_switch.get_active()
        services = []
        current_services = self._app.current_services
        to_replace = {}

        for row in self._sat_model:
            if row[-1]:
                sat = (row[0], row[1])
                skip = self._skip_import[sat]
                for s in filter(lambda srv: srv.fav_id not in skip, self._sat_services.get(sat[0], ())):
                    if replace_existing and s.fav_id in self._ids:
                        current_services[s.fav_id] = s
                        to_replace[s.fav_id] = s
                    elif s.fav_id not in self._ids:
                        services.append(s)

        self._append((), services)
        if to_replace:
            self._app.emit("services_update", to_replace)

        self._dialog_window.destroy()

    @run_idle
    def on_cursor_changed(self, view):
        self._services_model.clear()
        self._service_info_label.set_text("")
        model, paths = view.get_selection().get_selected_rows()
        if not paths:
            return

        if self._page is Page.SERVICES:
            self._current_bq = model.get(model.get_iter(paths[0]), 0, 1)
            self.update_bq_services()
        else:
            self._current_sat = model.get(model.get_iter(paths[0]), 0, 1)
            self.update_sat_services()

        self._services_count_label.set_text(str(len(self._services_model)))

    def update_bq_services(self):
        bq_services = self._bq_services.get(self._current_bq)
        skip = self._skip_import[self._current_bq]

        for bq_srv in bq_services:
            if bq_srv.type is BqServiceType.DEFAULT:
                srv = self._services.get(bq_srv.data, None)
                if srv:
                    bg = self._existing_srv_background if srv.fav_id in self._ids else None
                    self._services_model.append((srv.service, srv.service_type, srv.fav_id not in skip, bg, srv.fav_id))
            else:
                bg = self._existing_srv_background if bq_srv.data in self._ids else None
                self._services_model.append((bq_srv.name, bq_srv.type.value, bq_srv.data not in skip, bg, bq_srv.data))

    def update_sat_services(self):
        sat_services = self._sat_services.get(self._current_sat[0])
        skip = self._skip_import[self._current_sat]
        for srv in sat_services:
            bg = self._existing_srv_background if srv.fav_id in self._ids else None
            self._services_model.append((srv.service, srv.service_type, srv.fav_id not in skip, bg, srv.fav_id))

    def on_service_changed(self, view):
        path, column = view.get_cursor()
        if path:
            row = self._services_model[path][:]
            if row[1] == "IPTV":
                ref, url = get_iptv_data(row[-1])
                ref = f"{translate('Service reference')}: {ref}"
                info = f"{translate('Name')}: {row[0]}\n{ref}\nURL: {url}"
                self._service_info_label.set_text(info)
            else:
                srv = self._services.get(row[-1], None)
                self._service_info_label.set_text(self._app.get_hint_for_fav_list(srv) if srv else "")

    def on_bq_selected_toggled(self, toggle, path):
        self._bq_model.set_value(self._bq_model.get_iter(path), 2, not toggle.get_active())

    def on_sat_selected_toggled(self, toggle, path):
        self._sat_model.set_value(self._sat_model.get_iter(path), 2, not toggle.get_active())

    def on_service_selected_toggled(self, toggle, path):
        self._services_model.set_value(self._services_model.get_iter(path), 2, not toggle.get_active())

    def on_services_model_changed(self, model, path, itr):
        row = model[itr][:]
        fav_id = row[-1]
        skip = self._skip_import[self._current_bq if self._page is Page.SERVICES else self._current_sat]
        if row[2]:
            if fav_id in skip:
                skip.remove(fav_id)
        else:
            skip.add(fav_id)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    @run_idle
    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    def on_select_all(self, view):
        self.update_selection(view, True)

    def on_unselect_all(self, view):
        self.update_selection(view, False)

    def update_selection(self, view, select):
        view.get_model().foreach(lambda mod, path, itr: mod.set_value(itr, 2, select))

    def on_sat_view_realize(self, view):
        if not self._services:
            return True

        for srv in self._services.values():
            self._sat_services[srv.pos].append(srv)

        list(map(lambda s: self._sat_model.append((s, None, True)), self._sat_services))
        self._sat_count_label.set_text(str(len(self._sat_model)))

    def on_services_view_realize(self, view):
        if self._settings.use_colors:
            background = Gdk.RGBA()
            self._existing_srv_background = background if background.parse(self._settings.extra_color) else None
            self._service_exists_frame.modify_bg(Gtk.StateType.NORMAL, background.to_color())

    def on_resize(self, window):
        if self._settings:
            self._settings.add("import_dialog_window_size", window.get_size())

    def on_main_paned_realize(self, paned):
        width = paned.get_allocated_width()
        paned.set_position(width * 0.35)

    def on_visible_page(self, stack, param):
        self._page = Page(stack.get_visible_child_name())
        self._bouquets_settings_box.set_sensitive(self._page is Page.SERVICES)

    def on_bouquets_only_switch(self, switch, state):
        if state:
            self._replace_existing_switch.set_active(False)

    def on_key_press(self, view, event):
        """  Handling  keystrokes  """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return
        key = KeyboardKey(key_code)

        if key is KeyboardKey.SPACE:
            model = view.get_model()
            path, column = view.get_cursor()
            itr = model.get_iter(path)
            selected = model.get_value(itr, 2)
            model.set_value(itr, 2, not selected)


if __name__ == "__main__":
    pass

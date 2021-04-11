from contextlib import suppress
from pathlib import Path

from app.commons import run_idle, log
from app.eparser import get_bouquets, get_services, BouquetsReader
from app.eparser.ecommons import BqType, BqServiceType, Bouquet
from app.eparser.neutrino.bouquets import parse_webtv, parse_bouquets as get_neutrino_bouquets
from app.settings import SettingsType
from app.ui.dialogs import show_dialog, DialogType, get_chooser_dialog, get_message
from app.ui.main_helper import on_popup_menu
from .uicommons import Gtk, UI_RESOURCES_PATH, KeyboardKey, Column


def import_bouquet(transient, model, path, settings, services, appender, file_path=None):
    """ Import of single bouquet """
    itr = model.get_iter(path)
    bq_type = BqType(model.get(itr, Column.BQ_TYPE)[0])
    pattern, f_pattern = None, None
    profile = settings.setting_type

    if profile is SettingsType.ENIGMA_2:
        pattern = ".{}".format(bq_type.value)
        f_pattern = "userbouquet.*{}".format(pattern)
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
        file_path = "{}/".format(Path(file_path).parent)
        ImportDialog(transient, file_path, settings, services.keys(), lambda b, s: appender(b), (bqs,)).show()


def get_enigma2_bouquet(path):
    path, sep, f_name = path.rpartition("userbouquet.")
    name, sep, suf = f_name.rpartition(".")
    bq = BouquetsReader.get_bouquet(path, name, suf)
    bouquet = Bouquet(name=bq[0], type=BqType(suf).value, services=bq[1], locked=None, hidden=None)
    return bouquet


class ImportDialog:
    def __init__(self, transient, path, settings, service_ids, appender, bouquets=None):
        handlers = {"on_import": self.on_import,
                    "on_cursor_changed": self.on_cursor_changed,
                    "on_info_button_toggled": self.on_info_button_toggled,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_popup_menu": on_popup_menu,
                    "on_resize": self.on_resize,
                    "on_key_press": self.on_key_press}

        builder = Gtk.Builder()
        builder.set_translation_domain("demon-editor")
        builder.add_from_file(UI_RESOURCES_PATH + "import_dialog.glade")
        builder.connect_signals(handlers)

        self._bq_services = {}
        self._services = {}
        self._service_ids = service_ids
        self._append = appender
        self._profile = settings.setting_type
        self._settings = settings
        self._bouquets = bouquets

        self._dialog_window = builder.get_object("dialog_window")
        self._dialog_window.set_transient_for(transient)
        self._main_model = builder.get_object("main_list_store")
        self._main_view = builder.get_object("main_view")
        self._services_view = builder.get_object("services_view")
        self._services_model = builder.get_object("services_list_store")
        self._services_box = builder.get_object("services_box")
        self._info_check_button = builder.get_object("info_check_button")
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("message_label")
        window_size = self._settings.get("import_dialog_window_size")
        if window_size:
            self._dialog_window.resize(*window_size)

        self.init_data(path)

    def show(self):
        self._dialog_window.show()

    @run_idle
    def init_data(self, path):
        self._main_model.clear()
        self._services_model.clear()
        try:
            if not self._bouquets:
                log("Import [init data]: getting bouquets...")
                self._bouquets = get_bouquets(path, self._profile)
            for bqs in self._bouquets:
                for bq in bqs.bouquets:
                    self._main_model.append((bq.name, bq.type, True))
                    self._bq_services[(bq.name, bq.type)] = bq.services
                    
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
            log("Import error [init data]: {}".format(e))
            self.show_info_message(str(e), Gtk.MessageType.ERROR)

    def on_import(self, item):
        if not any(r[-1] for r in self._main_model):
            self.show_info_message(get_message("No selected item!"), Gtk.MessageType.ERROR)
            return

        if not self._bouquets or show_dialog(DialogType.QUESTION, self._dialog_window) == Gtk.ResponseType.CANCEL:
            return

        self.import_data()

    @run_idle
    def import_data(self):
        """ Importing data into models. """
        if not self._bouquets:
            return

        log("Importing data...")
        services = set()
        to_delete = set()
        for row in self._main_model:
            bq = (row[0], row[1])
            if row[-1]:
                for bq_srv in self._bq_services.get(bq, []):
                    srv = self._services.get(bq_srv.data, None)
                    if srv:
                        services.add(srv)
            else:
                to_delete.add(bq)
        bqs_to_delete = []
        for bqs in self._bouquets:
            for bq in bqs.bouquets:
                if (bq.name, bq.type) in to_delete:
                    bqs_to_delete.append(bq)
        for bqs in self._bouquets:
            bq = bqs.bouquets
            for b in bqs_to_delete:
                with suppress(ValueError):
                    bq.remove(b)
        self._append(self._bouquets, list(filter(lambda s: s.fav_id not in self._service_ids, services)))
        self._dialog_window.destroy()

    @run_idle
    def on_cursor_changed(self, view):
        if not self._info_check_button.get_active():
            return

        self._services_model.clear()
        model, paths = view.get_selection().get_selected_rows()
        if not paths:
            return

        bq_services = self._bq_services.get(model.get(model.get_iter(paths[0]), 0, 1))
        for bq_srv in bq_services:
            if bq_srv.type is BqServiceType.DEFAULT:
                srv = self._services.get(bq_srv.data, None)
                if srv:
                    self._services_model.append((srv.service, srv.service_type))
            else:
                self._services_model.append((bq_srv.name, bq_srv.type.value))

    def on_info_button_toggled(self, button):
        active = button.get_active()
        self._services_box.set_visible(active)

    def on_selected_toggled(self, toggle, path):
        self._main_model.set_value(self._main_model.get_iter(path), 2, not toggle.get_active())

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

    def on_resize(self, window):
        if self._settings:
            self._settings.add("import_dialog_window_size", window.get_size())

    def on_key_press(self, view, event):
        """  Handling  keystrokes  """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return
        key = KeyboardKey(key_code)

        if key is KeyboardKey.SPACE:
            path, column = view.get_cursor()
            itr = self._main_model.get_iter(path)
            selected = self._main_model.get_value(itr, 2)
            self._main_model.set_value(itr, 2, not selected)


if __name__ == "__main__":
    pass

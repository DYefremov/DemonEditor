from contextlib import suppress

from app.commons import run_idle
from app.eparser import get_bouquets, get_services
from app.properties import Profile
from app.ui.dialogs import get_message
from app.ui.main_helper import on_popup_menu
from .uicommons import Gtk, UI_RESOURCES_PATH


class ImportDialog:
    def __init__(self, transient, path, profile, service_ids, services_appender, bouquets_appender):
        handlers = {"on_import": self.on_import,
                    "on_cursor_changed": self.on_cursor_changed,
                    "on_info_button_toggled": self.on_info_button_toggled,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_popup_menu": on_popup_menu}

        builder = Gtk.Builder()
        builder.set_translation_domain("demon-editor")
        builder.add_from_file(UI_RESOURCES_PATH + "import_dialog.glade")
        builder.connect_signals(handlers)

        self._bq_services = {}
        self._services = {}
        self._service_ids = service_ids
        self.append_services = services_appender
        self.append_bouquets = bouquets_appender
        self._profile = profile
        self._bouquets = None

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

        self.init_data(path, profile)

    def show(self):
        self._dialog_window.show()

    def init_data(self, path, profile):
        try:
            self._bouquets = get_bouquets(path, profile)
            for bqs in self._bouquets:
                for bq in bqs.bouquets:
                    self._main_model.append((bq.name, bq.type, True))
                    self._bq_services[(bq.name, bq.type)] = bq.services
            # Note! Getting default format ver. 4
            services = get_services(path, profile, 4 if profile is Profile.ENIGMA_2 else 0)
            for srv in services:
                self._services[srv.fav_id] = srv

        except FileNotFoundError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)

    def on_import(self, item):
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

        self.append_bouquets(self._bouquets)
        self.append_services(list(filter(lambda s: s.fav_id not in self._service_ids, services)))

    @run_idle
    def on_cursor_changed(self, view):
        if not self._info_check_button.get_active():
            return

        self._services_model.clear()
        model, paths = view.get_selection().get_selected_rows()
        bq_services = self._bq_services.get(model.get(model.get_iter(paths[0]), 0, 1))
        for bq_srv in bq_services:
            srv = self._services.get(bq_srv.data, None)
            if srv:
                self._services_model.append((srv.service, srv.service_type))

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
        view.get_model().foreach(lambda mod, path, itr:  mod.set_value(itr, 2, select))


if __name__ == "__main__":
    pass

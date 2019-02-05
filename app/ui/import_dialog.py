from app.commons import run_idle
from app.eparser import get_bouquets, get_services
from app.properties import Profile
from app.ui.dialogs import get_message
from .uicommons import Gtk, UI_RESOURCES_PATH


class ImportDialog:
    def __init__(self, transient, path, profile):
        handlers = {"on_cursor_changed": self.on_cursor_changed,
                    "on_info_button_toggled": self.on_info_button_toggled,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_info_bar_close": self.on_info_bar_close}

        builder = Gtk.Builder()
        builder.set_translation_domain("demon-editor")
        builder.add_from_file(UI_RESOURCES_PATH + "import_dialog.glade")
        builder.connect_signals(handlers)

        self._bouquets = {}
        self._services = {}

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
            bouquets = get_bouquets(path, profile)
            for bqs in bouquets:
                for bq in bqs.bouquets:
                    self._main_model.append((bq.name, bq.type, True))
                    self._bouquets[(bq.name, bq.type)] = bq.services
            # Note! Getting default format ver. 4
            services = get_services(path, profile, 4 if profile is Profile.ENIGMA_2 else 0)
            for srv in services:
                self._services[srv.fav_id] = srv
            self.show_info_message(get_message("Not implemented yet!"), Gtk.MessageType.WARNING)
        except FileNotFoundError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)

    @run_idle
    def on_cursor_changed(self, view):
        if not self._info_check_button.get_active():
            return

        self._services_model.clear()
        model, paths = view.get_selection().get_selected_rows()
        bq_services = self._bouquets.get(model.get(model.get_iter(paths[0]), 0, 1))
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


if __name__ == "__main__":
    pass

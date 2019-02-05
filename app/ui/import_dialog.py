from app.commons import run_idle
from app.eparser import get_bouquets
from app.ui.dialogs import get_message
from .uicommons import Gtk, UI_RESOURCES_PATH


class ImportDialog:
    def __init__(self, transient, path, profile):
        handlers = {}

        builder = Gtk.Builder()
        builder.set_translation_domain("demon-editor")
        builder.add_from_file(UI_RESOURCES_PATH + "import_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog_window = builder.get_object("dialog_window")
        self._dialog_window.set_transient_for(transient)
        self._model = builder.get_object("main_list_store")
        self._main_view = builder.get_object("main_view")
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
                    self._model.append((bq.name, bq.type, True))
            self.show_info_message(get_message("Not implemented yet!"), Gtk.MessageType.WARNING)
        except FileNotFoundError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)


if __name__ == "__main__":
    pass

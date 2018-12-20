import os

from .uicommons import Gtk, UI_RESOURCES_PATH


class BackupDialog:
    def __init__(self, transient, backup_path):
        handlers = {"on_extract": self.on_extract, "on_remove": self.on_remove}

        builder = Gtk.Builder()
        builder.set_translation_domain("demon-editor")
        builder.add_from_file(UI_RESOURCES_PATH + "backup_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog_window = builder.get_object("dialog_window")
        self._dialog_window.set_transient_for(transient)
        self._model = builder.get_object("main_list_store")
        self._backup_path = backup_path
        self.init_data()

    def show(self):
        self._dialog_window.show()

    def init_data(self):
        try:
            files = os.listdir(self._backup_path)
        except FileNotFoundError as e:
            print(e)
        else:
            for file in filter(lambda x: x.endswith(".zip"), files):
                self._model.append((file.rstrip(".zip"), False))

    def on_extract(self, item):
        pass

    def on_remove(self, item):
        pass


if __name__ == "__main__":
    pass

import os
import shutil
from enum import Enum

from app.commons import run_idle
from app.ui.dialogs import show_dialog, DialogType
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH


class RestoreType(Enum):
    BOUQUETS = 0
    ALL = 1


class BackupDialog:
    def __init__(self, transient, data_path, callback):
        handlers = {"on_restore_bouquets": self.on_restore_bouquets,
                    "on_restore_all": self.on_restore_all,
                    "on_remove": self.on_remove,
                    "on_view_popup_menu": self.on_view_popup_menu,
                    "on_info_bar_close": self.on_info_bar_close}

        builder = Gtk.Builder()
        builder.set_translation_domain("demon-editor")
        builder.add_from_file(UI_RESOURCES_PATH + "backup_dialog.glade")
        builder.connect_signals(handlers)

        self._data_path = data_path
        self._backup_path = data_path + "backup/"
        self._open_data_callback = callback
        self._dialog_window = builder.get_object("dialog_window")
        self._dialog_window.set_transient_for(transient)
        self._model = builder.get_object("main_list_store")
        self._main_view = builder.get_object("main_view")
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("message_label")
        self.init_data()

    def show(self):
        self._dialog_window.show()

    def init_data(self):
        try:
            files = os.listdir(self._backup_path)
        except FileNotFoundError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            for file in filter(lambda x: x.endswith(".zip"), files):
                self._model.append((file.rstrip(".zip"), False))

    def on_restore_bouquets(self, item):
        self.restore(RestoreType.BOUQUETS)

    def on_restore_all(self, item):
        self.restore(RestoreType.ALL)

    def on_remove(self, item):
        model, paths = self._main_view.get_selection().get_selected_rows()
        if not paths:
            show_dialog(DialogType.ERROR, self._dialog_window, "No selected item!")
            return

        if show_dialog(DialogType.QUESTION, self._dialog_window) == Gtk.ResponseType.CANCEL:
            return

        itrs_to_delete = []
        try:
            for itr in map(model.get_iter, paths):
                file_name = model.get_value(itr, 0)
                os.remove("{}{}{}".format(self._backup_path, file_name, ".zip"))
                itrs_to_delete.append(itr)
        except FileNotFoundError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            list(map(model.remove, itrs_to_delete))

    def on_view_popup_menu(self, menu, event):
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
            menu.popup(None, None, None, None, event.button, event.time)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    def restore(self, restore_type):
        model, paths = self._main_view.get_selection().get_selected_rows()
        if not paths:
            show_dialog(DialogType.ERROR, self._dialog_window, "No selected item!")
            return

        if len(paths) > 1:
            show_dialog(DialogType.ERROR, self._dialog_window, "Please, select only one item!")
            return

        if show_dialog(DialogType.QUESTION, self._dialog_window) == Gtk.ResponseType.CANCEL:
            return

        file_name = model.get_value(model.get_iter(paths[0]), 0) + ".zip"
        file_name = self._backup_path + file_name

        if restore_type is RestoreType.ALL:
            try:
                shutil.unpack_archive(file_name, self._data_path)
            except FileNotFoundError as e:
                self.show_info_message(str(e), Gtk.MessageType.ERROR)
            else:
                self._open_data_callback(self._data_path)
        elif restore_type is RestoreType.BOUQUETS:
            show_dialog(DialogType.ERROR, transient=self._dialog_window, text="Not implemented yet!")


if __name__ == "__main__":
    pass

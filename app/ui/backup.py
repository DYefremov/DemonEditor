import os
import shutil
import tempfile
from datetime import datetime
from enum import Enum

from app.commons import run_idle
from app.properties import Profile
from app.ui.dialogs import show_dialog, DialogType
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH


class RestoreType(Enum):
    BOUQUETS = 0
    ALL = 1


class BackupDialog:
    def __init__(self, transient, data_path, profile, callback):
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
        self._profile = profile
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

        file_name = model.get_value(model.get_iter(paths[0]), 0)
        full_file_name = self._backup_path + file_name + ".zip"

        try:
            if restore_type is RestoreType.ALL:
                clear_data_path(self._data_path)
                shutil.unpack_archive(full_file_name, self._data_path)
            elif restore_type is RestoreType.BOUQUETS:
                tmp_dir = tempfile.gettempdir() + "/" + file_name
                cond = (".tv", ".radio") if self._profile is Profile.ENIGMA_2 else ("bouquets.xml", "bouquets.xml")
                shutil.unpack_archive(full_file_name, tmp_dir)
                for file in filter(lambda f: f.endswith(cond), os.listdir(self._data_path)):
                    os.remove(os.path.join(self._data_path, file))
                for file in filter(lambda f: f.endswith(cond), os.listdir(tmp_dir)):
                    shutil.move(os.path.join(tmp_dir, file), self._data_path + file)
                shutil.rmtree(tmp_dir)
        except FileNotFoundError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            self.show_info_message("Done!", Gtk.MessageType.INFO)
            self._open_data_callback(self._data_path)


def backup_data(path):
    """ Creating data backup from a folder at the specified path """
    backup_path = "{}backup/{}/".format(path, datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    # backup files in data dir(skipping dirs and satellites.xml)
    for file in filter(lambda f: f != "satellites.xml" and os.path.isfile(os.path.join(path, f)), os.listdir(path)):
        shutil.move(os.path.join(path, file), backup_path + file)
    # compressing to zip and delete remaining files
    shutil.make_archive(backup_path, "zip", backup_path)
    shutil.rmtree(backup_path)


def clear_data_path(path):
    """ Clearing data at the specified path excluding satellites.xml file """
    for file in filter(lambda f: f != "satellites.xml" and os.path.isfile(os.path.join(path, f)), os.listdir(path)):
        os.remove(os.path.join(path, file))


if __name__ == "__main__":
    pass

""" Common module for showing dialogs """
from enum import Enum

from . import Gtk


class DialogType(Enum):
    INPUT = "input_dialog"
    MESSAGE = ""
    CHOOSER = "path_chooser_dialog"
    ERROR = "error_dialog"
    QUESTION = "question_dialog"
    ABOUT = "about_dialog"


def show_dialog(dialog_type: DialogType, transient, text=None, options=None, action_type=None, file_filter=None):
    """ Shows dialogs by name """
    builder = Gtk.Builder()
    builder.add_from_file("app/ui/dialogs.glade")
    dialog = builder.get_object(dialog_type.value)
    dialog.set_transient_for(transient)

    if dialog_type is DialogType.CHOOSER and options:
        if action_type is not None:
            dialog.set_action(action_type)
        if file_filter is not None:
            dialog.add_filter(file_filter)
        dialog.set_current_folder(options["data_dir_path"])

        response = dialog.run()
        if response == -12:  # -12 for fix assertion 'gtk_widget_get_can_default (widget)' failed
            path = options["data_dir_path"]
            if dialog.get_filename():
                path = dialog.get_filename()
                if action_type is not Gtk.FileChooserAction.OPEN:
                    path = path + "/"

            response = path
        dialog.destroy()

        return response

    if dialog_type is DialogType.INPUT:
        entry = builder.get_object("input_entry")
        entry.set_text(text if text else "")
        response = dialog.run()
        txt = entry.get_text()
        dialog.destroy()

        return txt if response == Gtk.ResponseType.OK else Gtk.ResponseType.CANCEL

    if text:
        dialog.set_markup(text)
    response = dialog.run()
    dialog.destroy()

    return response


if __name__ == "__main__":
    pass

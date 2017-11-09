""" Common module for showing dialogs """
from . import Gtk


def show_dialog(dialog_name, transient, text=None, options=None):
    """ Shows dialogs by name """
    builder = Gtk.Builder()
    builder.add_from_file("app/ui/dialogs.glade")
    dialog = builder.get_object(dialog_name)
    dialog.set_transient_for(transient)

    if dialog_name == "path_chooser_dialog" and options:
        dialog.set_current_folder(options["data_dir_path"])

    if dialog_name == "input_dialog":
        entry = builder.get_object("input_entry")
        entry.set_text(text)
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

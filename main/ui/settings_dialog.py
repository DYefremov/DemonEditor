from main.properties import write_config
from . import Gtk

__current_data_path = ""


def show_settings_dialog(transient, options):
    handlers = {"on_data_dir_field_icon_press": on_data_dir_field_icon_press}
    builder = Gtk.Builder()
    builder.add_from_file("ui/dialogs.glade")
    builder.connect_signals(handlers)
    dialog = builder.get_object("settings_dialog")
    dialog.set_transient_for(transient)
    host_field = builder.get_object("host_field")
    host_field.set_text(options["host"])
    port_field = builder.get_object("port_field")
    port_field.set_text(options["port"])
    login_field = builder.get_object("login_field")
    login_field.set_text(options["user"])
    password_field = builder.get_object("password_field")
    password_field.set_text(options["password"])
    services_field = builder.get_object("services_field")
    services_field.set_text(options["services_path"])
    user_bouquet_field = builder.get_object("user_bouquet_field")
    user_bouquet_field.set_text(options["user_bouquet_path"])
    satellites_xml_field = builder.get_object("satellites_xml_field")
    satellites_xml_field.set_text(options["satellites_xml_path"])
    data_dir_field = builder.get_object("data_dir_field")
    data_dir_field.set_text(options["data_dir_path"])
    global __current_data_path
    __current_data_path = options["data_dir_path"]

    if dialog.run() == Gtk.ResponseType.OK:
        options["host"] = host_field.get_text()
        options["port"] = port_field.get_text()
        options["user"] = login_field.get_text()
        options["password"] = password_field.get_text()
        options["services_path"] = services_field.get_text()
        options["user_bouquet_path"] = user_bouquet_field.get_text()
        options["satellites_xml_path"] = satellites_xml_field.get_text()
        options["data_dir_path"] = data_dir_field.get_text()
        write_config(options)
    dialog.destroy()


def on_data_dir_field_icon_press(entry, icon, event_button):
    builder = Gtk.Builder()
    builder.add_from_file("ui/dialogs.glade")
    dialog = builder.get_object("path_chooser_dialog")
    dialog.set_current_folder(__current_data_path)
    response = dialog.run()
    if response == -12:  # -12 for fix assertion 'gtk_widget_get_can_default (widget)' failed
        entry.set_text(dialog.get_filename() if dialog.get_filename() else __current_data_path)
    dialog.destroy()

    return response


if __name__ == "__main__":
    pass

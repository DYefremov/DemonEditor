import gi
import os
from ftplib import FTP
from main.properties import get_config, write_config
from main.eparser import get_channels, get_transponders, get_bouquets

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

__status_bar = None
__options = get_config()
__services_model = None
__bouquets_model = None
__DATA_FILES_LIST = ("tv", "radio", "lamedb")


def on_about_app(item):
    builder = Gtk.Builder()
    builder.add_from_file("editor_ui.glade")
    dialog = builder.get_object("about_dialog")
    dialog.run()
    dialog.destroy()


def get_handlers():
    return {
        "on_close_main_window": Gtk.main_quit,
        "on_about_app": on_about_app,
        "on_preferences": on_preferences,
        "on_download": on_download,
        "on_upload": on_upload,
        "on_data_dir_field_icon_press": on_path_open,
        "on_data_open_services": on_data_open_services,
        "on_data_open_bouquets": on_data_open_bouquets,
        "on_tree_view_key_release": on_tree_view_key_release
    }


def on_data_open_services(items):
    try:
        data_path = get_config()["data_dir_path"]
        for ch in get_channels(data_path + "lamedb"):
            items.append(ch)
    except Exception as e:
        __status_bar.push(1, getattr(e, "message", repr(e)))


def on_data_open_bouquets(item):
    data_path = get_config()["data_dir_path"]
    data = get_bouquets(data_path)
    for name, bouquets in data:
        parent = item.append(None, [name])
        for bouquet in bouquets:
            item.append(parent, [bouquet])


def on_path_open(*args):
    builder = Gtk.Builder()
    builder.add_from_file("editor_ui.glade")
    dialog = builder.get_object("path_chooser_dialog")
    response = dialog.run()
    if response == -12:  # for fix assertion 'gtk_widget_get_can_default (widget)' failed
        args[0].set_text(dialog.get_filename())
    dialog.destroy()


def on_preferences(item):
    builder = Gtk.Builder()
    builder.add_from_file("editor_ui.glade")
    builder.connect_signals(get_handlers())
    dialog = builder.get_object("settings_dialog")
    host_field = builder.get_object("host_field")
    host_field.set_text(__options["host"])
    port_field = builder.get_object("port_field")
    port_field.set_text(__options["port"])
    login_field = builder.get_object("login_field")
    login_field.set_text(__options["user"])
    password_field = builder.get_object("password_field")
    password_field.set_text(__options["password"])
    services_field = builder.get_object("services_field")
    services_field.set_text(__options["services_path"])
    user_bouquet_field = builder.get_object("user_bouquet_field")
    user_bouquet_field.set_text(__options["user_bouquet_path"])
    satellites_xml_field = builder.get_object("satellites_xml_field")
    satellites_xml_field.set_text(__options["satellites_xml_path"])
    data_dir_field = builder.get_object("data_dir_field")
    data_dir_field.set_text(__options["data_dir_path"])

    if dialog.run() == Gtk.ResponseType.OK:
        __options["host"] = host_field.get_text()
        __options["port"] = port_field.get_text()
        __options["user"] = login_field.get_text()
        __options["password"] = password_field.get_text()
        __options["services_path"] = services_field.get_text()
        __options["user_bouquet_path"] = user_bouquet_field.get_text()
        __options["satellites_xml_path"] = satellites_xml_field.get_text()
        __options["data_dir_path"] = data_dir_field.get_text()
        write_config(__options)
    dialog.destroy()


def on_tree_view_key_release(widget, event):
    key = event.keyval
    if key == Gdk.KEY_Tab:
        print("Tab")
    if key == Gdk.KEY_Delete:
        print("Delete")
    if key == Gdk.KEY_Up:
        print("Up")
    if key == Gdk.KEY_Down:
        print("Down")

    print(widget.get_name())


def on_upload(item):
    connect(__options, False)


def on_download(item):
    connect(__options)


def on_reload(item):
    pass


def connect(properties, download=True):
    assert isinstance(properties, dict)
    try:
        with FTP(properties["host"]) as ftp:
            ftp.login(user=properties["user"], passwd=properties["password"])
            save_path = properties["data_dir_path"]
            if download:
                # bouquets section
                ftp.cwd(properties["services_path"])
                files = []
                ftp.dir(files.append)
                for file in files:
                    name = str(file).strip()
                    if name.endswith(__DATA_FILES_LIST):
                        name = name.split()[-1]
                        with open(save_path + name, 'wb') as f:
                            ftp.retrbinary('RETR ' + name, f.write)
                # satellites.xml section
                ftp.cwd(properties["satellites_xml_path"])
                files.clear()
                ftp.dir(files.append)
                for file in files:
                    name = str(file).strip()
                    xml_file = "satellites.xml"
                    if name.endswith(xml_file):
                        with open(save_path + xml_file, 'wb') as f:
                            ftp.retrbinary('RETR ' + xml_file, f.write)
                __status_bar.push(1, ftp.voidcmd("NOOP"))
                for name in os.listdir(save_path):
                    print(name)
            else:
                for file_name in os.listdir(save_path):
                    print(file_name)
                    # Open the file for transfer in binary mode
                    # f = open(file_name, "rb")
                    # transfer the file into receiver
                    # send = ftp.storbinary("STOR " + file_name, f)
    except Exception as e:
        __status_bar.remove_all(1)
        __status_bar.push(1, getattr(e, "message", repr(e)))  # Or maybe so: getattr(e, 'message', str(e))


def init_ui():
    builder = Gtk.Builder()
    builder.add_from_file("editor_ui.glade")
    main_window = builder.get_object("main_window")
    global __status_bar
    __status_bar = builder.get_object("status_bar")
    builder.connect_signals(get_handlers())
    main_window.show_all()


def start_app():
    init_ui()
    Gtk.main()


def close_app():
    Gtk.main_quit()


if __name__ == "__main__":
    start_app()

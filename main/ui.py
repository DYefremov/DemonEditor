import gi
from ftplib import FTP
from properties import get_config, write_config

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

status_bar = None


def on_about_app(item):
    builder = Gtk.Builder()
    builder.add_from_file("editor_ui.glade")
    dialog = builder.get_object("about_dialog")
    dialog.run()
    dialog.destroy()


def on_preferences(item):
    builder = Gtk.Builder()
    builder.add_from_file("editor_ui.glade")
    dialog = builder.get_object("settings_dialog")
    options = get_config()
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

    if dialog.run() == Gtk.ResponseType.OK:
        options["host"] = host_field.get_text()
        options["port"] = port_field.get_text()
        options["user"] = login_field.get_text()
        options["password"] = password_field.get_text()
        options["services_path"] = services_field.get_text()
        options["user_bouquet_path"] = user_bouquet_field.get_text()
        options["satellites_xml_path"] = satellites_xml_field.get_text()
        write_config(options)
    dialog.destroy()


def on_connect(item):
    connect(get_config())


def connect(properties):
    assert isinstance(properties, dict)
    try:
        with FTP(properties["host"]) as ftp:
            ftp.login(user=properties["user"], passwd=properties["password"])
            status_bar.push(1, ftp.voidcmd("NOOP"))
            ftp.cwd(properties["services_path"])
            ftp.retrlines("LIST")
    except Exception as e:
        status_bar.remove_all(1)
        status_bar.push(1, getattr(e, "message", repr(e)))  # Or maybe so: getattr(e, 'message', str(e))


def init_ui():
    handlers = {
        "on_close_main_window": Gtk.main_quit,
        "on_about_app": on_about_app,
        "on_preferences": on_preferences,
        "on_connect": on_connect
    }
    builder = Gtk.Builder()
    builder.add_from_file("editor_ui.glade")
    main_window = builder.get_object("main_window")
    global status_bar
    status_bar = builder.get_object("status_bar")
    builder.connect_signals(handlers)
    main_window.show_all()


def start_app():
    init_ui()
    Gtk.main()


def close_app():
    Gtk.main_quit()


if __name__ == "__main__":
    start_app()

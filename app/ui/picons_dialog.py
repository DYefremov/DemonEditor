from . import Gtk, Gdk, UI_RESOURCES_PATH


class PiconsDialog:
    def __init__(self, transient, path):
        handlers = {}

        builder = Gtk.Builder()
        builder.add_objects_from_file(UI_RESOURCES_PATH + "picons_dialog.glade", ("picons_dialog", "recive_image"))
        builder.connect_signals(handlers)
        self._dialog = builder.get_object("picons_dialog")
        self._dialog.set_transient_for(transient)

    def show(self):
        self._dialog.run()
        self._dialog.destroy()


if __name__ == "__main__":
    pass

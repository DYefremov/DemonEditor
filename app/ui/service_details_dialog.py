from . import Gtk, UI_RESOURCES_PATH


class ServiceDetailsDialog:
    def __init__(self, transient):
        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "service_details_dialog.glade")

        self._dialog = builder.get_object("service_details_dialog")
        self._dialog.set_transient_for(transient)

    def show(self):
        response = self._dialog.run()
        if response == Gtk.ResponseType.OK:
            pass
        self._dialog.destroy()

        return response


if __name__ == "__main__":
    dialog = ServiceDetailsDialog()
    dialog.show()

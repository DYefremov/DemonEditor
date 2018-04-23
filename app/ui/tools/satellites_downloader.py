from app.ui.uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN


class SatellitesDownloaderDialog:
    def __init__(self, transient, options):

        handlers = {}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "tools.glade",
                                      ("satellites_dialog", "source_urls_list_store", "satellites_list_store"))
        builder.connect_signals(handlers)
        self._dialog = builder.get_object("satellites_dialog")
        self._dialog.set_transient_for(transient)
        self._satellites_tree_view = builder.get_object("satellites_tree_view")

    def show(self):
        self._dialog.run()
        self._dialog.destroy()


if __name__ == "__main__":
    pass

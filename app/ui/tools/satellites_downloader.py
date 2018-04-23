from app.commons import run_idle
from app.tools.satellites import SatellitesParser
from ..uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN


class SatellitesDownloaderDialog:
    def __init__(self, transient, options):

        handlers = {"on_satellites_receive": self.on_satellites_receive}

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

    @run_idle
    def on_satellites_receive(self, item):
        parser = SatellitesParser(url="https://www.flysat.com/satlist.php")
        sats = parser.get_satellites()
        if sats:
            model = self._satellites_tree_view.get_model()
            model.clear()
            for sat in sats:
                model.append((sat[1], sat[2], sat[3], sat[0], False))


if __name__ == "__main__":
    pass

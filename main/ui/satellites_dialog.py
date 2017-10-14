import gi

from main.eparser import get_satellites

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk


class SatellitesDialog:
    def __init__(self, transient, data_path):
        handlers = {
            "on_satellites_list_load": self.on_satellites_list_load
        }
        builder = Gtk.Builder()
        builder.add_from_file("./ui/satellites_dialog.glade")
        builder.connect_signals(handlers)
        self._dialog = builder.get_object("satellites_editor_dialog")
        self._data_path = data_path
        self._dialog.set_transient_for(transient)

    def show(self):
        self._dialog.run()
        self._dialog.destroy()

    def on_satellites_list_load(self, model):
        """ Load satellites data into model """
        satellites = get_satellites(self._data_path)
        model.clear()
        aggr = [None for x in range(9)]
        for name, flags, pos, transponders in satellites:
            parent = model.append(None, [name, *aggr])
            for transponder in transponders:
                model.append(parent, ["Transponder:", *transponder])


if __name__ == "__main__":
    pass

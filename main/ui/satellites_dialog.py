from main.eparser import get_satellites
from . import Gtk

__data_path = None


def show_satellites_dialog(transient, data_path):
    global __data_path
    __data_path = data_path
    handlers = {"on_satellites_list_load": on_satellites_list_load}
    builder = Gtk.Builder()
    builder.add_from_file("./ui/satellites_dialog.glade")
    builder.connect_signals(handlers)
    dialog = builder.get_object("satellites_editor_dialog")
    dialog.set_transient_for(transient)
    dialog.run()
    dialog.destroy()


def on_satellites_list_load(model):
    """ Load satellites data into model """
    satellites = get_satellites(__data_path)
    model.clear()
    aggr = [None for x in range(9)]
    for name, flags, pos, transponders in satellites:
        parent = model.append(None, [name, *aggr])
        for transponder in transponders:
            model.append(parent, ["Transponder:", *transponder])


if __name__ == "__main__":
    pass

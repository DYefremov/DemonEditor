from main.eparser import get_satellites
from main.eparser.satxml import Satellite, Transponder
from . import Gtk

__data_path = None


def show_satellites_dialog(transient, data_path):
    global __data_path
    __data_path = data_path
    handlers = {"on_satellites_list_load": on_satellites_list_load, "on_remove": on_remove, "on_save": on_save}
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
        parent = model.append(None, [name, *aggr, flags, pos])
        for transponder in transponders:
            model.append(parent, ["Transponder:", *transponder, None, None])


def on_remove(view):
    selection = view.get_selection()
    model, paths = selection.get_selected_rows()
    itrs = [model.get_iter(path) for path in paths]
    for itr in itrs:
        model.remove(itr)


def on_save(view):
    model = view.get_model()
    satellites = []
    model.foreach(parse_data, satellites)
    for sat in satellites:
        print(sat)


def parse_data(model, path, itr, sats):
    if model.iter_has_child(itr):
        num_of_children = model.iter_n_children(itr)
        transponders = []
        for num in range(num_of_children):
            transponder_itr = model.iter_nth_child(itr, num)
            transponder = model.get(transponder_itr, *[item for item in range(model.get_n_columns())])
            transponders.append(Transponder(*transponder[1:-2]))
        sat = model.get(itr, *[item for item in range(model.get_n_columns())])
        satellite = Satellite(sat[0], sat[-2], sat[-1], transponders)
        sats.append(satellite)


if __name__ == "__main__":
    pass

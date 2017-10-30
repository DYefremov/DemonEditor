from main.commons import run_task
from main.eparser import get_satellites, write_satellites, Satellite, Transponder
from . import Gtk, Gdk


def show_satellites_dialog(transient, data_path):
    dialog = SatellitesDialog(transient, data_path)
    dialog.run()
    dialog.destroy()


class SatellitesDialog:
    __slots__ = ["_dialog", "_data_path", "_stores"]

    def __init__(self, transient, data_path):
        self._data_path = data_path

        handlers = {"on_satellites_list_load": self.on_satellites_list_load,
                    "on_remove": self.on_remove,
                    "on_save": self.on_save,
                    "on_popup_menu": self.on_popup_menu,
                    "on_edited": self.on_edited}

        builder = Gtk.Builder()
        builder.add_from_file("./ui/satellites_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("satellites_editor_dialog")
        self._dialog.set_transient_for(transient)
        self._stores = {3: builder.get_object("pol_store"),
                        4: builder.get_object("fec_store"),
                        5: builder.get_object("system_store"),
                        6: builder.get_object("mod_store")}

    def run(self):
        self._dialog.run()

    def destroy(self):
        self._dialog.destroy()

    @run_task
    def on_satellites_list_load(self, model):
        """ Load satellites data into model """
        satellites = get_satellites(self._data_path)
        model.clear()
        aggr = [None for x in range(9)]

        for name, flags, pos, transponders in satellites:
            parent = model.append(None, [name, *aggr, flags, pos])
            for transponder in transponders:
                model.append(parent, ["Transponder:", *transponder, None, None])

    def on_edited(self, view, path, value):
        path, focus_column = view.get_cursor()
        column_index = view.get_columns().index(focus_column)
        model = view.get_model()

        if column_index > 2:
            # value type is Gtk.TreeIter
            new_value = self._stores[column_index].get_value(value, 0)
            # model[path][column_index] = new_value
        else:
            model[path][column_index] = value

    @staticmethod
    def on_remove(view):
        selection = view.get_selection()
        model, paths = selection.get_selected_rows()
        itrs = [model.get_iter(path) for path in paths]
        for itr in itrs:
            model.remove(itr)

    @run_task
    def on_save(self, view):
        model = view.get_model()
        satellites = []
        model.foreach(self.parse_data, satellites)
        write_satellites(satellites, self._data_path + "tmp/")  # temporary!!!

    @staticmethod
    def parse_data(model, path, itr, sats):
        if model.iter_has_child(itr):
            num_of_children = model.iter_n_children(itr)
            transponders = []
            num_columns = model.get_n_columns()

            for num in range(num_of_children):
                transponder_itr = model.iter_nth_child(itr, num)
                transponder = model.get(transponder_itr, *[item for item in range(num_columns)])
                transponders.append(Transponder(*transponder[1:-2]))

            sat = model.get(itr, *[item for item in range(num_columns)])
            satellite = Satellite(sat[0], sat[-2], sat[-1], transponders)
            sats.append(satellite)

    @staticmethod
    def on_popup_menu(menu, event):
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
            menu.popup(None, None, None, None, event.button, event.time)


if __name__ == "__main__":
    pass

from math import fabs

from main.commons import run_task
from main.eparser import get_satellites, write_satellites, Satellite, Transponder
from . import Gtk, Gdk


def show_satellites_dialog(transient, options):
    dialog = SatellitesDialog(transient, options)
    dialog.run()
    dialog.destroy()


class SatellitesDialog:
    _aggr = [None for x in range(9)]  # aggregate

    __slots__ = ["_dialog", "_data_path", "_stores", "_options", "_sat_view"]

    def __init__(self, transient, options):
        self._data_path = options["data_dir_path"]
        self._options = options

        handlers = {"on_open": self.on_open,
                    "on_remove": self.on_remove,
                    "on_save": self.on_save,
                    "on_popup_menu": self.on_popup_menu,
                    "on_add": self.on_add,
                    "on_edit": self.on_edit,
                    "on_key_release": self.on_key_release,
                    "on_row_activated": self.on_row_activated,
                    "on_resize": self.on_resize}

        builder = Gtk.Builder()
        builder.add_objects_from_file("./ui/satellites_dialog.glade",
                                      ("satellites_editor_dialog", "satellites_tree_store", "popup_menu"))
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("satellites_editor_dialog")
        self._dialog.set_transient_for(transient)
        self._dialog.get_content_area().set_border_width(0)  # The width of the border around the main dialog area!
        self._sat_view = builder.get_object("satellites_editor_tree_view")
        # Setting the last size of the dialog window if it was saved
        window_size = self._options.get("sat_editor_window_size", None)
        if window_size:
            self._dialog.resize(*window_size)

        self._stores = {3: builder.get_object("pol_store"),
                        4: builder.get_object("fec_store"),
                        5: builder.get_object("system_store"),
                        6: builder.get_object("mod_store")}
        self.on_satellites_list_load(self._sat_view.get_model())

    def run(self):
        self._dialog.run()

    def destroy(self):
        self._dialog.destroy()

    def on_resize(self, window):
        """ Stores new size properties for dialog window after resize """
        if self._options:
            self._options["sat_editor_window_size"] = window.get_size()

    def on_open(self, model):
        builder = Gtk.Builder()
        builder.add_objects_from_file("./ui/dialogs.glade", ("path_chooser_dialog",))
        ch_dialog = builder.get_object("path_chooser_dialog")
        ch_dialog.set_transient_for(self._dialog)

        if ch_dialog.run() == 12:
            path = ch_dialog.get_filename()
            if path:
                print(path)
                self._data_path = path
            self.on_satellites_list_load(model)
        ch_dialog.destroy()

    @staticmethod
    def on_row_activated(view, path, column):
        if view.row_expanded(path):
            view.collapse_row(path)
        else:
            view.expand_row(path, column)

    def on_key_release(self, view, event):
        """  Handling  keystrokes  """
        key = event.keyval
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK

        if key == Gdk.KEY_Delete:
            self.on_remove(view)
        elif key == Gdk.KEY_Insert:
            self.on_add(view)
        elif key == Gdk.KEY_F2:
            self.on_edit(view)
        elif ctrl and key == Gdk.KEY_s or key == Gdk.KEY_S:
            self.on_satellite()
        elif ctrl and key == Gdk.KEY_t or key == Gdk.KEY_T:
            self.on_transponder()
        elif key == Gdk.KEY_space:
            pass

    @run_task
    def on_satellites_list_load(self, model):
        """ Load satellites data into model """
        satellites = get_satellites(self._data_path)
        model.clear()

        for name, flags, pos, transponders in satellites:
            parent = model.append(None, [name, *self._aggr, flags, pos])
            for transponder in transponders:
                model.append(parent, ["Transponder:", *transponder, None, None])

    def on_add(self, view):
        self.on_edit(view, force=True)

    def on_edit(self, view, force=False):
        """ """
        model, paths = view.get_selection().get_selected_rows()
        paths_count = len(paths)

        if paths_count == 0:
            return
        elif paths_count > 1:
            print("Error dialog!")
            return

        itr = model.get_iter(paths[0])
        row = model.get(itr, *[x for x in range(view.get_n_columns())])
        # maybe temporary!
        if row[-1]:  # satellite
            sat = self.on_satellite(None if force else Satellite(row[0], None, row[-1], None))
            if not sat:
                return
            if force:
                model.insert(None, int(paths[0][0] + 1), [sat.name, *self._aggr, sat.flags, sat.position])
            else:
                model.set(itr, {0: sat.name, 10: sat.flags, 11: sat.position})
        else:
            tr = self.on_transponder(None if force else Transponder(*row[1:-2]))
            if not tr:
                return
            if force:
                model.insert(model.iter_parent(itr), int(paths[0][0] + 1), ["Transponder:", *tr, None, None])
            else:
                model.set(itr, {1: tr.frequency, 2: tr.symbol_rate, 3: tr.polarization,
                                4: tr.fec_inner, 5: tr.system, 6: tr.modulation,
                                7: tr.pls_mode, 8: tr.pls_code, 9: tr.is_id})

    def on_satellite(self, satellite=None):
        sat_dialog = SatelliteDialog(self._dialog, satellite)
        sat = sat_dialog.run()
        sat_dialog.destroy()

        return sat

    def on_transponder(self, transponder=None):
        dialog = TransponderDialog(self._dialog, transponder)
        tr = dialog.run()
        dialog.destroy()

        return tr

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


class TransponderDialog:
    """ Shows dialog for adding or edit transponder """

    def __init__(self, transient, transponder: Transponder = None):
        builder = Gtk.Builder()
        builder.add_objects_from_file("./ui/satellites_dialog.glade",
                                      ("transponder_dialog",
                                       "pol_store", "fec_store",
                                       "mod_store", "system_store",
                                       "pls_mode_store"))

        self._dialog = builder.get_object("transponder_dialog")
        self._dialog.set_transient_for(transient)
        self._freq_entry = builder.get_object("freq_entry")
        self._rate_entry = builder.get_object("rate_entry")
        self._pol_box = builder.get_object("pol_box")
        self._fec_box = builder.get_object("fec_box")
        self._sys_box = builder.get_object("sys_box")
        self._mod_box = builder.get_object("mod_box")
        self._pls_mode_box = builder.get_object("pls_mode_box")
        self._pls_code_entry = builder.get_object("pls_code_entry")
        self._is_id_entry = builder.get_object("is_id_entry")

        if transponder:
            self.init_transponder(transponder)

    def run(self):
        if self._dialog.run() == Gtk.ResponseType.CANCEL:
            return

        return self.to_transponder()

    def destroy(self):
        self._dialog.destroy()

    def init_transponder(self, transponder):
        self._freq_entry.set_text(transponder.frequency)
        self._rate_entry.set_text(transponder.symbol_rate)
        self._pol_box.set_active_id(transponder.polarization)
        self._fec_box.set_active_id(transponder.fec_inner)
        self._sys_box.set_active_id(transponder.system)
        self._mod_box.set_active_id(transponder.modulation)
        self._pls_mode_box.set_active_id(transponder.pls_mode)
        self._is_id_entry.set_text(transponder.is_id if transponder.is_id else "")
        self._pls_code_entry.set_text(transponder.pls_code if transponder.pls_code else "")

    def to_transponder(self):
        return Transponder(frequency=self._freq_entry.get_text(),
                           symbol_rate=self._rate_entry.get_text(),
                           polarization=self._pol_box.get_active_id(),
                           fec_inner=self._fec_box.get_active_id(),
                           system=self._sys_box.get_active_id(),
                           modulation=self._mod_box.get_active_id(),
                           pls_mode=self._pls_mode_box.get_active_id(),
                           pls_code=self._pls_code_entry.get_text(),
                           is_id=self._is_id_entry.get_text())


class SatelliteDialog:
    """ Shows dialog for adding or edit satellite """

    def __init__(self, transient, satellite: Satellite = None):
        builder = Gtk.Builder()
        builder.add_objects_from_file("./ui/satellites_dialog.glade",
                                      ("satellite_dialog", "side_store", "pos_adjustment"))

        self._dialog = builder.get_object("satellite_dialog")
        self._dialog.set_transient_for(transient)
        self._sat_name = builder.get_object("sat_name_entry")
        self._sat_position = builder.get_object("sat_position_button")
        self._side = builder.get_object("side_box")

        if satellite:
            self._sat_name.set_text(satellite.name[0:satellite.name.find("(")].strip())
            pos = satellite.position
            pos = float("{}.{}".format(pos[:-1], pos[-1:]))
            self._sat_position.set_value(fabs(pos))
            self._side.set_active(0 if pos >= 0 else 1)

    def run(self):
        if self._dialog.run() == Gtk.ResponseType.CANCEL:
            return

        return self.to_satellite()

    def destroy(self):
        self._dialog.destroy()

    def to_satellite(self):
        name = self._sat_name.get_text()
        pos = round(self._sat_position.get_value(), 1)
        side = self._side.get_active()
        name = "{} ({}{})".format(name, pos, self._side.get_active_id())
        pos = "{}{}{}".format("-" if side == 1 else "", *str(pos).split("."))

        return Satellite(name=name, flags=None, position=pos, transponders=None)


if __name__ == "__main__":
    pass

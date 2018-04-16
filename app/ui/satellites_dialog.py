import re
from math import fabs

from app.commons import run_idle
from app.eparser import get_satellites, write_satellites, Satellite, Transponder
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, TEXT_DOMAIN
from .dialogs import show_dialog, DialogType, WaitDialog
from .main_helper import move_items, scroll_to


def show_satellites_dialog(transient, options):
    dialog = SatellitesDialog(transient, options)
    dialog.run()
    dialog.destroy()


class SatellitesDialog:
    __slots__ = ["_dialog", "_data_path", "_stores", "_options", "_sat_view", "_wait_dialog"]

    _aggr = [None for x in range(9)]  # aggregate

    def __init__(self, transient, options):
        self._data_path = options.get("data_dir_path") + "satellites.xml"
        self._options = options

        handlers = {"on_open": self.on_open,
                    "on_remove": self.on_remove,
                    "on_save": self.on_save,
                    "on_up": self.on_up,
                    "on_down": self.on_down,
                    "on_popup_menu": self.on_popup_menu,
                    "on_satellite_add": self.on_satellite_add,
                    "on_transponder_add": self.on_transponder_add,
                    "on_edit": self.on_edit,
                    "on_key_release": self.on_key_release,
                    "on_row_activated": self.on_row_activated,
                    "on_resize": self.on_resize,
                    "on_quit": self.on_quit}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "satellites_dialog.glade",
                                      ("satellites_editor_dialog", "satellites_tree_store",
                                       "popup_menu", "add_popup_menu", "add_menu_icon"))
        builder.connect_signals(handlers)
        # Adding custom image for add_menu_tool_button
        add_menu_tool_button = builder.get_object("add_menu_tool_button")
        add_menu_tool_button.set_image(builder.get_object("add_menu_icon"))

        self._dialog = builder.get_object("satellites_editor_dialog")
        self._dialog.set_transient_for(transient)
        self._dialog.get_content_area().set_border_width(0)  # The width of the border around the app dialog area!
        self._sat_view = builder.get_object("satellites_editor_tree_view")
        self._wait_dialog = WaitDialog(self._dialog)
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

    def on_quit(self, item):
        self.destroy()

    def on_open(self, model):
        file_filter = Gtk.FileFilter()
        file_filter.add_pattern("satellites.xml")
        file_filter.set_name("satellites.xml")
        response = show_dialog(dialog_type=DialogType.CHOOSER,
                               transient=self._dialog,
                               options=self._options,
                               action_type=Gtk.FileChooserAction.OPEN,
                               file_filter=file_filter)
        if response == Gtk.ResponseType.CANCEL:
            return

        if not str(response).endswith("satellites.xml"):
            show_dialog(DialogType.ERROR, self._dialog, text="No satellites.xml file is selected!")
            return
        self._data_path = response
        self.on_satellites_list_load(model)

    @staticmethod
    def on_row_activated(view, path, column):
        if view.row_expanded(path):
            view.collapse_row(path)
        else:
            view.expand_row(path, column)

    def on_up(self, item):
        move_items(Gdk.KEY_Up, self._sat_view)

    def on_down(self, item):
        move_items(Gdk.KEY_Down, self._sat_view)

    def on_key_release(self, view, event):
        """  Handling  keystrokes  """
        key = event.keyval
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK

        if key == Gdk.KEY_Delete:
            self.on_remove(view)
        elif key == Gdk.KEY_Insert:
            pass
        elif ctrl and key == Gdk.KEY_E or key == Gdk.KEY_e:
            self.on_edit(view)
        elif ctrl and key == Gdk.KEY_s or key == Gdk.KEY_S:
            self.on_satellite()
        elif ctrl and key == Gdk.KEY_t or key == Gdk.KEY_T:
            self.on_transponder()
        elif key == Gdk.KEY_space:
            pass
        elif ctrl and key in _MOVE_KEYS:
            move_items(key, self._sat_view)
        elif key == Gdk.KEY_Left or key == Gdk.KEY_Right:
            view.do_unselect_all(view)

    @run_idle
    def on_satellites_list_load(self, model):
        """ Load satellites data into model """
        try:
            self._wait_dialog.show()
            satellites = get_satellites(self._data_path)
        except FileNotFoundError as e:
            show_dialog(DialogType.ERROR, self._dialog, getattr(e, "message", str(e)) +
                        "\n\nPlease, download files from receiver or setup your path for read data!")
        else:
            model.clear()
            self.append_data(model, satellites)
        finally:
            self._wait_dialog.hide()

    @run_idle
    def append_data(self, model, satellites):
        for name, flags, pos, transponders in satellites:
            parent = model.append(None, [name, *self._aggr, flags, pos])
            for transponder in transponders:
                model.append(parent, ["Transponder:", *transponder, None, None])

    def on_add(self, view):
        """ Common adding """
        self.on_edit(view, force=True)

    def on_satellite_add(self, item):
        self.on_satellite(None)

    def on_transponder_add(self, item):
        self.on_transponder(None)

    def on_edit(self, view, force=False):
        """ Common edit """
        paths = self.check_selection(view, "Please, select only one item!")
        if not paths:
            return

        model = view.get_model()
        itr = model.get_iter(paths[0])
        row = model.get(itr, *[x for x in range(view.get_n_columns())])

        if row[-1]:  # satellite
            self.on_satellite(None if force else Satellite(row[0], None, row[-1], None), itr)
        else:
            self.on_transponder(None if force else Transponder(*row[1:-2]), itr)

    def on_satellite(self, satellite=None, edited_itr=None):
        """ Create or edit satellite"""
        sat_dialog = SatelliteDialog(self._dialog, satellite)
        sat = sat_dialog.run()
        sat_dialog.destroy()

        if sat:
            view = self._sat_view
            model = view.get_model()
            if satellite and edited_itr:
                model.set(edited_itr, {0: sat.name, 10: sat.flags, 11: sat.position})
            else:
                index = self.get_sat_position_index(sat.position, model)
                model.insert(None, index, [sat.name, *self._aggr, sat.flags, sat.position])
                scroll_to(index, view)

    def on_transponder(self, transponder=None, edited_itr=None):
        """ Create or edit transponder """

        paths = self.check_selection(self._sat_view, "Please, select only one satellite!")
        if paths is None:
            return
        elif len(paths) == 0:
            show_dialog(DialogType.ERROR, self._dialog, "No satellite is selected!")
            return

        dialog = TransponderDialog(self._dialog, transponder)
        tr = dialog.run()
        dialog.destroy()

        if tr:
            view = self._sat_view
            model = view.get_model()
            if transponder and edited_itr:
                model.set(edited_itr, {1: tr.frequency, 2: tr.symbol_rate, 3: tr.polarization,
                                       4: tr.fec_inner, 5: tr.system, 6: tr.modulation,
                                       7: tr.pls_mode, 8: tr.pls_code, 9: tr.is_id})
            else:
                row = ["Transponder:", *tr, None, None]
                model, paths = view.get_selection().get_selected_rows()
                itr = model.get_iter(paths[0])
                view.expand_row(paths[0], 0)
                # Get parent iter if selected transponder
                parent_itr = model.iter_parent(itr)
                if parent_itr:
                    itr = parent_itr
                freq = int(tr.frequency if tr.frequency else 0)
                tr_itr = model.iter_children(itr)
                # Inserting according to frequency value.
                while tr_itr:
                    cur_freq = int(model.get_value(tr_itr, 1))
                    if freq <= cur_freq:
                        path = model.get_path(tr_itr)
                        index = path.get_indices()[1]
                        model.insert(model.iter_parent(tr_itr), index, row)
                        scroll_to(path, view)
                        break
                    else:
                        tr_itr = model.iter_next(tr_itr)
                else:
                    itr = model.append(itr, row)
                    scroll_to(model.get_path(itr), view)

    def get_sat_position_index(self, pos, model):
        """ Search and returns index after given position """
        pos = int(pos)
        row = next(filter(lambda r: int(r[-1]) >= pos, model), None)

        return row.path[0] if row else len(model)

    def check_selection(self, view, message):
        """ Checks if any row is selected. Shows error dialog if selected more than one.

        returns selected path or None
        """
        model, paths = view.get_selection().get_selected_rows()
        paths_count = len(paths)

        if paths_count > 1:
            show_dialog(DialogType.ERROR, self._dialog, message)
            return

        return paths

    @staticmethod
    def on_remove(view):
        selection = view.get_selection()
        model, paths = selection.get_selected_rows()
        itrs = [model.get_iter(path) for path in paths]

        for itr in itrs:
            model.remove(itr)

    def on_save(self, view):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        model = view.get_model()
        satellites = []
        model.foreach(self.parse_data, satellites)
        write_satellites(satellites, self._data_path)

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

        handlers = {"on_entry_changed": self.on_entry_changed}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "satellites_dialog.glade",
                                      ("transponder_dialog",
                                       "pol_store", "fec_store",
                                       "mod_store", "system_store",
                                       "pls_mode_store"))
        builder.connect_signals(handlers)

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
        # pattern for frequency and rate entries (only digits)
        self._pattern = re.compile("\D")
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._freq_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                                     Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._rate_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                                     Gtk.STYLE_PROVIDER_PRIORITY_USER)
        if transponder:
            self.init_transponder(transponder)

    def run(self):
        while self._dialog.run() != Gtk.ResponseType.CANCEL:
            tr = self.to_transponder()
            if self.is_accept(tr):
                return tr
            show_dialog(DialogType.ERROR, self._dialog, "Please check your parameters and try again.")

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

    def on_entry_changed(self, entry):
        entry.set_name("digit-entry" if self._pattern.search(entry.get_text()) else "GtkEntry")

    def is_accept(self, tr):
        if self._pattern.search(tr.frequency) or not tr.frequency:
            return False
        elif self._pattern.search(tr.symbol_rate) or not tr.symbol_rate:
            return False
        elif None in (tr.polarization, tr.fec_inner, tr.system, tr.modulation):
            return False
        elif self._pattern.search(tr.pls_code) or self._pattern.search(tr.is_id):
            return False

        return True


class SatelliteDialog:
    """ Shows dialog for adding or edit satellite """

    def __init__(self, transient, satellite: Satellite = None):
        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "satellites_dialog.glade",
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
            self._side.set_active(0 if pos >= 0 else 1)  # E or W

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

        return Satellite(name=name, flags="0", position=pos, transponders=None)


if __name__ == "__main__":
    pass

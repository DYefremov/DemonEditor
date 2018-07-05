import re
import time
import concurrent.futures
from math import fabs

from app.commons import run_idle, run_task
from app.eparser import get_satellites, write_satellites, Satellite, Transponder
from app.tools.satellites import SatellitesParser, SatelliteSource
from .search import SearchProvider
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, TEXT_DOMAIN, MOVE_KEYS
from .dialogs import show_dialog, DialogType, WaitDialog
from .main_helper import move_items, scroll_to, append_text_to_tview, get_base_model


def show_satellites_dialog(transient, options):
    SatellitesDialog(transient, options).show()


class SatellitesDialog:
    _aggr = [None for x in range(9)]  # aggregate

    def __init__(self, transient, options):
        self._data_path = options.get("data_dir_path") + "satellites.xml"
        self._options = options

        handlers = {"on_open": self.on_open,
                    "on_remove": self.on_remove,
                    "on_save": self.on_save,
                    "on_update": self.on_update,
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
                                      ("satellites_editor_dialog", "satellites_tree_store", "popup_menu",
                                       "left_header_menu", "add_header_popover_menu"))
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("satellites_editor_dialog")
        self._dialog.set_transient_for(transient)
        # self._dialog.get_content_area().set_border_width(0)  # The width of the border around the app dialog area!
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

    @run_idle
    def show(self):
        self._dialog.run()
        self._dialog.destroy()

    def on_resize(self, window):
        """ Stores new size properties for dialog window after resize """
        if self._options:
            self._options["sat_editor_window_size"] = window.get_size()

    def on_quit(self, *args):
        self._dialog.destroy()

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
        elif ctrl and key in MOVE_KEYS:
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
        for sat in satellites:
            append_satellite(model, sat)

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
        if len(paths) > 1:
            show_dialog(DialogType.ERROR, self._dialog, message)
            return

        return paths

    @staticmethod
    def on_remove(view):
        selection = view.get_selection()
        model, paths = selection.get_selected_rows()

        for itr in [model.get_iter(path) for path in paths]:
            model.remove(itr)

    def on_save(self, view):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        model = view.get_model()
        satellites = []
        model.foreach(self.parse_data, satellites)
        write_satellites(satellites, self._data_path)

    def on_update(self, item):
        dialog = SatellitesUpdateDialog(self._dialog, self._sat_view.get_model())
        dialog.run()
        dialog.destroy()

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


# ***************** Transponder dialog *******************#

class TransponderDialog:
    """ Shows dialog for adding or edit transponder """

    def __init__(self, transient, transponder: Transponder = None):

        handlers = {"on_entry_changed": self.on_entry_changed}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "satellites_dialog.glade",
                                      ("transponder_dialog", "pol_store", "fec_store", "mod_store", "system_store",
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


# ***************** Satellite dialog *******************#

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


# ***************** Satellite update dialog *******************#

class SatellitesUpdateDialog:
    """ Dialog for update satellites over internet """

    def __init__(self, transient, main_model):
        handlers = {"on_update_satellites_list": self.on_update_satellites_list,
                    "on_receive_satellites_list": self.on_receive_satellites_list,
                    "on_cancel_receive": self.on_cancel_receive,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_find_toggled": self.on_find_toggled,
                    "on_filter": self.on_filter,
                    "on_search": self.on_search,
                    "on_search_down": self.on_search_down,
                    "on_search_up": self.on_search_up,
                    "on_quit": self.on_quit}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_objects_from_file(UI_RESOURCES_PATH + "satellites_dialog.glade",
                                      ("satellites_update_dialog", "update_source_store", "update_sat_list_store",
                                       "update_sat_list_model_filter", "update_sat_list_model_sort", "side_store",
                                       "pos_adjustment", "pos_adjustment2"))
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("satellites_update_dialog")
        self._dialog.set_transient_for(transient)
        self._main_model = main_model
        # self._dialog.get_content_area().set_border_width(0)
        self._sat_view = builder.get_object("sat_update_tree_view")
        self._source_box = builder.get_object("source_combo_box")
        self._sat_update_expander = builder.get_object("sat_update_expander")
        self._text_view = builder.get_object("text_view")
        self._receive_button = builder.get_object("receive_sat_list_tool_button")
        self._sat_update_info_bar = builder.get_object("sat_update_info_bar")
        self._info_bar_message_label = builder.get_object("info_bar_message_label")
        # Filter
        self._filter_info_bar = builder.get_object("sat_update_filter_info_bar")
        self._from_pos_button = builder.get_object("from_pos_button")
        self._to_pos_button = builder.get_object("to_pos_button")
        self._filter_from_combo_box = builder.get_object("filter_from_combo_box")
        self._filter_to_combo_box = builder.get_object("filter_to_combo_box")
        self._filter_model = builder.get_object("update_sat_list_model_filter")
        self._filter_model.set_visible_func(self.filter_function)
        self._filter_positions = (0, 0)
        # Search
        self._search_info_bar = builder.get_object("sat_update_search_info_bar")
        self._search_provider = SearchProvider((self._sat_view,),
                                               builder.get_object("sat_update_search_down_button"),
                                               builder.get_object("sat_update_search_up_button"))

        self._download_task = False
        self._parser = None

    def run(self):
        if self._dialog.run() == Gtk.ResponseType.CANCEL:
            self._download_task = False
            return

    def destroy(self):
        self._dialog.destroy()

    def on_update_satellites_list(self, item):
        if self._download_task:
            show_dialog(DialogType.ERROR, self._dialog, "The task is already running!")
            return

        model = get_base_model(self._sat_view.get_model())
        model.clear()
        self._download_task = True
        src = self._source_box.get_active()
        if not self._parser:
            self._parser = SatellitesParser()

        self.get_sat_list(src, self.append_satellites)

    @run_task
    def get_sat_list(self, src, callback):
        sats = self._parser.get_satellites_list(SatelliteSource.FLYSAT if src == 0 else SatelliteSource.LYNGSAT)
        if sats:
            callback(sats)
        self._download_task = False

    @run_idle
    def append_satellites(self, sats):
        model = get_base_model(self._sat_view.get_model())
        for sat in sats:
            model.append(sat)

    @run_task
    def on_receive_satellites_list(self, item):
        if self._download_task:
            show_dialog(DialogType.ERROR, self._dialog, "The task is already running!")
            return
        self.receive_satellites()

    @run_task
    def receive_satellites(self):
        self._download_task = True
        self._sat_update_expander.set_expanded(True)
        self._text_view.get_buffer().set_text("", 0)
        model = self._sat_view.get_model()
        start = time.time()

        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
            text = "Processing: {}\n"
            sats = []
            appender = self.append_output()
            next(appender)
            futures = {executor.submit(self._parser.get_satellite, sat[:-1]): sat for sat in [r for r in model if r[4]]}
            for future in concurrent.futures.as_completed(futures):
                if not self._download_task:
                    executor.shutdown()
                    appender.send("\nCanceled\n")
                    appender.close()
                    return
                data = future.result()
                appender.send(text.format(data[0]))
                sats.append(data)

            appender.send("-" * 75 + "\n")
            appender.send("Consumed : {:0.0f}s, {} satellites received.".format(start - time.time(), len(sats)))
            appender.close()
            # self.show_info_message(message, Gtk.MessageType.INFO)
            sats = {s[2]: s for s in sats}  # key = position, v = satellite

            for row in self._main_model:
                pos = row[-1]
                if pos in sats:
                    sat = sats.pop(pos)
                    itr = row.iter
                    self.update_satellite(itr, row, sat)

            for sat in sats.values():
                append_satellite(self._main_model, sat)

            self._download_task = False

    @run_idle
    def update_satellite(self, itr, row, sat):
        if self._main_model.iter_has_child(itr):
            children = row.iterchildren()
            for ch in children:
                self._main_model.remove(ch.iter)

        for tr in sat[3]:
            self._main_model.append(itr, ["Transponder:", *tr, None, None])

    def append_output(self):
        @run_idle
        def append(t):
            append_text_to_tview(t, self._text_view)

        while True:
            text = yield
            append(text)

    @run_idle
    def on_cancel_receive(self, item=None):
        self._download_task = False

    def on_selected_toggled(self, toggle, path):
        s_model = self._sat_view.get_model()
        itr = self._filter_model.convert_iter_to_child_iter(s_model.convert_iter_to_child_iter(s_model.get_iter(path)))
        self._filter_model.get_model().set_value(itr, 4, not toggle.get_active())
        self.update_receive_button_state(self._filter_model)

    @run_idle
    def update_receive_button_state(self, model):
        self._receive_button.set_sensitive((any(r[4] for r in model)))

    @run_idle
    def show_info_message(self, text, message_type):
        self._sat_update_info_bar.set_visible(True)
        self._sat_update_info_bar.set_message_type(message_type)
        self._info_bar_message_label.set_text(text)

    def on_info_bar_close(self, bar=None, resp=None):
        self._sat_update_info_bar.set_visible(False)

    def on_find_toggled(self, button: Gtk.ToggleToolButton):
        self._search_info_bar.set_visible(button.get_active())

    def on_filter_toggled(self, button: Gtk.ToggleToolButton):
        self._filter_info_bar.set_visible(button.get_active())

    @run_idle
    def on_filter(self, item):
        self._filter_positions = self.get_positions()
        self._filter_model.refilter()

    def filter_function(self, model, iter, data):
        if self._filter_model is None or self._filter_model == "None":
            return True

        from_pos, to_pos = self._filter_positions
        if from_pos == 0 and to_pos == 0:
            return True

        if from_pos > to_pos:
            from_pos, to_pos = to_pos, from_pos

        return from_pos <= float(self._parser.get_position(model.get(iter, 1)[0])) <= to_pos

    def get_positions(self):
        from_pos = round(self._from_pos_button.get_value(), 1) * (-1 if self._filter_from_combo_box.get_active() else 1)
        to_pos = round(self._to_pos_button.get_value(), 1) * (-1 if self._filter_to_combo_box.get_active() else 1)
        return from_pos, to_pos

    def on_search(self, entry):
        self._search_provider.search(entry.get_text())

    def on_search_down(self, item):
        self._search_provider.on_search_down()

    def on_search_up(self, item):
        self._search_provider.on_search_up()

    def on_quit(self):
        self._download_task = False


# ***************** Commons *******************#

@run_idle
def append_satellite(model, sat):
    """ Common function for append satellite to the model """
    name, flags, pos, transponders = sat
    parent = model.append(None, [name, *(None,) * 9, flags, pos])
    for transponder in transponders:
        model.append(parent, ["Transponder:", *transponder, None, None])


if __name__ == "__main__":
    pass

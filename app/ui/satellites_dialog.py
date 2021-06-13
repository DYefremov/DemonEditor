import concurrent.futures
import re
import time
from math import fabs

from gi.repository import GLib

from app.commons import run_idle, run_task, log
from app.eparser import get_satellites, write_satellites, Satellite, Transponder
from app.eparser.ecommons import PLS_MODE, get_key_by_value
from app.tools.satellites import SatellitesParser, SatelliteSource, ServicesParser
from .dialogs import show_dialog, DialogType, get_chooser_dialog, get_message, get_builder
from .main_helper import move_items, scroll_to, append_text_to_tview, get_base_model, on_popup_menu
from .search import SearchProvider
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, MOVE_KEYS, KeyboardKey, MOD_MASK

_UI_PATH = UI_RESOURCES_PATH + "satellites_dialog.glade"


def show_satellites_dialog(transient, options):
    SatellitesDialog(transient, options).show()


class SatellitesDialog:
    _aggr = [None for x in range(9)]  # aggregate

    def __init__(self, transient, settings):
        self._data_path = settings.data_local_path + "satellites.xml"
        self._settings = settings

        handlers = {"on_open": self.on_open,
                    "on_remove": self.on_remove,
                    "on_save": self.on_save,
                    "on_save_as": self.on_save_as,
                    "on_update": self.on_update,
                    "on_up": self.on_up,
                    "on_down": self.on_down,
                    "on_popup_menu": on_popup_menu,
                    "on_satellite_add": self.on_satellite_add,
                    "on_transponder_add": self.on_transponder_add,
                    "on_edit": self.on_edit,
                    "on_key_release": self.on_key_release,
                    "on_row_activated": self.on_row_activated,
                    "on_resize": self.on_resize,
                    "on_quit": self.on_quit}

        builder = get_builder(_UI_PATH, handlers, use_str=True,
                              objects=("satellites_editor_window", "satellites_tree_store", "popup_menu",
                                       "left_header_menu", "popup_menu_add_image", "popup_menu_add_image_2"))

        self._window = builder.get_object("satellites_editor_window")
        self._window.set_transient_for(transient)
        self._sat_view = builder.get_object("satellites_editor_tree_view")
        # Setting the last size of the dialog window if it was saved
        window_size = self._settings.get("sat_editor_window_size")
        if window_size:
            self._window.resize(*window_size)

        self._stores = {3: builder.get_object("pol_store"),
                        4: builder.get_object("fec_store"),
                        5: builder.get_object("system_store"),
                        6: builder.get_object("mod_store")}

        self.load_satellites_list(self._sat_view.get_model())

    def load_satellites_list(self, model):
        gen = self.on_satellites_list_load(model)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def show(self):
        self._window.show()

    def on_resize(self, window):
        """ Stores new size properties for dialog window after resize """
        if self._settings:
            self._settings.add("sat_editor_window_size", window.get_size())

    @run_idle
    def on_quit(self, *args):
        self._window.destroy()

    @run_idle
    def on_open(self, model):
        response = get_chooser_dialog(self._window, self._settings, "satellites.xml", ("*.xml",))
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        if not str(response).endswith("satellites.xml"):
            show_dialog(DialogType.ERROR, self._window, text="No satellites.xml file is selected!")
            return

        self._data_path = response
        self.load_satellites_list(model)

    @staticmethod
    def on_row_activated(view, path, column):
        if view.row_expanded(path):
            view.collapse_row(path)
        else:
            view.expand_row(path, column)

    def on_up(self, item):
        move_items(KeyboardKey.UP, self._sat_view)

    def on_down(self, item):
        move_items(KeyboardKey.DOWN, self._sat_view)

    def on_key_release(self, view, event):
        """  Handling  keystrokes  """
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return
        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK

        if key is KeyboardKey.DELETE:
            self.on_remove(view)
        elif key is KeyboardKey.INSERT:
            pass
        elif ctrl and key is KeyboardKey.E:
            self.on_edit(view)
        elif ctrl and key is KeyboardKey.S:
            self.on_satellite()
        elif ctrl and key is KeyboardKey.T:
            self.on_transponder()
        elif ctrl and key in MOVE_KEYS:
            move_items(key, self._sat_view)
        elif key is KeyboardKey.LEFT or key is KeyboardKey.RIGHT:
            view.do_unselect_all(view)

    def on_satellites_list_load(self, model):
        """ Load satellites data into model """
        try:
            satellites = get_satellites(self._data_path)
            yield True
        except FileNotFoundError as e:
            show_dialog(DialogType.ERROR, self._window, getattr(e, "message", str(e)) +
                        "\n\nPlease, download files from receiver or setup your path for read data!")
            return
        else:
            model.clear()
            for sat in satellites:
                append_satellite(model, sat)
                yield True

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
        sat_dialog = SatelliteDialog(self._window, satellite)
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
            show_dialog(DialogType.ERROR, self._window, "No satellite is selected!")
            return

        dialog = TransponderDialog(self._window, transponder)
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
            show_dialog(DialogType.ERROR, self._window, message)
            return

        return paths

    @run_idle
    def on_remove(self, view):
        """ Removal of selected satellites and transponders.

            The satellites are removed first! Then transponders.
        """
        selection = view.get_selection()
        model, paths = selection.get_selected_rows()
        itrs = [model.get_iter(path) for path in paths]
        satellites = list(filter(model.iter_has_child, itrs))
        if len(satellites):
            # Removing selected satellites.
            list(map(model.remove, satellites))
        else:
            # Removing selected transponders.
            list(map(model.remove, itrs))

    @run_idle
    def on_save(self, view):
        if show_dialog(DialogType.QUESTION, self._window) == Gtk.ResponseType.CANCEL:
            return

        model = view.get_model()
        satellites = []
        model.foreach(self.parse_data, satellites)
        write_satellites(satellites, self._data_path)

    def on_save_as(self, item):
        response = self.get_file_dialog_response(Gtk.FileChooserAction.SAVE)
        if response == Gtk.ResponseType.CANCEL:
            return
        show_dialog(DialogType.ERROR, transient=self._window, text="Not implemented yet!")

    @run_idle
    def on_update(self, item):
        SatellitesUpdateDialog(self._window, self._settings, self._sat_view.get_model()).show()

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


# ***************** Transponder dialog *******************#

class TransponderDialog:
    """ Shows dialog for adding or edit transponder """

    def __init__(self, transient, transponder: Transponder = None):

        handlers = {"on_entry_changed": self.on_entry_changed}
        objects = ("transponder_dialog", "pol_store", "fec_store", "mod_store", "system_store", "pls_mode_store")
        builder = get_builder(_UI_PATH, handlers, use_str=True, objects=objects)

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
        self._pattern = re.compile(r"\D")
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
        self._pls_mode_box.set_active_id(PLS_MODE.get(transponder.pls_mode, None))
        self._is_id_entry.set_text(transponder.is_id if transponder.is_id else "")
        self._pls_code_entry.set_text(transponder.pls_code if transponder.pls_code else "")

    def to_transponder(self):
        return Transponder(frequency=self._freq_entry.get_text(),
                           symbol_rate=self._rate_entry.get_text(),
                           polarization=self._pol_box.get_active_id(),
                           fec_inner=self._fec_box.get_active_id(),
                           system=self._sys_box.get_active_id(),
                           modulation=self._mod_box.get_active_id(),
                           pls_mode=get_key_by_value(PLS_MODE, self._pls_mode_box.get_active_id()),
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
        builder = get_builder(_UI_PATH, use_str=True, objects=("satellite_dialog", "side_store", "pos_adjustment"))

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


# ********************** Update dialogs ************************ #

class UpdateDialog:
    """ Base dialog for update satellites, transponders and services from the web."""

    def __init__(self, transient, settings, title=None):
        handlers = {"on_update_satellites_list": self.on_update_satellites_list,
                    "on_receive_data": self.on_receive_data,
                    "on_cancel_receive": self.on_cancel_receive,
                    "on_satellite_toggled": self.on_satellite_toggled,
                    "on_transponder_toggled": self.on_transponder_toggled,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_find_toggled": self.on_find_toggled,
                    "on_popup_menu": on_popup_menu,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_filter": self.on_filter,
                    "on_search": self.on_search,
                    "on_search_down": self.on_search_down,
                    "on_search_up": self.on_search_up,
                    "on_quit": self.on_quit}

        self._settings = settings
        self._download_task = False
        self._parser = None
        self._size_name = "{}_window_size".format("_".join(re.findall("[A-Z][^A-Z]*", self.__class__.__name__))).lower()

        builder = get_builder(UI_RESOURCES_PATH + "satellites_dialog.glade", handlers,
                              objects=("satellites_update_window", "update_source_store", "update_sat_list_store",
                                       "update_sat_list_model_filter", "update_sat_list_model_sort", "side_store",
                                       "pos_adjustment", "pos_adjustment2", "satellites_update_popup_menu",
                                       "remove_selection_image", "update_transponder_store", "update_service_store"))

        self._window = builder.get_object("satellites_update_window")
        self._window.set_transient_for(transient)
        if title:
            self._window.set_title(title)

        self._transponder_paned = builder.get_object("sat_update_tr_paned")
        self._sat_view = builder.get_object("sat_update_tree_view")
        self._transponder_view = builder.get_object("sat_update_tr_view")
        self._service_view = builder.get_object("sat_update_srv_view")
        self._source_box = builder.get_object("source_combo_box")
        self._sat_update_expander = builder.get_object("sat_update_expander")
        self._text_view = builder.get_object("text_view")
        self._receive_button = builder.get_object("receive_data_button")
        self._sat_update_info_bar = builder.get_object("sat_update_info_bar")
        self._info_bar_message_label = builder.get_object("info_bar_message_label")
        self._receive_button.bind_property("visible", builder.get_object("cancel_data_button"), "visible", 4)
        # Filter
        self._filter_bar = builder.get_object("sat_update_filter_bar")
        self._from_pos_button = builder.get_object("from_pos_button")
        self._to_pos_button = builder.get_object("to_pos_button")
        self._filter_from_combo_box = builder.get_object("filter_from_combo_box")
        self._filter_to_combo_box = builder.get_object("filter_to_combo_box")
        self._filter_model = builder.get_object("update_sat_list_model_filter")
        self._filter_model.set_visible_func(self.filter_function)
        self._filter_positions = (0, 0)
        # Search
        self._search_bar = builder.get_object("sat_update_search_bar")
        self._search_provider = SearchProvider((self._sat_view,),
                                               builder.get_object("sat_update_search_down_button"),
                                               builder.get_object("sat_update_search_up_button"))

        window_size = self._settings.get(self._size_name)
        if window_size:
            self._window.resize(*window_size)

    def show(self):
        self._window.show()

    @property
    def is_download(self):
        return self._download_task

    @is_download.setter
    def is_download(self, value):
        self._download_task = value
        self._receive_button.set_visible(not value)

    @run_idle
    def on_update_satellites_list(self, item):
        if self.is_download:
            show_dialog(DialogType.ERROR, self._window, "The task is already running!")
            return

        model = get_base_model(self._sat_view.get_model())
        model.clear()
        self.is_download = True
        src = self._source_box.get_active()
        if not self._parser:
            self._parser = SatellitesParser()

        self.get_sat_list(src, self.append_satellites)

    @run_task
    def get_sat_list(self, src, callback):
        sat_src = SatelliteSource.FLYSAT
        if src == 1:
            sat_src = SatelliteSource.LYNGSAT
        elif src == 2:
            sat_src = SatelliteSource.KINGOFSAT

        sats = self._parser.get_satellites_list(sat_src)
        if sats:
            callback(sats)
        self.is_download = False

    @run_idle
    def append_satellites(self, sats):
        model = get_base_model(self._sat_view.get_model())
        for sat in sats:
            model.append(sat)

    @run_idle
    def on_receive_data(self, item):
        if self.is_download:
            show_dialog(DialogType.ERROR, self._window, "The task is already running!")
            return

    @run_idle
    def update_expander(self):
        self._sat_update_expander.set_expanded(True)
        self._text_view.get_buffer().set_text("", 0)

    def append_output(self):
        @run_idle
        def append(t):
            append_text_to_tview(t, self._text_view)

        while True:
            text = yield
            append(text)

    def on_cancel_receive(self, item=None):
        self._download_task = False

    def on_satellite_toggled(self, toggle, path):
        model = self._sat_view.get_model()
        self.update_state(model, path, not toggle.get_active())
        self.update_receive_button_state(self._filter_model)

    def on_transponder_toggled(self, toggle, path):
        model = self._transponder_view.get_model()
        model.set_value(model.get_iter(path), 2, not toggle.get_active())

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
        self._search_bar.set_search_mode(button.get_active())

    def on_filter_toggled(self, button: Gtk.ToggleToolButton):
        self._filter_bar.set_search_mode(button.get_active())

    @run_idle
    def on_filter(self, item):
        self._filter_positions = self.get_positions()
        self._filter_model.refilter()

    def filter_function(self, model, itr, data):
        if self._filter_model is None or self._filter_model == "None":
            return True

        from_pos, to_pos = self._filter_positions
        if from_pos == 0 and to_pos == 0:
            return True

        if from_pos > to_pos:
            from_pos, to_pos = to_pos, from_pos

        return from_pos <= float(self._parser.get_position(model.get(itr, 1)[0])) <= to_pos

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

    def on_select_all(self, view):
        self.update_selection(view, True)

    def on_unselect_all(self, view):
        self.update_selection(view, False)

    def update_selection(self, view, select):
        model = view.get_model()
        view.get_model().foreach(lambda mod, path, itr: self.update_state(model, path, select))
        self.update_receive_button_state(self._filter_model)

    def update_state(self, model, path, select):
        """ Updates checkbox state by given path in the list """
        itr = self._filter_model.convert_iter_to_child_iter(model.convert_iter_to_child_iter(model.get_iter(path)))
        self._filter_model.get_model().set_value(itr, 4, select)

    def on_quit(self, window, event):
        self._settings.add(self._size_name, window.get_size())
        self.is_download = False


class SatellitesUpdateDialog(UpdateDialog):
    """ Dialog for update satellites from the web. """

    def __init__(self, transient, settings, main_model):
        super().__init__(transient=transient, settings=settings)

        self._main_model = main_model

    @run_idle
    def on_receive_data(self, item):
        if self.is_download:
            show_dialog(DialogType.ERROR, self._window, "The task is already running!")
            return

        self.receive_satellites()

    @run_task
    def receive_satellites(self):
        self.is_download = True
        self.update_expander()
        model = self._sat_view.get_model()
        start = time.time()

        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
            text = "Processing: {}\n"
            sats = []
            appender = self.append_output()
            next(appender)
            futures = {executor.submit(self._parser.get_satellite, sat[:-1]): sat for sat in [r for r in model if r[4]]}
            for future in concurrent.futures.as_completed(futures):
                if not self.is_download:
                    self.is_download = True
                    executor.shutdown()
                    appender.send("\nCanceled\n")
                    appender.close()
                    self.is_download = False
                    return
                data = future.result()
                appender.send(text.format(data[0]))
                sats.append(data)

            appender.send("-" * 75 + "\n")
            appender.send("Consumed: {:0.0f}s, {} satellites received.".format(time.time() - start, len(sats)))
            appender.close()

            sats = {s[2]: s for s in sats}  # key = position, v = satellite

            for row in self._main_model:
                pos = row[-1]
                if pos in sats:
                    sat = sats.pop(pos)
                    itr = row.iter
                    self.update_satellite(itr, row, sat)

            for sat in sats.values():
                append_satellite(self._main_model, sat)

            self.is_download = False

    @run_idle
    def update_satellite(self, itr, row, sat):
        if self._main_model.iter_has_child(itr):
            children = row.iterchildren()
            for ch in children:
                self._main_model.remove(ch.iter)

        for tr in sat[3]:
            self._main_model.append(itr, ["Transponder:", *tr, None, None])


class ServicesUpdateDialog(UpdateDialog):
    """ Dialog for updating services from the web. """

    def __init__(self, transient, settings, callback):
        super().__init__(transient=transient, settings=settings, title="Services update")

        self._callback = callback
        self._satellite_paths = {}
        self._transponders = {}
        self._services = {}
        self._selected_transponders = set()
        self._services_parser = ServicesParser(source=SatelliteSource.LYNGSAT)

        self._transponder_paned.set_visible(True)
        self._source_box.remove(0)
        self._source_box.remove(1)
        self._source_box.set_active(0)
        # Transponder view popup menu
        tr_popup_menu = Gtk.Menu()
        select_all_item = Gtk.ImageMenuItem.new_from_stock("gtk-select-all")
        select_all_item.connect("activate", lambda w: self.update_transponder_selection(True))
        tr_popup_menu.append(select_all_item)
        remove_selection_item = Gtk.ImageMenuItem.new_from_stock("gtk-undo")
        remove_selection_item.set_label(get_message("Remove selection"))
        remove_selection_item.connect("activate", lambda w: self.update_transponder_selection(False))
        tr_popup_menu.append(remove_selection_item)
        tr_popup_menu.show_all()

        self._sat_view.connect("row-activated", self.on_activate_satellite)
        self._transponder_view.connect("row-activated", self.on_activate_transponder)
        self._transponder_view.connect("button-press-event", lambda w, e: on_popup_menu(tr_popup_menu, e))
        self._transponder_view.connect("select_all", lambda w: self.update_transponder_selection(True))

    @run_idle
    def on_receive_data(self, item):
        if self.is_download:
            show_dialog(DialogType.ERROR, self._window, "The task is already running!")
            return

        self.receive_services()

    @run_task
    def receive_services(self):
        self.is_download = True
        self.update_expander()
        model = self._sat_view.get_model()
        appender = self.append_output()
        next(appender)

        start = time.time()
        non_cached_sats = []
        sat_names = {}
        t_names = {}
        t_urls = []
        services = []

        for r in (r for r in model if r[-1]):
            if not self.is_download:
                appender.send("\nCanceled\n")
                return

            sat, url = r[0], r[3]
            trs = self._transponders.get(url, None)
            if trs:
                for t in filter(lambda tp: tp.url in self._selected_transponders, trs):
                    t_urls.append(t.url)
                    t_names[t.url] = t.text
            else:
                non_cached_sats.append(url)
                sat_names[url] = sat

        if non_cached_sats:
            with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self._services_parser.get_transponders_links, u): u for u in non_cached_sats}
                for future in concurrent.futures.as_completed(futures):
                    if not self.is_download:
                        appender.send("\nCanceled.\n")
                        self.is_download = False
                        return

                    appender.send("Getting transponders for: {}.\n".format(sat_names.get(futures[future])))
                    for t in future.result():
                        t_urls.append(t.url)
                        t_names[t.url] = t.text

                appender.send("-" * 75 + "\n")
                appender.send("{} transponders received.\n\n".format(len(t_urls)))

        non_cached_ts = []
        for tr in t_urls:
            srvs = self._services.get(tr)
            services.extend(srvs) if srvs else non_cached_ts.append(tr)

        if non_cached_ts:
            with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self._services_parser.get_transponder_services, u): u for u in non_cached_ts}
                for future in concurrent.futures.as_completed(futures):
                    if not self.is_download:
                        appender.send("\nCanceled.\n")
                        self.is_download = False
                        return

                    appender.send("Getting services for: {}.\n".format(t_names.get(futures[future], "")))
                    list(map(services.append, future.result()))

        appender.send("-" * 75 + "\n")
        appender.send("Consumed: {:0.0f}s, {} services received.".format(time.time() - start, len(services)))

        try:
            from app.eparser.enigma.lamedb import LameDbReader
            # Used for double checking!
            reader = LameDbReader(path=None)
            srvs = reader.get_services_list("".join(reader.get_services_lines(services)))
        except ValueError as e:
            log("ServicesUpdateDialog [on receive data] error: {}".format(e))
        else:
            self._callback(srvs)

        self.is_download = False

    @run_task
    def get_sat_list(self, src, callback):
        sats = self._parser.get_satellites_list(SatelliteSource.LYNGSAT)
        if sats:
            callback(sats)
        self.is_download = False

    def on_satellite_toggled(self, toggle, path):
        model = self._sat_view.get_model()
        self.update_state(model, path, not toggle.get_active())
        self.update_receive_button_state(self._filter_model)

        url = model.get_value(model.get_iter(path), 3)
        selected = toggle.get_active()
        transponders = self._transponders.get(url, None)

        if transponders:
            for t in transponders:
                self._selected_transponders.add(t.url) if selected else self._selected_transponders.discard(t.url)

    def on_transponder_toggled(self, toggle, path):
        model = self._transponder_view.get_model()
        itr = model.get_iter(path)
        active = not toggle.get_active()
        url = self.update_transponder_state(itr, model, active)

        s_path = self._satellite_paths.get(url, None)
        if s_path:
            self.update_sat_state(model, s_path, active)

    def update_sat_state(self, model, path, active):
        sat_model = self._sat_view.get_model()
        if active:
            self.update_state(sat_model, path, active)
        else:
            self.update_state(sat_model, path, any((r[-1] for r in model)))
        self.update_receive_button_state(self._filter_model)

    def update_transponder_state(self, itr, model, active):
        model.set_value(itr, 2, active)
        url = model.get_value(itr, 1)
        self._selected_transponders.add(url) if active else self._selected_transponders.discard(url)
        return url

    @run_task
    def on_activate_satellite(self, view, path, column):
        model = view.get_model()
        itr = model.get_iter(path)
        url, selected = model.get_value(itr, 3), model.get_value(itr, 4)
        transponders = self._transponders.get(url, None)
        if transponders is None:
            GLib.idle_add(view.set_sensitive, False)
            transponders = self._services_parser.get_transponders_links(url)
            self._transponders[url] = transponders

            for t in transponders:
                t_url = t.url
                self._satellite_paths[t_url] = path
                self._selected_transponders.add(t_url) if selected else self._selected_transponders.discard(t_url)

        self.append_transponders(self._transponder_view.get_model(), transponders)

    @run_idle
    def append_transponders(self, model, trs_list):
        model.clear()
        list(map(model.append, [(t.text, t.url, t.url in self._selected_transponders) for t in trs_list]))
        self._sat_view.set_sensitive(True)

    @run_task
    def on_activate_transponder(self, view, path, column):
        url = view.get_model()[path][1]
        services = self._services.get(url, None)
        if services is None:
            GLib.idle_add(view.set_sensitive, False)
            services = self._services_parser.get_transponder_services(url)
            self._services[url] = services

        self.append_services(self._service_view.get_model(), services)

    @run_idle
    def append_services(self, model, srv_list):
        model.clear()
        for s in srv_list:
            model.append((None, s.service, s.package, s.service_type, str(s.ssid), None))

        self._transponder_view.set_sensitive(True)

    def update_transponder_selection(self, select):
        m = self._transponder_view.get_model()
        if not len(m):
            return

        s_path = self._satellite_paths.get({self.update_transponder_state(r.iter, m, select) for r in m}.pop(), None)
        if s_path:
            self.update_sat_state(m, s_path, select)


# ************************* Commons ************************* #


@run_idle
def append_satellite(model, sat):
    """ Common function for append satellite to the model """
    name, flags, pos, transponders = sat
    parent = model.append(None, [name, *(None,) * 9, flags, pos])
    for transponder in transponders:
        model.append(parent, ["Transponder:", *transponder, None, None])


if __name__ == "__main__":
    pass

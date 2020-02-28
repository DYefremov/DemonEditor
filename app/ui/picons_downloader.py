import os
import re
import shutil
import subprocess
import tempfile

from gi.repository import GLib, GdkPixbuf, Gio

from app.commons import run_idle, run_task, run_with_delay
from app.connections import upload_data, DownloadType, download_data, remove_picons
from app.settings import SettingsType
from app.tools.picons import PiconsParser, parse_providers, Provider, convert_to
from app.tools.satellites import SatellitesParser, SatelliteSource
from .dialogs import show_dialog, DialogType, get_message
from .main_helper import update_entry_data, append_text_to_tview, scroll_to, on_popup_menu, update_picons_data, \
    get_base_model
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, TEXT_DOMAIN, TV_ICON, GTK_PATH


class PiconsDialog:
    def __init__(self, transient, settings, picon_ids, sat_positions, callback):
        self._picon_ids = picon_ids
        self._sat_positions = sat_positions
        self._callback = callback
        self._TMP_DIR = tempfile.gettempdir() + "/"
        self._BASE_URL = "www.lyngsat.com/packages/"
        self._PATTERN = re.compile(r"^https://www\.lyngsat\.com/[\w-]+\.html$")
        self._POS_PATTERN = re.compile(r"^\d+\.\d+[EW]?$")
        self._current_process = None
        self._terminate = False

        handlers = {"on_receive": self.on_receive,
                    "on_load_providers": self.on_load_providers,
                    "on_cancel": self.on_cancel,
                    "on_close": self.on_close,
                    "on_send": self.on_send,
                    "on_download": self.on_download,
                    "on_remove": self.on_remove,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_picons_dir_open": self.on_picons_dir_open,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_url_changed": self.on_url_changed,
                    "on_picons_filter_changed": self.on_picons_filter_changed,
                    "on_position_edited": self.on_position_edited,
                    "on_notebook_switch_page": self.on_notebook_switch_page,
                    "on_convert": self.on_convert,
                    "on_picons_folder_changed": self.on_picons_folder_changed,
                    "on_view_drag_data_get": self.on_view_drag_data_get,
                    "on_picons_view_realize": self.on_picons_view_realize,
                    "on_satellites_view_realize": self.on_satellites_view_realize,
                    "on_satellite_selection": self.on_satellite_selection,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_popup_menu": on_popup_menu}

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "picons_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("picons_dialog")
        self._dialog.set_transient_for(transient)
        self._picons_view = builder.get_object("picons_view")
        self._providers_view = builder.get_object("providers_view")
        self._satellites_view = builder.get_object("satellites_view")
        self._picons_filter_model = builder.get_object("picons_filter_model")
        self._picons_filter_model.set_visible_func(self.picons_filter_function)
        self._explorer_path_button = builder.get_object("explorer_path_button")
        self._expander = builder.get_object("expander")
        self._text_view = builder.get_object("text_view")
        self._info_bar = builder.get_object("info_bar")
        self._filter_bar = builder.get_object("filter_bar")
        self._filter_button = builder.get_object("filter_button")
        self._picons_filter_entry = builder.get_object("picons_filter_entry")
        self._ip_entry = builder.get_object("ip_entry")
        self._picons_entry = builder.get_object("picons_entry")
        self._url_entry = builder.get_object("url_entry")
        self._picons_dir_entry = builder.get_object("picons_dir_entry")
        self._info_bar = builder.get_object("info_bar")
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")
        self._load_providers_button = builder.get_object("load_providers_button")
        self._receive_button = builder.get_object("receive_button")
        self._convert_button = builder.get_object("convert_button")
        self._enigma2_path_button = builder.get_object("enigma2_path_button")
        self._save_to_button = builder.get_object("save_to_button")
        self._send_button = builder.get_object("send_button")
        self._cancel_button = builder.get_object("cancel_button")
        self._enigma2_radio_button = builder.get_object("enigma2_radio_button")
        self._neutrino_mp_radio_button = builder.get_object("neutrino_mp_radio_button")
        self._resize_no_radio_button = builder.get_object("resize_no_radio_button")
        self._resize_220_132_radio_button = builder.get_object("resize_220_132_radio_button")
        self._resize_100_60_radio_button = builder.get_object("resize_100_60_radio_button")
        self._satellite_label = builder.get_object("satellite_label")
        self._header_download_box = builder.get_object("header_download_box")
        self._satellite_label.bind_property("visible", builder.get_object("loading_data_label"), "visible", 4)
        self._satellite_label.bind_property("visible", builder.get_object("loading_data_spinner"), "visible", 4)
        self._cancel_button.bind_property("visible", self._header_download_box, "visible", 4)
        self._convert_button.bind_property("visible", self._header_download_box, "visible", 4)
        self._load_providers_button.bind_property("visible", self._receive_button, "visible")
        self._load_providers_button.bind_property("visible", builder.get_object("download_box_separator"), "visible")
        self._filter_bar.bind_property("search-mode-enabled", self._filter_bar, "visible")
        # Init drag-and-drop
        self.init_drag_and_drop()
        # Style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._url_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                                    Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._settings = settings
        self._s_type = settings.setting_type
        self._ip_entry.set_text(self._settings.host)
        self._picons_entry.set_text(self._settings.picons_path)
        self._picons_path = self._settings.picons_local_path
        self._picons_dir_entry.set_text(self._picons_path)

        window_size = self._settings.get("picons_downloader_window_size")
        if window_size:
            self._dialog.resize(*window_size)

        if not len(self._picon_ids) and self._s_type is SettingsType.ENIGMA_2:
            message = get_message("To automatically set the identifiers for picons,\n"
                                  "first load the required services list into the main application window.")
            self.show_info_message(message, Gtk.MessageType.WARNING)
            self._satellite_label.show()

    def show(self):
        self._dialog.show()

    def on_picons_view_realize(self, view):
        self._explorer_path_button.set_current_folder(self._picons_path)

    def on_picons_folder_changed(self, button):
        path = button.get_filename()
        if not path or not os.path.exists(path):
            return

        GLib.idle_add(self._explorer_path_button.set_sensitive, False)
        gen = self.update_picons(path)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def update_picons(self, path):
        p_model = self._picons_view.get_model()
        self._picons_view.set_model(None)
        model = get_base_model(p_model)
        model.clear()
        self._picons_view.set_model(p_model)

        for file in os.listdir(path):
            if self._terminate:
                return

            try:
                p = GdkPixbuf.Pixbuf.new_from_file(filename="{}/{}".format(path, file))
            except GLib.GError as e:
                pass
            else:
                yield model.append((p, file))

        self._explorer_path_button.set_sensitive(True)
        yield True

    # ***************** Drag-and-drop ********************* #

    def init_drag_and_drop(self):
        self._picons_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self._picons_view.drag_source_add_uri_targets()

    def on_view_drag_data_get(self, view, drag_context, data, info, time):
        model = view.get_model()
        path = view.get_selected_items()[0]
        p_path = "{}/{}".format(self._explorer_path_button.get_filename(), model.get_value(model.get_iter(path), 1))
        data.set_uris([p_path])

    # ******************** ####### ************************* #

    def on_satellites_view_realize(self, view):
        self.get_satellites(view)

    @run_task
    def get_satellites(self, view):
        sats = SatellitesParser().get_satellites_list(SatelliteSource.LYNGSAT)
        if not sats:
            self.show_info_message("Getting satellites list error!", Gtk.MessageType.ERROR)
        gen = self.append_satellites(view.get_model(), sats)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def append_satellites(self, model, sats):
        try:
            for sat in sats:
                pos = sat[1]
                name, pos = "{} ({})".format(sat[0], pos), "{}{}".format("-" if pos[-1] == "W" else "", pos[:-1])

                if not self._terminate and model:
                    if pos in self._sat_positions:
                        yield model.append((name, sat[3], pos))
        finally:
            self._satellite_label.show()

    def on_satellite_selection(self, view, path, column):
        model = view.get_model()
        self._url_entry.set_text(model.get(model.get_iter(path), 1)[0])

    @run_idle
    def on_load_providers(self, item):
        self._expander.set_expanded(True)
        self.on_info_bar_close()
        self._cancel_button.show()
        url = self._url_entry.get_text()

        try:
            exe = "{}wget".format("./" if GTK_PATH else "")
            self._current_process = subprocess.Popen([exe, "-pkP", self._TMP_DIR, url],
                                                     stdout=subprocess.PIPE,
                                                     stderr=subprocess.PIPE,
                                                     universal_newlines=True)
        except FileNotFoundError as e:
            self._cancel_button.hide()
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            GLib.io_add_watch(self._current_process.stderr, GLib.IO_IN, self.write_to_buffer)
            model = self._providers_view.get_model()
            model.clear()
            self.append_providers(url, model)

    @run_task
    def append_providers(self, url, model):
        self._current_process.wait()
        try:
            self._terminate = False
            providers = parse_providers(self._TMP_DIR + url[url.find("w"):])
        except FileNotFoundError:
            pass  # NOP
        else:
            if providers:
                for p in providers:
                    if self._terminate:
                        return
                    model.append((self.get_pixbuf(p[0]) if p[0] else TV_ICON, *p[1:]))
            self.update_receive_button_state()
        finally:
            GLib.idle_add(self._cancel_button.hide)
            self._terminate = False

    def get_pixbuf(self, img_url):
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(filename=self._TMP_DIR + "www.lyngsat.com/" + img_url,
                                                       width=48, height=48, preserve_aspect_ratio=True)

    def on_receive(self, item):
        self._cancel_button.show()
        self.start_download()

    @run_task
    def start_download(self):
        if self._current_process.poll() is None:
            self.show_dialog("The task is already running!", DialogType.ERROR)
            return

        self._terminate = False
        self._expander.set_expanded(True)

        providers = self.get_selected_providers()
        for prv in providers:
            if not self._POS_PATTERN.match(prv[2]):
                self.show_info_message(
                    get_message("Specify the correct position value for the provider!"), Gtk.MessageType.ERROR)
                scroll_to(prv.path, self._providers_view)
                return

        try:
            for prv in providers:
                if self._terminate:
                    return
                self.process_provider(Provider(*prv))

            if self._resize_no_radio_button.get_active():
                self.resize(self._picons_path)

            self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO)
        finally:
            GLib.idle_add(self._cancel_button.hide)
            self._terminate = False

    def process_provider(self, prv):
        url = prv.url
        self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
        exe = "{}wget".format("./" if GTK_PATH else "")
        self._current_process = subprocess.Popen([exe, "-pkP", self._TMP_DIR, url],
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE,
                                                 universal_newlines=True)
        GLib.io_add_watch(self._current_process.stderr, GLib.IO_IN, self.write_to_buffer)
        self._current_process.wait()
        path = self._TMP_DIR + (url[url.find("//") + 2:] if prv.single else self._BASE_URL + url[url.rfind("/") + 1:])
        PiconsParser.parse(path, self._picons_path, self._TMP_DIR, prv, self._picon_ids, self.get_picons_format())

    def write_to_buffer(self, fd, condition):
        if condition == GLib.IO_IN:
            char = fd.read(1)
            self.append_output(char)
            return True
        return False

    @run_idle
    def append_output(self, char):
        append_text_to_tview(char, self._text_view)

    def resize(self, path):
        self.show_info_message(get_message("Resizing..."), Gtk.MessageType.INFO)
        exe = "{}mogrify".format("./" if GTK_PATH else "")
        is_220_132 = self._resize_220_132_radio_button.get_active()
        command = "{} -resize {}! *.png".format(exe, "220x132" if is_220_132 else "100x60").split()
        try:
            self._current_process = subprocess.Popen(command, universal_newlines=True, cwd=path)
            self._current_process.wait()
        except FileNotFoundError as e:
            self.show_info_message("Conversion error. " + str(e), Gtk.MessageType.ERROR)

    def on_cancel(self, item=None):
        if self.is_task_running() and show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return True

        self.terminate_task()

    @run_task
    def terminate_task(self):
        self._terminate = True

        if self._current_process:
            self._current_process.terminate()
            self.show_info_message(get_message("The task is canceled!"), Gtk.MessageType.WARNING)

    def on_close(self, window, event):
        if self.on_cancel():
            return True

        self._terminate = True
        self.save_window_size(window)
        self.clean_data()
        self._callback()
        GLib.idle_add(self._dialog.destroy)

    def save_window_size(self, window):
        t, _ = self._text_view.get_allocated_size()
        b, _ = self._info_bar.get_allocated_size()
        size = window.get_size()
        self._settings.add("picons_downloader_window_size", (size.width, size.height - t.height - b.height))

    @run_task
    def clean_data(self):
        path = self._TMP_DIR + "www.lyngsat.com"
        if os.path.exists(path):
            shutil.rmtree(path)

    def on_send(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
        self.run_func(lambda: upload_data(settings=self._settings,
                                          download_type=DownloadType.PICONS,
                                          callback=self.append_output,
                                          done_callback=lambda: self.show_info_message(get_message("Done!"),
                                                                                       Gtk.MessageType.INFO)))

    def on_download(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self.run_func(lambda: download_data(settings=self._settings,
                                            download_type=DownloadType.PICONS,
                                            callback=self.append_output))

    def on_remove(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self.run_func(lambda: remove_picons(settings=self._settings,
                                            callback=self.append_output,
                                            done_callback=lambda: self.show_info_message(get_message("Done!"),
                                                                                         Gtk.MessageType.INFO)))

    @run_task
    def run_func(self, func):
        try:
            GLib.idle_add(self._expander.set_expanded, True)
            GLib.idle_add(self._header_download_box.set_sensitive, False)
            func()
        except OSError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        GLib.idle_add(self._header_download_box.set_sensitive, True)

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    def on_picons_dir_open(self, entry, icon, event_button):
        update_entry_data(entry, self._dialog, settings=self._settings)

    @run_idle
    def on_selected_toggled(self, toggle, path):
        model = self._providers_view.get_model()
        model.set_value(model.get_iter(path), 7, not toggle.get_active())
        self.update_receive_button_state()

    def on_select_all(self, view):
        self.update_selection(view, True)

    def on_unselect_all(self, view):
        self.update_selection(view, False)

    def update_selection(self, view, select):
        view.get_model().foreach(lambda mod, path, itr: mod.set_value(itr, 7, select))
        self.update_receive_button_state()

    def on_filter_toggled(self, button):
        active = button.get_active()
        self._filter_bar.set_search_mode(active)
        if not active:
            self._picons_filter_entry.set_text("")

    def on_url_changed(self, entry):
        suit = self._PATTERN.search(entry.get_text())
        entry.set_name("GtkEntry" if suit else "digit-entry")
        self._load_providers_button.set_sensitive(suit if suit else False)

    @run_with_delay(1)
    def on_picons_filter_changed(self, entry):
        GLib.idle_add(self._picons_filter_model.refilter, priority=GLib.PRIORITY_LOW)

    def picons_filter_function(self, model, itr, data):
        if self._picons_filter_model is None or self._picons_filter_model == "None":
            return True

        t = model.get_value(itr, 1)
        return not t or self._picons_filter_entry.get_text().upper() in t.upper()

    def on_position_edited(self, render, path, value):
        model = self._providers_view.get_model()
        model.set_value(model.get_iter(path), 2, value)

    @run_idle
    def on_notebook_switch_page(self, nb, box, tab_num):
        self._convert_button.set_visible(tab_num > 1)
        self._load_providers_button.set_visible(tab_num == 1)
        is_explorer = tab_num == 0
        self._filter_button.set_visible(is_explorer)
        if is_explorer:
            self.on_picons_folder_changed(self._explorer_path_button)

    @run_idle
    def on_convert(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        picons_path = self._enigma2_path_button.get_filename()
        save_path = self._save_to_button.get_filename()
        if not picons_path or not save_path:
            show_dialog(DialogType.ERROR, transient=self._dialog, text="Select paths!")
            return

        self._expander.set_expanded(True)
        convert_to(src_path=picons_path,
                   dest_path=save_path,
                   s_type=SettingsType.ENIGMA_2,
                   callback=self.append_output,
                   done_callback=lambda: self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO))

    @run_idle
    def update_receive_button_state(self):
        try:
            self._receive_button.set_sensitive(len(self.get_selected_providers()) > 0)
        except TypeError:
            pass  # NOP

    def get_selected_providers(self):
        """ returns selected providers """
        return [r for r in self._providers_view.get_model() if r[7]]

    @run_idle
    def show_dialog(self, message, dialog_type):
        show_dialog(dialog_type, self._dialog, message)

    def get_picons_format(self):
        picon_format = SettingsType.ENIGMA_2

        if self._neutrino_mp_radio_button.get_active():
            picon_format = SettingsType.NEUTRINO_MP

        return picon_format

    def is_task_running(self):
        return self._current_process and self._current_process.poll() is None


if __name__ == "__main__":
    pass

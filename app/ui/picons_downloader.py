import os
import re
import shutil
import subprocess
import tempfile
import time

from gi.repository import GLib, GdkPixbuf

from app.commons import run_idle, run_task
from app.connections import upload_data, DownloadType
from app.tools.picons import PiconsParser, parse_providers, Provider, convert_to
from app.properties import Profile
from app.tools.satellites import SatellitesParser, SatelliteSource
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, TEXT_DOMAIN, TV_ICON
from .dialogs import show_dialog, DialogType, get_message
from .main_helper import update_entry_data, append_text_to_tview, scroll_to, on_popup_menu


class PiconsDialog:
    def __init__(self, transient, options, picon_ids, sat_positions, profile=Profile.ENIGMA_2):
        self._picon_ids = picon_ids
        self._sat_positions = sat_positions
        self._TMP_DIR = tempfile.gettempdir() + "/"
        self._BASE_URL = "www.lyngsat.com/packages/"
        self._PATTERN = re.compile("^https://www\.lyngsat\.com/[\w-]+\.html$")
        self._POS_PATTERN = re.compile("^\d+\.\d+[EW]?$")
        self._current_process = None
        self._terminate = False

        handlers = {"on_receive": self.on_receive,
                    "on_load_providers": self.on_load_providers,
                    "on_cancel": self.on_cancel,
                    "on_close": self.on_close,
                    "on_send": self.on_send,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_picons_dir_open": self.on_picons_dir_open,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_url_changed": self.on_url_changed,
                    "on_position_edited": self.on_position_edited,
                    "on_notebook_switch_page": self.on_notebook_switch_page,
                    "on_convert": self.on_convert,
                    "on_satellites_view_realize": self.on_satellites_view_realize,
                    "on_satellite_selection": self.on_satellite_selection,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_popup_menu": on_popup_menu}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_from_file(UI_RESOURCES_PATH + "picons_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("picons_dialog")
        self._dialog.set_transient_for(transient)
        self._providers_tree_view = builder.get_object("providers_tree_view")
        self._satellites_tree_view = builder.get_object("satellites_tree_view")
        self._expander = builder.get_object("expander")
        self._text_view = builder.get_object("text_view")
        self._info_bar = builder.get_object("info_bar")
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
        self._enigma2_radio_button = builder.get_object("enigma2_radio_button")
        self._neutrino_mp_radio_button = builder.get_object("neutrino_mp_radio_button")
        self._resize_no_radio_button = builder.get_object("resize_no_radio_button")
        self._resize_220_132_radio_button = builder.get_object("resize_220_132_radio_button")
        self._resize_100_60_radio_button = builder.get_object("resize_100_60_radio_button")
        # style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._url_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                                    Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._properties = options.get(profile.value)
        self._profile = profile
        self._ip_entry.set_text(self._properties.get("host", ""))
        self._picons_entry.set_text(self._properties.get("picons_path", ""))
        self._picons_path = self._properties.get("picons_dir_path", "")
        self._picons_dir_entry.set_text(self._picons_path)
        self._enigma2_picons_path = self._picons_path
        if profile is Profile.NEUTRINO_MP:
            self._enigma2_picons_path = options.get(Profile.ENIGMA_2.value).get("picons_dir_path", "")
        if not len(self._picon_ids) and self._profile is Profile.ENIGMA_2:
            message = get_message("To automatically set the identifiers for picons,\n"
                                  "first load the required services list into the main application window.")
            self.show_info_message(message, Gtk.MessageType.WARNING)

    def show(self):
        self._dialog.run()
        self._dialog.destroy()

    def on_satellites_view_realize(self, view):
        self.get_satellites(view)

    @run_task
    def get_satellites(self, view):
        sats = SatellitesParser().get_satellites_list(SatelliteSource.LYNGSAT)
        gen = self.append_satellites(view.get_model(), sats)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def append_satellites(self, model, sats):
        for sat in sats:
            pos = sat[1]
            name = "{} ({})".format(sat[0], pos)
            pos = "{}{}".format("-" if pos[-1] == "W" else "", pos[:-1])
            if not self._terminate and model:
                if pos in self._sat_positions:
                    model.append((name, sat[3], pos))
            yield True

    def on_satellite_selection(self, view, path, column):
        model = view.get_model()
        self._url_entry.set_text(model.get(model.get_iter(path), 1)[0])

    @run_idle
    def on_load_providers(self, item):
        self._expander.set_expanded(True)
        url = self._url_entry.get_text()
        self._current_process = subprocess.Popen(["wget", "-pkP", self._TMP_DIR, url],
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE,
                                                 universal_newlines=True)
        GLib.io_add_watch(self._current_process.stderr, GLib.IO_IN, self.write_to_buffer)
        model = self._providers_tree_view.get_model()
        model.clear()
        self.update_receive_button_state()
        self.append_providers(url, model)

    @run_task
    def append_providers(self, url, model):
        self._current_process.wait()
        providers = parse_providers(self._TMP_DIR + url[url.find("w"):])
        if providers:
            for p in providers:
                model.append((self.get_pixbuf(p[0]) if p[0] else TV_ICON, *p[1:]))
        self.update_receive_button_state()

    def get_pixbuf(self, img_url):
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(filename=self._TMP_DIR + "www.lyngsat.com/" + img_url,
                                                       width=48, height=48, preserve_aspect_ratio=True)

    @run_idle
    def on_receive(self, item):
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
                scroll_to(prv.path, self._providers_tree_view)
                return

        for prv in providers:
            if self._terminate:
                break
            self.process_provider(Provider(*prv))
        self.resize(self._picons_path)
        if not self._terminate:
            self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO)

    def process_provider(self, prv):
        url = prv.url
        self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
        self._current_process = subprocess.Popen(["wget", "-pkP", self._TMP_DIR, url],
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
        else:
            return False

    @run_idle
    def append_output(self, char):
        append_text_to_tview(char, self._text_view)

    def resize(self, path):
        if self._resize_no_radio_button.get_active():
            return

        self.show_info_message(get_message("Resizing..."), Gtk.MessageType.INFO)
        command = "mogrify -resize {}! *.png".format(
            "320x240" if self._resize_220_132_radio_button.get_active() else "100x60").split()
        try:
            self._current_process = subprocess.Popen(command, universal_newlines=True, cwd=path)
            self._current_process.wait()
        except FileNotFoundError as e:
            self.show_info_message("Conversion error. " + str(e), Gtk.MessageType.ERROR)
            self.on_cancel()

    @run_task
    def on_cancel(self, item=None):
        if self._current_process:
            self._terminate = True
            self._current_process.terminate()
            time.sleep(1)

    @run_idle
    def on_close(self, item):
        self.on_cancel(item)
        path = self._TMP_DIR + "www.lyngsat.com"
        if os.path.exists(path):
            shutil.rmtree(path)

    def on_send(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
        self.upload_picons()

    @run_task
    def upload_picons(self):
        if self._current_process is not None and self._current_process.poll() is None:
            self.show_dialog("The task is already running!", DialogType.ERROR)
            return

        try:
            upload_data(properties=self._properties,
                        download_type=DownloadType.PICONS,
                        profile=self._profile,
                        callback=lambda: self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO))
        except OSError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    def on_picons_dir_open(self, entry, icon, event_button):
        update_entry_data(entry, self._dialog, options={"data_dir_path": self._picons_path})

    @run_idle
    def on_selected_toggled(self, toggle, path):
        model = self._providers_tree_view.get_model()
        model.set_value(model.get_iter(path), 7, not toggle.get_active())
        self.update_receive_button_state()

    def on_select_all(self, view):
        self.update_selection(view, True)

    def on_unselect_all(self, view):
        self.update_selection(view, False)

    def update_selection(self, view, select):
        view.get_model().foreach(lambda mod, path, itr:  mod.set_value(itr, 7, select))

    def on_url_changed(self, entry):
        suit = self._PATTERN.search(entry.get_text())
        entry.set_name("GtkEntry" if suit else "digit-entry")
        self._load_providers_button.set_sensitive(suit if suit else False)

    def on_position_edited(self, render, path, value):
        model = self._providers_tree_view.get_model()
        model.set_value(model.get_iter(path), 2, value)

    @run_idle
    def on_notebook_switch_page(self, nb, box, tab_num):
        self._load_providers_button.set_visible(not tab_num)
        self._receive_button.set_visible(not tab_num)
        self._convert_button.set_visible(tab_num)
        self._send_button.set_visible(not tab_num)

        if self._enigma2_path_button.get_filename() is None:
            self._enigma2_path_button.set_current_folder(self._enigma2_picons_path)

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
                   profile=Profile.ENIGMA_2,
                   callback=self.append_output,
                   done_callback=lambda: self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO))

    @run_idle
    def update_receive_button_state(self):
        self._receive_button.set_sensitive(len(self.get_selected_providers()) > 0)

    def get_selected_providers(self):
        """ returns selected providers """
        return [r for r in self._providers_tree_view.get_model() if r[7]]

    @run_idle
    def show_dialog(self, message, dialog_type):
        show_dialog(dialog_type, self._dialog, message)

    def get_picons_format(self):
        picon_format = Profile.ENIGMA_2

        if self._neutrino_mp_radio_button.get_active():
            picon_format = Profile.NEUTRINO_MP

        return picon_format


if __name__ == "__main__":
    pass

import re
import subprocess
import tempfile
import time

from gi.repository import GLib, GdkPixbuf

from app.commons import run_idle, run_task
from app.ftp import upload_data, DownloadDataType
from app.picons.picons import PiconsParser, parse_providers, Provider
from app.properties import Profile
from . import Gtk, Gdk, UI_RESOURCES_PATH
from .dialogs import show_dialog, DialogType
from .main_helper import update_entry_data


class PiconsDialog:
    def __init__(self, transient, options, profile=Profile.ENIGMA_2):
        self._TMP_DIR = tempfile.gettempdir() + "/"
        self._BASE_URL = "www.lyngsat.com/packages/"
        self._PATTERN = re.compile("^https://www\.lyngsat\.com/[\w-]+\.html$")
        self._current_process = None
        self._picons_path = options.get("picons_dir_path", "")
        self._terminate = False

        handlers = {"on_receive": self.on_receive,
                    "on_load_providers": self.on_load_providers,
                    "on_cancel": self.on_cancel,
                    "on_close": self.on_close,
                    "on_send": self.on_send,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_picons_dir_open": self.on_picons_dir_open,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_url_changed": self.on_url_changed}

        builder = Gtk.Builder()
        builder.add_objects_from_file(UI_RESOURCES_PATH + "picons_dialog.glade",
                                      ("picons_dialog", "receive_image", "providers_list_store"))
        builder.connect_signals(handlers)
        self._dialog = builder.get_object("picons_dialog")
        self._dialog.set_transient_for(transient)
        self._providers_tree_view = builder.get_object("providers_tree_view")
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
        self._load_providers_tool_button = builder.get_object("load_providers_tool_button")
        self._receive_tool_button = builder.get_object("receive_tool_button")
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

        self._properties = options
        self._profile = profile
        self._ip_entry.set_text(options.get("host", ""))
        self._picons_entry.set_text(options.get("picons_path", ""))
        self._picons_path = options.get("picons_dir_path", "")
        self._picons_dir_entry.set_text(self._picons_path)

    def show(self):
        self._dialog.run()
        self._dialog.destroy()

    @run_idle
    def on_load_providers(self, item):
        self._expander.set_expanded(True)
        url = self._url_entry.get_text()
        self._current_process = subprocess.Popen(["wget", "-pkP", self._TMP_DIR, url],
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE,
                                                 universal_newlines=True)
        GLib.io_add_watch(self._current_process.stderr, GLib.IO_IN, self.write_to_buffer)
        self.append_providers(url)

    @run_task
    def append_providers(self, url):
        model = self._providers_tree_view.get_model()
        model.clear()
        self._current_process.wait()
        providers = parse_providers(self._TMP_DIR + url[url.find("w"):])
        if providers:
            for p in providers:
                logo = self.get_pixbuf(p[0])
                model.append((logo, p.name, p.url, p.on_id, p.selected))
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

        for prv in self.get_selected_providers():
            if self._terminate:
                break
            self.process_provider(Provider(*prv))

    def process_provider(self, provider):
        url = provider.url
        self.show_info_message("Please, wait...", Gtk.MessageType.INFO)
        self._current_process = subprocess.Popen(["wget", "-pkP", self._TMP_DIR, url],
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE,
                                                 universal_newlines=True)
        GLib.io_add_watch(self._current_process.stderr, GLib.IO_IN, self.write_to_buffer)
        self._current_process.wait()
        path = self._TMP_DIR + self._BASE_URL + url[url.rfind("/") + 1:]
        PiconsParser.parse(path, self._picons_path, self._TMP_DIR, provider.on_id, self.get_picons_format())
        self.resize(self._picons_path)
        self.show_info_message("Done", Gtk.MessageType.INFO)

    def write_to_buffer(self, fd, condition):
        if condition == GLib.IO_IN:
            char = fd.read(1)
            self.append_output(char)
            return True
        else:
            return False

    @run_idle
    def append_output(self, char):
        buf = self._text_view.get_buffer()
        buf.insert_at_cursor(char)
        self.scroll_to_end(buf)

    def scroll_to_end(self, buf):
        insert = buf.get_insert()
        self._text_view.scroll_to_mark(insert, 0.0, True, 0.0, 1.0)

    def resize(self, path):
        if self._resize_no_radio_button.get_active():
            return

        self.show_info_message("Resizing...", Gtk.MessageType.INFO)
        command = "mogrify -resize {}! *.png".format(
            "320x240" if self._resize_220_132_radio_button.get_active() else "100x60").split()
        self._current_process = subprocess.Popen(command, universal_newlines=True, cwd=path)
        self._current_process.wait()

    @run_task
    def on_cancel(self, item):
        if self._current_process:
            self._terminate = True
            self._current_process.terminate()
            time.sleep(1)

    @run_idle
    def on_close(self, item):
        self.on_cancel(item)
        self._dialog.destroy()

    def on_send(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self.show_info_message("Please, wait...", Gtk.MessageType.INFO)
        self.upload_picons()

    @run_task
    def upload_picons(self):
        if self._current_process is not None and self._current_process.poll() is None:
            self.show_dialog("The task is already running!", DialogType.ERROR)
            return

        upload_data(properties=self._properties,
                    download_type=DownloadDataType.PICONS,
                    profile=self._profile,
                    callback=lambda: self.show_info_message("Done!", Gtk.MessageType.INFO))

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
        model.set_value(model.get_iter(path), 4, not toggle.get_active())
        self.update_receive_button_state()

    def on_url_changed(self, entry):
        suit = self._PATTERN.search(entry.get_text())
        entry.set_name("GtkEntry" if suit else "digit-entry")
        self._load_providers_tool_button.set_sensitive(suit if suit else False)

    @run_idle
    def update_receive_button_state(self):
        self._receive_tool_button.set_sensitive(len(self.get_selected_providers()) > 0)

    def get_selected_providers(self):
        """ returns selected providers """
        return [r for r in self._providers_tree_view.get_model() if r[4]]

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

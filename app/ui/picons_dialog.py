import subprocess
import tempfile
import time

from gi.repository import GLib

from app.commons import run_idle, run_task
from app.picons.picons import PiconsParser
from . import Gtk, UI_RESOURCES_PATH
from .main_helper import update_entry_data


class PiconsDialog:
    def __init__(self, transient, options):
        self._TMP_DIR = tempfile.gettempdir() + "/"
        self._BASE_URL = "www.lyngsat.com/packages/"
        self._current_process = None
        self._picons_path = options.get("picons_dir_path", "")

        handlers = {"on_receive": self.on_receive,
                    "on_cancel": self.on_cancel,
                    "on_close": self.on_close,
                    "on_send": self.on_send,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_picons_dir_open": self.on_picons_dir_open}

        builder = Gtk.Builder()
        builder.add_objects_from_file(UI_RESOURCES_PATH + "picons_dialog.glade", ("picons_dialog", "receive_image"))
        builder.connect_signals(handlers)
        self._dialog = builder.get_object("picons_dialog")
        self._dialog.set_transient_for(transient)
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

        self._ip_entry.set_text(options.get("host", ""))
        self._picons_entry.set_text(options.get("picons_path", ""))
        self._picons_dir_entry.set_text(self._picons_path)

    def show(self):
        self._dialog.run()
        self._dialog.destroy()

    @run_idle
    def on_receive(self, item):
        self.start_download()

    def start_download(self):
        self._expander.set_expanded(True)
        self.show_info_message("Please, wait...", Gtk.MessageType.INFO)
        url = "https://" + self._BASE_URL + "NTV-Plus.html"
        self._current_process = subprocess.Popen(["wget", "-pkP", self._TMP_DIR, url],
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE,
                                                 universal_newlines=True)
        GLib.io_add_watch(self._current_process.stderr, GLib.IO_IN, self.write_to_buffer)
        self.batch_rename()

    @run_task
    def batch_rename(self):
        self._current_process.wait()
        path = self._TMP_DIR + self._BASE_URL + "NTV-Plus.html"
        PiconsParser.parse(path, self._picons_path, self._TMP_DIR)
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

    @run_task
    def on_cancel(self, item):
        if self._current_process:
            self._current_process.kill()
            time.sleep(1)

    @run_idle
    def on_close(self, item):
        self.on_cancel(item)
        self._dialog.destroy()

    def on_send(self, item):
        pass

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    def on_picons_dir_open(self, entry, icon, event_button):
        update_entry_data(entry, self._dialog, options={"data_dir_path": self._picons_path})


if __name__ == "__main__":
    pass

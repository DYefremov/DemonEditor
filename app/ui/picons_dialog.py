import subprocess
import time

from gi.repository import GLib

from app.commons import run_idle, run_task
from . import Gtk, UI_RESOURCES_PATH


class PiconsDialog:
    def __init__(self, transient, options):
        self._current_process = None
        self._picons_path = options.get("picons_dir_path", "")

        handlers = {"on_receive": self.on_receive,
                    "on_cancel": self.on_cancel,
                    "on_close": self.on_close,
                    "on_send": self.on_send}

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

        self._ip_entry.set_text(options.get("host", ""))
        self._picons_entry.set_text(options.get("picons_path", ""))
        self._picons_dir_entry.set_text(self._picons_path)

    def show(self):
        self._dialog.run()
        self._dialog.destroy()

    def on_receive(self, item):
        self._current_process = subprocess.Popen("ls", stdout=subprocess.PIPE)
        GLib.io_add_watch(self._current_process.stdout, GLib.IO_IN, self.write_to_buffer)

    def write_to_buffer(self, fd, condition):
        if condition == GLib.IO_IN:
            char = fd.read(1)
            buf = self._text_view.get_buffer()
            buf.insert_at_cursor(str(char))
            return True
        else:
            return False

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


if __name__ == "__main__":
    pass

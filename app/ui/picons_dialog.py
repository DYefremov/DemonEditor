import subprocess
import time

from gi.repository import GLib

from app.commons import run_idle, run_task
from . import Gtk, UI_RESOURCES_PATH


class PiconsDialog:
    def __init__(self, transient, path):
        self._current_process = None

        handlers = {"on_receive": self.on_receive,
                    "on_cancel": self.on_cancel,
                    "on_close": self.on_close,
                    "on_send": self.on_send}

        builder = Gtk.Builder()
        builder.add_objects_from_file(UI_RESOURCES_PATH + "picons_dialog.glade",
                                      ("picons_dialog", "receive_image", "text_buffer"))
        builder.connect_signals(handlers)
        self._dialog = builder.get_object("picons_dialog")
        self._dialog.set_transient_for(transient)
        self._expander = builder.get_object("expander")
        self._text_view = builder.get_object("text_view")
        self._info_bar = builder.get_object("info_bar")

    def show(self):
        self._dialog.run()
        self._dialog.destroy()

    def on_receive(self, item):
        self._current_process = subprocess.Popen("ls", stdout=subprocess.PIPE)
        GLib.io_add_watch(self._current_process.stdout,  # file descriptor
                          GLib.IO_IN,  # condition
                          self.write_to_buffer)  # callback

    def write_to_buffer(self, fd, condition):
        """https://pygabriel.wordpress.com/2009/07/27/redirecting-the-stdout-on-a-gtk-textview/"""
        if condition == GLib.IO_IN:
            char = fd.read(1)  # we read one byte per time, to avoid blocking
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

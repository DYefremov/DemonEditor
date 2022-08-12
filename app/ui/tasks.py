# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2022 Dmitriy Yefremov
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Author: Dmitriy Yefremov
#


from .uicommons import Gtk, GLib


class BGTaskWidget(Gtk.Box):
    """ Widget for displaying and running background tasks. """

    TASK_LIMIT = 1

    def __init__(self, app, text, target, *args):
        super().__init__(spacing=2, orientation=Gtk.Orientation.HORIZONTAL, valign=Gtk.Align.CENTER)
        self._app = app

        self._label = Gtk.Label(text)
        self.pack_start(self._label, False, False, 0)

        self._spinner = Gtk.Spinner(active=True)
        self.pack_start(self._spinner, False, False, 0)

        close_button = Gtk.Button.new_from_icon_name("gtk-close", Gtk.IconSize.MENU)
        close_button.set_relief(Gtk.ReliefStyle.NONE)
        close_button.set_valign(Gtk.Align.CENTER)
        close_button.set_tooltip_text("Cancel")
        close_button.set_name("task-button")
        close_button.connect("clicked", lambda b: self._app.emit("task-cancel", self))
        self.pack_start(close_button, False, False, 0)

        self.show_all()

        # Just prototype. -> It may not work properly!
        # TODO: Different options need to be tested. Possibly with normal threads.
        from concurrent.futures import ThreadPoolExecutor

        self._executor = ThreadPoolExecutor(max_workers=self.TASK_LIMIT)
        future = self._executor.submit(target, *args)
        future.add_done_callback(lambda f: GLib.idle_add(self._app.emit, "task-done", self))

    @property
    def text(self):
        return self._label.get_text()

    @text.setter
    def text(self, value):
        self._label.set_text(value)

    @property
    def tooltip(self):
        return self.get_tooltip_text()

    @tooltip.setter
    def tooltip(self, value):
        self.set_tooltip_text(value)

    def cancel(self):
        self._executor.shutdown(wait=False)
        self._app.emit("task-canceled", None)


if __name__ == '__main__':
    pass

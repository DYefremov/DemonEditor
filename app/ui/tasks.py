# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2026 Dmitriy Yefremov
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


from app.ui.dialogs import translate
from .uicommons import Gtk, GLib, LoadingProgressBar


class BGTaskWidget(Gtk.Box):
    """ Widget for displaying and running background tasks. """

    def __init__(self, app, text, target, *args):
        super().__init__(spacing=2, orientation=Gtk.Orientation.HORIZONTAL, valign=Gtk.Align.CENTER)
        self._app = app

        self._progress = LoadingProgressBar(margin_start=5, margin_end=5, show_text=True, valign=Gtk.Align.CENTER)
        self._progress.set_text(translate(text))
        self.pack_start(self._progress, False, False, 0)

        close_button = Gtk.Button.new_from_icon_name("window-close", Gtk.IconSize.MENU)
        close_button.set_relief(Gtk.ReliefStyle.NONE)
        close_button.set_valign(Gtk.Align.CENTER)
        close_button.set_tooltip_text(translate("Cancel"))
        close_button.set_name("task-button")
        close_button.connect("clicked", lambda b: self._app.emit("task-cancel", self))
        self.pack_start(close_button, False, False, 0)

        self.show_all()
        # Just prototype. -> It may not work properly!
        from gi.repository.Gio import Task, Cancellable

        self._task = Task.new(self, Cancellable.new(), lambda s, t: GLib.idle_add(self._app.emit, "task-done", self))
        self._task.set_priority(GLib.PRIORITY_LOW)
        self._task.set_return_on_cancel(True)
        self._task.run_in_thread(lambda t, s, d, c: target(*args))

    @property
    def text(self):
        return self._progress.get_text()

    @text.setter
    def text(self, value):
        self._progress.set_text(value)

    @property
    def tooltip(self):
        return self.get_tooltip_text()

    @tooltip.setter
    def tooltip(self, value):
        self.set_tooltip_text(value)

    def cancel(self):
        cancelable = self._task.get_cancellable()
        if cancelable:
            cancelable.cancel()

        self._app.emit("task-canceled", None)


if __name__ == '__main__':
    pass

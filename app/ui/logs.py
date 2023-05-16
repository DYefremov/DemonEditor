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


import logging

from gi.repository import GLib

from app.commons import LOGGER_NAME, LOG_FORMAT, LOG_DATE_FORMAT
from app.ui.dialogs import get_builder
from app.ui.main_helper import append_text_to_tview
from app.ui.uicommons import Gtk, UI_RESOURCES_PATH


class LogsClient(Gtk.Box):
    """ Logger GUI client. """

    class LogHandler(logging.Handler):
        def __init__(self, view):
            logging.Handler.__init__(self)
            self._view = view
            self.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

        def handle(self, rec: logging.LogRecord):
            GLib.idle_add(append_text_to_tview, f"{self.format(rec)}\n", self._view)

    def __init__(self, app, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._app = app

        handlers = {"on_clear": self.on_clear, "on_close": self.on_close}
        builder = get_builder(UI_RESOURCES_PATH + "logs.glade", handlers)

        self._log_view = builder.get_object("log_view")
        self.pack_start(builder.get_object("log_frame"), True, True, 0)

        logger = logging.getLogger(LOGGER_NAME)
        logger.addHandler(LogsClient.LogHandler(self._log_view))

        self.show()

    def on_clear(self, button):
        GLib.idle_add(self._log_view.get_buffer().set_text, "")

    def on_close(self, button):
        self._app.change_action_state("on_logs_show", GLib.Variant.new_boolean(False))


if __name__ == "__main__":
    pass

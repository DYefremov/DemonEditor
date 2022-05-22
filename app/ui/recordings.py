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


""" Module for working with recordings. """
from datetime import datetime
from ftplib import all_errors
from urllib.parse import quote

from .dialogs import get_builder, show_dialog, DialogType
from .main_helper import get_base_paths, get_base_model
from .uicommons import Gtk, Gdk, GLib, UI_RESOURCES_PATH, Column
from ..commons import run_task, run_idle, log
from ..connections import UtfFTP, HttpAPI
from ..settings import IS_DARWIN, PlayStreamsMode


class RecordingsTool(Gtk.Box):
    ROOT = ".."
    DEFAULT_PATH = "/hdd"

    def __init__(self, app, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._app = app
        self._app.connect("layout-changed", self.on_layout_changed)
        self._app.connect("profile-changed", self.init)
        self._settings = settings
        self._ftp = None
        # Icon.
        theme = Gtk.IconTheme.get_default()
        icon = "folder-symbolic" if IS_DARWIN else "folder"
        self._icon = theme.load_icon(icon, 24, 0) if theme.lookup_icon(icon, 24, 0) else None

        handlers = {"on_path_press": self.on_path_press,
                    "on_path_activated": self.on_path_activated,
                    "on_recordings_activated": self.on_recordings_activated,
                    "on_recording_remove": self.on_recording_remove,
                    "on_recordings_model_changed": self.on_recordings_model_changed,
                    "on_recordings_filter_changed": self.on_recordings_filter_changed,
                    "on_recordings_filter_toggled": self.on_recordings_filter_toggled}

        builder = get_builder(f"{UI_RESOURCES_PATH}recordings.glade", handlers)

        self._rec_view = builder.get_object("recordings_view")
        self._paths_view = builder.get_object("recordings_paths_view")
        self._paned = builder.get_object("recordings_paned")
        self._model = builder.get_object("recordings_model")
        self._filter_model = builder.get_object("recordings_filter_model")
        self._filter_model.set_visible_func(self.recordings_filter_function)
        self._filter_entry = builder.get_object("recordings_filter_entry")
        self._recordings_count_label = builder.get_object("recordings_count_label")
        self.pack_start(builder.get_object("recordings_box"), True, True, 0)
        if settings.alternate_layout:
            self.on_layout_changed(app, True)

        self.init()
        self.show()

    def clear_data(self):
        self._model.clear()
        self._paths_view.get_model().clear()

    def on_layout_changed(self, app, alt_layout):
        ch1 = self._paned.get_child1()
        ch2 = self._paned.get_child2()
        self._paned.remove(ch1)
        self._paned.remove(ch2)
        self._paned.add1(ch2)
        self._paned.add(ch1)

    @run_task
    def init(self, app=None, arg=None):
        GLib.idle_add(self.clear_data)
        try:
            if self._ftp:
                self._ftp.close()

            self._ftp = UtfFTP(host=self._settings.host, user=self._settings.user, passwd=self._settings.password)
            self._ftp.encoding = "utf-8"
        except all_errors:
            pass  # NOP
        else:
            self.init_paths(self.DEFAULT_PATH)

    @run_idle
    def init_paths(self, path=None):
        self.clear_data()
        if not self._ftp:
            return

        if path:
            try:
                self._ftp.cwd(path)
            except all_errors as e:
                pass

        files = []
        try:
            self._ftp.dir(files.append)
        except all_errors as e:
            log(e)
        else:
            self.append_paths(files)

    @run_idle
    def append_paths(self, files):
        model = self._paths_view.get_model()
        model.clear()
        model.append((None, self.ROOT, self._ftp.pwd()))

        for f in files:
            f_data = self._ftp.get_file_data(f)
            if len(f_data) < 9:
                log(f"{__class__.__name__}. Folder data parsing error. [{f}]")
                continue

            f_type = f_data[0][0]

            if f_type == "d":
                model.append((self._icon, f_data[8], self._ftp.pwd()))

    def on_path_activated(self, view, path, column):
        row = view.get_model()[path][:]
        path = f"{row[-1]}/{row[1]}/"
        self._app.send_http_request(HttpAPI.Request.RECORDINGS, quote(path), self.update_recordings_data)

    def on_path_press(self, view, event):
        target = view.get_path_at_pos(event.x, event.y)
        if not target or event.button != Gdk.BUTTON_PRIMARY:
            return

        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.init_paths(self._paths_view.get_model()[target[0]][1])

    @run_idle
    def update_recordings_data(self, recordings):
        self._model.clear()
        list(map(self._model.append, (self.get_recordings_row(r) for r in recordings.get("recordings", []))))

    def get_recordings_row(self, rec):
        service = rec.get("e2servicename")
        title = rec.get("e2title", "")
        time = datetime.fromtimestamp(int(rec.get("e2time", "0"))).strftime("%A, %H:%M")
        length = rec.get("e2length", "0")
        file = rec.get("e2filename", "")
        desc = rec.get("e2description", "")

        return service, title, time, length, file, desc, rec

    def on_recordings_activated(self, view, path, column):
        rec = view.get_model()[path][-1]
        self._app.send_http_request(HttpAPI.Request.STREAM_TS, rec.get("e2filename", ""), self.on_play_recording)

    def on_play_recording(self, m3u):
        url = self._app.get_url_from_m3u(m3u)
        if url:
            self._app.emit("play-recording", url)

    def on_recording_remove(self, action, value=None):
        """ Removes recordings via FTP. """
        if show_dialog(DialogType.QUESTION, self._app.app_window) != Gtk.ResponseType.OK:
            return

        model, paths = self._rec_view.get_selection().get_selected_rows()
        paths = get_base_paths(paths, model)
        model = get_base_model(model)

        if paths and self._ftp:
            for file, itr in ((model[p][-1].get("e2filename", ""), model.get_iter(p)) for p in paths):
                resp = self._ftp.delete_file(file)
                if resp.startswith("2"):
                    GLib.idle_add(model.remove, itr)
                else:
                    self._app.show_error_message(resp)
                    break

    def on_recordings_model_changed(self, model, path, itr=None):
        self._recordings_count_label.set_text(str(len(model)))

    def on_recordings_filter_changed(self, entry):
        self._filter_model.refilter()

    def recordings_filter_function(self, model, itr, data):
        txt = self._filter_entry.get_text().upper()
        return next((s for s in model.get(itr, 0, 1, 2, 3, 4, 5) if s and txt in s.upper()), False)

    def on_recordings_filter_toggled(self, button):
        if not button.get_active():
            self._filter_entry.set_text("")

    def on_playback(self, box, state):
        """ Updates state of the UI elements for playback mode. """
        if self._settings.play_streams_mode is PlayStreamsMode.BUILT_IN:
            self._paned.set_orientation(Gtk.Orientation.VERTICAL)
            self.update_rec_columns_visibility(False)

    def on_playback_close(self, box, state):
        """ Restores UI elements state after playback mode. """
        self._paned.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.update_rec_columns_visibility(True)

    def update_rec_columns_visibility(self, state):
        for c in (Column.REC_SERVICE, Column.REC_TIME, Column.REC_LEN, Column.REC_FILE, Column.REC_DESC):
            self._rec_view.get_column(c).set_visible(state)


if __name__ == "__main__":
    pass

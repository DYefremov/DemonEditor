# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2023 Dmitriy Yefremov
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


""" Additional module for playback. """
from functools import lru_cache

from gi.repository import GLib, GObject, Gio

from app.commons import run_idle, run_with_delay
from app.connections import HttpAPI
from app.eparser.ecommons import BqServiceType
from app.settings import PlayStreamsMode, IS_DARWIN, SettingsType, USE_HEADER_BAR
from app.tools.media import Player
from app.ui.dialogs import get_builder, get_message
from app.ui.main_helper import get_iptv_url
from app.ui.uicommons import Gtk, Gdk, UI_RESOURCES_PATH, FavClickMode, Column, Page


class PlayerBox(Gtk.Box):

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        # Signals.
        GObject.signal_new("playback-full-screen", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("playback-close", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("play", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("stop", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))
        GObject.signal_new("pause", self, GObject.SIGNAL_RUN_LAST,
                           GObject.TYPE_PYOBJECT, (GObject.TYPE_PYOBJECT,))

        self._app = app
        self._app.connect("fav-clicked", self.on_fav_clicked)
        self._app.connect("srv-clicked", self.on_srv_clicked)
        self._app.connect("iptv-clicked", self.on_iptv_clicked)
        self._app.connect("page-changed", self.on_page_changed)
        self._app.connect("play-current", self.on_play_current)
        self._app.connect("play-recording", self.on_play_recording)
        self._fav_view = app.fav_view
        self._player = None
        self._current_mrl = None
        self._full_screen = False
        self._playback_window = None
        self._audio_track_menu = None
        self._subtitle_track_menu = None
        self._play_mode = self._app.app_settings.play_streams_mode

        handlers = {"on_realize": self.on_realize,
                    "on_press": self.on_press,
                    "on_next": self.on_next,
                    "on_previous": self.on_previous,
                    "on_rewind": self.on_rewind,
                    "on_full_screen": self.on_full_screen,
                    "on_close": self.on_close}

        builder = get_builder(UI_RESOURCES_PATH + "playback.glade", handlers)
        self.set_spacing(5)
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self._event_box = builder.get_object("event_box")
        self.pack_start(self._event_box, True, True, 0)
        if not IS_DARWIN:
            self.pack_end(builder.get_object("tool_bar"), False, True, 0)
            self._scale = builder.get_object("scale")
            self._full_time_label = builder.get_object("full_time_label")
            self._current_time_label = builder.get_object("current_time_label")
            self._rewind_box = builder.get_object("rewind_box")
            self._tool_bar = builder.get_object("tool_bar")
            self._prev_button = builder.get_object("prev_button")
            self._next_button = builder.get_object("next_button")
            self._audio_menu_button = builder.get_object("audio_menu_button")
            self._video_menu_button = builder.get_object("video_menu_button")
            self._subtitle_menu_button = builder.get_object("subtitle_menu_button")
            self._fav_view.bind_property("sensitive", self._prev_button, "sensitive")
            self._fav_view.bind_property("sensitive", self._next_button, "sensitive")

        self.connect("delete-event", self.on_delete)
        self.connect("show", self.set_player_area_size)

    def on_fav_clicked(self, app, mode):
        if mode is not FavClickMode.STREAM and not self._app.http_api:
            return

        self._fav_view.set_sensitive(False)
        if mode is FavClickMode.STREAM:
            self.on_play_stream()
        elif mode is FavClickMode.ZAP_PLAY:
            self._app.on_zap(self.on_watch)
        elif mode is FavClickMode.PLAY:
            self.on_play_service()

    def on_srv_clicked(self, app, mode):
        if not self._app.http_api:
            return

        view = self._app.services_view
        path, column = view.get_cursor()
        if path:
            srv = self._app.current_services.get(view.get_model()[path][Column.SRV_FAV_ID], None)
            if not srv or not srv.picon_id:
                return

            ref = self._app.get_service_ref_data(srv)
            s_type = self._app.app_settings.setting_type
            error_msg = "No connection to the receiver!"
            if s_type is SettingsType.ENIGMA_2:
                def zap(rq):
                    self.on_watch() if rq and rq.get("e2state", False) else self.on_error(None, error_msg)

                self._app.http_api.send(HttpAPI.Request.ZAP, ref, zap)
            elif self._s_type is SettingsType.NEUTRINO_MP:
                def zap(rq):
                    self.on_watch() if rq and rq.get("data", None) == "ok" else self.on_error(None, error_msg)

                self._app.http_api.send(HttpAPI.Request.N_ZAP, f"?{ref}", zap)

    def on_iptv_clicked(self, app, mode):
        if not self._app.http_api:
            return

        view = self._app.iptv_services_view
        path, column = view.get_cursor()
        if path:
            row = view.get_model()[path][:]
            url = get_iptv_url(row, self._app.app_settings.setting_type, Column.IPTV_FAV_ID)
            self.play(url, row[Column.IPTV_SERVICE]) if url else self.on_error(None, "No reference is present!")

    def on_play_current(self, app, url):
        self.on_watch()

    def on_play_recording(self, app, url):
        self.play(url)

    def on_page_changed(self, app, page):
        self.on_close()
        self.set_visible(False)

    def on_realize(self, box):
        if not self._player:
            settings = self._app.app_settings
            try:
                self._player = Player.make(settings.stream_lib, settings.play_streams_mode, self._event_box)
            except (ImportError, NameError) as e:
                self._app.show_error_message(str(e))
                return True
            else:
                self.init_playback_elements()
                self.emit("play", self._current_mrl)
            finally:
                if settings.play_streams_mode is PlayStreamsMode.BUILT_IN:
                    self.set_player_area_size(box)

    def init_playback_elements(self):
        self._player.connect("error", self.on_error)
        self._player.connect("played", self.on_played)
        self._player.connect("audio-track", self.on_audio_track_changed)
        self._player.connect("subtitle-track", self.on_subtitle_track_changed)
        self._app.app_window.connect("key-press-event", self.on_key_press)

        builder = get_builder(UI_RESOURCES_PATH + "app_menu.ui")
        self._audio_track_menu = builder.get_object("audio_track_menu")
        self._subtitle_track_menu = builder.get_object("subtitle_track_menu")
        audio_menu = builder.get_object("audio_menu")
        video_menu = builder.get_object("video_menu")
        subtitle_menu = builder.get_object("subtitle_menu")

        if not USE_HEADER_BAR:
            menu_bar = self._app.get_menubar()
            menu_bar.insert_section(1, None, audio_menu)
            menu_bar.insert_section(2, None, video_menu)
            menu_bar.insert_section(3, None, subtitle_menu)

        if not IS_DARWIN:
            self._player.connect("position", self.on_time_changed)
            self._audio_menu_button.set_menu_model(self._audio_track_menu)
            self._video_menu_button.set_menu_model(builder.get_object("aspect_ratio_menu"))
            self._subtitle_menu_button.set_menu_model(self._subtitle_track_menu)
        # Actions.
        self._app.set_action("on_play", self.on_play)
        self._app.set_action("on_stop", self.on_stop)
        audio_track_action = Gio.SimpleAction.new_stateful("on_set_audio_track", GLib.VariantType.new("i"),
                                                           GLib.Variant("i", 0))
        audio_track_action.connect("activate", self.on_set_audio_track)
        self._app.add_action(audio_track_action)
        aspect_action = Gio.SimpleAction.new_stateful("on_set_aspect_ratio", GLib.VariantType.new("s"),
                                                      GLib.Variant("s", ""))
        aspect_action.connect("activate", self.on_set_aspect_ratio)
        self._app.add_action(aspect_action)
        subtitle_track_action = Gio.SimpleAction.new_stateful("on_set_subtitle_track", GLib.VariantType.new("i"),
                                                              GLib.Variant("i", -1))
        subtitle_track_action.connect("activate", self.on_set_subtitle_track)
        self._app.add_action(subtitle_track_action)

    def on_play(self, action=None, value=None):
        self.emit("play", None)

    def on_stop(self, action=None, value=None):
        self.emit("stop", None)

    def on_next(self, button):
        if self._fav_view.do_move_cursor(self._fav_view, Gtk.MovementStep.DISPLAY_LINES, 1):
            self.set_player_action()

    def on_previous(self, button):
        if self._fav_view.do_move_cursor(self._fav_view, Gtk.MovementStep.DISPLAY_LINES, -1):
            self.set_player_action()

    def on_rewind(self, scale, scroll_type, value):
        self._player.set_time(int(value))

    def on_full_screen(self, item=None):
        self._full_screen = not self._full_screen
        if self._play_mode is PlayStreamsMode.BUILT_IN:
            self._tool_bar.set_visible(not self._full_screen)
            self.emit("playback-full-screen", not self._full_screen)
        elif self._playback_window:
            if not IS_DARWIN:
                self._tool_bar.set_visible(not self._full_screen)
            self._playback_window.fullscreen() if self._full_screen else self._playback_window.unfullscreen()

    def on_close(self, action=None, value=None):
        if self._playback_window:
            self._app.app_settings.add("playback_window_size", self._playback_window.get_size())
            self._playback_window.hide()

        self.on_stop()
        self.hide()
        self.emit("playback-close", None)

        return True

    @run_with_delay(1)
    def on_audio_track_changed(self, player, tracks):
        self._audio_track_menu.remove_all()
        for t in tracks:
            item = Gio.MenuItem.new(t[1], None)
            item.set_action_and_target_value("app.on_set_audio_track", GLib.Variant("i", t[0]))
            self._audio_track_menu.append_item(item)

    @run_with_delay(1)
    def on_subtitle_track_changed(self, player, tracks):
        self._subtitle_track_menu.remove_all()
        for t in tracks:
            item = Gio.MenuItem.new(t[1], None)
            item.set_action_and_target_value("app.on_set_subtitle_track", GLib.Variant("i", t[0]))
            self._subtitle_track_menu.append_item(item)

    def on_set_audio_track(self, action, value):
        action.set_state(value)
        self._player.set_audio_track(value.get_int32())

    def on_set_aspect_ratio(self, action, value):
        action.set_state(value)
        self._player.set_aspect_ratio(value.get_string())

    def on_set_subtitle_track(self, action, value):
        action.set_state(value)
        self._player.set_subtitle_track(value.get_int32())

    def on_press(self, area, event):
        if event.button == Gdk.BUTTON_PRIMARY:
            if event.type == Gdk.EventType.BUTTON_PRESS:
                self.emit("pause", None)
            elif event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
                self.on_full_screen()

    def on_key_press(self, widget, event):
        if self._player and self.get_visible():
            key = event.keyval
            if any((key == Gdk.KEY_F11, key == Gdk.KEY_f, self._full_screen and key == Gdk.KEY_Escape)):
                self.on_full_screen()

    def on_delete(self, box):
        if self._player:
            self._player.release()

    @run_with_delay(1)
    def set_player_action(self):
        click_mode = self._app.app_settings.fav_click_mode
        self._fav_view.set_sensitive(False)
        if click_mode is FavClickMode.PLAY:
            self.on_play_service()
        elif click_mode is FavClickMode.ZAP_PLAY:
            self._app.on_zap(self.on_watch)
        elif click_mode is FavClickMode.STREAM:
            self.on_play_stream()

    def update_buttons(self):
        if self._player:
            path, column = self._fav_view.get_cursor()
            current_index = path[0]
            self._player_prev_button.set_sensitive(current_index != 0)
            self._player_next_button.set_sensitive(len(self._fav_model) != current_index + 1)

    @lru_cache(maxsize=1)
    def on_duration_changed(self, duration):
        self._scale.set_value(0)
        self._scale.get_adjustment().set_upper(duration)
        GLib.idle_add(self._rewind_box.set_visible, duration > 0, priority=GLib.PRIORITY_LOW)
        GLib.idle_add(self._current_time_label.set_text, "0", priority=GLib.PRIORITY_LOW)
        GLib.idle_add(self._full_time_label.set_text, self.get_time_str(duration),
                      priority=GLib.PRIORITY_LOW)

    def on_time_changed(self, widget, t):
        if not self._full_screen and self._rewind_box.get_visible():
            GLib.idle_add(self._current_time_label.set_text, self.get_time_str(t),
                          priority=GLib.PRIORITY_LOW)

    def get_time_str(self, duration):
        """ Returns a string representation of time from duration in milliseconds """
        m, s = divmod(duration // 1000, 60)
        h, m = divmod(m, 60)
        return f"{str(h) + ':' if h else ''}{m:02d}:{s:02d}"

    def set_player_area_size(self, widget):
        w, h = self._app.app_window.get_size()
        widget.set_size_request(w * 0.6, -1)

    @run_idle
    def show_playback_window(self, title=None):
        width, height = 480, 240
        size = self._app.app_settings.get("playback_window_size")
        if size:
            width, height = size

        if self._playback_window:
            self._playback_window.show()
            self._playback_window.set_title(title or self.get_playback_title())
        else:
            self._playback_window = Gtk.Window(title=title or self.get_playback_title(),
                                               window_position=Gtk.WindowPosition.CENTER,
                                               icon_name="demon-editor")

            self._playback_window.connect("delete-event", self.on_close)
            self._playback_window.connect("key-press-event", self.on_key_press)
            self._playback_window.bind_property("visible", self._event_box, "visible")

            if not IS_DARWIN:
                self._prev_button.set_visible(False)
                self._next_button.set_visible(False)

            self.reparent(self._playback_window)
            self._playback_window.set_application(self._app)

        self.show()
        self._playback_window.resize(width, height)
        self._playback_window.show()

    def get_playback_title(self):
        if self._app.page is not Page.RECORDINGS:
            path, column = self._fav_view.get_cursor()
            if path:
                return f"DemonEditor [{self._app.fav_view.get_model()[path][:][Column.FAV_SERVICE]}]"
        else:
            return f"DemonEditor [{get_message('Recordings')}]"
        return f"DemonEditor [{get_message('Playback')}]"

    def on_play_stream(self):
        path, column = self._fav_view.get_cursor()
        if path:
            row = self._fav_view.get_model()[path][:]
            if row[Column.FAV_TYPE] != BqServiceType.IPTV.name:
                self.on_error(None, "Not allowed in this context!")
                return

            url = get_iptv_url(row, self._app.app_settings.setting_type)
            self.play(url) if url else self.on_error(None, "No reference is present!")

    def on_play_service(self, item=None):
        path, column = self._fav_view.get_cursor()
        if not path or not self._app.http_api:
            return

        ref = self._app.get_service_ref(path)
        if not ref:
            return

        if self._player and self._player.is_playing():
            self.emit("stop", None)

        s_type = self._app.app_settings.setting_type
        req = HttpAPI.Request.STREAM if s_type is SettingsType.ENIGMA_2 else HttpAPI.Request.N_STREAM
        self._app.http_api.send(req, ref, self.watch)

    def on_watch(self, item=None):
        """ Switch to the channel and watch in the player. """
        s_type = self._app.app_settings.setting_type
        if s_type is SettingsType.ENIGMA_2:
            self._app.http_api.send(HttpAPI.Request.STREAM_CURRENT, "", self.watch)
        elif s_type is SettingsType.NEUTRINO_MP:
            self._app.http_api.send(HttpAPI.Request.N_ZAP, "",
                                    lambda rf: self._app.http_api.send(HttpAPI.Request.N_STREAM, rf.get("data", ""),
                                                                       self.watch))

    def watch(self, data):
        url = self._app.get_url_from_m3u(data)
        GLib.timeout_add_seconds(1, self.play, url) if url else self.on_error(None, "Can't Playback!")

    def play(self, url, title=None):
        if self._play_mode is PlayStreamsMode.M3U:
            self._app.save_stream_to_m3u(url)
            return

        if self._play_mode is not self._app.app_settings.play_streams_mode:
            self.on_error(None, "Play mode has been changed!\nRestart the program to apply the settings.")
            return

        if self._play_mode is PlayStreamsMode.BUILT_IN:
            self.show()
        elif self._play_mode is PlayStreamsMode.WINDOW:
            self.show_playback_window(title)

        if self._player:
            self.emit("play", url)
        else:
            self._current_mrl = url

    @run_idle
    def on_played(self, player, duration):
        self._fav_view.set_sensitive(True)
        if not IS_DARWIN:
            self.on_duration_changed(duration)

    @run_idle
    def on_error(self, player, msg):
        self._app.show_error_message(msg)
        self._fav_view.set_sensitive(True)


if __name__ == "__main__":
    pass

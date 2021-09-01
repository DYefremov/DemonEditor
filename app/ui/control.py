# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2021 Dmitriy Yefremov
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


""" Receiver control module via HTTP API. """
import os
from datetime import datetime
from urllib.parse import quote

from gi.repository import GLib

from .dialogs import get_builder
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, Page
from ..commons import run_task, run_with_delay, log, run_idle
from ..connections import HttpAPI


class EpgBox(Gtk.Box):
    def __init__(self, app, http_api, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._http_api = http_api
        self._app = app
        self._app.connect("fav-changed", self.on_service_changed)

        handlers = {"on_epg_press": self.on_epg_press}

        builder = get_builder(UI_RESOURCES_PATH + "control.glade", handlers, objects=("epg_frame", "epg_model"))
        self._view = builder.get_object("epg_view")
        self.add(builder.get_object("epg_frame"))
        self.show()

    def on_epg_press(self, list_box, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS and len(list_box) > 0:
            row = list_box.get_selected_row()
            if row:
                self.set_timer_from_event_data(row.event_data)

    def on_service_changed(self, app, ref):
        self._app._wait_dialog.show()
        self._http_api.send(HttpAPI.Request.EPG, quote(ref), self.update_epg_data)

    @run_idle
    def update_epg_data(self, epg):
        model = self._view.get_model()
        model.clear()
        list(map(model.append, (self.get_event_row(e) for e in epg.get("event_list", []))))
        self._app._wait_dialog.hide()

    def get_event_row(self, event):
        title = event.get("e2eventtitle", "")
        desc = event.get("e2eventdescription", "")

        start = int(event.get("e2eventstart", "0"))
        start_time = datetime.fromtimestamp(start)
        end_time = datetime.fromtimestamp(start + int(event.get("e2eventduration", "0")))
        time = "{} - {}".format(start_time.strftime("%A, %H:%M"), end_time.strftime("%H:%M"))

        return title, time, desc, event


class TimersBox(Gtk.Box):
    def __init__(self, app, http_api, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._http_api = http_api
        self._app = app
        self._app.connect("page-changed", self.update_timer_list)

        handlers = {}

        builder = get_builder(UI_RESOURCES_PATH + "control.glade", handlers, objects=("timers_frame", "timer_model"))
        self._view = builder.get_object("timer_view")
        self._remove_button = builder.get_object("timer_remove_button")
        self.add(builder.get_object("timers_frame"))
        self.show()

    def update_timer_list(self, app, page):
        if page is Page.TIMERS:
            self._app._wait_dialog.show()
            self._http_api.send(HttpAPI.Request.TIMER_LIST, "", self.update_timers_data)

    @run_idle
    def update_timers_data(self, timers):
        model = self._view.get_model()
        model.clear()
        list(map(model.append, (self.get_timer_row(t) for t in timers.get("timer_list", []))))
        self._remove_button.set_visible(len(model))
        self._app._wait_dialog.hide()

    def get_timer_row(self, timer):
        name = timer.get("e2name", "") or ""
        description = timer.get("e2description", "") or ""
        service = timer.get("e2servicename", "") or ""
        start_time = datetime.fromtimestamp(int(timer.get("e2timebegin", "0")))
        end_time = datetime.fromtimestamp(int(timer.get("e2timeend", "0")))
        time = "{} - {}".format(start_time.strftime("%A, %H:%M"), end_time.strftime("%H:%M"))

        return name, service, time, description, timer


class ControlBox(Gtk.HBox):

    def __init__(self, app, http_api, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._http_api = http_api
        self._settings = settings
        self._app = app

        handlers = {"on_volume_changed": self.on_volume_changed}

        builder = get_builder(UI_RESOURCES_PATH + "control.glade", handlers,
                              objects=("control_box", "volume_adjustment"))

        self.add(builder.get_object("control_box"))
        self._stack = builder.get_object("stack")
        self._screenshot_image = builder.get_object("screenshot_image")
        self._screenshot_button_box = builder.get_object("screenshot_button_box")
        self._screenshot_check_button = builder.get_object("screenshot_check_button")
        self._screenshot_check_button.bind_property("active", self._screenshot_image, "visible")
        self._snr_value_label = builder.get_object("snr_value_label")
        self._ber_value_label = builder.get_object("ber_value_label")
        self._agc_value_label = builder.get_object("agc_value_label")
        self._volume_button = builder.get_object("volume_button")
        self.init_actions(app)
        self.show()

    def init_actions(self, app):
        # Remote controller actions
        app.set_action("on_up", lambda a, v: self.on_remote_action(HttpAPI.Remote.UP))
        app.set_action("on_down", lambda a, v: self.on_remote_action(HttpAPI.Remote.DOWN))
        app.set_action("on_left", lambda a, v: self.on_remote_action(HttpAPI.Remote.LEFT))
        app.set_action("on_right", lambda a, v: self.on_remote_action(HttpAPI.Remote.RIGHT))
        app.set_action("on_ok", lambda a, v: self.on_remote_action(HttpAPI.Remote.OK))
        app.set_action("on_menu", lambda a, v: self.on_remote_action(HttpAPI.Remote.MENU))
        app.set_action("on_exit", lambda a, v: self.on_remote_action(HttpAPI.Remote.EXIT))
        app.set_action("on_red", lambda a, v: self.on_remote_action(HttpAPI.Remote.RED))
        app.set_action("on_green", lambda a, v: self.on_remote_action(HttpAPI.Remote.GREEN))
        app.set_action("on_yellow", lambda a, v: self.on_remote_action(HttpAPI.Remote.YELLOW))
        app.set_action("on_blue", lambda a, v: self.on_remote_action(HttpAPI.Remote.BLUE))
        # Power
        app.set_action("on_standby", lambda a, v: self.on_power_action(HttpAPI.Power.STANDBY))
        app.set_action("on_wake_up", lambda a, v: self.on_power_action(HttpAPI.Power.WAKEUP))
        app.set_action("on_reboot", lambda a, v: self.on_power_action(HttpAPI.Power.REBOOT))
        app.set_action("on_restart_gui", lambda a, v: self.on_power_action(HttpAPI.Power.RESTART_GUI))
        app.set_action("on_shutdown", lambda a, v: self.on_power_action(HttpAPI.Power.DEEP_STANDBY))
        # Screenshots
        app.set_action("on_screenshot_all", self.on_screenshot_all)
        app.set_action("on_screenshot_video", self.on_screenshot_video)
        app.set_action("on_screenshot_osd", self.on_screenshot_osd)

    # ***************** Remote controller ********************* #

    def on_remote(self, action, state=False):
        """ Shows/Hides [R key] remote controller. """
        action.set_state(state)
        self._remote_revealer.set_visible(state)
        self._remote_revealer.set_reveal_child(state)

        if state:
            self._http_api.send(HttpAPI.Request.VOL, "state", self.update_volume)

    def on_remote_action(self, action):
        self._http_api.send(HttpAPI.Request.REMOTE, action, self.on_response)

    @run_with_delay(0.5)
    def on_volume_changed(self, button, value):
        self._http_api.send(HttpAPI.Request.VOL, "{:.0f}".format(value), self.on_response)

    def update_volume(self, vol):
        if "error_code" in vol:
            return

        GLib.idle_add(self._volume_button.set_value, int(vol.get("e2current", "0")))

    def on_response(self, resp):
        if "error_code" in resp:
            return

        if self._screenshot_check_button.get_active():
            ref = "mode=all" if self._http_api.is_owif else "d="
            self._http_api.send(HttpAPI.Request.GRUB, ref, self.update_screenshot)

    @run_task
    def update_screenshot(self, data):
        if "error_code" in data:
            return

        data = data.get("img_data", None)
        if data:
            from gi.repository import GdkPixbuf

            allocation = self._screenshot_image.get_parent().get_allocation()
            loader = GdkPixbuf.PixbufLoader.new_with_type("jpeg")
            loader.set_size(allocation.width, allocation.height)
            try:
                loader.write(data)
                pix = loader.get_pixbuf()
            except GLib.Error:
                pass  # NOP
            else:
                GLib.idle_add(self._screenshot_image.set_from_pixbuf, pix)
            finally:
                loader.close()

    def on_screenshot_all(self, action, value=None):
        self._http_api.send(HttpAPI.Request.GRUB, "mode=all" if self._http_api.is_owif else "d=",
                            self.on_screenshot)

    def on_screenshot_video(self, action, value=None):
        self._http_api.send(HttpAPI.Request.GRUB, "mode=video" if self._http_api.is_owif else "v=",
                            self.on_screenshot)

    def on_screenshot_osd(self, action, value=None):
        self._http_api.send(HttpAPI.Request.GRUB, "mode=osd" if self._http_api.is_owif else "o=",
                            self.on_screenshot)

    @run_task
    def on_screenshot(self, data):
        if "error_code" in data:
            return

        img = data.get("img_data", None)
        if img:
            is_darwin = self._settings.is_darwin
            GLib.idle_add(self._screenshot_button_box.set_sensitive, is_darwin)
            path = os.path.expanduser("~/Desktop") if is_darwin else None

            try:
                import tempfile
                import subprocess

                with tempfile.NamedTemporaryFile(mode="wb", suffix=".jpg", dir=path, delete=not is_darwin) as tf:
                    tf.write(img)
                    cmd = ["open" if is_darwin else "xdg-open", tf.name]
                    subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
            finally:
                GLib.idle_add(self._screenshot_button_box.set_sensitive, True)

    def on_power_action(self, action):
        self._http_api.send(HttpAPI.Request.POWER, action, lambda resp: log("Power status changed..."))

    def update_signal(self, sig):
        self._snr_value_label.set_text(sig.get("e2snrdb", "0 dB").strip())
        self._ber_value_label.set_text(str(sig.get("e2ber", None) or "0").strip())
        self._agc_value_label.set_text(sig.get("e2acg", "0 %").strip())

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


""" Receiver control module via HTTP API. """
import os
import re

from gi.repository import GLib

from .dialogs import get_builder, get_message
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH
from ..commons import run_task, run_with_delay, log, run_idle
from ..connections import HttpAPI
from ..settings import IS_DARWIN, IS_LINUX, IS_WIN


class ControlTool(Gtk.Box):

    def __init__(self, app, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._settings = settings
        self._app = app
        self._app.connect("layout-changed", self.on_layout_changed)
        self._pix = None

        handlers = {"on_volume_changed": self.on_volume_changed,
                    "on_screenshot_draw": self.on_screenshot_draw,
                    "on_network_toggled": self.on_network_toggled,
                    "on_network_view_query_tooltip": self.on_network_view_query_tooltip}

        builder = get_builder(UI_RESOURCES_PATH + "control.glade", handlers)

        self.pack_start(builder.get_object("control_box"), True, True, 0)
        self._remote_box = builder.get_object("remote_box")
        self._screenshot_area = builder.get_object("screenshot_area")
        self._screenshot_button_box = builder.get_object("screenshot_button_box")
        self._screenshot_check_button = builder.get_object("screenshot_check_button")
        self._screenshot_check_button.bind_property("active", self._screenshot_area, "visible")
        self._snr_value_label = builder.get_object("snr_value_label")
        self._ber_value_label = builder.get_object("ber_value_label")
        self._agc_value_label = builder.get_object("agc_value_label")
        self._snr_level_bar = builder.get_object("snr_level_bar")
        self._ber_level_bar = builder.get_object("ber_level_bar")
        self._agc_level_bar = builder.get_object("agc_level_bar")
        self._volume_button = builder.get_object("volume_button")
        self._header_box = builder.get_object("control_header_box")
        # Network.
        self._network_button = builder.get_object("control_network_button")
        self._network_model = builder.get_object("network_model")

        self.init_actions(app)

        if settings.alternate_layout:
            self.on_layout_changed(app, True)

        self.show()

    def init_actions(self, app):
        # Remote controller actions.
        app.set_action("on_up", lambda a, v: self.on_remote_action(HttpAPI.Remote.UP))
        app.set_action("on_down", lambda a, v: self.on_remote_action(HttpAPI.Remote.DOWN))
        app.set_action("on_left", lambda a, v: self.on_remote_action(HttpAPI.Remote.LEFT))
        app.set_action("on_right", lambda a, v: self.on_remote_action(HttpAPI.Remote.RIGHT))
        app.set_action("on_back", lambda a, v: self.on_remote_action(HttpAPI.Remote.BACK))
        app.set_action("on_info", lambda a, v: self.on_remote_action(HttpAPI.Remote.INFO))
        app.set_action("on_ok", lambda a, v: self.on_remote_action(HttpAPI.Remote.OK))
        app.set_action("on_menu", lambda a, v: self.on_remote_action(HttpAPI.Remote.MENU))
        app.set_action("on_exit", lambda a, v: self.on_remote_action(HttpAPI.Remote.EXIT))
        app.set_action("on_ch_up", lambda a, v: self.on_remote_action(HttpAPI.Remote.CH_UP))
        app.set_action("on_ch_down", lambda a, v: self.on_remote_action(HttpAPI.Remote.CH_DOWN))
        app.set_action("on_red", lambda a, v: self.on_remote_action(HttpAPI.Remote.RED))
        app.set_action("on_green", lambda a, v: self.on_remote_action(HttpAPI.Remote.GREEN))
        app.set_action("on_yellow", lambda a, v: self.on_remote_action(HttpAPI.Remote.YELLOW))
        app.set_action("on_blue", lambda a, v: self.on_remote_action(HttpAPI.Remote.BLUE))
        app.set_action("on_audio", lambda a, v: self.on_remote_action(HttpAPI.Remote.AUDIO))
        app.set_action("on_tv", lambda a, v: self.on_remote_action(HttpAPI.Remote.TV))
        app.set_action("on_radio", lambda a, v: self.on_remote_action(HttpAPI.Remote.RADIO))
        app.set_action("on_fav", lambda a, v: self.on_remote_action(HttpAPI.Remote.FAV))
        # Playback.
        app.set_action("on_prev_media", lambda a, v: self.on_player_action(HttpAPI.Request.PLAYER_PREV))
        app.set_action("on_play_media", lambda a, v: self.on_player_action(HttpAPI.Request.PLAYER_PLAY))
        app.set_action("on_stop_media", lambda a, v: self.on_player_action(HttpAPI.Request.PLAYER_STOP))
        app.set_action("on_next_media", lambda a, v: self.on_player_action(HttpAPI.Request.PLAYER_NEXT))
        # Power.
        app.set_action("on_standby", lambda a, v: self.on_power_action(HttpAPI.Power.STANDBY))
        app.set_action("on_wake_up", lambda a, v: self.on_power_action(HttpAPI.Power.WAKEUP))
        app.set_action("on_reboot", lambda a, v: self.on_power_action(HttpAPI.Power.REBOOT))
        app.set_action("on_restart_gui", lambda a, v: self.on_power_action(HttpAPI.Power.RESTART_GUI))
        app.set_action("on_shutdown", lambda a, v: self.on_power_action(HttpAPI.Power.DEEP_STANDBY))
        # Screenshots.
        app.set_action("on_screenshot_all", self.on_screenshot_all)
        app.set_action("on_screenshot_video", self.on_screenshot_video)
        app.set_action("on_screenshot_osd", self.on_screenshot_osd)

    def on_layout_changed(self, app, alt_layout):
        children = self._remote_box.get_children()
        self._remote_box.reorder_child(children[0], len(children) - 1)
        self._remote_box.reorder_child(children[-1], 0)
        pack_type = Gtk.PackType.END if alt_layout else Gtk.PackType.START
        self._header_box.set_child_packing(self._network_button, False, False, 0, pack_type)

    # ***************** Remote controller ********************* #

    def on_remote(self, action, state=False):
        """ Shows/Hides [R key] remote controller. """
        action.set_state(state)
        self._remote_revealer.set_visible(state)
        self._remote_revealer.set_reveal_child(state)

        if state:
            self._app.send_http_request(HttpAPI.Request.VOL, "state", self.update_volume)

    def on_remote_action(self, action):
        self._app.send_http_request(HttpAPI.Request.REMOTE, action, self.on_response)

    def on_player_action(self, action):
        self._app.send_http_request(action, "", self.on_response)

    @run_with_delay(0.5)
    def on_volume_changed(self, button, value):
        self._app.send_http_request(HttpAPI.Request.VOL, f"{value:.0f}", self.on_response)

    def update_volume(self, vol):
        if "error_code" in vol:
            return

        GLib.idle_add(self._volume_button.set_value, int(vol.get("e2current", "0")))

    def on_response(self, resp):
        if "error_code" in resp:
            return

        if self._screenshot_check_button.get_active() and self._app.http_api:
            ref = "mode=all" if self._app.http_api.is_owif else "d="
            self._app.send_http_request(HttpAPI.Request.GRUB, ref, self.update_screenshot)

    @run_task
    def update_screenshot(self, data):
        if "error_code" in data:
            return

        data = data.get("img_data", None)
        if data:
            from gi.repository import GdkPixbuf

            allocation = self._screenshot_area.get_parent().get_allocation()
            loader = GdkPixbuf.PixbufLoader.new_with_type("jpeg")
            loader.set_size(allocation.width, allocation.height)
            try:
                loader.write(data)
                pix = loader.get_pixbuf()
            except GLib.Error:
                pass  # NOP
            else:
                self._pix = pix
                self._screenshot_area.queue_draw()  # Redrawing the area!
            finally:
                loader.close()

    def on_screenshot_draw(self, area, cr):
        """ Called to automatically resize the screenshot.  """
        if self._pix:
            cr.scale(area.get_allocated_width() / self._pix.get_width(),
                     area.get_allocated_height() / self._pix.get_height())
            img_surface = Gdk.cairo_surface_create_from_pixbuf(self._pix, 1, None)
            cr.set_source_surface(img_surface, 0, 0)
            cr.paint()

    def on_screenshot_all(self, action, value=None):
        if self._app.http_api:
            self._app.send_http_request(HttpAPI.Request.GRUB, "mode=all" if self._app.http_api.is_owif else "d=",
                                        self.on_screenshot)

    def on_screenshot_video(self, action, value=None):
        if self._app.http_api:
            self._app.send_http_request(HttpAPI.Request.GRUB, "mode=video" if self._app.http_api.is_owif else "v=",
                                        self.on_screenshot)

    def on_screenshot_osd(self, action, value=None):
        if self._app.http_api:
            self._app.send_http_request(HttpAPI.Request.GRUB, "mode=osd" if self._app.http_api.is_owif else "o=",
                                        self.on_screenshot)

    @run_task
    def on_screenshot(self, data):
        if "error_code" in data:
            return

        img = data.get("img_data", None)
        if img:
            GLib.idle_add(self._screenshot_button_box.set_sensitive, not IS_LINUX)
            path = os.path.expanduser("~/Desktop") if not IS_LINUX else None

            try:
                import tempfile
                import subprocess

                with tempfile.NamedTemporaryFile(mode="wb", suffix=".jpg", dir=path, delete=IS_LINUX) as tf:
                    tf.write(img)
                    if IS_LINUX:
                        cmd = ["xdg-open", tf.name]
                    elif IS_DARWIN:
                        cmd = ["open", tf.name]
                    else:
                        cmd = [tf.name]

                    if not IS_WIN:
                        subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
                # File must be closed.
                if IS_WIN:
                    subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=IS_WIN).communicate()
            finally:
                GLib.idle_add(self._screenshot_button_box.set_sensitive, True)

    def on_power_action(self, action):
        self._app.send_http_request(HttpAPI.Request.POWER, action, lambda resp: log("Power status changed..."))

    def update_signal(self, sig):
        snr = sig.get("e2snr", "0 %").strip() if sig else "0 %"
        acg = sig.get("e2acg", "0 %").strip() if sig else "0 %"
        ber = (sig.get("e2ber", None) or "").strip() if sig else ""
        # Labels.
        self._snr_value_label.set_text(snr)
        self._agc_value_label.set_text(acg)
        self._ber_value_label.set_text(ber)
        # Level bars.
        self._snr_level_bar.set_value(int(snr.strip("%N/A") or 0))
        self._agc_level_bar.set_value(int(acg.rstrip("%N/A") or 0))
        self._ber_level_bar.set_value(int(ber.rstrip("N/A") or 0))

    # ***************** Network explorer ********************** #

    def on_network_toggled(self, button):
        self._network_model.clear()
        if button.get_active():
            self.update_network()

    @run_task
    def update_network(self):
        pattern = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')

        ips = [match for match in re.findall(pattern, os.popen("arp -a").read())]
        for ip in ips:
            if not self._network_button.get_active():
                break

            url = f"http://{ip}/web/{HttpAPI.Request.INFO.value}"
            try:
                resp = HttpAPI.get_response(HttpAPI.Request.INFO, url, timeout=5)
            except OSError as e:
                log(f"{ip} {e}")
            else:
                if resp.get("e2distroversion", None):
                    log(f"Receiver found. Model: {resp.get('e2model', 'N/A')} [{ip} ]")
                    self.append_box_data(resp)

    @run_idle
    def append_box_data(self, data):
        ip = data.get('e2lanip', 'N/A')
        itr = self._network_model.append((data.get("e2model", "N/A"), ip, None, data, None))
        GLib.timeout_add_seconds(3, self.check_power_state, itr, priority=GLib.PRIORITY_LOW)

    def on_network_view_query_tooltip(self, view, x, y, keyboard_mode, tooltip):
        result = view.get_dest_row_at_pos(x, y)
        if not result:
            return False

        path, pos = result
        model = view.get_model()
        data = model[path][3]

        dist = data.get("e2distroversion", "N/A")
        img = data.get("e2imageversion", "N/A")
        txt = f"Distro version: {dist}\nImage version: {img}"
        tooltip.set_text(txt)
        view.set_tooltip_row(tooltip, path)
        return True

    def check_power_state(self, itr):
        active = self._network_button.get_active()
        if not active:
            return False

        data = self._network_model.get_value(itr, 3)
        url = f"http://{data.get('e2lanip', 'N/A')}/web/powerstate"
        self.update_power_state(itr, url)
        return active

    @run_task
    def update_power_state(self, itr, url):
        try:
            resp = HttpAPI.get_response(HttpAPI.Request.POWER, url, timeout=2)
        except OSError as e:
            log(e)
        else:
            state = get_message("On" if resp.get("e2instandby", "N/A").strip() == "false" else "Standby")
            GLib.idle_add(self._network_model.set_value, itr, 2, state)


if __name__ == "__main__":
    pass

""" Receiver control module via HTTP API. """
import os
from datetime import datetime
from enum import Enum

from gi.repository import GLib

from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH
from ..commons import run_task, run_with_delay, log, run_idle
from ..connections import HttpAPI


class ControlBox(Gtk.HBox):
    class Tool(Enum):
        """ The currently displayed tool. """
        REMOTE = "control"
        EPG = "epg"
        TIMERS = "timers"

    class EpgRow(Gtk.HBox):
        def __init__(self, event: dict, **properties):
            super().__init__(**properties)

            self._ev_id = event.get("e2eventid", "")
            self._ref = event.get("e2eventservicereference", "")
            self.set_orientation(Gtk.Orientation.VERTICAL)

            title_label = Gtk.Label(event.get("e2eventtitle", ""))

            description = Gtk.Label()
            description.set_markup("<i>{}</i>".format(event.get("e2eventdescription", "")))
            description.set_line_wrap(True)
            description.set_max_width_chars(25)

            start = int(event.get("e2eventstart", "0"))
            start_time = datetime.fromtimestamp(start)
            end_time = datetime.fromtimestamp(start + int(event.get("e2eventduration", "0")))
            time_label = Gtk.Label()
            time_label.set_margin_top(5)
            time_str = "{} - {}".format(start_time.strftime("%A, %H:%M"), end_time.strftime("%H:%M"))
            time_label.set_markup("<b>{}</b>".format(time_str))

            self.add(time_label)
            self.add(title_label)
            self.add(description)
            sep = Gtk.Separator()
            sep.set_margin_top(5)
            self.add(sep)
            self.set_spacing(5)

            self.show_all()

    def __init__(self, app, http_api, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._http_api = http_api
        self._settings = settings
        self._update_epg = False
        self._app = app

        handlers = {"on_visible_tool": self.on_visible_tool,
                    "on_volume_changed": self.on_volume_changed,
                    "on_epg_press": self.on_epg_press}

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "control.glade")
        builder.connect_signals(handlers)

        self.add(builder.get_object("main_box"))
        self._screenshot_image = builder.get_object("screenshot_image")
        self._screenshot_button_box = builder.get_object("screenshot_button_box")
        self._screenshot_check_button = builder.get_object("screenshot_check_button")
        self._screenshot_check_button.bind_property("active", self._screenshot_image, "visible")
        self._snr_value_label = builder.get_object("snr_value_label")
        self._ber_value_label = builder.get_object("ber_value_label")
        self._agc_value_label = builder.get_object("agc_value_label")
        self._volume_button = builder.get_object("volume_button")
        self._epg_list_box = builder.get_object("epg_list_box")
        self._timers_list_box = builder.get_object("timers_list_box")
        self._app._control_revealer.bind_property("visible", self, "visible")
        builder.get_object("stack_switcher").set_visible(settings.is_enable_experimental)
        builder.get_object("epg_box").set_visible(settings.is_enable_experimental)

        self.init_actions(app)
        self.connect("hide", self.on_hide)
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

    @property
    def update_epg(self):
        return self._update_epg

    def on_visible_tool(self, stack, param):
        tool = self.Tool(stack.get_visible_child_name())
        self._update_epg = tool is self.Tool.EPG

        if tool is self.Tool.TIMERS:
            self.update_timer_list()

    def on_hide(self, item):
        self._update_epg = False

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

            loader = GdkPixbuf.PixbufLoader.new_with_type("jpeg")
            loader.set_size(280, 165)
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

    # ************************ EPG **************************** #

    def on_service_changed(self, ref):
        self._app._wait_dialog.show()
        self._http_api.send(HttpAPI.Request.EPG, ref, self.update_epg_data)

    @run_idle
    def update_epg_data(self, epg):
        list(map(self._epg_list_box.remove, (r for r in self._epg_list_box)))
        list(map(lambda e: self._epg_list_box.add(self.EpgRow(e)), epg.get("event_list", [])))
        self._app._wait_dialog.hide()

    def on_epg_press(self, list_box: Gtk.ListBox, event: Gdk.EventButton):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS and len(list_box) > 0:
            pass

    # *********************** Timers *************************** #

    def update_timer_list(self):
        self._app._wait_dialog.show()
        self._http_api.send(HttpAPI.Request.TIMER_LIST, "", self.update_timers_data)

    @run_idle
    def update_timers_data(self, timers):
        timers = timers.get("timer_list", [])
        list(map(self._timers_list_box.remove, (r for r in self._timers_list_box)))
        self._app._wait_dialog.hide()

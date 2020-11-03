""" Receiver control module via HTTP API. """
import os

from gi.repository import GLib

from .uicommons import Gtk, UI_RESOURCES_PATH
from ..commons import run_task, run_with_delay, log
from ..connections import HttpRequestType, HttpAPI


class ControlBox(Gtk.HBox):
    def __init__(self, app, http_api, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._http_api = http_api
        self._settings = settings

        handlers = {"on_volume_changed": self.on_volume_changed}

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "control.glade")
        builder.connect_signals(handlers)

        self.add(builder.get_object("main_box"))
        self._screenshot_image = builder.get_object("screenshot_image")
        self._screenshots_button = builder.get_object("screenshots_button")
        self._screenshot_check_button = builder.get_object("screenshot_check_button")
        self._screenshot_check_button.bind_property("active", self._screenshot_image, "visible")
        self._snr_value_label = builder.get_object("snr_value_label")
        self._ber_value_label = builder.get_object("ber_value_label")
        self._agc_value_label = builder.get_object("agc_value_label")
        self._volume_button = builder.get_object("volume_button")
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

        self.show()

    # ***************** Remote controller ********************* #

    def on_remote(self, action, state=False):
        """ Shows/Hides [R key] remote controller. """
        action.set_state(state)
        self._remote_revealer.set_visible(state)
        self._remote_revealer.set_reveal_child(state)

        if state:
            self._http_api.send(HttpRequestType.VOL, "state", self.update_volume)

    def on_remote_action(self, action):
        self._http_api.send(HttpRequestType.REMOTE, action, self.on_response)

    @run_with_delay(0.5)
    def on_volume_changed(self, button, value):
        self._http_api.send(HttpRequestType.VOL, "{:.0f}".format(value), self.on_response)

    def update_volume(self, vol):
        if "error_code" in vol:
            return

        GLib.idle_add(self._volume_button.set_value, int(vol.get("e2current", "0")))

    def on_response(self, resp):
        if "error_code" in resp:
            return

        if self._screenshot_check_button.get_active():
            ref = "mode=all" if self._http_api.is_owif else "d="
            self._http_api.send(HttpRequestType.GRUB, ref, self.update_screenshot)

    @run_task
    def update_screenshot(self, data):
        if "error_code" in data:
            return

        data = data.get("img_data", None)
        if data:
            from gi.repository import GdkPixbuf

            loader = GdkPixbuf.PixbufLoader.new_with_type("jpeg")
            loader.set_size(200, 120)
            loader.write(data)
            pix = loader.get_pixbuf()
            loader.close()
            GLib.idle_add(self._screenshot_image.set_from_pixbuf, pix)

    def on_screenshot_all(self, action, value=None):
        self._http_api.send(HttpRequestType.GRUB, "mode=all" if self._http_api.is_owif else "d=",
                            self.on_screenshot)

    def on_screenshot_video(self, action, value=None):
        self._http_api.send(HttpRequestType.GRUB, "mode=video" if self._http_api.is_owif else "v=",
                            self.on_screenshot)

    def on_screenshot_osd(self, action, value=None):
        self._http_api.send(HttpRequestType.GRUB, "mode=osd" if self._http_api.is_owif else "o=",
                            self.on_screenshot)

    @run_task
    def on_screenshot(self, data):
        if "error_code" in data:
            return

        img = data.get("img_data", None)
        if img:
            is_darwin = self._settings.is_darwin
            GLib.idle_add(self._screenshots_button.set_sensitive, is_darwin)
            path = os.path.expanduser("~/Desktop") if is_darwin else None

            try:
                import tempfile
                import subprocess

                with tempfile.NamedTemporaryFile(mode="wb", suffix=".jpg", dir=path, delete=not is_darwin) as tf:
                    tf.write(img)
                    cmd = ["open" if is_darwin else "xdg-open", tf.name]
                    subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
            finally:
                GLib.idle_add(self._screenshots_button.set_sensitive, True)

    def on_power_action(self, action):
        self._http_api.send(HttpRequestType.POWER, action, lambda resp: log("Power status changed..."))

    def update_signal(self, sig):
        self._snr_value_label.set_text(sig.get("e2snrdb", "0 dB").strip())
        self._ber_value_label.set_text(str(sig.get("e2ber", None) or "0").strip())
        self._agc_value_label.set_text(sig.get("e2acg", "0 %").strip())



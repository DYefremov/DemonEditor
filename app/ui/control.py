""" Receiver control module via HTTP API. """
import os
from datetime import datetime
from enum import Enum
from urllib.parse import quote

from gi.repository import GLib

from .dialogs import get_dialogs_string, show_dialog, DialogType, get_message
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, Column
from ..commons import run_task, run_with_delay, log, run_idle
from ..connections import HttpAPI
from ..eparser.ecommons import BqServiceType


class ControlBox(Gtk.HBox):
    _TIME_STR = "%Y-%m-%d %H:%M"

    class Tool(Enum):
        """ The currently displayed tool. """
        REMOTE = "control"
        EPG = "epg"
        TIMERS = "timers"
        TIMER = "timer"

    class EpgRow(Gtk.ListBoxRow):
        def __init__(self, event: dict, **properties):
            super().__init__(**properties)

            self._event_data = event
            h_box = Gtk.HBox()
            h_box.set_orientation(Gtk.Orientation.VERTICAL)

            self._title = event.get("e2eventtitle", "")
            title_label = Gtk.Label(self._title)

            self._desc = event.get("e2eventdescription", "")
            description = Gtk.Label()
            description.set_markup("<i>{}</i>".format(self._desc))
            description.set_line_wrap(True)
            description.set_max_width_chars(25)

            start = int(event.get("e2eventstart", "0"))
            start_time = datetime.fromtimestamp(start)
            end_time = datetime.fromtimestamp(start + int(event.get("e2eventduration", "0")))
            time_label = Gtk.Label()
            time_label.set_margin_top(5)
            self._time_header = "{} - {}".format(start_time.strftime("%A, %H:%M"), end_time.strftime("%H:%M"))
            time_label.set_markup("<b>{}</b>".format(self._time_header))

            h_box.add(time_label)
            h_box.add(title_label)
            h_box.add(description)
            sep = Gtk.Separator()
            sep.set_margin_top(5)
            h_box.add(sep)
            h_box.set_spacing(5)

            self.add(h_box)
            self.show_all()

        @property
        def event_data(self):
            return self._event_data

        @property
        def title(self):
            return self._title

        @property
        def desc(self):
            return self._desc

        @property
        def time_header(self):
            return self._time_header

    class TimerRow(Gtk.ListBoxRow):

        _UI_PATH = UI_RESOURCES_PATH + "timer_row.glade"

        def __init__(self, timer, **properties):
            super().__init__(**properties)

            self._timer = timer

            builder = Gtk.Builder()
            builder.add_from_string(get_dialogs_string(self._UI_PATH))
            row_box = builder.get_object("timer_row_box")
            name_label = builder.get_object("timer_name_label")
            description_label = builder.get_object("timer_description_label")
            service_name_label = builder.get_object("timer_service_name_label")
            time_label = builder.get_object("timer_time_label")

            name_label.set_text(timer.get("e2name", "") or "")
            description_label.set_text(timer.get("e2description", "") or "")
            service_name_label.set_text(timer.get("e2servicename", "") or "")
            # Time
            start_time = datetime.fromtimestamp(int(timer.get("e2timebegin", "0")))
            end_time = datetime.fromtimestamp(int(timer.get("e2timeend", "0")))
            time_label.set_text("{} - {}".format(start_time.strftime("%A, %H:%M"), end_time.strftime("%H:%M")))

            self.add(row_box)
            self.show()

        @property
        def timer(self):
            return self._timer

    class TimerAction(Enum):
        ADD = 0
        EVENT = 1
        CHANGE = 2

    def __init__(self, app, http_api, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._http_api = http_api
        self._settings = settings
        self._update_epg = False
        self._app = app
        self._last_tool = self.Tool.REMOTE
        self._timer_action = self.TimerAction.ADD
        self._current_timer = {}

        handlers = {"on_visible_tool": self.on_visible_tool,
                    "on_volume_changed": self.on_volume_changed,
                    "on_epg_press": self.on_epg_press,
                    "on_epg_filter_changed": self.on_epg_filter_changed,
                    "on_timers_press": self.on_timers_press,
                    "on_timers_drag_data_received": self.on_timers_drag_data_received}

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "control.glade")
        builder.connect_signals(handlers)

        self.add(builder.get_object("main_box_frame"))
        self._stack = builder.get_object("stack")
        self._screenshot_image = builder.get_object("screenshot_image")
        self._screenshot_button_box = builder.get_object("screenshot_button_box")
        self._screenshot_check_button = builder.get_object("screenshot_check_button")
        self._screenshot_check_button.bind_property("active", self._screenshot_image, "visible")
        self._snr_value_label = builder.get_object("snr_value_label")
        self._ber_value_label = builder.get_object("ber_value_label")
        self._agc_value_label = builder.get_object("agc_value_label")
        self._volume_button = builder.get_object("volume_button")
        self._epg_list_box = builder.get_object("epg_list_box")
        self._epg_list_box.set_filter_func(self.epg_filter_function)
        self._epg_filter_entry = builder.get_object("epg_filter_entry")
        self._timers_list_box = builder.get_object("timers_list_box")
        self._app._control_revealer.bind_property("visible", self, "visible")
        # Timers
        self._timer_remove_button = builder.get_object("timer_remove_button")
        self._timer_remove_button.bind_property("visible", builder.get_object("timer_edit_button"), "visible")
        # Timer
        self._timer_name_entry = builder.get_object("timer_name_entry")
        self._timer_desc_entry = builder.get_object("timer_desc_entry")
        self._timer_service_entry = builder.get_object("timer_service_entry")
        self._timer_service_ref_entry = builder.get_object("timer_service_ref_entry")
        self._timer_event_id_entry = builder.get_object("timer_event_id_entry")
        self._timer_begins_entry = builder.get_object("timer_begins_entry")
        self._timer_ends_entry = builder.get_object("timer_ends_entry")
        self._timer_begins_calendar = builder.get_object("timer_begins_calendar")
        self._timer_begins_hr_button = builder.get_object("timer_begins_hr_button")
        self._timer_begins_min_button = builder.get_object("timer_begins_min_button")
        self._timer_ends_calendar = builder.get_object("timer_ends_calendar")
        self._timer_ends_hr_button = builder.get_object("timer_ends_hr_button")
        self._timer_ends_min_button = builder.get_object("timer_ends_min_button")
        self._timer_enabled_switch = builder.get_object("timer_enabled_switch")
        self._timer_action_combo_box = builder.get_object("timer_action_combo_box")
        self._timer_after_combo_box = builder.get_object("timer_after_combo_box")
        self._timer_mo_check_button = builder.get_object("timer_mo_check_button")
        self._timer_tu_check_button = builder.get_object("timer_tu_check_button")
        self._timer_we_check_button = builder.get_object("timer_we_check_button")
        self._timer_th_check_button = builder.get_object("timer_th_check_button")
        self._timer_fr_check_button = builder.get_object("timer_fr_check_button")
        self._timer_sa_check_button = builder.get_object("timer_sa_check_button")
        self._timer_su_check_button = builder.get_object("timer_su_check_button")
        self._timer_location_switch = builder.get_object("timer_location_switch")
        self._timer_location_entry = builder.get_object("timer_location_entry")
        self._timer_location_switch.bind_property("active", self._timer_location_entry, "sensitive")
        # Disable DnD for timer entries.
        self._timer_name_entry.drag_dest_unset()
        self._timer_desc_entry.drag_dest_unset()
        self._timer_service_entry.drag_dest_unset()
        # DnD initialization for the timer list.
        self._timers_list_box.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.DEFAULT | Gdk.DragAction.COPY)
        self._timers_list_box.drag_dest_add_text_targets()

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
        # Timers
        app.set_action("on_timer_add", self.on_timer_add)
        app.set_action("on_timer_add_from_event", self.on_timer_add_from_event)
        app.set_action("on_timer_remove", self.on_timer_remove)
        app.set_action("on_timer_edit", self.on_timer_edit)
        app.set_action("on_timer_save", self.on_timer_save)
        app.set_action("on_timer_cancel", self.on_timer_cancel)
        app.set_action("on_timer_begins_set", self.on_timer_begins_set)
        app.set_action("on_timer_ends_set", self.on_timer_ends_set)

    @property
    def update_epg(self):
        return self._update_epg

    def on_visible_tool(self, stack, param):
        tool = self.Tool(stack.get_visible_child_name())
        self._update_epg = tool is self.Tool.EPG

        if tool is self.Tool.TIMERS:
            self.update_timer_list()

        if tool is not self.Tool.TIMER:
            self._last_tool = tool

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

    def on_epg_press(self, list_box, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS and len(list_box) > 0:
            row = list_box.get_selected_row()
            if row:
                self.set_timer_from_event_data(row.event_data)

    def on_epg_filter_changed(self, entry):
        self._epg_list_box.invalidate_filter()

    def epg_filter_function(self, row: EpgRow):
        txt = self._epg_filter_entry.get_text().upper()
        return any((not txt, txt in row.time_header.upper(), txt in row.title.upper(), txt in row.desc.upper()))

    def on_timer_add_from_event(self, action, value=None):
        rows = self._epg_list_box.get_selected_rows()
        if not rows:
            self._app.show_error_dialog("No selected item!")
            return

        refs = []
        for row in rows:
            event = row.event_data
            ref = "timeraddbyeventid?sRef={}&eventid={}&justplay=0".format(event.get("e2eventservicereference", ""),
                                                                           event.get("e2eventid", ""))
            refs.append(ref)

        gen = self.write_timers_list(refs)
        GLib.idle_add(lambda: next(gen, False))

    def write_timers_list(self, refs):
        self._app._wait_dialog.show()
        tasks = list(refs)
        for ref in refs:
            self._http_api.send(HttpAPI.Request.TIMER, ref, lambda x: tasks.pop())
            yield True

        while tasks:
            yield True

        self._stack.set_visible_child_name(self.Tool.TIMERS.value)

    # *********************** Timers *************************** #

    def on_timers_press(self, list_box, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS and len(list_box) > 0:
            self.on_timer_edit()

    def update_timer_list(self):
        self._app._wait_dialog.show()
        self._http_api.send(HttpAPI.Request.TIMER_LIST, "", self.update_timers_data)

    @run_idle
    def update_timers_data(self, timers):
        list(map(self._timers_list_box.remove, (r for r in self._timers_list_box)))
        list(map(lambda t: self._timers_list_box.add(self.TimerRow(t)), timers.get("timer_list", [])))
        self._timer_remove_button.set_visible(len(self._timers_list_box))
        self._app._wait_dialog.hide()

    def on_timer_add(self, action=None, value=None):
        self._timer_action = self.TimerAction.ADD
        date = datetime.now()
        self.set_begins_date(date)
        self.set_ends_date(date)
        self._timer_event_id_entry.set_text("")
        self._timer_location_switch.set_active(False)
        self.set_repetition_flags(0)
        self._stack.set_visible_child_name(self.Tool.TIMER.value)

    def on_timer_remove(self, action, value=None):
        rows = self._timers_list_box.get_selected_rows()
        if not rows or show_dialog(DialogType.QUESTION, self._app._main_window) != Gtk.ResponseType.OK:
            return

        refs = {}
        for row in rows:
            timer = row.timer
            ref = "timerdelete?sRef={}&begin={}&end={}".format(timer.get("e2servicereference", ""),
                                                               timer.get("e2timebegin", ""),
                                                               timer.get("e2timeend", ""))
            refs[ref] = row

        self._app._wait_dialog.show("Deleting data...")
        gen = self.remove_timers(refs)
        GLib.idle_add(lambda: next(gen, False))

    def remove_timers(self, refs):
        tasks = list(refs)
        removed = set()
        for ref in refs:
            yield from self.remove_timer(ref, removed, tasks)

        while tasks:
            yield True

        list(map(self._timers_list_box.remove, (refs[ref] for ref in refs if ref in removed)))
        self._app._wait_dialog.hide()
        self._timer_remove_button.set_visible(len(self._timers_list_box))
        yield True

    def remove_timer(self, ref, removed, tasks=None):
        def callback(resp):
            if resp.get("e2state", "") == "True":
                log(resp.get("e2statetext", ""))
                removed.add(ref)
            else:
                log(resp.get("e2statetext", None) or "Timer deletion error.")
            if tasks:
                tasks.pop()

        self._http_api.send(HttpAPI.Request.TIMER, ref, callback)
        yield True

    def on_timer_edit(self, action=None, value=None):
        row = self._timers_list_box.get_selected_row()
        if row:
            self._timer_action = self.TimerAction.CHANGE

            timer = row.timer
            self._current_timer = timer
            self._timer_name_entry.set_text(timer.get("e2name", ""))
            self._timer_desc_entry.set_text(timer.get("e2description", "") or "")
            self._timer_service_entry.set_text(timer.get("e2servicename", "") or "")
            self._timer_service_ref_entry.set_text(timer.get("e2servicereference", ""))
            self._timer_event_id_entry.set_text(timer.get("e2eit", ""))
            self._timer_enabled_switch.set_active((timer.get("e2disabled", "0") == "0"))
            self._timer_action_combo_box.set_active_id(timer.get("e2justplay", "0"))
            self._timer_after_combo_box.set_active_id(timer.get("e2afterevent", "0"))
            self.set_time_data(int(timer.get("e2timebegin", "0")), int(timer.get("e2timeend", "0")))
            location = timer.get("e2location", "")
            self._timer_location_entry.set_text("" if location == "None" else location)
            # Days
            self.set_repetition_flags(int(timer.get("e2repeated", "0")))
            self._stack.set_visible_child_name(self.Tool.TIMER.value)

    def on_timer_save(self, action, value=None):
        args = []
        t_data = self.get_timer_data()
        s_ref = t_data.get("sRef", "")

        if self._timer_action is self.TimerAction.EVENT:
            args.append("timeraddbyeventid?sRef={}".format(s_ref))
            args.append("eventid={}".format(t_data.get("eit", "0")))
            args.append("justplay={}".format(t_data.get("justplay", "")))
            args.append("tags={}".format(""))
        else:
            if self._timer_action is self.TimerAction.ADD:
                args.append("timeradd?sRef={}".format(s_ref))
                args.append("deleteOldOnSave={}".format(0))
            elif self._timer_action is self.TimerAction.CHANGE:
                args.append("timerchange?sRef={}".format(s_ref))
                args.append("channelOld={}".format(s_ref))
                args.append("beginOld={}".format(self._current_timer.get("e2timebegin", "0")))
                args.append("endOld={}".format(self._current_timer.get("e2timeend", "0")))
                args.append("deleteOldOnSave={}".format(1))

            args.append("begin={}".format(t_data.get("begin", "")))
            args.append("end={}".format(t_data.get("end", "")))
            args.append("name={}".format(quote(t_data.get("name", ""))))
            args.append("description={}".format(quote(t_data.get("description", ""))))
            args.append("tags={}".format(""))
            args.append("eit={}".format("0"))
            args.append("disabled={}".format(t_data.get("disabled", "1")))
            args.append("justplay={}".format(t_data.get("justplay", "1")))
            args.append("afterevent={}".format(t_data.get("afterevent", "0")))
            args.append("repeated={}".format(self.get_repetition_flags()))

            if self._timer_location_switch.get_active():
                args.append("dirname={}".format(self._timer_location_entry.get_text()))

        self._http_api.send(HttpAPI.Request.TIMER, "&".join(args), self.timer_add_edit_callback)

    @run_idle
    def timer_add_edit_callback(self, resp):
        if "error_code" in resp:
            msg = "Error getting timer status.\n{}".format(resp.get("error_code"))
            self._app.show_error_dialog(msg)
            log(msg)
            return

        state = resp.get("e2state", None)
        if state == "False":
            msg = resp.get("e2statetext", "")
            self._app.show_error_dialog(msg)
            log(msg)
        if state == "True":
            log(resp.get("e2statetext", ""))
            self._stack.set_visible_child_name(self._last_tool.value)
        else:
            log("Error getting timer status. No response!")

    def on_timer_cancel(self, action, value=None):
        self._stack.set_visible_child_name(self._last_tool.value)

    def on_timer_begins_set(self, action, value=None):
        self.set_begins_date(self.get_begins_date())

    def on_timer_ends_set(self, action, value=None):
        self.set_ends_date(self.get_ends_date())

    def get_begins_date(self):
        date = self._timer_begins_calendar.get_date()
        return datetime(year=date.year, month=date.month + 1, day=date.day,
                        hour=int(self._timer_begins_hr_button.get_value()),
                        minute=int(self._timer_begins_min_button.get_value()))

    def set_begins_date(self, date):
        hour = date.hour
        minute = date.minute
        self._timer_begins_hr_button.set_value(hour)
        self._timer_begins_min_button.set_value(minute)
        self._timer_begins_calendar.select_day(date.day)
        self._timer_begins_calendar.select_month(date.month - 1, date.year)
        self._timer_begins_entry.set_text("{}-{}-{} {}:{:02d}".format(date.year, date.month, date.day, hour, minute))

    def get_ends_date(self):
        date = self._timer_ends_calendar.get_date()
        return datetime(year=date.year, month=date.month + 1, day=date.day,
                        hour=int(self._timer_ends_hr_button.get_value()),
                        minute=int(self._timer_ends_min_button.get_value()))

    def set_ends_date(self, date):
        hour = date.hour
        minute = date.minute
        self._timer_ends_hr_button.set_value(hour)
        self._timer_ends_min_button.set_value(minute)
        self._timer_ends_calendar.select_day(date.day)
        self._timer_ends_calendar.select_month(date.month - 1, date.year)
        self._timer_ends_entry.set_text("{}-{}-{} {}:{:02d}".format(date.year, date.month, date.day, hour, minute))

    def set_timer_from_event_data(self, timer):
        self._stack.set_visible_child_name(self.Tool.TIMER.value)
        self._timer_action = self.TimerAction.EVENT
        self._timer_name_entry.set_text(timer.get("e2eventtitle", ""))
        self._timer_desc_entry.set_text(timer.get("e2eventdescription", ""))
        self._timer_service_entry.set_text(timer.get("e2eventservicename", ""))
        self._timer_service_ref_entry.set_text(timer.get("e2eventservicereference", ""))
        self._timer_event_id_entry.set_text(timer.get("e2eventid", ""))
        self._timer_action_combo_box.set_active_id("1")
        self._timer_after_combo_box.set_active_id("3")
        start_time = int(timer.get("e2eventstart", "0"))
        self.set_time_data(start_time, start_time + int(timer.get("e2eventduration", "0")))

    def set_time_data(self, start_time, end_time):
        """ Sets values for time widgets. """
        ev_time_start = datetime.fromtimestamp(start_time) or datetime.now()
        ev_time_end = datetime.fromtimestamp(end_time) or datetime.now()
        self._timer_begins_entry.set_text(ev_time_start.strftime(self._TIME_STR))
        self._timer_ends_entry.set_text(ev_time_end.strftime(self._TIME_STR))
        self._timer_begins_calendar.select_day(ev_time_start.day)
        self._timer_begins_calendar.select_month(ev_time_start.month - 1, ev_time_start.year)
        self._timer_ends_calendar.select_day(ev_time_end.day)
        self._timer_ends_calendar.select_month(ev_time_end.month - 1, ev_time_end.year)
        self._timer_begins_hr_button.set_value(ev_time_start.hour)
        self._timer_begins_min_button.set_value(ev_time_start.minute)
        self._timer_ends_hr_button.set_value(ev_time_end.hour)
        self._timer_ends_min_button.set_value(ev_time_end.minute)

    def get_timer_data(self):
        """ Returns timer data as a dict. """
        return {"sRef": self._timer_service_ref_entry.get_text(),
                "begin": int(datetime.strptime(self._timer_begins_entry.get_text(), self._TIME_STR).timestamp()),
                "end": int(datetime.strptime(self._timer_ends_entry.get_text(), self._TIME_STR).timestamp()),
                "name": self._timer_name_entry.get_text(),
                "description": self._timer_desc_entry.get_text(),
                "dirname": "",
                "eit": self._timer_event_id_entry.get_text(),
                "disabled": int(not self._timer_enabled_switch.get_active()),
                "justplay": self._timer_action_combo_box.get_active_id(),
                "afterevent": self._timer_after_combo_box.get_active_id(),
                "repeated": self.get_repetition_flags()}

    def get_repetition_flags(self):
        """ Returns flags for repetition. """
        day_flags = 0
        for i, box in enumerate((self._timer_mo_check_button,
                                 self._timer_tu_check_button,
                                 self._timer_we_check_button,
                                 self._timer_th_check_button,
                                 self._timer_fr_check_button,
                                 self._timer_sa_check_button,
                                 self._timer_su_check_button)):

            if box.get_active():
                day_flags = day_flags | (1 << i)

        return day_flags

    def set_repetition_flags(self, flags):
        for i, box in enumerate((self._timer_mo_check_button,
                                 self._timer_tu_check_button,
                                 self._timer_we_check_button,
                                 self._timer_th_check_button,
                                 self._timer_fr_check_button,
                                 self._timer_sa_check_button,
                                 self._timer_su_check_button)):
            box.set_active(flags & 1 == 1)
            flags = flags >> 1

    # ***************** Drag-and-drop ********************* #

    def on_timers_drag_data_received(self, box, context, x, y, data, info, time):
        txt = data.get_text()
        if txt:
            itr_str, sep, source = txt.partition(self._app.DRAG_SEP)
            if not source:
                return

            itrs = itr_str.split(",")
            if len(itrs) > 1:
                self._app.show_error_dialog("Please, select only one item!")
                return

            fav_id = None
            if source == self._app.FAV_MODEL_NAME:
                model = self._app.fav_view.get_model()
                fav_id = model.get_value(model.get_iter_from_string(itrs[0]), Column.FAV_ID)
            elif source == self._app.SERVICE_MODEL_NAME:
                model = self._app.services_view.get_model()
                fav_id = model.get_value(model.get_iter_from_string(itrs[0]), Column.SRV_FAV_ID)

            service = self._app.current_services.get(fav_id, None)
            if service:
                if service.service_type == BqServiceType.ALT.name:
                    msg = "Alternative service.\n\n {}".format(get_message("Not implemented yet!"))
                    show_dialog(DialogType.ERROR, transient=self._app._main_window, text=msg)
                    context.finish(False, False, time)
                    return

                self._timer_name_entry.set_text(service.service)
                self._timer_service_entry.set_text(service.service)
                self._timer_service_ref_entry.set_text(service.picon_id.rstrip(".png").replace("_", ":"))
                self.on_timer_add()
            context.finish(True, False, time)

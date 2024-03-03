# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2024 Dmitriy Yefremov
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


""" Module for working with timers. """
from datetime import datetime, timedelta
from enum import Enum
from urllib.parse import quote

from app.ui.main_helper import on_popup_menu
from .dialogs import get_builder, translate, show_dialog, DialogType, BaseDialog
from .uicommons import Gtk, Gdk, GLib, UI_RESOURCES_PATH, Page, Column, KeyboardKey, MOD_MASK
from ..commons import run_idle, log
from ..connections import HttpAPI
from ..eparser.ecommons import BqServiceType


class TimerTool(Gtk.Box):
    TIME_STR = "%Y-%m-%d %H:%M"

    ACTION = {"0": "Record", "1": "Zap"}

    AFTER_EVENT = {"0": "Do Nothing",
                   "1": "Standby",
                   "2": "Shut down",
                   "3": "Auto"}

    class TimerAction(Enum):
        ADD = 0
        EVENT = 1
        CHANGE = 2

    class TimerDialog(BaseDialog):
        def __init__(self, parent, action=None, timer_data=None, *args, **kwargs):
            super().__init__(parent=parent, title="Timer",
                             buttons=(translate("Cancel"), Gtk.ResponseType.CANCEL,
                                      translate("Save"), Gtk.ResponseType.OK), *args, **kwargs)

            self._action = action or TimerTool.TimerAction.ADD
            self._timer_data = timer_data or {}
            self._request = ""

            handlers = {"on_timer_begins_set": self.on_timer_begins_set,
                        "on_timer_ends_set": self.on_timer_ends_set}

            builder = get_builder(f"{UI_RESOURCES_PATH}timers.glade", handlers,
                                  objects=("timer_dialog_frame", "timer_ends_popover", "end_hour_adjustment",
                                           "min_end_adjustment", "timer_begins_popover", "begins_hour_adjustment",
                                           "min_begins_adjustment"))

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
            self._days_buttons = (builder.get_object("timer_mo_check_button"),
                                  builder.get_object("timer_tu_check_button"),
                                  builder.get_object("timer_we_check_button"),
                                  builder.get_object("timer_th_check_button"),
                                  builder.get_object("timer_fr_check_button"),
                                  builder.get_object("timer_sa_check_button"),
                                  builder.get_object("timer_su_check_button"))

            self._timer_location_switch = builder.get_object("timer_location_switch")
            self._timer_location_entry = builder.get_object("timer_location_entry")
            self._timer_location_switch.bind_property("active", self._timer_location_entry, "sensitive")
            # Disable DnD for timer entries.
            self._timer_name_entry.drag_dest_unset()
            self._timer_desc_entry.drag_dest_unset()
            self._timer_service_entry.drag_dest_unset()

            self.get_content_area().pack_start(builder.get_object("timer_dialog_frame"), True, True, 0)

            if self._action is TimerTool.TimerAction.ADD:
                self.set_timer_for_add()
            elif self._action is TimerTool.TimerAction.CHANGE:
                self.set_timer_for_edit()
            elif self._action is TimerTool.TimerAction.EVENT:
                self.set_timer_from_event_data()
            else:
                log(f"{__class__.__name__} error: No action set for timer!")

        @property
        def request(self):
            return self._request

        def run(self):
            resp = super().run()
            if resp == Gtk.ResponseType.OK:
                self._request = self.get_request()
            return resp

        def get_request(self):
            """ Constructs str representation of add/update request. """
            args = []
            t_data = self.get_timer_data()
            s_ref = quote(t_data.get("sRef", ""))

            if self._action is TimerTool.TimerAction.EVENT:
                args.append(f"timeraddbyeventid?sRef={s_ref}")
                args.append(f"eventid={t_data.get('eit', '0')}")
                args.append(f"justplay={t_data.get('justplay', '')}")
                args.append(f"tags={''}")
            else:
                if self._action is TimerTool.TimerAction.ADD:
                    args.append(f"timeradd?sRef={s_ref}")
                    args.append(f"deleteOldOnSave={0}")
                elif self._action is TimerTool.TimerAction.CHANGE:
                    args.append(f"timerchange?sRef={s_ref}")
                    args.append(f"channelOld={s_ref}")
                    args.append(f"beginOld={self._timer_data.get('e2timebegin', '0')}")
                    args.append(f"endOld={self._timer_data.get('e2timeend', '0')}")
                    args.append(f"deleteOldOnSave={1}")

                args.append(f"begin={t_data.get('begin', '')}")
                args.append(f"end={t_data.get('end', '')}")
                args.append(f"name={quote(t_data.get('name', ''))}")
                args.append(f"description={quote(t_data.get('description', ''))}")
                args.append(f"tags={''}")
                args.append(f"eit={'0'}")
                args.append(f"disabled={t_data.get('disabled', '1')}")
                args.append(f"justplay={t_data.get('justplay', '1')}")
                args.append(f"afterevent={t_data.get('afterevent', '0')}")
                args.append(f"repeated={TimerTool.get_repetition_flags(self._days_buttons)}")

                if self._timer_location_switch.get_active():
                    args.append(f"dirname={self._timer_location_entry.get_text()}")

            return "&".join(args)

        def on_timer_begins_set(self, action, value=None):
            b_date = self.get_begins_date()
            if b_date > self.get_ends_date():
                self.set_ends_date(b_date + timedelta(hours=1))
            self.set_begins_date(b_date)

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
            self._timer_begins_entry.set_text(f"{date.year}-{date.month:02d}-{date.day:02d} {hour:02d}:{minute:02d}")

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
            self._timer_ends_entry.set_text(f"{date.year}-{date.month:02d}-{date.day:02d} {hour:02d}:{minute:02d}")

        def set_timer_for_add(self):
            self._timer_service_entry.set_text(self._timer_data.get("e2servicename", ""))
            self._timer_service_ref_entry.set_text(self._timer_data.get("e2servicereference", ""))
            date = datetime.now()
            self.set_begins_date(date)
            self.set_ends_date(date + timedelta(hours=1))
            self._timer_event_id_entry.set_text("")
            self._timer_location_switch.set_active(False)
            TimerTool.set_repetition_flags(0, self._days_buttons)

        def set_timer_for_edit(self):
            self._timer_name_entry.set_text(self._timer_data.get("e2name", ""))
            self._timer_desc_entry.set_text(self._timer_data.get("e2description", "") or "")
            self._timer_service_entry.set_text(self._timer_data.get("e2servicename", "") or "")
            self._timer_service_ref_entry.set_text(self._timer_data.get("e2servicereference", ""))
            self._timer_event_id_entry.set_text(self._timer_data.get("e2eit", ""))
            self._timer_enabled_switch.set_active((self._timer_data.get("e2disabled", "0") == "0"))
            self._timer_action_combo_box.set_active_id(self._timer_data.get("e2justplay", "0"))
            self._timer_after_combo_box.set_active_id(self._timer_data.get("e2afterevent", "0"))
            self.set_time_data(int(self._timer_data.get("e2timebegin", "0")),
                               int(self._timer_data.get("e2timeend", "0")))
            location = self._timer_data.get("e2location", "")
            self._timer_location_entry.set_text("" if location == "None" else location)
            TimerTool.set_repetition_flags(int(self._timer_data.get("e2repeated", "0")), self._days_buttons)

        def set_timer_from_event_data(self):
            self._timer_name_entry.set_text(self._timer_data.get("e2eventtitle", None) or "")
            self._timer_desc_entry.set_text(self._timer_data.get("e2eventdescription", None) or "")
            self._timer_service_entry.set_text(self._timer_data.get("e2eventservicename", None) or "")
            self._timer_service_ref_entry.set_text(self._timer_data.get("e2eventservicereference", None) or "")
            self._timer_event_id_entry.set_text(self._timer_data.get("e2eventid", None) or "")
            self._timer_action_combo_box.set_active_id("1")
            self._timer_after_combo_box.set_active_id("3")
            start_time = int(self._timer_data.get("e2eventstart", "0") or "0")
            self.set_time_data(start_time, start_time + int(self._timer_data.get("e2eventduration", "0") or "0"))

        def set_time_data(self, start_time, end_time):
            """ Sets values for time widgets. """
            now = datetime.now()
            ev_time_start = datetime.fromtimestamp(start_time) or now
            ev_time_end = datetime.fromtimestamp(end_time) or now + timedelta(hours=1)
            self._timer_begins_entry.set_text(ev_time_start.strftime(TimerTool.TIME_STR))
            self._timer_ends_entry.set_text(ev_time_end.strftime(TimerTool.TIME_STR))
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
                    "begin": int(
                        datetime.strptime(self._timer_begins_entry.get_text(), TimerTool.TIME_STR).timestamp()),
                    "end": int(datetime.strptime(self._timer_ends_entry.get_text(), TimerTool.TIME_STR).timestamp()),
                    "name": self._timer_name_entry.get_text(),
                    "description": self._timer_desc_entry.get_text(),
                    "dirname": "",
                    "eit": self._timer_event_id_entry.get_text(),
                    "disabled": int(not self._timer_enabled_switch.get_active()),
                    "justplay": self._timer_action_combo_box.get_active_id(),
                    "afterevent": self._timer_after_combo_box.get_active_id(),
                    "repeated": TimerTool.get_repetition_flags(self._days_buttons)}

    def __init__(self, app, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._app = app
        self._app.connect("page-changed", self.update_timer_list)
        # Icon.
        theme = Gtk.IconTheme.get_default()
        icon = "alarm-symbolic"
        self._icon = theme.load_icon(icon, 16, 0) if theme.lookup_icon(icon, 16, 0) else None

        handlers = {"on_timer_add": self.on_timer_add,
                    "on_timer_edit": self.on_timer_edit,
                    "on_timer_remove": self.on_timer_remove,
                    "on_model_changed": self.on_model_changed,
                    "on_timers_press": self.on_timers_press,
                    "on_timers_key_release": self.on_timers_key_release,
                    "on_timer_cursor_changed": self.on_timer_cursor_changed,
                    "on_timers_drag_data_received": self.on_timers_drag_data_received}

        builder = get_builder(f"{UI_RESOURCES_PATH}timers.glade", handlers,
                              objects=("timers_frame", "timer_model", "popup_menu", "popup_menu_add_image"))

        self._view = builder.get_object("timer_view")
        self._remove_button = builder.get_object("timer_remove_button")
        self._remove_button.bind_property("sensitive", builder.get_object("timer_edit_button"), "sensitive")
        self._remove_button.bind_property("sensitive", builder.get_object("edit_menu_item"), "sensitive")
        self._remove_button.bind_property("sensitive", builder.get_object("remove_menu_item"), "sensitive")
        self._info_button = builder.get_object("timer_info_check_button")
        self._info_button.bind_property("active", builder.get_object("timer_info_frame"), "visible")
        self._info_enabled_switch = builder.get_object("timer_info_enabled_switch")
        self._timers_count_label = builder.get_object("timers_count_label")
        self._ref_info_label = builder.get_object("timer_ref_value_label")
        self._event_id_info_label = builder.get_object("timer_event_id_value_label")
        self._begins_info_label = builder.get_object("timer_begins_value_label")
        self._ends_info_label = builder.get_object("timer_ends_value_label")
        self._action_info_label = builder.get_object("timer_action_value_label")
        self._after_info_label = builder.get_object("timer_after_value_label")
        self._timer_location_switch = builder.get_object("timer_location_switch")
        self._info_location_entry = builder.get_object("timer_info_location_entry")
        self._days_buttons = (builder.get_object("timer_info_mo_check_button"),
                              builder.get_object("timer_info_tu_check_button"),
                              builder.get_object("timer_info_we_check_button"),
                              builder.get_object("timer_info_th_check_button"),
                              builder.get_object("timer_info_fr_check_button"),
                              builder.get_object("timer_info_sa_check_button"),
                              builder.get_object("timer_info_su_check_button"))
        # Disable button presses.
        list(map(lambda b: b.connect("button-press-event", lambda bx, e: True), self._days_buttons))
        self._info_enabled_switch.connect("button-press-event", lambda b, e: True)
        # DnD initialization for the timer list.
        self._view.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.DEFAULT | Gdk.DragAction.COPY)
        self._view.drag_dest_add_text_targets()

        self.pack_start(builder.get_object("timers_frame"), True, True, 0)
        self.show()

    def update_timer_list(self, app, page):
        if page is Page.TIMERS:
            self._app.wait_dialog.show()
            self._app.send_http_request(HttpAPI.Request.TIMER_LIST, "", self.update_timers_data)

    @run_idle
    def update_timers_data(self, timers):
        model = self._view.get_model()
        model.clear()
        list(map(model.append, (self.get_timer_row(t) for t in timers.get("timer_list", []))))
        self._remove_button.set_sensitive(len(model))
        self._app.wait_dialog.hide()

    def get_timer_row(self, timer):
        disabled = self._icon if timer.get("e2disabled", "0") == "0" else None
        name = timer.get("e2name", "") or ""
        description = timer.get("e2description", "") or ""
        service = timer.get("e2servicename", "") or ""
        start_time = datetime.fromtimestamp(int(timer.get("e2timebegin", "0")))
        end_time = datetime.fromtimestamp(int(timer.get("e2timeend", "0")))
        time = f"{start_time.strftime('%a, %x, %H:%M')} - {end_time.strftime('%H:%M')}"

        return disabled, name, service, time, description, timer

    def on_timer_add(self, timer=None, value=None):
        model, paths = self._app.fav_view.get_selection().get_selected_rows()
        p_count = len(paths)

        if p_count == 1:
            service = self._app.current_services.get(model[paths][Column.FAV_ID], None)
            if service:
                self.add_timer({"e2servicename": service.service,
                                "e2servicereference": service.picon_id.rstrip(".png").replace("_", ":")})
        elif p_count > 1:
            self._app.show_error_message("Please, select only one item!")
        else:
            self._app.show_error_message("No selected item!")

    def add_timer(self, timer_data):
        dialog = self.TimerDialog(self._app.app_window, self.TimerAction.ADD, timer_data)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self._app.send_http_request(HttpAPI.Request.TIMER, dialog.request, self.timer_add_edit_callback)
        dialog.destroy()

    def on_timer_edit(self, action=None, value=None):
        model, paths = self._view.get_selection().get_selected_rows()
        if len(paths) > 1:
            self._app.show_error_message("Please, select only one item!")
            return

        dialog = self.TimerDialog(self._app.app_window, self.TimerAction.CHANGE, model[paths][-1])
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self._app.send_http_request(HttpAPI.Request.TIMER, dialog.request, self.timer_add_edit_callback)
        dialog.destroy()

    @run_idle
    def timer_add_edit_callback(self, resp):
        if "error_code" in resp:
            msg = f"Error getting timer status.\n{resp.get('error_code')}"
            self._app.show_error_message(msg)
            log(msg)
            return

        state = resp.get("e2state", None)
        if state == "False":
            msg = resp.get("e2statetext", "")
            self._app.show_error_message(msg)
            log(msg)
        if state == "True":
            msg = resp.get("e2statetext", "")
            log(msg)
            self._app.show_info_message(msg, Gtk.MessageType.INFO)
            self.update_timer_list(self._app, Page.TIMERS)
        else:
            log("Error getting timer status. No response!")

    def on_timer_remove(self, action=None, value=None):
        model, paths = self._view.get_selection().get_selected_rows()
        if not paths or show_dialog(DialogType.QUESTION, self._app.app_window) != Gtk.ResponseType.OK:
            return

        refs = {}
        for path in paths:
            timer = model[path][-1]
            ref = "timerdelete?sRef={}&begin={}&end={}".format(quote(timer.get("e2servicereference", "")),
                                                               timer.get("e2timebegin", ""),
                                                               timer.get("e2timeend", ""))
            refs[ref] = model.get_iter(path)

        self._app.wait_dialog.show("Deleting data...")
        gen = self.remove_timers(refs)
        GLib.idle_add(lambda: next(gen, False))

    def remove_timers(self, refs):
        tasks = list(refs)
        removed = set()
        for ref in refs:
            yield from self.remove_timer(ref, removed, tasks)

        while tasks:
            yield True

        model = self._view.get_model()
        list(map(model.remove, (refs[ref] for ref in refs if ref in removed)))
        self._app.wait_dialog.hide()
        self._remove_button.set_sensitive(len(model))
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

        self._app.send_http_request(HttpAPI.Request.TIMER, ref, callback)
        yield True

    def on_model_changed(self, model, path, itr=None):
        self._timers_count_label.set_text(str(len(model)))

    def on_timers_press(self, menu, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS and len(self._view.get_model()) > 0:
            self.on_timer_edit()
        else:
            on_popup_menu(menu, event)

    def on_timers_key_release(self, view, event):
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK

        if key is KeyboardKey.DELETE:
            self.on_timer_remove()
        elif ctrl and key is KeyboardKey.E:
            self.on_timer_edit()
        elif ctrl and key is KeyboardKey.INSERT:
            self.on_timer_add()

    def on_timer_cursor_changed(self, view):
        path, column = view.get_cursor()
        if not path:
            return

        timer = view.get_model()[path][-1]
        self._info_enabled_switch.set_active((timer.get("e2disabled", "0") == "0"))
        self._ref_info_label.set_text(timer.get("e2servicereference", ""))
        self._event_id_info_label.set_text(timer.get("e2eit", ""))
        self._action_info_label.set_text(translate(self.ACTION.get(timer.get("e2justplay", "0"), "0")))
        self._after_info_label.set_text(translate(self.AFTER_EVENT.get(timer.get("e2afterevent", "0"), "0")))
        self._begins_info_label.set_text(str(datetime.fromtimestamp(int(timer.get("e2timebegin", "0")))))
        self._ends_info_label.set_text(str(datetime.fromtimestamp(int(timer.get("e2timeend", "0")))))
        self.set_repetition_flags(int(timer.get("e2repeated", "0")), self._days_buttons)
        location = timer.get("e2location", "")
        self._info_location_entry.set_text("" if location == "None" else location)

    @staticmethod
    def get_repetition_flags(boxes):
        """ Returns flags for repetition.

             @param boxes: Buttons tuple for the days of the week.
         """
        day_flags = 0
        for i, box in enumerate(boxes):
            if box.get_active():
                day_flags = day_flags | (1 << i)

        return day_flags

    @staticmethod
    def set_repetition_flags(flags, boxes):
        """ Sets flags for repetition.

            @param flags: Flags value.
            @param boxes: Buttons tuple for the days of the week.
        """
        for i, box in enumerate(boxes):
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
                self._app.show_error_message("Please, select only one item!")
                return

            fav_id = None
            if source == self._app.FAV_MODEL:
                model = self._app.fav_view.get_model()
                fav_id = model.get_value(model.get_iter_from_string(itrs[0]), Column.FAV_ID)
            elif source == self._app.SERVICE_MODEL:
                model = self._app.services_view.get_model()
                fav_id = model.get_value(model.get_iter_from_string(itrs[0]), Column.SRV_FAV_ID)

            service = self._app.current_services.get(fav_id, None)
            if service:
                if service.service_type == BqServiceType.ALT.name:
                    msg = "Alternative service.\n\n {get_message('Not implemented yet!')}"
                    show_dialog(DialogType.ERROR, transient=self._app.app_window, text=msg)
                    context.finish(False, False, time)
                    return

                self.add_timer({"e2servicename": service.service,
                                "e2servicereference": service.picon_id.rstrip(".png").replace("_", ":")})

            context.finish(True, False, time)


if __name__ == "__main__":
    pass

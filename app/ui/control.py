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
from enum import Enum
from ftplib import all_errors
from urllib.parse import quote

from gi.repository import GLib

from .dialogs import get_builder, show_dialog, DialogType, get_message
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, Page, Column, KeyboardKey, IS_GNOME_SESSION
from ..commons import run_task, run_with_delay, log, run_idle
from ..connections import HttpAPI, UtfFTP
from ..eparser.ecommons import BqServiceType
from ..settings import IS_DARWIN, PlayStreamsMode, IS_LINUX, IS_WIN


class EpgTool(Gtk.Box):
    def __init__(self, app, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._app = app
        self._app.connect("fav-changed", self.on_service_changed)

        handlers = {"on_epg_press": self.on_epg_press,
                    "on_timer_add": self.on_timer_add,
                    "on_epg_filter_changed": self.on_epg_filter_changed,
                    "on_epg_filter_toggled": self.on_epg_filter_toggled}

        builder = get_builder(UI_RESOURCES_PATH + "control.glade", handlers,
                              objects=("epg_frame", "epg_model", "epg_filter_model", "epg_sort_model"))
        self._view = builder.get_object("epg_view")
        self._model = builder.get_object("epg_model")
        self._filter_model = builder.get_object("epg_filter_model")
        self._filter_model.set_visible_func(self.epg_filter_function)
        self._filter_entry = builder.get_object("epg_filter_entry")
        builder.get_object("epg_filter_button").bind_property("active", self._filter_entry, "visible")
        self.pack_start(builder.get_object("epg_frame"), True, True, 0)
        self.show()

    def on_timer_add(self, action=None, value=None):
        model, paths = self._view.get_selection().get_selected_rows()
        p_count = len(paths)

        if p_count == 1:
            dialog = TimerTool.TimerDialog(self._app.app_window, TimerTool.TimerAction.EVENT, model[paths][-1])
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                gen = self.write_timers_list([dialog.get_request()])
                GLib.idle_add(lambda: next(gen, False))
            dialog.destroy()
        elif p_count > 1:
            if show_dialog(DialogType.QUESTION, self._app.app_window,
                           "Add timers for selected events?") != Gtk.ResponseType.OK:
                return True

            self.add_timers_list((model[p][-1] for p in paths))
        else:
            self._app.show_error_message("No selected item!")

    def add_timers_list(self, paths):
        ref_str = "timeraddbyeventid?sRef={}&eventid={}&justplay=0"
        refs = [ref_str.format(ev.get("e2eventservicereference", ""), ev.get("e2eventid", "")) for ev in paths]

        gen = self.write_timers_list(refs)
        GLib.idle_add(lambda: next(gen, False))

    def write_timers_list(self, refs):
        self._app.wait_dialog.show()
        tasks = list(refs)
        for ref in refs:
            self._app.send_http_request(HttpAPI.Request.TIMER, ref, lambda x: tasks.pop())
            yield True

        while tasks:
            yield True

        self._app.emit("change-page", Page.TIMERS.value)

    def on_epg_press(self, view, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS and len(view.get_model()) > 0:
            self.on_timer_add()

    def on_service_changed(self, app, ref):
        self._app.wait_dialog.show()
        self._app.send_http_request(HttpAPI.Request.EPG, quote(ref), self.update_epg_data)

    @run_idle
    def update_epg_data(self, epg):
        self._model.clear()
        list(map(self._model.append, (self.get_event_row(e) for e in epg.get("event_list", []))))
        self._app.wait_dialog.hide()

    def get_event_row(self, event):
        title = event.get("e2eventtitle", "") or ""
        desc = event.get("e2eventdescription", "") or ""

        start = int(event.get("e2eventstart", "0"))
        start_time = datetime.fromtimestamp(start)
        end_time = datetime.fromtimestamp(start + int(event.get("e2eventduration", "0")))
        time = f"{start_time.strftime('%A, %H:%M')} - {end_time.strftime('%H:%M')}"

        return title, time, desc, event

    def on_epg_filter_changed(self, entry):
        self._filter_model.refilter()

    def on_epg_filter_toggled(self, button):
        if not button.get_active():
            self._filter_entry.set_text("")

    def epg_filter_function(self, model, itr, data):
        txt = self._filter_entry.get_text().upper()
        return next((s for s in model.get(itr, 0, 1, 2) if txt in s.upper()), False)


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

    class TimerDialog(Gtk.Dialog):
        def __init__(self, parent, action=None, timer_data=None, *args, **kwargs):
            super().__init__(use_header_bar=IS_GNOME_SESSION, *args, **kwargs)

            self._action = action or TimerTool.TimerAction.ADD
            self._timer_data = timer_data or {}
            self._request = ""

            handlers = {"on_timer_begins_set": self.on_timer_begins_set,
                        "on_timer_ends_set": self.on_timer_ends_set}

            builder = get_builder(UI_RESOURCES_PATH + "control.glade", handlers,
                                  objects=("timer_dialog_frame", "timer_ends_popover", "end_hour_adjustment",
                                           "min_end_adjustment", "timer_begins_popover", "begins_hour_adjustment",
                                           "min_begins_adjustment"))

            self.set_title(get_message("Timer"))
            self.set_modal(True)
            self.set_skip_pager_hint(True)
            self.set_skip_taskbar_hint(True)
            self.set_transient_for(parent)
            self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
            self.set_resizable(False)

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

            self.add_buttons(get_message("Cancel"), Gtk.ResponseType.CANCEL, get_message("Save"), Gtk.ResponseType.OK)
            self.get_content_area().pack_start(builder.get_object("timer_dialog_frame"), True, True, 5)

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
            self._timer_begins_entry.set_text(f"{date.year}-{date.month}-{date.day} {hour}:{minute:02d}")

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
            self._timer_ends_entry.set_text(f"{date.year}-{date.month}-{date.day} {hour}:{minute:02d}")

        def set_timer_for_add(self):
            self._timer_service_entry.set_text(self._timer_data.get("e2servicename", ""))
            self._timer_service_ref_entry.set_text(self._timer_data.get("e2servicereference", ""))
            date = datetime.now()
            self.set_begins_date(date)
            self.set_ends_date(date)
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
            self._timer_name_entry.set_text(self._timer_data.get("e2eventtitle", ""))
            self._timer_desc_entry.set_text(self._timer_data.get("e2eventdescription", ""))
            self._timer_service_entry.set_text(self._timer_data.get("e2eventservicename", ""))
            self._timer_service_ref_entry.set_text(self._timer_data.get("e2eventservicereference", ""))
            self._timer_event_id_entry.set_text(self._timer_data.get("e2eventid", ""))
            self._timer_action_combo_box.set_active_id("1")
            self._timer_after_combo_box.set_active_id("3")
            start_time = int(self._timer_data.get("e2eventstart", "0"))
            self.set_time_data(start_time, start_time + int(self._timer_data.get("e2eventduration", "0")))

        def set_time_data(self, start_time, end_time):
            """ Sets values for time widgets. """
            ev_time_start = datetime.fromtimestamp(start_time) or datetime.now()
            ev_time_end = datetime.fromtimestamp(end_time) or datetime.now()
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
                    "on_timers_press": self.on_timers_press,
                    "on_timers_key_press": self.on_timers_key_press,
                    "on_timer_cursor_changed": self.on_timer_cursor_changed,
                    "on_timers_drag_data_received": self.on_timers_drag_data_received}

        builder = get_builder(UI_RESOURCES_PATH + "control.glade", handlers, objects=("timers_frame", "timer_model"))
        self._view = builder.get_object("timer_view")
        self._remove_button = builder.get_object("timer_remove_button")
        self._remove_button.bind_property("sensitive", builder.get_object("timer_edit_button"), "sensitive")
        self._info_button = builder.get_object("timer_info_check_button")
        self._info_button.bind_property("active", builder.get_object("timer_info_frame"), "visible")
        self._info_enabled_switch = builder.get_object("timer_info_enabled_switch")
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
        time = f"{start_time.strftime('%A, %H:%M')} - {end_time.strftime('%H:%M')}"

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

    def on_timers_press(self, view, event):
        if event.get_event_type() == Gdk.EventType.DOUBLE_BUTTON_PRESS and len(view.get_model()) > 0:
            self.on_timer_edit()

    def on_timers_key_press(self, view, event):
        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return

        key = KeyboardKey(key_code)
        if key is KeyboardKey.DELETE:
            self.on_timer_remove()

    def on_timer_cursor_changed(self, view):
        path, column = view.get_cursor()
        if not path:
            return

        timer = view.get_model()[path][-1]
        self._info_enabled_switch.set_active((timer.get("e2disabled", "0") == "0"))
        self._ref_info_label.set_text(timer.get("e2servicereference", ""))
        self._event_id_info_label.set_text(timer.get("e2eit", ""))
        self._action_info_label.set_text(get_message(self.ACTION.get(timer.get("e2justplay", "0"), "0")))
        self._after_info_label.set_text(get_message(self.AFTER_EVENT.get(timer.get("e2afterevent", "0"), "0")))
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
                    show_dialog(DialogType.ERROR, transient=self._app._main_window, text=msg)
                    context.finish(False, False, time)
                    return

                self.add_timer({"e2servicename": service.service,
                                "e2servicereference": service.picon_id.rstrip(".png").replace("_", ":")})

            context.finish(True, False, time)


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
                    "on_recordings_model_changed": self.on_recordings_model_changed}

        builder = get_builder(UI_RESOURCES_PATH + "control.glade", handlers,
                              objects=("recordings_box", "recordings_model", "rec_paths_model"))
        self._rec_view = builder.get_object("recordings_view")
        self._paths_view = builder.get_object("recordings_paths_view")
        self._paned = builder.get_object("recordings_paned")
        self._recordings_count_label = builder.get_object("recordings_count_label")
        self.pack_start(builder.get_object("recordings_box"), True, True, 0)
        if settings.alternate_layout:
            self.on_layout_changed(app, True)

        self.init()
        self.show()

    def clear_data(self):
        self._rec_view.get_model().clear()
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
        model = self._rec_view.get_model()
        model.clear()
        list(map(model.append, (self.get_recordings_row(r) for r in recordings.get("recordings", []))))

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


class ControlTool(Gtk.Box):

    def __init__(self, app, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._settings = settings
        self._app = app
        self._app.connect("layout-changed", self.on_layout_changed)
        self._pix = None

        handlers = {"on_volume_changed": self.on_volume_changed,
                    "on_screenshot_draw": self.on_screenshot_draw}

        builder = get_builder(UI_RESOURCES_PATH + "control.glade", handlers,
                              objects=("control_box", "volume_adjustment"))

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
        app.set_action("on_red", lambda a, v: self.on_remote_action(HttpAPI.Remote.RED))
        app.set_action("on_green", lambda a, v: self.on_remote_action(HttpAPI.Remote.GREEN))
        app.set_action("on_yellow", lambda a, v: self.on_remote_action(HttpAPI.Remote.YELLOW))
        app.set_action("on_blue", lambda a, v: self.on_remote_action(HttpAPI.Remote.BLUE))
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
        self._remote_box.reorder_child(self._remote_box.get_children()[0], 1)

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

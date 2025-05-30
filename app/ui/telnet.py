# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2025 Dmitriy Yefremov
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


import re
import socket
from collections import deque

from gi.repository import GLib

from app.commons import run_task, run_idle, log
from app.connections import ExtTelnet
from app.ui.uicommons import Gtk, Gdk, UI_RESOURCES_PATH, KeyboardKey, MOD_MASK


class TelnetClient(Gtk.Box):
    """ Very simple telnet client. """
    _COLOR_PATTERN = re.compile("\x1b.*?m")  # Color info
    _ERASING_PATTERN = re.compile("\x1b.*?K")  # Erase to right
    _APP_MODE_PATTERN = re.compile("\x1b.*?(1h)|(1l)")  # h - on, l - off
    _ALL_PATTERN = re.compile(r'(\x1b\[|\x9b)[0-?]*[@-~]')
    _NOT_SUPPORTED = {"mc", "mcedit", "vi", "nano"}

    def __init__(self, app, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._app = app
        self._app.connect("profile-changed", self.on_profile_changed)

        self._tn = None
        self._app_mode = False
        self._commands = deque(maxlen=10)

        self._handlers = {"on_clear": self.on_clear,
                          "on_text_view_realize": self.on_text_view_realize,
                          "on_view_key_press": self.on_view_key_press,
                          "on_connect": self.on_connect,
                          "on_disconnect": self.on_disconnect}

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "telnet.glade")
        builder.connect_signals(self._handlers)

        self._text_view = builder.get_object("text_view")
        self._buf = builder.get_object("text_buffer")
        self._end_tag = builder.get_object("end_tag")
        self._connect_button = builder.get_object("connect_button")
        self._connect_button.bind_property("visible", builder.get_object("disconnect_button"), "visible", 4)

        main_frame = builder.get_object("telnet_frame")
        provider = Gtk.CssProvider()
        provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        main_frame.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        self.pack_start(main_frame, True, True, 0)
        self.show()

    def on_profile_changed(self, app, data):
        self.on_clear()
        self.on_disconnect()
        self.on_connect()

    def on_text_view_realize(self, view):
        self.on_connect()

    @run_task
    def on_connect(self, item=None):
        try:
            GLib.idle_add(self._connect_button.set_visible, False)
            settings = self._app.app_settings
            user, password, timeout = settings.user, settings.password, settings.telnet_timeout
            self._tn = ExtTelnet(self.append_output, host=settings.host, port=settings.telnet_port, timeout=timeout)

            if user != "":
                self._tn.read_until(b"login: ")
                self._tn.write(user.encode("utf-8") + b"\n")
            if password != "":
                self._tn.read_until(b"Password: ")
                self._tn.write(password.encode("utf-8") + b"\n")

            self._tn.interact()
        except (OSError, EOFError, socket.timeout, ConnectionRefusedError) as e:
            log(f"{self.__class__.__name__}: {e}")
            self._app.show_info_message(str(e), Gtk.MessageType.ERROR)
        finally:
            GLib.idle_add(self._connect_button.set_visible, True)

    @run_task
    def on_disconnect(self, item=None):
        if self._tn:
            GLib.idle_add(self._connect_button.set_visible, True)
            self._tn.close()

    def on_command_done(self, entry):
        command = entry.get_text()
        entry.set_text("")
        if command and self._tn:
            self._tn.write(command.encode("ascii") + b"\r")

    def on_clear(self, item=None):
        self._buf.delete(self._buf.get_start_iter(), self._buf.get_end_iter())

    def on_view_key_press(self, view, event):
        """ Handling  keystrokes on press. """
        if event.keyval == Gdk.KEY_Return:
            self.do_command()
            return True

        key_code = event.hardware_keycode
        if not KeyboardKey.value_exist(key_code):
            return None

        key = KeyboardKey(key_code)
        ctrl = event.state & MOD_MASK
        if ctrl and key is KeyboardKey.C:
            if self._tn and self._tn.sock:
                self._tn.write(b"\x03")  # interrupt

        # Last commands navigation.
        if key is KeyboardKey.UP:
            self.delete_last_command()
            if self._commands:
                cmd = self._commands.pop()
                self._commands.appendleft(cmd)
                self._buf.insert_at_cursor(cmd, -1)
            return True
        elif key is KeyboardKey.DOWN:
            self.delete_last_command()
            if self._commands:
                cmd = self._commands.popleft()
                self._commands.append(cmd)
                self._buf.insert_at_cursor(cmd, -1)
            return True
        return False

    def delete_last_command(self):
        end = self._buf.get_end_iter()
        if end.ends_tag(self._end_tag):
            return

        if end.backward_to_tag_toggle(self._end_tag):
            self._buf.delete(self._buf.get_end_iter(), end)

    def do_command(self):
        count = self._buf.get_line_count()
        begin = self._buf.get_iter_at_line(count)
        end = self._buf.get_end_iter()
        command = []

        while end.backward_to_tag_toggle(self._end_tag):
            command.append(self._buf.get_text(end, begin, False))
            break
        else:  # if buf is empty
            command.append(self._buf.get_text(begin, end, False))

        # To preventing duplication of the command in the buf.
        self._buf.delete(end, begin)

        if command and self._tn.sock:
            cmd = command[0]
            if cmd in self._NOT_SUPPORTED:
                self._app.show_info_message(f"'{cmd}' is not supported by this client.", Gtk.MessageType.ERROR)
            else:
                self._tn.write(cmd.encode("ascii") + b"\r")
                self._commands.append(cmd)

    @run_idle
    def append_output(self, txt):
        t = txt.decode("ascii", errors="ignore")

        ap = re.search(self._APP_MODE_PATTERN, t)
        if ap:
            on, of = ap.group(1), ap.group(2)
            if on:
                self._app_mode = True
            elif of:
                self._app_mode = False
                self.on_clear()

        t = re.sub(self._ALL_PATTERN, "", t)  # Removing [replacing] ascii escape sequences.

        if self._app_mode:
            start, end = self._buf.get_start_iter(), self._buf.get_end_iter()
            count = self._buf.get_line_count()
            new_lines = t.split("\r\n")
            ext_lines = self._buf.get_text(start, end, True).split("\r\n")
            if count < len(new_lines):
                self._buf.set_text(re.sub(self._ERASING_PATTERN, "", t))
            else:
                for i, line in enumerate(new_lines):
                    if line:
                        ext_lines[i] = re.sub(self._ERASING_PATTERN, "", line)
                self._buf.set_text("\r\n".join(ext_lines))
        else:
            self._buf.insert_at_cursor(t, -1)

        insert = self._buf.get_insert()
        self._text_view.scroll_to_mark(insert, 0.0, True, 0.0, 1.0)
        self._buf.apply_tag(self._end_tag, self._buf.get_start_iter(), self._buf.get_end_iter())


if __name__ == "__main__":
    pass

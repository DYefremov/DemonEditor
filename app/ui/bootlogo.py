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


import os
import subprocess
import sys
from ftplib import all_errors
from pathlib import Path

from app.commons import log, run_task
from app.connections import UtfFTP
from app.settings import IS_DARWIN
from app.ui.dialogs import translate, get_chooser_dialog
from app.ui.main_helper import get_picon_pixbuf, redraw_image
from app.ui.uicommons import HeaderBar
from .uicommons import Gtk, GLib

_FFMPEG_OUTPUT_FILE = 'bootlogo.m1v'
_E2_BASE_PATH = "/usr/share"


class BootLogoManager(Gtk.Window):

    def __init__(self, app, **kwargs):
        super().__init__(title=translate("Boot Logo"), icon_name="demon-editor", application=app,
                         transient_for=app.app_window, destroy_with_parent=True,
                         window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
                         default_width=560, default_height=320, modal=True, **kwargs)

        self._app = app
        self._exe = f"{'./' if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS') else ''}ffmpeg"
        self._pix = None

        margin = {"margin_start": 5, "margin_end": 5, "margin_top": 5, "margin_bottom": 5}
        base_margin = {"margin_start": 10, "margin_end": 10, "margin_top": 10, "margin_bottom": 10}

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame = Gtk.Frame(shadow_type=Gtk.ShadowType.IN, **base_margin)
        frame.get_style_context().add_class("view")
        data_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.VERTICAL, **base_margin)
        data_box.set_margin_bottom(margin.get("margin_bottom", 5))
        data_box.set_margin_start(10)
        frame.add(data_box)
        self._image_area = Gtk.DrawingArea()
        self._image_area.connect("draw", self.on_image_draw)
        data_box.pack_end(self._image_area, True, True, 0)
        self.add(main_box)
        # Buttons
        add_button = Gtk.Button.new_from_icon_name("insert-image-symbolic", Gtk.IconSize.BUTTON)
        add_button.set_tooltip_text(translate("Add image"))
        add_button.set_always_show_image(True)
        add_button.connect("clicked", self.on_add_image)
        receive_button = Gtk.Button.new_from_icon_name("network-receive-symbolic", Gtk.IconSize.BUTTON)
        receive_button.set_tooltip_text(translate("Download from the receiver"))
        receive_button.set_always_show_image(True)
        receive_button.connect("clicked", self.on_receive)
        transmit_button = Gtk.Button.new_from_icon_name("network-transmit-symbolic", Gtk.IconSize.BUTTON)
        transmit_button.set_tooltip_text(translate("Transfer to receiver"))
        transmit_button.set_always_show_image(True)
        transmit_button.connect("clicked", self.on_transmit)
        convert_button = Gtk.Button.new_from_icon_name("object-rotate-right-symbolic", Gtk.IconSize.BUTTON)
        convert_button.set_tooltip_text(translate("Convert"))
        convert_button.set_always_show_image(True)
        convert_button.set_sensitive(False)
        convert_button.connect("clicked", self.on_convert)

        action_box = Gtk.ButtonBox()
        action_box.set_layout(Gtk.ButtonBoxStyle.EXPAND)
        action_box.add(add_button)
        action_box.add(convert_button)
        data_box.pack_start(action_box, False, False, 0)

        # Header and toolbar.
        if app.app_settings.use_header_bar:
            header = HeaderBar()
            header.pack_start(receive_button)
            header.pack_start(transmit_button)

            self.set_titlebar(header)
            header.show_all()
        else:
            toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            toolbar.get_style_context().add_class("primary-toolbar")
            margin["margin_start"] = 15
            margin["margin_top"] = 10
            button_box = Gtk.Box(spacing=5, orientation=Gtk.Orientation.HORIZONTAL, **margin)
            button_box.pack_start(receive_button, False, False, 0)
            button_box.pack_start(transmit_button, False, False, 0)
            toolbar.pack_start(button_box, True, True, 0)
            main_box.pack_start(toolbar, False, False, 0)

        main_box.pack_start(frame, True, True, 0)
        main_box.show_all()

        ws_property = "boot_logo_manager_window_size"
        window_size = self._app.app_settings.get(ws_property, None)
        if window_size:
            self.resize(*window_size)

        self.connect("delete-event", lambda w, e: self._app.app_settings.add(ws_property, w.get_size()))
        self.connect("realize", self.init)

    def init(self, *args):
        log(f"{self.__class__.__name__} [init] Checking FFmpeg...")
        try:
            out = subprocess.check_output([self._exe, "-version"], stderr=subprocess.STDOUT)
        except FileNotFoundError as e:
            msg = translate("Check if FFmpeg is installed!")
            self._app.show_error_message(f"Error. {e} {msg}")
            log(e)
        else:
            lines = out.decode(errors="ignore").splitlines()
            log(lines[0] if lines else lines)

    def on_add_image(self, button):
        file_filter = None
        if IS_DARWIN:
            file_filter = Gtk.FileFilter()
            file_filter.set_name("*.jpg, *.jpeg, *.png")
            file_filter.add_mime_type("image/jpeg")
            file_filter.add_mime_type("image/png")

        response = get_chooser_dialog(self._app.app_window, self._app.app_settings, "*.jpg, *.jpeg, *.png files",
                                      ("*.jpg", "*.jpeg", "*.png"), "Select image", file_filter)
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return

        self._pix = get_picon_pixbuf(response, -1)
        self._image_area.queue_draw()

    def on_receive(self, button):
        self.download_data("bootlogo.mvi")

    def on_transmit(self, button):
        self._app.show_error_message("Not implemented yet!")

    def on_convert(self, button):
        self._app.show_error_message("Not implemented yet!")

    def convert_to_mvi(self, image_path, output="bootlogo.mvi", frame_rate=25, bit_rate=2000, resolution="hd720"):
        cmd = [self._exe,
               "-i", image_path,
               "-r", str(frame_rate),
               "-b", str(bit_rate),
               "-s", resolution,
               _FFMPEG_OUTPUT_FILE]

        try:
            from PIL import Image
        except ImportError as e:
            self._app.show_error_message(f"{translate('Conversion error.')} {e}")
        else:
            with Image.open(image_path) as img:
                width, height = img.size
                if width != 1280 and height != 720:
                    log(f"{self.__class__.__name__} [convert] Resizing image...")
                    img.resize((1280, 720), Image.Resampling.LANCZOS)
                    path = Path(image_path)
                    tmp = path.parent.joinpath(f"{path.name}.tmp.{path.suffix}").absolute()
                    cmd[2] = tmp
                    img.save(tmp)

                # Processing image.
                log(f"{self.__class__.__name__} [convert] Converting...")
                subprocess.run(cmd)

                if Path(_FFMPEG_OUTPUT_FILE).exists():
                    os.rename(_FFMPEG_OUTPUT_FILE, output)
                    log(f"{self.__class__.__name__} [convert] -> '{output}'. Done!")

                if cmd[2] != image_path:
                    tmp_path = Path(cmd[2])
                    if tmp_path.exists():
                        tmp_path.unlink()

    def convert_to_image(self, video_path, img_path):
        cmd = [self._exe, "-y", "-i", video_path, img_path]
        subprocess.run(cmd)

    @run_task
    def download_data(self, f_name, receive=True, clb=None):
        try:
            settings = self._app.app_settings
            with UtfFTP(host=settings.host, user=settings.user, passwd=settings.password) as ftp:
                ftp.encoding = "utf-8"
                ftp.cwd(_E2_BASE_PATH)
                if receive:
                    dest = Path(settings.profile_data_path).joinpath("bootlogo")
                    dest.mkdir(parents=True, exist_ok=True)
                    path = f"{dest}{os.sep}"
                    ftp.download_file(f_name, path)
                    vp = Path(f"{path}{f_name}")
                    img_path = f"{path}logo.jpg"

                    if vp.exists():
                        rn_path = f"{path}{_FFMPEG_OUTPUT_FILE}"
                        vp.rename(rn_path)
                        self.convert_to_image(rn_path, img_path)
                        self._pix = get_picon_pixbuf(img_path, -1)
                        self._image_area.queue_draw()

        except all_errors as e:
            log(e)
            GLib.iddle_add(self._app.show_error_message, e)

    def on_image_draw(self, area, cr):
        if self._pix:
            redraw_image(area, cr, self._pix)


if __name__ == "__main__":
    pass

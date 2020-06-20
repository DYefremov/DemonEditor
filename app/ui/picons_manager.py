import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse, unquote

from gi.repository import GLib, GdkPixbuf

from app.commons import run_idle, run_task, run_with_delay
from app.connections import upload_data, DownloadType, download_data, remove_picons
from app.settings import SettingsType, Settings
from app.tools.picons import PiconsParser, parse_providers, Provider, convert_to
from app.tools.satellites import SatellitesParser, SatelliteSource
from .dialogs import show_dialog, DialogType, get_message
from .main_helper import update_entry_data, append_text_to_tview, scroll_to, on_popup_menu, get_base_model, set_picon, \
    get_picon_pixbuf
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, TV_ICON, Column, GTK_PATH


class PiconsDialog:
    def __init__(self, transient, settings, picon_ids, sat_positions, app):
        self._picon_ids = picon_ids
        self._sat_positions = sat_positions
        self._app = app
        self._TMP_DIR = tempfile.gettempdir() + "/"
        self._BASE_URL = "www.lyngsat.com/packages/"
        self._PATTERN = re.compile(r"^https://www\.lyngsat\.com/[\w-]+\.html$")
        self._POS_PATTERN = re.compile(r"^\d+\.\d+[EW]?$")
        self._current_process = None
        self._terminate = False
        self._filter_binding = None
        self._services = None
        self._current_picon_info = None

        handlers = {"on_receive": self.on_receive,
                    "on_load_providers": self.on_load_providers,
                    "on_cancel": self.on_cancel,
                    "on_close": self.on_close,
                    "on_send": self.on_send,
                    "on_download": self.on_download,
                    "on_remove": self.on_remove,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_picons_dir_open": self.on_picons_dir_open,
                    "on_selected_toggled": self.on_selected_toggled,
                    "on_url_changed": self.on_url_changed,
                    "on_picons_filter_changed": self.on_picons_filter_changed,
                    "on_position_edited": self.on_position_edited,
                    "on_visible_page": self.on_visible_page,
                    "on_convert": self.on_convert,
                    "on_picons_src_changed": self.on_picons_src_changed,
                    "on_picons_dest_changed": self.on_picons_dest_changed,
                    "on_picons_view_drag_data_get": self.on_picons_view_drag_data_get,
                    "on_picons_src_view_drag_drop": self.on_picons_src_view_drag_drop,
                    "on_picons_src_view_drag_data_received": self.on_picons_src_view_drag_data_received,
                    "on_picons_src_view_drag_end": self.on_picons_src_view_drag_end,
                    "on_picon_info_image_drag_data_received": self.on_picon_info_image_drag_data_received,
                    "on_send_button_drag_data_received": self.on_send_button_drag_data_received,
                    "on_download_button_drag_data_received": self.on_download_button_drag_data_received,
                    "on_remove_button_drag_data_received": self.on_remove_button_drag_data_received,
                    "on_selective_send": self.on_selective_send,
                    "on_selective_download": self.on_selective_download,
                    "on_selective_remove": self.on_selective_remove,
                    "on_local_remove": self.on_local_remove,
                    "on_picons_dest_view_realize": self.on_picons_dest_view_realize,
                    "on_satellites_view_realize": self.on_satellites_view_realize,
                    "on_satellite_selection": self.on_satellite_selection,
                    "on_select_all": self.on_select_all,
                    "on_unselect_all": self.on_unselect_all,
                    "on_filter_toggled": self.on_filter_toggled,
                    "on_fiter_srcs_toggled": self.on_fiter_srcs_toggled,
                    "on_filter_services_switch": self.on_filter_services_switch,
                    "on_picon_activated": self.on_picon_activated,
                    "on_popup_menu": on_popup_menu}

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "picons_manager.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("picons_dialog")
        self._dialog.set_transient_for(transient)
        self._picons_src_view = builder.get_object("picons_src_view")
        self._picons_dest_view = builder.get_object("picons_dest_view")
        self._providers_view = builder.get_object("providers_view")
        self._satellites_view = builder.get_object("satellites_view")
        self._picons_src_filter_model = builder.get_object("picons_src_filter_model")
        self._picons_src_filter_model.set_visible_func(self.picons_src_filter_function)
        self._picons_dst_filter_model = builder.get_object("picons_dst_filter_model")
        self._picons_dst_filter_model.set_visible_func(self.picons_dst_filter_function)
        self._explorer_src_path_button = builder.get_object("explorer_src_path_button")
        self._explorer_dest_path_button = builder.get_object("explorer_dest_path_button")
        self._expander = builder.get_object("expander")
        self._text_view = builder.get_object("text_view")
        self._info_bar = builder.get_object("info_bar")
        self._filter_bar = builder.get_object("filter_bar")
        self._filter_button = builder.get_object("filter_button")
        self._src_filter_button = builder.get_object("src_filter_button")
        self._dst_filter_button = builder.get_object("dst_filter_button")
        self._picons_filter_entry = builder.get_object("picons_filter_entry")
        self._ip_entry = builder.get_object("ip_entry")
        self._picons_entry = builder.get_object("picons_entry")
        self._url_entry = builder.get_object("url_entry")
        self._picons_dir_entry = builder.get_object("picons_dir_entry")
        self._message_label = builder.get_object("info_bar_message_label")
        self._info_check_button = builder.get_object("info_check_button")
        self._picon_info_image = builder.get_object("picon_info_image")
        self._picon_info_label = builder.get_object("picon_info_label")
        self._load_providers_button = builder.get_object("load_providers_button")
        self._receive_button = builder.get_object("receive_button")
        self._convert_button = builder.get_object("convert_button")
        self._enigma2_path_button = builder.get_object("enigma2_path_button")
        self._save_to_button = builder.get_object("save_to_button")
        self._send_button = builder.get_object("send_button")
        self._download_button = builder.get_object("download_button")
        self._remove_button = builder.get_object("remove_button")
        self._cancel_button = builder.get_object("cancel_button")
        self._enigma2_radio_button = builder.get_object("enigma2_radio_button")
        self._neutrino_mp_radio_button = builder.get_object("neutrino_mp_radio_button")
        self._resize_no_radio_button = builder.get_object("resize_no_radio_button")
        self._resize_220_132_radio_button = builder.get_object("resize_220_132_radio_button")
        self._resize_100_60_radio_button = builder.get_object("resize_100_60_radio_button")
        self._satellite_label = builder.get_object("satellite_label")
        self._explorer_action_box = builder.get_object("explorer_action_box")
        self._satellite_label.bind_property("visible", builder.get_object("loading_data_label"), "visible", 4)
        self._satellite_label.bind_property("visible", builder.get_object("loading_data_spinner"), "visible", 4)
        self._cancel_button.bind_property("visible", builder.get_object("receive_button"), "visible", 4)
        self._cancel_button.bind_property("visible", self._load_providers_button, "visible", 4)
        self._convert_button.bind_property("visible", self._explorer_action_box, "visible", 4)
        downloader_action_box = builder.get_object("downloader_action_box")
        self._explorer_action_box.bind_property("visible", downloader_action_box, "visible", 4)
        self._convert_button.bind_property("visible", downloader_action_box, "visible", 4)
        self._filter_bar.bind_property("search-mode-enabled", self._filter_bar, "visible")
        self._explorer_src_path_button.bind_property("sensitive", builder.get_object("picons_view_sw"), "sensitive")
        self._filter_button.bind_property("active", builder.get_object("filter_service_box"), "visible")
        self._filter_button.bind_property("active", builder.get_object("src_title_grid"), "visible")
        self._filter_button.bind_property("active", builder.get_object("dst_title_grid"), "visible")
        self._filter_button.bind_property("visible", self._info_check_button, "visible")
        explorer_info_bar = builder.get_object("explorer_info_bar")
        explorer_info_bar.bind_property("visible", builder.get_object("explorer_info_bar_frame"), "visible")
        self._info_check_button.bind_property("active", explorer_info_bar, "visible")
        # Init drag-and-drop
        self.init_drag_and_drop()
        # Style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._url_entry.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                                    Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._settings = settings
        self._s_type = settings.setting_type
        self._ip_entry.set_text(self._settings.host)
        self._picons_entry.set_text(self._settings.picons_path)
        self._picons_dir_entry.set_text(self._settings.picons_local_path)

        window_size = self._settings.get("picons_downloader_window_size")
        if window_size:
            self._dialog.resize(*window_size)

        if not len(self._picon_ids) and self._s_type is SettingsType.ENIGMA_2:
            message = get_message("To automatically set the identifiers for picons,\n"
                                  "first load the required services list into the main application window.")
            self.show_info_message(message, Gtk.MessageType.WARNING)
            self._satellite_label.show()

    def show(self):
        self._dialog.show()

    def on_picons_dest_view_realize(self, view):
        self._services = {s.picon_id: s for s in self._app.current_services.values() if s.picon_id}
        self._explorer_dest_path_button.select_filename(self._settings.picons_local_path)

    def on_picons_src_changed(self, button):
        self.update_picons_data(self._picons_src_view, button)

    def on_picons_dest_changed(self, button):
        self.update_picon_info()
        self.update_picons_data(self._picons_dest_view, button)

    def update_picons_data(self, view, button):
        path = button.get_filename()
        if not path or not os.path.exists(path):
            return

        GLib.idle_add(button.set_sensitive, False)
        gen = self.update_picons(path, view, button)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def update_picons(self, path, view, button):
        p_model = view.get_model()
        if not p_model:
            button.set_sensitive(True)
            return

        model = get_base_model(p_model)
        view.set_model(None)
        factor = self._app.DEL_FACTOR

        for index, itr in enumerate([row.iter for row in model]):
            model.remove(itr)
            if index % factor == 0:
                yield True

        for file in os.listdir(path):
            if self._terminate:
                return

            p_path = "{}/{}".format(path, file)
            p = self.get_pixbuf_at_scale(p_path, 72, 48, True)
            if p:
                yield model.append((p, file, p_path))

        view.set_model(p_model)
        button.set_sensitive(True)
        yield True

    def update_picons_from_file(self, view, uri):
        """ Adds picons in the view on dragging from file system. """
        path = Path(urlparse(unquote(uri)).path.strip())
        f_path = str(path.resolve())
        if not f_path:
            return

        model = get_base_model(view.get_model())

        if path.is_file():
            p = self.get_pixbuf_at_scale(f_path, 72, 48, True)
            if p:
                model.append((p, path.name, f_path))
        elif path.is_dir():
            self._explorer_src_path_button.select_filename(f_path)

    def get_pixbuf_at_scale(self, path, width, height, p_ratio):
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width, height, p_ratio)
        except GLib.GError:
            pass

    # ***************** Drag-and-drop ********************* #

    def init_drag_and_drop(self):
        self._picons_src_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self._picons_src_view.drag_source_add_uri_targets()

        self._picons_dest_view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self._picons_dest_view.drag_source_add_uri_targets()

        self._picons_src_view.enable_model_drag_dest([], Gdk.DragAction.DEFAULT | Gdk.DragAction.MOVE)
        self._picons_src_view.drag_dest_add_text_targets()

        self._picon_info_image.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self._picon_info_image.drag_dest_add_uri_targets()

        self._send_button.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self._send_button.drag_dest_add_uri_targets()

        self._download_button.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self._download_button.drag_dest_add_uri_targets()

        self._remove_button.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self._remove_button.drag_dest_add_uri_targets()

    def on_picons_view_drag_data_get(self, view, drag_context, data, info, time):
        model, path = view.get_selection().get_selected_rows()
        if path:
            p_uri = Path(model[path][-1]).as_uri()
            dest_uri = Path(self._explorer_dest_path_button.get_filename()).as_uri()
            data.set_uris(["{}::::{}".format(p_uri, dest_uri)])

    def on_picons_src_view_drag_drop(self, view, drag_context, x, y, time):
        view.stop_emission_by_name("drag_drop")
        targets = drag_context.list_targets()
        view.drag_get_data(drag_context, targets[-1] if targets else Gdk.atom_intern("text/plain", False), time)

    def on_picons_src_view_drag_data_received(self, view, drag_context, x, y, data, info, time):
        view.stop_emission_by_name("drag_data_received")
        txt = data.get_text()
        if not txt:
            return

        if txt.startswith("file://"):
            self.update_picons_from_file(view, txt)
            return

        itr_str, sep, src = txt.partition("::::")
        if src == self._app.BQ_MODEL_NAME:
            return

        path, pos = view.get_dest_row_at_pos(x, y) or (None, None)
        if not path:
            return

        model = view.get_model()
        if src == self._app.FAV_MODEL_NAME:
            target_view = self._app.fav_view
            c_id = Column.FAV_ID
        else:
            target_view = self._app.services_view
            c_id = Column.SRV_FAV_ID

        t_mod = target_view.get_model()
        dest_path = self._explorer_dest_path_button.get_filename() + "/"
        self.update_picons_dest_view(self._app.on_assign_picon(target_view, model[path][-1], dest_path))
        self.show_assign_info([t_mod.get_value(t_mod.get_iter_from_string(itr), c_id) for itr in itr_str.split(",")])

    @run_idle
    def update_picons_dest_view(self, picons):
        """ Update destination view on adding/changing picons. """
        if picons:
            dest_model = get_base_model(self._picons_dest_view.get_model())
            paths = {r[1]: r.iter for r in dest_model}

            for p_path in picons:
                p = self.get_pixbuf_at_scale(p_path, 72, 48, True)
                if p:
                    p_name = Path(p_path).name
                    itr = paths.get(p_name, None)
                    if itr:
                        dest_model.set_value(itr, 0, p)
                    else:
                        itr = dest_model.append((p, p_name, p_path))
                    scroll_to(dest_model.get_path(itr), self._picons_dest_view)

    @run_idle
    def show_assign_info(self, fav_ids):
        self._expander.set_expanded(True)
        self._text_view.get_buffer().set_text("")
        for i in fav_ids:
            srv = self._app.current_services.get(i, None)
            if srv:
                info = self._app.get_hint_for_srv_list(srv)
                self.append_output("Picon assignment for the service:\n{}\n{}\n".format(info, " * " * 30))

    def on_picons_src_view_drag_end(self, view, drag_context):
        self.update_picons_dest_view(self._app.picons_buffer)

    def on_picon_info_image_drag_data_received(self, img, drag_context, x, y, data, info, time):
        if not self._current_picon_info:
            self.show_info_message("No selected item!", Gtk.MessageType.ERROR)
            return

        uris = data.get_uris()
        if uris:
            name, fav_id = self._current_picon_info
            src, sep, dst = uris[0].partition("::::")
            src = urlparse(unquote(src)).path
            dst = "{}/{}".format(urlparse(unquote(dst)).path, name)
            if src != dst:
                shutil.copy(src, dst)
                for row in get_base_model(self._picons_dest_view.get_model()):
                    if name == row[1]:
                        row[0] = self.get_pixbuf_at_scale(row[-1], 72, 48, True)
                        img.set_from_pixbuf(self.get_pixbuf_at_scale(row[-1], 100, 60, True))

                gen = self.update_picon_in_lists(dst, fav_id)
                GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def on_send_button_drag_data_received(self, button, drag_context, x, y, data, info, time):
        path = self.get_path_from_uris(data)
        if path:
            self.on_send(files_filter={path.name}, path=path.parent)

    def on_download_button_drag_data_received(self, button, drag_context, x, y, data, info, time):
        path = self.get_path_from_uris(data)
        if path:
            self.on_download(files_filter={path.name})

    def on_remove_button_drag_data_received(self, button, drag_context, x, y, data, info, time):
        path = self.get_path_from_uris(data)
        if path:
            self.on_remove(files_filter={path.name})

    def get_path_from_uris(self, data):
        uris = data.get_uris()
        if uris:
            src, sep, dst = uris[0].partition("::::")
            return Path(urlparse(unquote(src)).path).resolve()

    def update_picon_in_lists(self, dst, fav_id):
        picon = get_picon_pixbuf(dst)
        p_pos = Column.SRV_PICON
        yield set_picon(fav_id, get_base_model(self._app.services_view.get_model()), picon, Column.SRV_FAV_ID, p_pos)
        yield set_picon(fav_id, get_base_model(self._app.fav_view.get_model()), picon, Column.FAV_ID, p_pos)

    # ******************** Download/Upload/Remove ************************* #

    def on_selective_send(self, view):
        path = self.get_selected_path(view)
        if path:
            self.on_send(files_filter={path.name}, path=path.parent)

    def on_selective_download(self, view):
        path = self.get_selected_path(view)
        if path:
            self.on_download(files_filter={path.name})

    def on_selective_remove(self, view):
        path = self.get_selected_path(view)
        if path:
            self.on_remove(files_filter={path.name})

    def on_local_remove(self, view):
        model, paths = view.get_selection().get_selected_rows()
        if paths and show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.OK:
            itr = model.get_iter(paths.pop())
            p_path = Path(model.get_value(itr, 2)).resolve()
            if p_path.is_file():
                p_path.unlink()
                base_model = get_base_model(model)
                filter_model = model.get_model()
                itr = filter_model.convert_iter_to_child_iter(model.convert_iter_to_child_iter(itr))
                base_model.remove(itr)

    def on_send(self, item=None, files_filter=None, path=None):
        dest_path = path or self.check_dest_path()
        if not dest_path:
            return

        settings = Settings(self._settings.settings)
        settings.picons_local_path = "{}/".format(dest_path)
        self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
        self.run_func(lambda: upload_data(settings=settings,
                                          download_type=DownloadType.PICONS,
                                          callback=self.append_output,
                                          done_callback=lambda: self.show_info_message(get_message("Done!"),
                                                                                       Gtk.MessageType.INFO),
                                          files_filter=files_filter))

    def on_download(self, item=None, files_filter=None, path=None):
        path = path or self.check_dest_path()
        if not path:
            return

        settings = Settings(self._settings.settings)
        settings.picons_local_path = path + "/"
        self.run_func(lambda: download_data(settings=settings,
                                            download_type=DownloadType.PICONS,
                                            callback=self.append_output,
                                            files_filter=files_filter), True)

    def on_remove(self, item=None, files_filter=None):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self.run_func(lambda: remove_picons(settings=self._settings,
                                            callback=self.append_output,
                                            done_callback=lambda: self.show_info_message(get_message("Done!"),
                                                                                         Gtk.MessageType.INFO),
                                            files_filter=files_filter))

    def get_selected_path(self, view):
        model, paths = view.get_selection().get_selected_rows()
        if paths:
            return Path(model[paths.pop()][-1]).resolve()

    def check_dest_path(self):
        """ Checks the destination path and returns if present. """
        if show_dialog(DialogType.QUESTION, self._dialog) != Gtk.ResponseType.OK:
            return

        path = self._explorer_dest_path_button.get_filename()
        if not path:
            show_dialog(DialogType.ERROR, transient=self._dialog, text="Select paths!")
            return
        return path

    # ******************** Downloader ************************* #

    def on_satellites_view_realize(self, view):
        self.get_satellites(view)

    @run_task
    def get_satellites(self, view):
        sats = SatellitesParser().get_satellites_list(SatelliteSource.LYNGSAT)
        if not sats:
            self.show_info_message("Getting satellites list error!", Gtk.MessageType.ERROR)
        gen = self.append_satellites(view.get_model(), sats)
        GLib.idle_add(lambda: next(gen, False), priority=GLib.PRIORITY_LOW)

    def append_satellites(self, model, sats):
        try:
            for sat in sats:
                pos = sat[1]
                name, pos = "{} ({})".format(sat[0], pos), "{}{}".format("-" if pos[-1] == "W" else "", pos[:-1])

                if not self._terminate and model:
                    if pos in self._sat_positions:
                        yield model.append((name, sat[3], pos))
        finally:
            self._satellite_label.show()

    def on_satellite_selection(self, view, path, column):
        model = view.get_model()
        self._url_entry.set_text(model.get(model.get_iter(path), 1)[0])

    @run_idle
    def on_load_providers(self, item):
        self._expander.set_expanded(True)
        self.on_info_bar_close()
        self._cancel_button.show()
        url = self._url_entry.get_text()

        try:
            exe = "{}wget".format("./" if GTK_PATH else "")
            self._current_process = subprocess.Popen([exe, "-pkP", self._TMP_DIR, url],
                                                     stdout=subprocess.PIPE,
                                                     stderr=subprocess.PIPE,
                                                     universal_newlines=True)
        except FileNotFoundError as e:
            self._cancel_button.hide()
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        else:
            GLib.io_add_watch(self._current_process.stderr, GLib.IO_IN, self.write_to_buffer)
            model = self._providers_view.get_model()
            model.clear()
            self.append_providers(url, model)

    @run_task
    def append_providers(self, url, model):
        self._current_process.wait()
        try:
            self._terminate = False
            providers = parse_providers(self._TMP_DIR + url[url.find("w"):])
        except FileNotFoundError:
            pass  # NOP
        else:
            if providers:
                for p in providers:
                    if self._terminate:
                        return
                    model.append((self.get_pixbuf(p[0]) if p[0] else TV_ICON, *p[1:]))
            self.update_receive_button_state()
        finally:
            GLib.idle_add(self._cancel_button.hide)
            self._terminate = False

    def get_pixbuf(self, img_url):
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(filename=self._TMP_DIR + "www.lyngsat.com/" + img_url,
                                                       width=48, height=48, preserve_aspect_ratio=True)

    def on_receive(self, item):
        self._cancel_button.show()
        self.start_download()

    @run_task
    def start_download(self):
        if self._current_process.poll() is None:
            self.show_dialog("The task is already running!", DialogType.ERROR)
            return

        self._terminate = False
        self._expander.set_expanded(True)

        providers = self.get_selected_providers()
        for prv in providers:
            if not self._POS_PATTERN.match(prv[2]):
                self.show_info_message(
                    get_message("Specify the correct position value for the provider!"), Gtk.MessageType.ERROR)
                scroll_to(prv.path, self._providers_view)
                return

        try:
            for prv in providers:
                if self._terminate:
                    return
                self.process_provider(Provider(*prv))

            if self._resize_no_radio_button.get_active():
                self.resize(self._picons_dir_entry.get_text())

            self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO)
        finally:
            GLib.idle_add(self._cancel_button.hide)
            self._terminate = False

    def process_provider(self, prv):
        url = prv.url
        self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
        exe = "{}wget".format("./" if GTK_PATH else "")
        self._current_process = subprocess.Popen([exe, "-pkP", self._TMP_DIR, url],
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE,
                                                 universal_newlines=True)
        GLib.io_add_watch(self._current_process.stderr, GLib.IO_IN, self.write_to_buffer)
        self._current_process.wait()
        path = self._TMP_DIR + (url[url.find("//") + 2:] if prv.single else self._BASE_URL + url[url.rfind("/") + 1:])
        PiconsParser.parse(path, self._picons_dir_entry.get_text(),
                           self._TMP_DIR, prv, self._picon_ids, self.get_picons_format())

    def write_to_buffer(self, fd, condition):
        if condition == GLib.IO_IN:
            char = fd.read(1)
            self.append_output(char)
            return True
        return False

    @run_idle
    def append_output(self, char):
        append_text_to_tview(char, self._text_view)

    def resize(self, path):
        self.show_info_message(get_message("Resizing..."), Gtk.MessageType.INFO)
        exe = "{}mogrify".format("./" if GTK_PATH else "")
        is_220_132 = self._resize_220_132_radio_button.get_active()
        command = "{} -resize {}! *.png".format(exe, "220x132" if is_220_132 else "100x60").split()
        try:
            self._current_process = subprocess.Popen(command, universal_newlines=True, cwd=path)
            self._current_process.wait()
        except FileNotFoundError as e:
            self.show_info_message("Conversion error. " + str(e), Gtk.MessageType.ERROR)

    def on_cancel(self, item=None):
        if self.is_task_running() and show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return True

        self.terminate_task()

    @run_task
    def terminate_task(self):
        self._terminate = True

        if self._current_process:
            self._current_process.terminate()
            self.show_info_message(get_message("The task is canceled!"), Gtk.MessageType.WARNING)

    def on_close(self, window, event):
        if self.on_cancel():
            return True

        self._terminate = True
        self.save_window_size(window)
        self.clean_data()
        self._app.update_picons()
        GLib.idle_add(self._dialog.destroy)

    def save_window_size(self, window):
        size = window.get_size()
        height = size.height - self._text_view.get_allocated_height() - self._info_bar.get_allocated_height()
        self._settings.add("picons_downloader_window_size", (size.width, height))

    @run_task
    def clean_data(self):
        path = self._TMP_DIR + "www.lyngsat.com"
        if os.path.exists(path):
            shutil.rmtree(path)

    @run_task
    def run_func(self, func, update=False):
        try:
            GLib.idle_add(self._expander.set_expanded, True)
            GLib.idle_add(self._explorer_action_box.set_sensitive, False)
            func()
        except OSError as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        finally:
            GLib.idle_add(self._explorer_action_box.set_sensitive, True)
            if update:
                self.on_picons_dest_changed(self._explorer_dest_path_button)

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(get_message(text))

    def on_picons_dir_open(self, entry, icon, event_button):
        update_entry_data(entry, self._dialog, settings=self._settings)

    @run_idle
    def on_selected_toggled(self, toggle, path):
        model = self._providers_view.get_model()
        model.set_value(model.get_iter(path), 7, not toggle.get_active())
        self.update_receive_button_state()

    def on_select_all(self, view):
        self.update_selection(view, True)

    def on_unselect_all(self, view):
        self.update_selection(view, False)

    def update_selection(self, view, select):
        view.get_model().foreach(lambda mod, path, itr: mod.set_value(itr, 7, select))
        self.update_receive_button_state()

    # *********************** Filter **************************** #

    def on_filter_toggled(self, button):
        active = button.get_active()
        self._filter_bar.set_search_mode(active)
        if not active:
            self._picons_filter_entry.set_text("")

    def on_fiter_srcs_toggled(self, filter_model):
        """ Activates re-filtering for model when filter check-button has toggled. """
        GLib.idle_add(filter_model.refilter, priority=GLib.PRIORITY_LOW)

    def on_filter_services_switch(self, button, state):
        """ Activates or deactivates filtering in the main list of services. """
        if state:
            self._filter_binding = self._picons_filter_entry.bind_property("text", self._app.filter_entry, "text")
            self._app.filter_entry.set_text(self._picons_filter_entry.get_text())
        else:
            if self._filter_binding:
                self._filter_binding.unbind()
                self._app.filter_entry.set_text("")

    @run_with_delay(1)
    def on_picons_filter_changed(self, entry):
        GLib.idle_add(self._picons_src_filter_model.refilter, priority=GLib.PRIORITY_LOW)
        GLib.idle_add(self._picons_dst_filter_model.refilter, priority=GLib.PRIORITY_LOW)

    def picons_src_filter_function(self, model, itr, data):
        return self.filter_function(itr, model, self._src_filter_button.get_active())

    def picons_dst_filter_function(self, model, itr, data):
        return self.filter_function(itr, model, self._dst_filter_button.get_active())

    def filter_function(self, itr, model, active):
        """ Main filtering function. """
        if any((not active, model is None, model == "None")):
            return True

        t = model.get_value(itr, 1)
        if not t:
            return True

        txt = self._picons_filter_entry.get_text().upper()
        return txt in t.upper() or t in (
            map(lambda s: s.picon_id, filter(lambda s: txt in s.service.upper(), self._app.current_services.values())))

    def on_picon_activated(self, view):
        if self._info_check_button.get_active():
            model, path = view.get_selection().get_selected_rows()
            if not path:
                return

            row = model[path][:]
            name, path = row[1], row[-1]
            srv = self._services.get(row[1], None)
            self.update_picon_info(name, path, srv)

    def update_picon_info(self, name=None, path=None, srv=None):
        self._picon_info_image.set_from_pixbuf(self.get_pixbuf_at_scale(path, 100, 60, True) if path else None)
        self._picon_info_label.set_text(self.get_service_info(srv))
        self._current_picon_info = (name, srv.fav_id) if srv else None

    def get_service_info(self, srv):
        """ Returns short info about the service. """
        if not srv:
            return ""

        if srv.service_type == "IPTV":
            return self._app.get_hint_for_srv_list(srv)

        header, ref = self._app.get_hint_header_info(srv)
        return "{}  {}: {}\n{}: {}  {}: {}\n{}".format(header.rstrip(), get_message("Package"), srv.package,
                                                       get_message("System"), srv.system, get_message("Freq"), srv.freq,
                                                       ref)

    def on_url_changed(self, entry):
        suit = self._PATTERN.search(entry.get_text())
        entry.set_name("GtkEntry" if suit else "digit-entry")
        self._load_providers_button.set_sensitive(suit if suit else False)

    def on_position_edited(self, render, path, value):
        model = self._providers_view.get_model()
        model.set_value(model.get_iter(path), 2, value)

    @run_idle
    def on_visible_page(self, stack: Gtk.Stack, param):
        name = stack.get_visible_child_name()
        self._convert_button.set_visible(name == "converter")
        is_explorer = name == "explorer"
        self._explorer_action_box.set_visible(is_explorer)
        if is_explorer:
            self.on_picons_dest_changed(self._explorer_dest_path_button)

    @run_idle
    def on_convert(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        picons_path = self._enigma2_path_button.get_filename()
        save_path = self._save_to_button.get_filename()
        if not picons_path or not save_path:
            show_dialog(DialogType.ERROR, transient=self._dialog, text="Select paths!")
            return

        self._expander.set_expanded(True)
        convert_to(src_path=picons_path,
                   dest_path=save_path,
                   s_type=SettingsType.ENIGMA_2,
                   callback=self.append_output,
                   done_callback=lambda: self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO))

    @run_idle
    def update_receive_button_state(self):
        try:
            self._receive_button.set_sensitive(len(self.get_selected_providers()) > 0)
        except TypeError:
            pass  # NOP

    def get_selected_providers(self):
        """ returns selected providers """
        return [r for r in self._providers_view.get_model() if r[7]]

    @run_idle
    def show_dialog(self, message, dialog_type):
        show_dialog(dialog_type, self._dialog, message)

    def get_picons_format(self):
        picon_format = SettingsType.ENIGMA_2

        if self._neutrino_mp_radio_button.get_active():
            picon_format = SettingsType.NEUTRINO_MP

        return picon_format

    def is_task_running(self):
        return self._current_process and self._current_process.poll() is None


if __name__ == "__main__":
    pass

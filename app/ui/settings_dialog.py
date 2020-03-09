import os
import re
from enum import Enum

from app.commons import run_task, run_idle
from app.connections import test_telnet, test_ftp, TestException, test_http, HttpApiException
from app.settings import SettingsType, Settings
from app.ui.dialogs import show_dialog, DialogType
from .main_helper import update_entry_data, scroll_to
from .uicommons import Gtk, Gdk, UI_RESOURCES_PATH, FavClickMode, DEFAULT_ICON


def show_settings_dialog(transient, options):
    return SettingsDialog(transient, options).show()


class Property(Enum):
    FTP = "ftp"
    HTTP = "http"
    TELNET = "telnet"


class SettingsDialog:
    _DIGIT_ENTRY_NAME = "digit-entry"
    _DIGIT_PATTERN = re.compile("(?:^[\\s]*$|\\D)")

    def __init__(self, transient, settings: Settings):
        handlers = {"on_field_icon_press": self.on_field_icon_press,
                    "on_settings_type_changed": self.on_settings_type_changed,
                    "on_reset": self.on_reset,
                    "on_response": self.on_response,
                    "apply_settings": self.apply_settings,
                    "on_apply_profile_settings": self.on_apply_profile_settings,
                    "on_connection_test": self.on_connection_test,
                    "on_info_bar_close": self.on_info_bar_close,
                    "on_set_color_switch": self.on_set_color_switch,
                    "on_http_mode_switch": self.on_http_mode_switch,
                    "on_yt_dl_switch": self.on_yt_dl_switch,
                    "on_default_path_mode_switch": self.on_default_path_mode_switch,
                    "on_default_data_path_changed": self.on_default_data_path_changed,
                    "on_profile_add": self.on_profile_add,
                    "on_profile_edit": self.on_profile_edit,
                    "on_profile_remove": self.on_profile_remove,
                    "on_profile_deleted": self.on_profile_deleted,
                    "on_profile_inserted": self.on_profile_inserted,
                    "on_profile_edited": self.on_profile_edited,
                    "on_profile_selected": self.on_profile_selected,
                    "on_profile_set_default": self.on_profile_set_default,
                    "on_lang_changed": self.on_lang_changed,
                    "on_main_settings_visible": self.on_main_settings_visible,
                    "on_network_settings_visible": self.on_network_settings_visible,
                    "on_http_use_ssl_toggled": self.on_http_use_ssl_toggled,
                    "on_click_mode_togged": self.on_click_mode_togged,
                    "on_transcoding_preset_changed": self.on_transcoding_preset_changed,
                    "on_apply_presets": self.on_apply_presets,
                    "on_digit_entry_changed": self.on_digit_entry_changed,
                    "on_view_popup_menu": self.on_view_popup_menu}

        builder = Gtk.Builder()
        builder.add_from_file(UI_RESOURCES_PATH + "settings_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("settings_dialog")
        self._dialog.set_transient_for(transient)
        self._header_bar = builder.get_object("header_bar")
        self._main_stack = builder.get_object("main_stack")
        # Network
        self._host_field = builder.get_object("host_field")
        self._port_field = builder.get_object("port_field")
        self._login_field = builder.get_object("login_field")
        self._password_field = builder.get_object("password_field")
        self._http_login_field = builder.get_object("http_login_field")
        self._http_password_field = builder.get_object("http_password_field")
        self._http_port_field = builder.get_object("http_port_field")
        self._http_use_ssl_check_button = builder.get_object("http_use_ssl_check_button")
        self._telnet_login_field = builder.get_object("telnet_login_field")
        self._telnet_password_field = builder.get_object("telnet_password_field")
        self._telnet_port_field = builder.get_object("telnet_port_field")
        self._telnet_timeout_spin_button = builder.get_object("telnet_timeout_spin_button")
        self._settings_stack = builder.get_object("settings_stack")
        # Paths
        self._services_field = builder.get_object("services_field")
        self._user_bouquet_field = builder.get_object("user_bouquet_field")
        self._satellites_xml_field = builder.get_object("satellites_xml_field")
        self._data_dir_field = builder.get_object("data_dir_field")
        self._picons_field = builder.get_object("picons_field")
        self._picons_dir_field = builder.get_object("picons_dir_field")
        self._backup_dir_field = builder.get_object("backup_dir_field")
        self._default_data_dir_field = builder.get_object("default_data_dir_field")
        self._record_data_dir_field = builder.get_object("record_data_dir_field")
        self._default_data_paths_switch = builder.get_object("default_data_paths_switch")
        # Info bar
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")
        self._test_spinner = builder.get_object("test_spinner")
        # Settings type
        self._enigma_radio_button = builder.get_object("enigma_radio_button")
        self._neutrino_radio_button = builder.get_object("neutrino_radio_button")
        self._support_ver5_switch = builder.get_object("support_ver5_switch")
        # Streaming
        header_separator = builder.get_object("header_separator")
        self._apply_presets_button = builder.get_object("apply_presets_button")
        self._transcoding_switch = builder.get_object("transcoding_switch")
        self._edit_preset_switch = builder.get_object("edit_preset_switch")
        self._presets_combo_box = builder.get_object("presets_combo_box")
        self._video_bitrate_field = builder.get_object("video_bitrate_field")
        self._video_width_field = builder.get_object("video_width_field")
        self._video_height_field = builder.get_object("video_height_field")
        self._audio_bitrate_field = builder.get_object("audio_bitrate_field")
        self._audio_channels_combo_box = builder.get_object("audio_channels_combo_box")
        self._audio_sample_rate_combo_box = builder.get_object("audio_sample_rate_combo_box")
        self._apply_presets_button.bind_property("visible", header_separator, "visible")
        self._transcoding_switch.bind_property("active", builder.get_object("record_box"), "sensitive")
        self._edit_preset_switch.bind_property("active", self._apply_presets_button, "sensitive")
        self._edit_preset_switch.bind_property("active", builder.get_object("video_options_frame"), "sensitive")
        self._edit_preset_switch.bind_property("active", builder.get_object("audio_options_frame"), "sensitive")
        # Program
        self._before_save_switch = builder.get_object("before_save_switch")
        self._before_downloading_switch = builder.get_object("before_downloading_switch")
        self._program_frame = builder.get_object("program_frame")
        self._extra_support_grid = builder.get_object("extra_support_grid")
        self._colors_grid = builder.get_object("colors_grid")
        self._set_color_switch = builder.get_object("set_color_switch")
        self._new_color_button = builder.get_object("new_color_button")
        self._extra_color_button = builder.get_object("extra_color_button")
        self._load_on_startup_switch = builder.get_object("load_on_startup_switch")
        # HTTP API
        self._support_http_api_switch = builder.get_object("support_http_api_switch")
        self._enable_y_dl_switch = builder.get_object("enable_y_dl_switch")
        self._enable_send_to_switch = builder.get_object("enable_send_to_switch")
        self._click_mode_disabled_button = builder.get_object("click_mode_disabled_button")
        self._click_mode_stream_button = builder.get_object("click_mode_stream_button")
        self._click_mode_play_button = builder.get_object("click_mode_play_button")
        self._click_mode_zap_button = builder.get_object("click_mode_zap_button")
        self._click_mode_zap_and_play_button = builder.get_object("click_mode_zap_and_play_button")
        self._click_mode_zap_button.bind_property("sensitive", self._click_mode_play_button, "sensitive")
        self._click_mode_zap_button.bind_property("sensitive", self._click_mode_zap_and_play_button, "sensitive")
        self._click_mode_zap_button.bind_property("sensitive", self._enable_send_to_switch, "sensitive")
        self._enable_send_to_switch.bind_property("sensitive", builder.get_object("enable_send_to_label"), "sensitive")
        self._extra_support_grid.bind_property("sensitive", builder.get_object("v5_support_grid"), "sensitive")
        # Profiles
        self._profile_view = builder.get_object("profile_tree_view")
        self._profile_add_button = builder.get_object("profile_add_button")
        self._profile_remove_button = builder.get_object("profile_remove_button")
        self._apply_profile_button = builder.get_object("apply_profile_button")
        self._apply_profile_button.bind_property("visible", header_separator, "visible")
        self._apply_profile_button.bind_property("visible", builder.get_object("reset_button"), "visible")
        # Language
        self._lang_combo_box = builder.get_object("lang_combo_box")
        # Style
        self._style_provider = Gtk.CssProvider()
        self._style_provider.load_from_path(UI_RESOURCES_PATH + "style.css")
        self._digit_elems = (self._port_field, self._http_port_field, self._telnet_port_field, self._video_width_field,
                             self._video_bitrate_field, self._video_height_field, self._audio_bitrate_field)
        for el in self._digit_elems:
            el.get_style_context().add_provider_for_screen(Gdk.Screen.get_default(), self._style_provider,
                                                           Gtk.STYLE_PROVIDER_PRIORITY_USER)
        # Settings
        self._ext_settings = settings
        self._settings = Settings(settings.settings)
        self._profiles = self._settings.profiles
        self._s_type = self._settings.setting_type
        self.set_settings()
        self.init_ui_elements(self._s_type)
        self.init_profiles()

    @run_idle
    def init_ui_elements(self, s_type):
        is_enigma_profile = s_type is SettingsType.ENIGMA_2
        self._neutrino_radio_button.set_active(s_type is SettingsType.NEUTRINO_MP)
        self.update_header_bar()
        self._settings_stack.get_child_by_name(Property.HTTP.value).set_visible(is_enigma_profile)
        self._program_frame.set_sensitive(is_enigma_profile)
        self._extra_support_grid.set_sensitive(is_enigma_profile)
        http_active = self._support_http_api_switch.get_active()
        self._click_mode_zap_button.set_sensitive(is_enigma_profile and http_active)
        self._lang_combo_box.set_active_id(self._settings.language)
        self.on_info_bar_close() if is_enigma_profile else self.show_info_message(
            "The Neutrino has only experimental support. Not all features are supported!", Gtk.MessageType.WARNING)

    def init_profiles(self):
        p_def = self._settings.default_profile
        model = self._profile_view.get_model()
        for ind, p in enumerate(self._profiles):
            icon = DEFAULT_ICON if p == p_def else None
            model.append((p, icon))
            if icon:
                scroll_to(ind, self._profile_view)
        self._profile_remove_button.set_sensitive(len(self._profile_view.get_model()) > 1)

    def update_header_bar(self):
        label, sep, st = self._header_bar.get_subtitle().partition(":")
        if self._s_type is SettingsType.ENIGMA_2:
            self._header_bar.set_subtitle("{}: {}".format(label, self._enigma_radio_button.get_label()))
        elif self._s_type is SettingsType.NEUTRINO_MP:
            self._header_bar.set_subtitle("{}: {}".format(label, self._neutrino_radio_button.get_label()))

    def show(self):
        self._dialog.run()

    def on_response(self, dialog, resp):
        if resp == Gtk.ResponseType.OK and not self.apply_settings():
            return

        self._dialog.destroy()
        return resp

    def on_field_icon_press(self, entry, icon, event_button):
        update_entry_data(entry, self._dialog, self._settings)

    def on_settings_type_changed(self, item):
        s_type = SettingsType.ENIGMA_2 if self._enigma_radio_button.get_active() else SettingsType.NEUTRINO_MP
        if s_type is not self._s_type:
            self._settings.setting_type = s_type
            self._s_type = s_type
            self.on_reset()
        self.init_ui_elements(s_type)

    def on_reset(self, item=None):
        self._settings.reset()
        self.set_settings()

    def set_settings(self):
        self._s_type = self._settings.setting_type
        self._host_field.set_text(self._settings.host)
        self._port_field.set_text(self._settings.port)
        self._login_field.set_text(self._settings.user)
        self._password_field.set_text(self._settings.password)
        self._http_login_field.set_text(self._settings.http_user)
        self._http_password_field.set_text(self._settings.http_password)
        self._http_port_field.set_text(self._settings.http_port)
        self._http_use_ssl_check_button.set_active(self._settings.http_use_ssl)
        self._telnet_login_field.set_text(self._settings.telnet_user)
        self._telnet_password_field.set_text(self._settings.telnet_password)
        self._telnet_port_field.set_text(self._settings.telnet_port)
        self._telnet_timeout_spin_button.set_value(self._settings.telnet_timeout)
        self._services_field.set_text(self._settings.services_path)
        self._user_bouquet_field.set_text(self._settings.user_bouquet_path)
        self._satellites_xml_field.set_text(self._settings.satellites_xml_path)
        self._picons_field.set_text(self._settings.picons_path)
        self._data_dir_field.set_text(self._settings.data_local_path)
        self._picons_dir_field.set_text(self._settings.picons_local_path)
        self._backup_dir_field.set_text(self._settings.backup_local_path)
        self._default_data_dir_field.set_text(self._settings.default_data_path)
        self._record_data_dir_field.set_text(self._settings.records_path)
        self._before_save_switch.set_active(self._settings.backup_before_save)
        self._before_downloading_switch.set_active(self._settings.backup_before_downloading)
        self.set_fav_click_mode(self._settings.fav_click_mode)
        self._load_on_startup_switch.set_active(self._settings.load_last_config)
        self._default_data_paths_switch.set_active(self._settings.profile_folder_is_default)
        self._transcoding_switch.set_active(self._settings.activate_transcoding)
        self._presets_combo_box.set_active_id(self._settings.active_preset)
        self.on_transcoding_preset_changed(self._presets_combo_box)

        if self._s_type is SettingsType.ENIGMA_2:
            self._support_ver5_switch.set_active(self._settings.v5_support)
            self._support_http_api_switch.set_active(self._settings.http_api_support)
            self._enable_y_dl_switch.set_active(self._settings.enable_yt_dl)
            self._enable_send_to_switch.set_active(self._settings.enable_send_to)
            self._set_color_switch.set_active(self._settings.use_colors)
            new_rgb = Gdk.RGBA()
            new_rgb.parse(self._settings.new_color)
            extra_rgb = Gdk.RGBA()
            extra_rgb.parse(self._settings.extra_color)
            self._new_color_button.set_rgba(new_rgb)
            self._extra_color_button.set_rgba(extra_rgb)

        if self._s_type is SettingsType.ENIGMA_2:
            self._enigma_radio_button.activate()
        else:
            self._neutrino_radio_button.activate()

    def on_apply_profile_settings(self, item):
        if not self.is_data_correct(self._digit_elems):
            show_dialog(DialogType.ERROR, self._dialog, "Error. Verify the data!")
            return

        self._s_type = SettingsType.ENIGMA_2 if self._enigma_radio_button.get_active() else SettingsType.NEUTRINO_MP
        self._settings.setting_type = self._s_type
        self._settings.host = self._host_field.get_text()
        self._settings.port = self._port_field.get_text()
        self._settings.user = self._login_field.get_text()
        self._settings.password = self._password_field.get_text()
        self._settings.http_user = self._http_login_field.get_text()
        self._settings.http_password = self._http_password_field.get_text()
        self._settings.http_port = self._http_port_field.get_text()
        self._settings.http_use_ssl = self._http_use_ssl_check_button.get_active()
        self._settings.telnet_user = self._telnet_login_field.get_text()
        self._settings.telnet_password = self._telnet_password_field.get_text()
        self._settings.telnet_port = self._telnet_port_field.get_text()
        self._settings.telnet_timeout = int(self._telnet_timeout_spin_button.get_value())
        self._settings.services_path = self._services_field.get_text()
        self._settings.user_bouquet_path = self._user_bouquet_field.get_text()
        self._settings.satellites_xml_path = self._satellites_xml_field.get_text()
        self._settings.picons_path = self._picons_field.get_text()
        self._settings.data_local_path = self._data_dir_field.get_text()
        self._settings.picons_local_path = self._picons_dir_field.get_text()
        self._settings.backup_local_path = self._backup_dir_field.get_text()

    def apply_settings(self, item=None):
        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        self._ext_settings.profiles = self._settings.profiles
        self._ext_settings.backup_before_save = self._before_save_switch.get_active()
        self._ext_settings.backup_before_downloading = self._before_downloading_switch.get_active()
        self._ext_settings.fav_click_mode = self.get_fav_click_mode()
        self._ext_settings.language = self._lang_combo_box.get_active_id()
        self._ext_settings.load_last_config = self._load_on_startup_switch.get_active()
        self._ext_settings.profile_folder_is_default = self._default_data_paths_switch.get_active()
        self._ext_settings.default_data_path = self._default_data_dir_field.get_text()
        self._ext_settings.records_path = self._record_data_dir_field.get_text()
        self._ext_settings.activate_transcoding = self._transcoding_switch.get_active()
        self._ext_settings.active_preset = self._presets_combo_box.get_active_id()

        if self._s_type is SettingsType.ENIGMA_2:
            self._ext_settings.use_colors = self._set_color_switch.get_active()
            self._ext_settings.new_color = self._new_color_button.get_rgba().to_string()
            self._ext_settings.extra_color = self._extra_color_button.get_rgba().to_string()
            self._ext_settings.v5_support = self._support_ver5_switch.get_active()
            self._ext_settings.http_api_support = self._support_http_api_switch.get_active()
            self._ext_settings.enable_yt_dl = self._enable_y_dl_switch.get_active()
            self._ext_settings.enable_send_to = self._enable_send_to_switch.get_active()

        self._ext_settings.default_profile = list(filter(lambda r: r[1], self._profile_view.get_model()))[0][0]
        self._ext_settings.save()
        return True

    @run_task
    def on_connection_test(self, item):
        if self._test_spinner.get_state() is Gtk.StateType.ACTIVE:
            return
        self.show_spinner(True)
        current_property = Property(self._settings_stack.get_visible_child_name())
        if current_property is Property.HTTP:
            self.test_http()
        elif current_property is Property.TELNET:
            self.test_telnet()
        elif current_property is Property.FTP:
            self.test_ftp()

    def test_http(self):
        user, password = self._http_login_field.get_text(), self._http_password_field.get_text()
        host, port = self._host_field.get_text(), self._http_port_field.get_text()
        use_ssl = self._http_use_ssl_check_button.get_active()
        try:
            self.show_info_message(test_http(host, port, user, password, use_ssl=use_ssl), Gtk.MessageType.INFO)
        except TestException as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        except HttpApiException as e:
            self.show_info_message(str(e), Gtk.MessageType.WARNING)
        finally:
            self.show_spinner(False)

    def test_telnet(self):
        timeout = int(self._telnet_timeout_spin_button.get_value())
        host, port = self._host_field.get_text(), self._telnet_port_field.get_text()
        user, password = self._telnet_login_field.get_text(), self._telnet_password_field.get_text()
        try:
            self.show_info_message(test_telnet(host, port, user, password, timeout), Gtk.MessageType.INFO)
            self.show_spinner(False)
        except TestException as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
            self.show_spinner(False)

    def test_ftp(self):
        host, port = self._host_field.get_text(), self._port_field.get_text()
        user, password = self._login_field.get_text(), self._password_field.get_text()
        try:
            self.show_info_message("OK.  {}".format(test_ftp(host, port, user, password)), Gtk.MessageType.INFO)
        except TestException as e:
            self.show_info_message(str(e), Gtk.MessageType.ERROR)
        finally:
            self.show_spinner(False)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)

    @run_idle
    def show_spinner(self, show):
        self._test_spinner.start() if show else self._test_spinner.stop()
        self._test_spinner.set_state(Gtk.StateType.ACTIVE if show else Gtk.StateType.NORMAL)

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    def on_set_color_switch(self, switch, state):
        self._colors_grid.set_sensitive(state)

    def on_http_mode_switch(self, switch, state):
        self._click_mode_zap_button.set_sensitive(state)
        if any((self._click_mode_play_button.get_active(),
                self._click_mode_zap_button.get_active(),
                self._click_mode_zap_and_play_button.get_active())):
            self._click_mode_disabled_button.set_active(True)

    def on_yt_dl_switch(self, switch, state):
        self.show_info_message("Not implemented yet!", Gtk.MessageType.WARNING)

    def on_default_path_mode_switch(self, switch, state):
        self._settings.profile_folder_is_default = state

    def on_default_data_path_changed(self, entry):
        self._settings.default_data_path = entry.get_text()

    def on_profile_add(self, item):
        model = self._profile_view.get_model()
        count = 0
        name = "profile"
        while name in self._profiles:
            count += 1
            name = "profile{}".format(count)

        self._profiles[name] = self._s_type.get_default_settings()
        model.append((name, None))
        scroll_to(len(model) - 1, self._profile_view)
        self.on_profile_selected(self._profile_view)
        self.on_reset()

    def on_profile_edit(self, item=None):
        model, paths = self._profile_view.get_selection().get_selected_rows()
        self._profile_view.set_cursor(paths, self._profile_view.get_column(0), True)

    def on_profile_remove(self, item):
        model, paths = self._profile_view.get_selection().get_selected_rows()
        if paths:
            row = model[paths]
            is_default = row[1]
            self._profiles.pop(row[0], None)
            del model[paths]

            if is_default:
                model.set_value(model.get_iter_first(), 1, DEFAULT_ICON)

    def on_profile_deleted(self, model, paths):
        self._profile_remove_button.set_sensitive(len(model) > 1)

    def on_profile_edited(self, render, path, new_value):
        row = self._profile_view.get_model()[path]
        old_name = row[0]
        if old_name == new_value:
            return

        if new_value in self._profiles:
            show_dialog(DialogType.ERROR, self._dialog, "A profile with that name exists!")
            return

        p_settings = self._profiles.pop(old_name, None)
        if p_settings:
            row[0] = new_value
            self._profiles[new_value] = p_settings
            self.update_local_paths(new_value, old_name)
        self.on_profile_selected(self._profile_view)

    def update_local_paths(self, p_name, old_name, force_rename=False):
        data_path = self._settings.data_local_path
        picons_path = self._settings.picons_local_path
        backup_path = self._settings.backup_local_path

        self._settings.data_local_path = p_name.join(data_path.rsplit(old_name, 1))
        self._settings.picons_local_path = p_name.join(picons_path.rsplit(old_name, 1))
        self._settings.backup_local_path = p_name.join(backup_path.rsplit(old_name, 1))

        if force_rename:
            try:
                if os.path.isdir(picons_path):
                    os.rename(picons_path, self._settings.picons_local_path)
                if os.path.isdir(data_path):
                    os.rename(data_path, self._settings.data_local_path)
                if os.path.isdir(backup_path):
                    os.rename(backup_path, self._settings.backup_local_path)
            except OSError as e:
                self.show_info_message(str(e), Gtk.MessageType.ERROR)

    def on_profile_selected(self, view):
        model, paths = self._profile_view.get_selection().get_selected_rows()
        if paths:
            profile = model.get_value(model.get_iter(paths), 0)
            self._settings.current_profile = profile
            self.set_settings()

    def on_profile_set_default(self, item):
        model, paths = self._profile_view.get_selection().get_selected_rows()
        if paths:
            itr = model.get_iter(paths)
            model.foreach(lambda m, p, i: model.set_value(i, 1, None))
            model.set_value(itr, 1, DEFAULT_ICON)
            self._settings.default_profile = model.get_value(itr, 0)

    def on_profile_inserted(self, model, path, itr):
        self._profile_remove_button.set_sensitive(len(model) > 1)

    def on_lang_changed(self, box):
        if box.get_active_id() != self._settings.language:
            self.show_info_message("Save and restart the program to apply the settings.", Gtk.MessageType.WARNING)

    def on_main_settings_visible(self, stack, param):
        name = stack.get_visible_child_name()
        self._apply_profile_button.set_visible(name == "profiles")
        self._apply_presets_button.set_visible(name == "streaming")

    def on_network_settings_visible(self, stack, param):
        self._http_use_ssl_check_button.set_visible(Property(stack.get_visible_child_name()) is Property.HTTP)

    def on_http_use_ssl_toggled(self, button):
        active = button.get_active()
        self._settings.http_use_ssl = active
        port = "443" if active else "80"
        self._http_port_field.set_text(port)
        self._settings.http_port = port

    def on_click_mode_togged(self, button):
        if self._main_stack.get_visible_child_name() != "extra":
            return

        mode = self.get_fav_click_mode()
        if mode is FavClickMode.PLAY:
            self.show_info_message("Operates in standby mode or current active transponder!", Gtk.MessageType.WARNING)
        else:
            self.on_info_bar_close()

    @run_idle
    def set_fav_click_mode(self, mode):
        mode = FavClickMode(mode)
        self._click_mode_disabled_button.set_active(mode is FavClickMode.DISABLED)
        self._click_mode_stream_button.set_active(mode is FavClickMode.STREAM)
        self._click_mode_play_button.set_active(mode is FavClickMode.PLAY)
        self._click_mode_zap_button.set_active(mode is FavClickMode.ZAP)
        self._click_mode_zap_and_play_button.set_active(mode is FavClickMode.ZAP_PLAY)

    def get_fav_click_mode(self):
        if self._click_mode_zap_button.get_active():
            return FavClickMode.ZAP
        if self._click_mode_play_button.get_active():
            return FavClickMode.PLAY
        if self._click_mode_zap_and_play_button.get_active():
            return FavClickMode.ZAP_PLAY
        if self._click_mode_stream_button.get_active():
            return FavClickMode.STREAM

        return FavClickMode.DISABLED

    def on_transcoding_preset_changed(self, button):
        presets = self._settings.transcoding_presets
        prs = presets.get(button.get_active_id())
        self._video_bitrate_field.set_text(prs.get("vb", "0"))
        self._video_width_field.set_text(prs.get("width", "0"))
        self._video_height_field.set_text(prs.get("height", "0"))
        self._audio_bitrate_field.set_text(prs.get("ab", "0"))
        self._audio_channels_combo_box.set_active_id(prs.get("channels", "2"))
        self._audio_sample_rate_combo_box.set_active_id(prs.get("samplerate", "44100"))

    def on_apply_presets(self, item):
        if not self.is_data_correct(self._digit_elems):
            show_dialog(DialogType.ERROR, self._dialog, "Error. Verify the data!")
            return

        if show_dialog(DialogType.QUESTION, self._dialog) == Gtk.ResponseType.CANCEL:
            return

        presets = self._settings.transcoding_presets
        prs = presets.get(self._presets_combo_box.get_active_id())
        prs["vb"] = self._video_bitrate_field.get_text()
        prs["width"] = self._video_width_field.get_text()
        prs["height"] = self._video_height_field.get_text()
        prs["ab"] = self._audio_bitrate_field.get_text()
        prs["channels"] = self._audio_channels_combo_box.get_active_id()
        prs["samplerate"] = self._audio_sample_rate_combo_box.get_active_id()
        self._ext_settings.transcoding_presets = presets
        self._edit_preset_switch.set_active(False)

    def on_digit_entry_changed(self, entry):
        if self._DIGIT_PATTERN.search(entry.get_text()):
            entry.set_name(self._DIGIT_ENTRY_NAME)
        else:
            entry.set_name("GtkEntry")

    def is_data_correct(self, elems):
        return not any(elem.get_name() == self._DIGIT_ENTRY_NAME for elem in elems)

    def on_view_popup_menu(self, menu, event):
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_SECONDARY:
            menu.popup(None, None, None, None, event.button, event.time)


if __name__ == "__main__":
    pass

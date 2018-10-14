from gi.repository import GLib

from app.commons import run_idle, run_task
from app.ftp import download_data, DownloadType, upload_data
from app.properties import Profile
from .uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN
from .dialogs import show_dialog, DialogType, get_message


class DownloadDialog:
    def __init__(self, transient, properties, open_data_callback, profile=Profile.ENIGMA_2):
        self._properties = properties
        self._open_data_callback = open_data_callback
        self._profile = profile

        handlers = {"on_receive": self.on_receive,
                    "on_send": self.on_send,
                    "on_info_bar_close": self.on_info_bar_close}

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_from_file(UI_RESOURCES_PATH + "download_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("download_dialog")
        self._dialog.set_transient_for(transient)
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")
        self._host_entry = builder.get_object("host_entry").set_text(properties["host"])
        self._data_path_entry = builder.get_object("data_path_entry").set_text(properties["data_dir_path"])
        self._remove_unused_check_button = builder.get_object("remove_unused_check_button")
        self._all_radio_button = builder.get_object("all_radio_button")
        self._bouquets_radio_button = builder.get_object("bouquets_radio_button")
        self._satellites_radio_button = builder.get_object("satellites_radio_button")
        self._webtv_radio_button = builder.get_object("webtv_radio_button")
        if profile is Profile.NEUTRINO_MP:
            self._webtv_radio_button.set_visible(True)

    def show(self):
        self._dialog.run()
        self._dialog.destroy()

    @run_idle
    def on_receive(self, item):
        self.download(True, self.get_download_type())

    @run_idle
    def on_send(self, item):
        if show_dialog(DialogType.QUESTION, self._dialog) != Gtk.ResponseType.CANCEL:
            self.download(False, self.get_download_type())

    def get_download_type(self):
        download_type = DownloadType.ALL
        if self._bouquets_radio_button.get_active():
            download_type = DownloadType.BOUQUETS
        elif self._satellites_radio_button.get_active():
            download_type = DownloadType.SATELLITES
        elif self._webtv_radio_button.get_active():
            download_type = DownloadType.WEBTV
        return download_type

    def run(self):
        return self._dialog.run()

    def destroy(self):
        self._dialog.destroy()

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_task
    def download(self, download, d_type):
        """ Download/upload data from/to receiver """
        try:
            if download:
                download_data(properties=self._properties, download_type=d_type)
            else:
                self.show_info_message(get_message("Please, wait..."), Gtk.MessageType.INFO)
                upload_data(properties=self._properties,
                            download_type=d_type,
                            remove_unused=self._remove_unused_check_button.get_active(),
                            profile=self._profile,
                            callback=lambda: self.show_info_message(get_message("Done!"), Gtk.MessageType.INFO))
        except Exception as e:
            message = str(getattr(e, "message", str(e)))
            self.show_info_message(message, Gtk.MessageType.ERROR)
        else:
            if download and d_type is not DownloadType.SATELLITES:
                GLib.idle_add(self._open_data_callback)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)


if __name__ == "__main__":
    pass

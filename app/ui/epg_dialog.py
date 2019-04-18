from app.commons import run_idle
from app.tools.epg import EPG
from .main_helper import on_popup_menu
from .uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN


class EpgDialog:

    def __init__(self, transient, options, services, fav_model):

        handlers = {"on_info_bar_close": self.on_info_bar_close,
                    "on_popup_menu": on_popup_menu}

        self._services = services
        self._ex_fav_model = fav_model
        self._options = options

        builder = Gtk.Builder()
        builder.set_translation_domain(TEXT_DOMAIN)
        builder.add_from_file(UI_RESOURCES_PATH + "epg_dialog.glade")
        builder.connect_signals(handlers)

        self._dialog = builder.get_object("epg_dialog_window")
        self._dialog.set_transient_for(transient)
        self._bouquet_model = builder.get_object("bouquet_list_store")
        self._services_model = builder.get_object("services_list_store")
        self._info_bar = builder.get_object("info_bar")
        self._message_label = builder.get_object("info_bar_message_label")

        self.init_data()

    @run_idle
    def init_data(self):
        for r in self._ex_fav_model:
            self._bouquet_model.append(r[:])

        try:
            refs = EPG.get_epg_refs(self._options.get("data_dir_path", "") + "epg.dat")

            # for source lamedb
            srvs = {k[:k.rfind(":")]: v for k, v in self._services.items()}
            list(map(self._services_model.append,
                     map(lambda s: (s.service, s.fav_id),
                         filter(None, [srvs.get(ref) for ref in refs]))))

        except (FileNotFoundError, ValueError) as e:
            self.show_info_message("Read epg.dat error: {}".format(e), Gtk.MessageType.ERROR)
        else:
            if len(self._services_model) == 0:
                msg = "Current epg.dat file does not contains references for the services of this bouquet!"
                self.show_info_message(msg, Gtk.MessageType.ERROR)

    def show(self):
        self._dialog.show()

    def on_info_bar_close(self, bar=None, resp=None):
        self._info_bar.set_visible(False)

    @run_idle
    def show_info_message(self, text, message_type):
        self._info_bar.set_visible(True)
        self._info_bar.set_message_type(message_type)
        self._message_label.set_text(text)


if __name__ == "__main__":
    pass

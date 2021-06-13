""" Common module for showing dialogs """
import locale
from enum import Enum
from functools import lru_cache
from pathlib import Path

from app.commons import run_idle
from .uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN, IS_GNOME_SESSION


class Dialog(Enum):
    MESSAGE = """
    <?xml version="1.0" encoding="UTF-8"?>
    <interface>
      <requires lib="gtk+" version="3.16"/>
      <object class="GtkMessageDialog" id="message_dialog">
        <property name="use-header-bar">{use_header}</property>
        <property name="can_focus">False</property>
        <property name="modal">True</property>
        <property name="default_width">320</property>
        <property name="destroy_with_parent">True</property>
        <property name="type_hint">dialog</property>
        <property name="skip_taskbar_hint">True</property>
        <property name="skip_pager_hint">True</property>
        <property name="gravity">center</property>
        <property name="message_type">{message_type}</property>
        <property name="buttons">{buttons_type}</property>
      </object>
    </interface>
  """


class Action(Enum):
    EDIT = 0
    ADD = 1


class DialogType(Enum):
    INPUT = "input"
    CHOOSER = "chooser"
    ERROR = "error"
    QUESTION = "question"
    INFO = "info"
    ABOUT = "about"
    WAIT = "wait"

    def __str__(self):
        return self.value


class WaitDialog:
    def __init__(self, transient, text=None):
        builder, dialog = get_dialog_from_xml(DialogType.WAIT, transient)
        self._dialog = dialog
        self._dialog.set_transient_for(transient)
        self._label = builder.get_object("wait_dialog_label")
        self._default_text = text or self._label.get_text()

    def show(self, text=None):
        self.set_text(text)
        self._dialog.show()

    @run_idle
    def set_text(self, text):
        self._label.set_text(get_message(text or self._default_text))

    @run_idle
    def hide(self):
        self._dialog.hide()

    @run_idle
    def destroy(self):
        self._dialog.destroy()


def show_dialog(dialog_type, transient, text=None, settings=None, action_type=None, file_filter=None, buttons=None,
                title=None, create_dir=False):
    """ Shows dialogs by name. """
    if dialog_type in (DialogType.INFO, DialogType.ERROR):
        return get_message_dialog(transient, dialog_type, Gtk.ButtonsType.OK, text)
    elif dialog_type is DialogType.CHOOSER and settings:
        return get_file_chooser_dialog(transient, text, settings, action_type, file_filter, buttons, title, create_dir)
    elif dialog_type is DialogType.INPUT:
        return get_input_dialog(transient, text)
    elif dialog_type is DialogType.QUESTION:
        action = action_type if action_type else Gtk.ButtonsType.OK_CANCEL
        return get_message_dialog(transient, DialogType.QUESTION, action, text or "Are you sure?")
    elif dialog_type is DialogType.ABOUT:
        return get_about_dialog(transient)


def get_chooser_dialog(transient, settings, name, patterns, title=None):
    file_filter = Gtk.FileFilter()
    file_filter.set_name(name)
    for p in patterns:
        file_filter.add_pattern(p)

    return show_dialog(dialog_type=DialogType.CHOOSER,
                       transient=transient,
                       settings=settings,
                       action_type=Gtk.FileChooserAction.OPEN,
                       file_filter=file_filter,
                       title=title)


def get_file_chooser_dialog(transient, text, settings, action_type, file_filter, buttons=None, title=None, dirs=False):
    text = get_message(text) if text else ""
    action_type = Gtk.FileChooserAction.SELECT_FOLDER if action_type is None else action_type
    buttons = buttons or (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
    dialog = Gtk.FileChooserDialog(text, transient, action_type, buttons, use_header_bar=IS_GNOME_SESSION)
    dialog.set_title(get_message(title) if title else "")
    dialog.set_create_folders(dirs)

    if file_filter is not None:
        dialog.add_filter(file_filter)

    dialog.set_current_folder(settings.data_local_path)
    response = dialog.run()

    if response not in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
        path = Path(dialog.get_filename() or dialog.get_current_folder())
        if path.is_dir():
            response = "{}/".format(path.resolve())
        elif path.is_file():
            response = str(path.resolve())
    dialog.destroy()

    return response


def get_input_dialog(transient, text):
    builder, dialog = get_dialog_from_xml(DialogType.INPUT, transient, use_header=IS_GNOME_SESSION)
    entry = builder.get_object("input_entry")
    entry.set_text(text if text else "")
    response = dialog.run()
    txt = entry.get_text()
    dialog.destroy()

    return txt if response == Gtk.ResponseType.OK else Gtk.ResponseType.CANCEL


def get_message_dialog(transient, message_type, buttons_type, text):
    builder = Gtk.Builder()
    builder.set_translation_domain(TEXT_DOMAIN)
    dialog_str = Dialog.MESSAGE.value.format(use_header=0, message_type=message_type, buttons_type=int(buttons_type))
    builder.add_from_string(dialog_str)
    dialog = builder.get_object("message_dialog")
    dialog.set_transient_for(transient)
    dialog.set_markup(get_message(text))
    response = dialog.run()
    dialog.destroy()

    return response


def get_about_dialog(transient):
    builder, dialog = get_dialog_from_xml(DialogType.ABOUT, transient)
    dialog.set_transient_for(transient)
    response = dialog.run()
    dialog.destroy()

    return response


def get_dialog_from_xml(dialog_type, transient, use_header=0, title=""):
    dialog_name = dialog_type.value + "_dialog"
    builder = Gtk.Builder()
    builder.set_translation_domain(TEXT_DOMAIN)
    dialog_str = get_dialogs_string(UI_RESOURCES_PATH + "dialogs.glade").format(use_header=use_header, title=title)
    builder.add_objects_from_string(dialog_str, (dialog_name,))
    dialog = builder.get_object(dialog_name)
    dialog.set_transient_for(transient)

    return builder, dialog


def get_message(message):
    """ returns translated message """
    return locale.dgettext(TEXT_DOMAIN, message)


@lru_cache(maxsize=5)
def get_dialogs_string(path):
    with open(path, "r") as f:
        return "".join(f)


def get_builder(path, handlers=None, use_str=False, objects=None):
    """ Creates and returns a Gtk.Builder instance. """
    builder = Gtk.Builder()
    builder.set_translation_domain(TEXT_DOMAIN)

    if use_str:
        if objects:
            builder.add_objects_from_string(get_dialogs_string(path).format(use_header=IS_GNOME_SESSION), objects)
        else:
            builder.add_from_string(get_dialogs_string(path).format(use_header=IS_GNOME_SESSION))
    else:
        if objects:
            builder.add_objects_from_file(path, objects)
        else:
            builder.add_from_file(path)

    builder.connect_signals(handlers or {})

    return builder


if __name__ == "__main__":
    pass

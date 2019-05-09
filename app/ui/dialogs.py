""" Common module for showing dialogs """
import locale
import os
from enum import Enum

from app.commons import run_idle
from .uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN

_IS_GNOME_SESSION = int(bool(os.environ.get("GNOME_DESKTOP_SESSION_ID")))


class Button(Enum):
    OK = """
    <child type="action">
          <object class="GtkButton" id="ok_button">
            <property name="label">gtk-ok</property>
            <property name="visible">True</property>
            <property name="can_focus">True</property>
            <property name="receives_default">True</property>
            <property name="use_stock">True</property>
            <property name="always_show_image">True</property>
          </object>
        </child>
    """
    CANCEL = """
    <child type="action">
          <object class="GtkButton" id="cancel_button">
            <property name="label">gtk-cancel</property>
            <property name="visible">True</property>
            <property name="can_focus">True</property>
            <property name="receives_default">True</property>
            <property name="use_stock">True</property>
            <property name="always_show_image">True</property>
          </object>
        </child>
    """

    def __str__(self):
        return self.value


class ButtonAction(Enum):
    CANCEL = '<action-widget response="-6">cancel_button</action-widget>'
    OK = '<action-widget response="-5">ok_button</action-widget>'

    def __str__(self):
        return self.value


class Dialog(Enum):
    INPUT = """
    <?xml version="1.0" encoding="UTF-8"?>
    <interface>
      <requires lib="gtk+" version="3.16"/>
      <object class="GtkDialog" id="input_dialog">
        <property name="use-header-bar">{use_header}</property>
        <property name="default_width">320</property>
        <property name="resizable">False</property>
        <property name="modal">True</property>
        <property name="title" translatable="yes">{title}</property>
        <property name="can_focus">False</property>
        <property name="type_hint">dialog</property>
        <property name="skip_taskbar_hint">True</property>
        <property name="skip_pager_hint">True</property>
        <property name="gravity">center</property>
        {cancel_button}
        {ok_button}
        <child>
          <placeholder/>
        </child>
        <child internal-child="vbox">
          <object class="GtkBox">
            <property name="can_focus">False</property>
            <property name="orientation">vertical</property>
            <property name="spacing">2</property>
            <child>
              <object class="GtkEntry" id="input_entry">
                <property name="visible">True</property>
                <property name="can_focus">True</property>
                <property name="primary_icon_stock">gtk-edit</property>
                <property name="primary_icon_activatable">False</property>
                <property name="secondary_icon_activatable">False</property>
                <property name="secondary_icon_sensitive">False</property>
              </object>
              <packing>
                <property name="expand">False</property>
                <property name="fill">True</property>
                <property name="position">1</property>
              </packing>
            </child>
          </object>
        </child>
        <action-widgets>
          {cancel_action}
          {ok_action}
        </action-widgets>
      </object>
    </interface>
    """
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
        <property name="text" translatable="yes">{text}</property>
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
        if text is not None:
            builder.get_object("wait_dialog_label").set_text(text)

    def show(self):
        self._dialog.show()

    @run_idle
    def hide(self):
        self._dialog.hide()

    @run_idle
    def destroy(self):
        self._dialog.destroy()


def show_dialog(dialog_type: DialogType, transient, text=None, options=None, action_type=None, file_filter=None):
    """ Shows dialogs by name """
    if dialog_type in (DialogType.INFO, DialogType.ERROR):
        return get_message_dialog(transient, dialog_type, Gtk.ButtonsType.OK, text)
    elif dialog_type is DialogType.CHOOSER and options:
        return get_file_chooser_dialog(transient, text, options, action_type, file_filter)
    elif dialog_type is DialogType.INPUT:
        return get_input_dialog(transient, text)
    elif dialog_type is DialogType.QUESTION:
        return get_message_dialog(transient, DialogType.QUESTION, Gtk.ButtonsType.OK_CANCEL, "Are you sure?")
    elif dialog_type is DialogType.ABOUT:
        return get_about_dialog(transient)


def get_chooser_dialog(transient, options, pattern, name):
    file_filter = Gtk.FileFilter()
    file_filter.add_pattern(pattern)
    file_filter.set_name(name)

    return show_dialog(dialog_type=DialogType.CHOOSER,
                       transient=transient,
                       options=options,
                       action_type=Gtk.FileChooserAction.OPEN,
                       file_filter=file_filter)


def get_file_chooser_dialog(transient, text, options, action_type, file_filter):
    dialog = Gtk.FileChooserDialog(get_message(text) if text else "", transient,
                                   action_type if action_type is not None else Gtk.FileChooserAction.SELECT_FOLDER,
                                   (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK),
                                   use_header_bar=_IS_GNOME_SESSION)
    if file_filter is not None:
        dialog.add_filter(file_filter)

    path = options.get("data_dir_path")
    dialog.set_current_folder(path)
    response = dialog.run()
    if response == Gtk.ResponseType.OK:
        if dialog.get_filename():
            path = dialog.get_filename()
            if action_type is not Gtk.FileChooserAction.OPEN:
                path = path + "/"
            response = path
    dialog.destroy()

    return response


def get_input_dialog(transient, text):
    builder = Gtk.Builder()
    builder.add_from_string(Dialog.INPUT.value.format(use_header=_IS_GNOME_SESSION, title="",
                                                      ok_button=Button.OK, cancel_button=Button.CANCEL,
                                                      cancel_action=ButtonAction.CANCEL, ok_action=ButtonAction.OK))
    dialog = builder.get_object("input_dialog")
    dialog.set_transient_for(transient)
    entry = builder.get_object("input_entry")
    entry.set_text(text if text else "")
    response = dialog.run()
    txt = entry.get_text()
    dialog.destroy()

    return txt if response == Gtk.ResponseType.OK else Gtk.ResponseType.CANCEL


def get_message_dialog(transient, message_type, buttons_type, text):
    builder = Gtk.Builder()
    builder.set_translation_domain(TEXT_DOMAIN)
    builder.add_from_string(Dialog.MESSAGE.value.format(use_header=0,
                                                        message_type=message_type,
                                                        buttons_type=int(buttons_type),
                                                        text=text))
    dialog = builder.get_object("message_dialog")
    dialog.set_transient_for(transient)
    response = dialog.run()
    dialog.destroy()

    return response


def get_about_dialog(transient):
    builder, dialog = get_dialog_from_xml(DialogType.ABOUT, transient)
    dialog.set_transient_for(transient)
    response = dialog.run()
    dialog.destroy()

    return response


def get_dialog_from_xml(dialog_type, transient):
    dialog_name = dialog_type.value + "_dialog"
    builder = Gtk.Builder()
    builder.set_translation_domain(TEXT_DOMAIN)
    builder.add_objects_from_file(UI_RESOURCES_PATH + "dialogs.glade", (dialog_name,))
    dialog = builder.get_object(dialog_name)
    dialog.set_transient_for(transient)

    return builder, dialog


def get_message(message):
    """ returns translated message """
    return locale.dgettext(TEXT_DOMAIN, message)


if __name__ == "__main__":
    pass

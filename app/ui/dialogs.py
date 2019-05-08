""" Common module for showing dialogs """
import locale
import os
from enum import Enum

from app.commons import run_idle
from .uicommons import Gtk, UI_RESOURCES_PATH, TEXT_DOMAIN

_IS_GNOME_SESSION = int(bool(os.environ.get("GNOME_DESKTOP_SESSION_ID")))


class Button(Enum):
    def __str__(self):
        return self.value

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


class ButtonAction(Enum):
    def __str__(self):
        return self.value

    CANCEL = '<action-widget response="-6">cancel_button</action-widget>'
    OK = '<action-widget response="-5">ok_button</action-widget>'


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
      <object class="GtkMessageDialog" id="message_dialog">
        <property name="use-header-bar">{use_header}</property>
        <property name="width_request">320</property>
        <property name="can_focus">False</property>
        <property name="resizable">False</property>
        <property name="modal">True</property>
        <property name="default_width">320</property>
        <property name="default_height">240</property>
        <property name="destroy_with_parent">True</property>
        <property name="type_hint">dialog</property>
        <property name="message_type">question</property>
        <property name="buttons">ok-cancel</property>
        <property name="text" translatable="yes">{text}</property>
      </object>
    </interface>
  """


class Action(Enum):
    EDIT = 0
    ADD = 1


class DialogType(Enum):
    INPUT = "input_dialog"
    CHOOSER = "path_chooser_dialog"
    ERROR = "error_dialog"
    QUESTION = "question_dialog"
    ABOUT = "about_dialog"
    WAIT = "wait_dialog"
    INFO = "info_dialog"


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
    if dialog_type is DialogType.INFO:
        return get_info_dialog(transient, text)
    elif dialog_type is DialogType.CHOOSER and options:
        return get_file_chooser_dialog(transient, text, options, action_type, file_filter)
    elif dialog_type is DialogType.INPUT:
        return get_input_dialog(transient, text)
    elif dialog_type is DialogType.QUESTION:
        return get_message_dialog(transient, DialogType.QUESTION)
    else:
        builder, dialog = get_dialog_from_xml(dialog_type, transient)
        if text:
            dialog.set_markup(get_message(text))
        response = dialog.run()
        dialog.destroy()

        return response


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


def get_info_dialog(transient, text):
    dialog = Gtk.MessageDialog(text=get_message(text),
                               parent=transient,
                               type=Gtk.MessageType.INFO,
                               buttons=Gtk.ButtonsType.OK,
                               use_header_bar=_IS_GNOME_SESSION)
    dialog.run()
    dialog.destroy()


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


def get_message_dialog(transient, dialog_type):
    builder = Gtk.Builder()
    builder.set_translation_domain(TEXT_DOMAIN)
    builder.add_from_string(Dialog.MESSAGE.value.format(use_header=0, text="Are you sure?"))
    dialog = builder.get_object("message_dialog")
    dialog.set_transient_for(transient)
    response = dialog.run()
    dialog.destroy()
    return response


def get_dialog_from_xml(dialog_type, transient):
    builder = Gtk.Builder()
    builder.set_translation_domain(TEXT_DOMAIN)
    builder.add_objects_from_file(UI_RESOURCES_PATH + "dialogs.glade", (dialog_type.value,))
    dialog = builder.get_object(dialog_type.value)
    dialog.set_transient_for(transient)

    return builder, dialog


def get_message(message):
    """ returns translated message """
    return locale.dgettext(TEXT_DOMAIN, message)


if __name__ == "__main__":
    pass

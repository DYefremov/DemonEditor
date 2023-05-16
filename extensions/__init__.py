# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2023 Dmitriy Yefremov
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

import json
import logging
import os
from pathlib import Path

CONFIG_PATH = f"{Path.home()}{os.sep}.config{os.sep}demon-editor{os.sep}extensions{os.sep}"


class Singleton(type):
    _INSTANCE = None

    def __call__(cls, *args, **kwargs):
        if not cls._INSTANCE:
            cls._INSTANCE = type.__call__(cls, *args, **kwargs)
        return cls._INSTANCE


class BaseExtension(metaclass=Singleton):
    """ Base extension (plugin) class. """
    # The label that will be displayed in the "Tools" menu.
    LABEL = "Base extension"
    VERSION = "1.0"
    # Additional flags.
    EMBEDDED = False
    SWITCHABLE = False

    _LOGGER_NAME = "main_logger"

    def __init__(self, app):
        # Current application instance.
        # It can be used all public methods, properties or signals.
        self.app = app
        self._config_path = f"{CONFIG_PATH}{self.__class__.__name__}{os.sep}config"

        self.log(f"Extension initialized...")

    def exec(self):
        """ Triggers an action for the given extension.

            E.g. shows a dialog or runs an external script.
        """
        self.app.show_info_message(f"Hello from {self.__class__.__name__} class!")

    def stop(self):
        """ Stops (terminates) the task or the extension itself. """
        self.log("Terminating a task...")

    def log(self, message, level=logging.ERROR):
        """ Shows log messages. """
        logging.getLogger(self._LOGGER_NAME).log(level, f"[{self.__class__.__name__}] {message}")

    def reset_config(self):
        path = Path(self._config_path)
        if path.is_file():
            path.unlink()

    @property
    def config(self) -> dict:
        if not Path(self._config_path).is_file():
            return {}

        with open(self._config_path, "r", encoding="utf-8") as config_file:
            try:
                return json.load(config_file)
            except ValueError as e:
                self.log(f"Configuration load error: {e}")
        return {}

    @config.setter
    def config(self, value: dict):
        Path(self._config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as config_file:
            json.dump(value, config_file, indent="    ")


if __name__ == "__main__":
    pass

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

    def __init__(self, app):
        # Current application instance.
        # It can be used all public methods, properties or signals.
        self.app = app

    def exec(self):
        """ Triggers an action for the given extension.

            E.g. shows a dialog or runs an external script.
        """
        self.app.show_info_message(f"Hello from {self.__class__.__name__} class!")


if __name__ == "__main__":
    pass

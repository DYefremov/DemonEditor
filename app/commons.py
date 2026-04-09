# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2026 Dmitriy Yefremov
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
# Author: Dmitriy Yefremov <https://github.com/DYefremov>
#


import logging
from collections import defaultdict
from functools import wraps
from threading import Timer

from gi.repository import GLib
from gi.repository.Gio import Task

_LOG_FILE = "demon-editor.log"
LOG_DATE_FORMAT = "%d-%m-%y %H:%M:%S"
LOGGER_NAME = "main_logger"
LOG_FORMAT = "%(asctime)s %(message)s"


def init_logger():
    logging.Logger(LOGGER_NAME)
    logging.basicConfig(level=logging.INFO,
                        format=LOG_FORMAT,
                        datefmt=LOG_DATE_FORMAT,
                        handlers=[logging.FileHandler(_LOG_FILE), logging.StreamHandler()])
    log("Logging is enabled.", level=logging.INFO)


def log(message, level=logging.ERROR, debug=False, fmt_message="{}"):
    """ The main logging function. """
    logger = logging.getLogger(LOGGER_NAME)
    if debug:
        from traceback import format_exc
        logger.log(level, fmt_message.format(format_exc()))
    else:
        logger.log(level, message)


def run_idle(func):
    """ Runs a function with a lower priority """

    @wraps(func)
    def wrapper(*args, **kwargs):
        GLib.idle_add(func, *args, **kwargs)

    return wrapper


def run_task(func):
    """ Runs a function in a separate thread. """

    @wraps(func)
    def wrapper(*args, **kwargs):
        task = Task()
        task.run_in_thread(lambda t, s, d, c: func(*args, **kwargs))

    return wrapper


def run_with_delay(timeout=5):
    """  Starts the function with a delay.

         If the previous timer still works, it will canceled!
     """

    def run_with(func):
        timer = None

        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal timer
            if timer and timer.is_alive():
                timer.cancel()

            def run():
                GLib.idle_add(func, *args, **kwargs, priority=GLib.PRIORITY_LOW)

            timer = Timer(interval=timeout, function=run)
            timer.start()

        return wrapper

    return run_with


def get_size_from_bytes(size):
    """ Simple convert function from bytes to other units like K, M or G. """
    try:
        b = float(size)
    except ValueError:
        return size
    else:
        kb, mb, gb = 1024.0, 1048576.0, 1073741824.0

        if b < kb:
            return str(b)
        elif kb <= b < mb:
            return f"{b / kb:.1f} K"
        elif mb <= b < gb:
            return f"{b / mb:.1f} M"
        elif gb <= b:
            return f"{b / gb:.1f} G"


class DefaultDict(defaultdict):
    """ Extended to support functions with params as default factory. """

    def __missing__(self, key):
        if self.default_factory:
            value = self[key] = self.default_factory(key)
            return value
        return super().__missing__(key)

    def get(self, key, default=None):
        return self[key]


if __name__ == "__main__":
    pass

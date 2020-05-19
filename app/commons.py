import logging
from functools import wraps
from threading import Thread, Timer

from gi.repository import GLib

_LOG_FILE = "demon-editor.log"
_DATE_FORMAT = "%d-%m-%y %H:%M:%S"
_LOGGER_NAME = None


def init_logger():
    global _LOGGER_NAME
    _LOGGER_NAME = "main_logger"
    logging.Logger(_LOGGER_NAME)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(message)s",
                        datefmt=_DATE_FORMAT,
                        handlers=[logging.FileHandler(_LOG_FILE), logging.StreamHandler()])
    log("Logging is enabled.", level=logging.INFO)


def log(message, level=logging.ERROR):
    logging.getLogger(_LOGGER_NAME).log(level, message)


def run_idle(func):
    """ Runs a function with a lower priority """

    @wraps(func)
    def wrapper(*args, **kwargs):
        GLib.idle_add(func, *args, **kwargs)

    return wrapper


def run_task(func):
    """ Runs function in separate thread """

    @wraps(func)
    def wrapper(*args, **kwargs):
        task = Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        task.start()

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


if __name__ == "__main__":
    pass

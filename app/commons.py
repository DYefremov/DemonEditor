import logging
from functools import wraps
from threading import Thread

from gi.repository import GLib

_LOG_FILE = "app_log.log"
_DATE_FORMAT = "%d-%m-%y %H:%M:%S"
_LOGGER_NAME = "main_logger"
logging.Logger(_LOGGER_NAME)
logging.basicConfig(level=logging.INFO,
                    filename=_LOG_FILE,
                    format="%(asctime)s %(message)s",
                    datefmt=_DATE_FORMAT)


def get_logger():
    return logging.getLogger(_LOGGER_NAME)


def log(message, level=logging.ERROR):
    get_logger().log(level, message)


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


if __name__ == "__main__":
    pass

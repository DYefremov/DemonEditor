from functools import wraps
from threading import Thread

from gi.repository import GLib


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

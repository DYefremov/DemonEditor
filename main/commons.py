from functools import wraps
from threading import Thread


def run_task(func):
    """ Runs function in separate thread """

    @wraps(func)
    def wrapper(*args, **kwargs):
        task = Thread(target=func(*args, **kwargs))
        task.start()

    return wrapper


if __name__ == "__main__":
    pass

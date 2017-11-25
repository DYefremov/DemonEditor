""" This module used for parsing blacklist file

    Parent Lock/Unlock
"""
from contextlib import suppress

__FILE_NAME = "blacklist"


def get_blacklist(path):
    with suppress(FileNotFoundError):
        with open(path + __FILE_NAME, "r") as file:
            # filter empty values and "\n"
            return {*list(filter(None, (x.strip() for x in file.readlines())))}


def write_blacklist(path, channels):
    if channels:
        with open(path + __FILE_NAME, "w") as file:
            file.writelines("\n".join(channels))


if __name__ == "__main__":
    pass

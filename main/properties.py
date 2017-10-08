import json
import os
from pathlib import Path


CONFIG_PATH = str(Path.home()) + "/.config/demon-editor/"
CONFIG_FILE = CONFIG_PATH + "config.json"
DATA_PATH = "data/"


def get_config():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)  # create dir if not exist
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    if not os.path.isfile(CONFIG_FILE) or os.stat(CONFIG_FILE).st_size == 0:
        with open(CONFIG_FILE, "w") as default_config_file:
            json.dump(get_default_settings(), default_config_file)

    with open(CONFIG_FILE, "r") as config_file:
        return json.load(config_file)


def write_config(config):
    assert isinstance(config, dict)
    with open(CONFIG_FILE, "w") as config_file:
        json.dump(config, config_file)


def get_default_settings():
    return {"host": "127.0.0.1", "port": "21",
            "user": "root", "password": "root",
            "services_path": "/etc/enigma2/",
            "user_bouquet_path": "/etc/enigma2/",
            "satellites_xml_path": "/etc/tuxbox/",
            "data_dir_path": DATA_PATH}


if __name__ == "__main__":
    pass

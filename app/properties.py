import json
import os
from enum import Enum
from pathlib import Path

CONFIG_PATH = str(Path.home()) + "/.config/demon-editor/"
CONFIG_FILE = CONFIG_PATH + "config.json"
DATA_PATH = "data/"


class Profile(Enum):
    """ Profiles for settings """
    ENIGMA_2 = "0"
    NEUTRINO_MP = "1"


def get_config():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)  # create dir if not exist
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)

    if not os.path.isfile(CONFIG_FILE) or os.stat(CONFIG_FILE).st_size == 0:
        reset_config()

    with open(CONFIG_FILE, "r") as config_file:
        return json.load(config_file)


def reset_config():
    with open(CONFIG_FILE, "w") as default_config_file:
        json.dump(get_default_settings(), default_config_file)


def write_config(config):
    assert isinstance(config, dict)
    with open(CONFIG_FILE, "w") as config_file:
        json.dump(config, config_file)


def get_default_settings():
    return {
        Profile.ENIGMA_2.value: {
            "host": "127.0.0.1", "port": "21",
            "user": "root", "password": "root",
            "telnet_user": "", "telnet_password": "",
            "telnet_port": "21", "telnet_timeout": 5,
            "services_path": "/etc/enigma2/",
            "user_bouquet_path": "/etc/enigma2/",
            "satellites_xml_path": "/etc/tuxbox/",
            "picons_path": "/usr/share/enigma2/picon",
            "data_dir_path": DATA_PATH + "enigma2/",
            "picons_dir_path": DATA_PATH + "enigma2/picons"},
        Profile.NEUTRINO_MP.value: {
            "host": "127.0.0.1", "port": "21",
            "user": "root", "password": "root",
            "telnet_user": "root", "telnet_password": "",
            "telnet_port": "21", "telnet_timeout": 1,
            "services_path": "/var/tuxbox/config/zapit/",
            "user_bouquet_path": "/var/tuxbox/config/zapit/",
            "satellites_xml_path": "/var/tuxbox/config/",
            "picons_path": "/usr/share/tuxbox/neutrino/icons/logo/",
            "data_dir_path": DATA_PATH + "neutrino/",
            "picons_dir_path": DATA_PATH + "neutrino/picons"},
        "profile": Profile.ENIGMA_2.value}


if __name__ == "__main__":
    pass

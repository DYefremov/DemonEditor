""" Module for parsing bouquets """
from collections import namedtuple

__BOUQUETS_PATH = "../data/"

Bouquet = namedtuple("Bouquet", ["name", "type", "services"])
Bouquets = namedtuple("Bouquets", ["name", "bouquets"])


def get_bouquets(path):
    return parse_bouquets(path, "bouquets.tv", "tv"), parse_bouquets(path, "bouquets.radio", "radio")


def write_bouquet(path, name, channels):
    bouquet = ["#NAME {}\n".format(name)]
    for ch in channels:
        data_type = int(ch.data_id.split(":")[-2])
        if data_type == 22:
            data_type = 16
        elif data_type == 25:
            data_type = 19
        bouquet.append("#SERVICE {}:0:{}:{}:0:0:0:\n".format(1, data_type, ch.fav_id))
    with open(path + "_userbouquet.{}.tv".format(name), "w") as file:
        file.writelines(bouquet)


def get_bouquet(path, name, bq_type):
    """ Parsing services ids from bouquet file """
    with open(path + "userbouquet.{}.{}".format(name, bq_type)) as file:
        chs_list = file.read()
        ids = []
        for ch in chs_list.split("#SERVICE")[1:]:
            ch_data = ch.strip().split(":")
            ids.append("{}:{}:{}:{}".format(ch_data[3], ch_data[4], ch_data[5], ch_data[6]))
    return ids


def parse_bouquets(path, bq_name, bq_type):
    with open(path + bq_name) as file:
        lines = file.readlines()
        bouquets = None
        nm_sep = "#NAME"
        for line in lines:
            if nm_sep in line:
                _, _, name = line.partition(nm_sep)
                bouquets = Bouquets(name.strip(), [])
            if bouquets and "#SERVICE" in line:
                name = line.split(".")[1]
                bouquets[1].append(Bouquet(name=name, type=bq_type, services=get_bouquet(path, name, bq_type)))
    return bouquets


if __name__ == "__main__":
    pass

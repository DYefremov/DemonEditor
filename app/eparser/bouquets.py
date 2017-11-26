""" Module for parsing bouquets """
from collections import namedtuple

_BOUQUETS_PATH = "../data/"
_TV_ROOT_FILE_NAME = "bouquets.tv"
_RADIO_ROOT_FILE_NAME = "bouquets.radio"

Bouquet = namedtuple("Bouquet", ["name", "type", "services"])
Bouquets = namedtuple("Bouquets", ["name", "type", "bouquets"])


def get_bouquets(path):
    return parse_bouquets(path, "bouquets.tv", "tv"), parse_bouquets(path, "bouquets.radio", "radio")


def write_bouquets(path, bouquets, bouquets_services):
    srv_line = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "userbouquet.{}.{}" ORDER BY bouquet\n'
    line = []

    for bqs in bouquets:
        line.clear()
        line.append("#NAME {}\n".format(bqs.name))

        for bq in bqs.bouquets:
            line.append(srv_line.format(bq.name, bq.type))
            write_bouquet(path, bq.name, bq.type, bq.services)

        with open(path + "bouquets.{}".format(bqs.type), "w") as file:
            file.writelines(line)


def write_bouquet(path, name, bq_type, channels):
    bouquet = ["#NAME {}\n".format(name)]

    for ch in channels:
        if not ch:  # if was duplicate
            continue
        bouquet.append("#SERVICE {}\n".format(to_bouquet_id(ch)))

    with open(path + "userbouquet.{}.{}".format(name, bq_type), "w") as file:
        file.writelines(bouquet)


def to_bouquet_id(ch):
    """ Creates bouquet channel id """
    data_type = int(ch.data_id.split(":")[-2])
    if data_type == 22:
        data_type = 16
    elif data_type == 25:
        data_type = 19
    service = "{}:0:{}:{}:0:0:0:".format(1, data_type, ch.fav_id)

    return service


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
                bouquets = Bouquets(name.strip(), bq_type, [])
            if bouquets and "#SERVICE" in line:
                name = line.split(".")[1]
                bouquets[2].append(Bouquet(name=name, type=bq_type, services=get_bouquet(path, name, bq_type)))

    return bouquets


if __name__ == "__main__":
    pass

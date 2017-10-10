""" Module for parsing bouquets """

#  temporary
from collections import namedtuple

__BOUQUETS_PATH = "../data/"

Bouquet = namedtuple("Bouquet", ["name", "type"])
Bouquets = namedtuple("Bouquets", ["name", "bouquets"])


def get_bouquets(path):
    return [parse_bouquets(path, "bouquets.tv"), parse_bouquets(path, "bouquets.radio")]


def get_bouquet(path, name, type):
    with open(path + "userbouquet.{}.{}".format(name, type)) as file:
        print(file.read())


def parse_bouquets(path, name):
    with open(path + name) as file:
        lines = file.readlines()
        bouquets = None
        nm_sep = "#NAME"
        for line in lines:
            if nm_sep in line:
                _, _, name = line.partition(nm_sep)
                bouquets = Bouquets(name.strip(), [])
            if bouquets is not None and "#SERVICE" in line:
                bouquets[1].append(line.split(".")[1])
    return bouquets


if __name__ == "__main__":
    # print(get_bouquet(__BOUQUETS_PATH, "TV", "tv"))
    pass

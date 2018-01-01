from xml.dom.minidom import parse

from ..ecommons import Bouquets, Bouquet, BouquetService, BqServiceType

_FILE = "bouquets.xml"
_U_FILE = "ubouquets.xml"
_PATH = "/home/dimon/WORK/projects/DemonEditor/data/neutrino/"


def get_bouquets(path):
    return parse_bouquets(_PATH + _FILE, "TV", "tv"), parse_bouquets(_PATH + _U_FILE, "User", "user")


def parse_bouquets(file, name, bq_type):
    dom = parse(file)
    bouquets = Bouquets(name=name, type=bq_type, bouquets=[])

    for elem in dom.getElementsByTagName("Bouquet"):
        if elem.hasAttributes():
            bq_name = elem.attributes["name"].value
            # hidden = elem.attributes["hidden"].value
            # locked = elem.attributes["locked"].value
            # epg = elem.attributes["epg"].value
            services = []
            for srv_elem in elem.getElementsByTagName("S"):
                if srv_elem.hasAttributes():
                    ssid = srv_elem.attributes["i"].value
                    srv_name = srv_elem.attributes["n"].value
                    tr_n = srv_elem.attributes["t"].value
                    pos = srv_elem.attributes["on"].value
                    sys = srv_elem.attributes["s"].value
                    frq = srv_elem.attributes["frq"].value,
                    l = srv_elem.attributes["l"].value
                    # fav_id = "{}:{}".format(tr_n, ssid)
                    services.append(BouquetService(None, BqServiceType.DEFAULT, srv_name, 0))
            bouquets[2].append(Bouquet(name=bq_name, type=bq_type, services=services))

    return bouquets


def write_bouquets(path, bouquets):
    pass

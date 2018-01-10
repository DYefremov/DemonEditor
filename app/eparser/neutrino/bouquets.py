import os
from contextlib import suppress
from enum import Enum
from xml.dom.minidom import parse, Document

from app.ui import LOCKED_ICON, HIDE_ICON
from ..ecommons import Bouquets, Bouquet, BouquetService, BqServiceType, PROVIDER

_FILE = "bouquets.xml"
_U_FILE = "ubouquets.xml"


class BqType(Enum):
    BOUQUET = "bouquet"
    TV = "tv"


def get_bouquets(path):
    return (parse_bouquets(path + _FILE, "Providers", BqType.BOUQUET.value),
            parse_bouquets(path + _U_FILE, "FAV", BqType.TV.value))


def parse_bouquets(file, name, bq_type):
    bouquets = Bouquets(name=name, type=bq_type, bouquets=[])
    if not os.path.exists(file):
        return bouquets

    dom = parse(file)

    for elem in dom.getElementsByTagName("Bouquet"):
        if elem.hasAttributes():
            bq_name = elem.attributes["name"].value
            hidden = elem.attributes.get("hidden")
            hidden = hidden.value if hidden else hidden
            locked = elem.attributes.get("locked")
            locked = locked.value if locked else locked
            # epg = elem.attributes["epg"].value
            services = []
            for srv_elem in elem.getElementsByTagName("S"):
                if srv_elem.hasAttributes():
                    ssid = srv_elem.attributes["i"].value
                    on = srv_elem.attributes["on"].value
                    fav_id = "{}:{}".format(on, ssid)
                    services.append(BouquetService(None, BqServiceType.DEFAULT, fav_id, 0))
            bouquets[2].append(Bouquet(name=bq_name,
                                       type=bq_type,
                                       services=services,
                                       locked=LOCKED_ICON if locked == "1" else None,
                                       hidden=HIDE_ICON if hidden == "1" else None))

    if BqType(bq_type) is BqType.BOUQUET:
        for bq in bouquets.bouquets:
            if bq.services:
                name = bq.name
                name = name[name.index("]") + 1:]
                key = int(bq.services[0].data.split(":")[0], 16)
                if key not in PROVIDER:
                    PROVIDER[key] = name

    return bouquets


def write_bouquets(path, bouquets):
    if len(bouquets) < 2:
        for f in path + _FILE, path + _U_FILE:
            with suppress(FileNotFoundError):
                os.remove(f)

    for bq in bouquets:
        bq_type = BqType(bq.type)
        write_bouquet(path + (_FILE if bq_type is BqType.BOUQUET else _U_FILE), bq)


def write_bouquet(file, bouquet):
    doc = Document()
    root = doc.createElement("zapit")
    doc.appendChild(root)
    comment = doc.createComment(" File was created in DemonEditor. Enjoy watching! ")
    doc.appendChild(comment)

    for bq in bouquet.bouquets:
        bq_elem = doc.createElement("Bouquet")
        bq_elem.setAttribute("name", bq.name)
        bq_elem.setAttribute("hidden", "1" if bq.hidden else "0")
        bq_elem.setAttribute("locked", "1" if bq.locked else "0")
        bq_elem.setAttribute("epg", "0")
        root.appendChild(bq_elem)

        for srv in bq.services:
            on, sep, ssid = srv.fav_id.partition(":")
            srv_elem = doc.createElement("S")
            srv_elem.setAttribute("i", ssid)
            srv_elem.setAttribute("n", srv.service)
            srv_elem.setAttribute("t", srv.transponder.split(":")[0].lstrip("0"))
            srv_elem.setAttribute("on", on)
            srv_elem.setAttribute("s", srv.pos.replace(".", ""))
            srv_elem.setAttribute("frq", srv.freq[:-3])
            srv_elem.setAttribute("l", "0")  # temporary !!!
            bq_elem.appendChild(srv_elem)

    doc.writexml(open(file, "w"), addindent="    ", newl="\n", encoding="UTF-8")


if __name__ == "__main__":
    pass

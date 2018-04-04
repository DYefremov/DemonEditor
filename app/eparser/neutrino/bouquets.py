import os
from xml.dom.minidom import parse, Document

from app.eparser.iptv import NEUTRINO_FAV_ID_FORMAT
from app.ui import LOCKED_ICON, HIDE_ICON
from ..ecommons import Bouquets, Bouquet, BouquetService, BqServiceType, PROVIDER, BqType

_FILE = "bouquets.xml"
_U_FILE = "ubouquets.xml"
_W_FILE = "webtv.xml"

_COMMENT = " File was created in DemonEditor. Enjoy watching! "


def get_bouquets(path):
    return (parse_bouquets(path + _FILE, "Providers", BqType.BOUQUET.value),
            parse_bouquets(path + _U_FILE, "FAV", BqType.TV.value),
            parse_webtv(path + _W_FILE, "WEBTV", BqType.WEBTV.value))


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
                    tr_id = srv_elem.attributes["t"].value
                    fav_id = "{}:{}:{}".format(tr_id, on, ssid)
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
                key = int(bq.services[0].data.split(":")[1], 16)
                if key not in PROVIDER:
                    PROVIDER[key] = name

    return bouquets


def parse_webtv(path, name, bq_type):
    bouquets = Bouquets(name=name, type=bq_type, bouquets=[])
    if not os.path.exists(path):
        return bouquets

    dom = parse(path)
    services = []
    for elem in dom.getElementsByTagName("webtv"):
        if elem.hasAttributes():
            title = elem.attributes["title"].value
            url = elem.attributes["url"].value
            description = elem.attributes.get("description")
            description = description.value if description else description
            urlkey = elem.attributes.get("urlkey", None)
            urlkey = urlkey.value if urlkey else urlkey
            account = elem.attributes.get("account", None)
            account = account.value if account else account
            usrname = elem.attributes.get("usrname", None)
            usrname = usrname.value if usrname else usrname
            psw = elem.attributes.get("psw", None)
            psw = psw.value if psw else psw
            s_type = elem.attributes.get("type", None)
            s_type = s_type.value if s_type else s_type
            iconsrc = elem.attributes.get("iconsrc", None)
            iconsrc = iconsrc.value if iconsrc else iconsrc
            iconsrc_b = elem.attributes.get("iconsrc_b", None)
            iconsrc_b = iconsrc_b.value if iconsrc_b else iconsrc_b
            group = elem.attributes.get("group", None)
            group = group.value if group else group
            fav_id = NEUTRINO_FAV_ID_FORMAT.format(url, description, urlkey, account, usrname, psw, s_type, iconsrc,
                                                   iconsrc_b, group)
            srv = BouquetService(name=title,
                                 type=BqServiceType.IPTV,
                                 data=fav_id,
                                 num=0)
            services.append(srv)
    bouquet = Bouquet(name="default", type=bq_type, services=services, locked=None, hidden=None)
    bouquets[2].append(bouquet)

    return bouquets


def write_bouquets(path, bouquets):
    for bq in bouquets:
        bq_type = BqType(bq.type)
        if bq_type is BqType.WEBTV:
            write_webtv(path + _W_FILE, bq)
        else:
            write_bouquet(path + (_FILE if bq_type is BqType.BOUQUET else _U_FILE), bq)


def write_bouquet(file, bouquet):
    doc = Document()
    root = doc.createElement("zapit")
    doc.appendChild(root)
    comment = doc.createComment(_COMMENT)
    doc.appendChild(comment)

    for bq in bouquet.bouquets:
        bq_elem = doc.createElement("Bouquet")
        bq_elem.setAttribute("name", bq.name)
        bq_elem.setAttribute("hidden", "1" if bq.hidden else "0")
        bq_elem.setAttribute("locked", "1" if bq.locked else "0")
        bq_elem.setAttribute("epg", "0")
        root.appendChild(bq_elem)

        for srv in bq.services:
            tr_id, on, ssid = srv.fav_id.split(":")
            srv_elem = doc.createElement("S")
            srv_elem.setAttribute("i", ssid)
            srv_elem.setAttribute("n", srv.service)
            srv_elem.setAttribute("t", tr_id)
            srv_elem.setAttribute("on", on)
            srv_elem.setAttribute("s", srv.pos.replace(".", ""))
            srv_elem.setAttribute("frq", srv.freq[:-3])
            srv_elem.setAttribute("l", "0")  # temporary !!!
            bq_elem.appendChild(srv_elem)

    doc.writexml(open(file, "w"), addindent="    ", newl="\n", encoding="UTF-8")


def write_webtv(file, bouquet):
    doc = Document()
    root = doc.createElement("webtvs")
    doc.appendChild(root)
    comment = doc.createComment(_COMMENT)
    doc.appendChild(comment)

    for bq in bouquet.bouquets:
        for srv in bq.services:
            url, description, urlkey, account, usrname, psw, s_type, iconsrc, iconsrc_b, group = srv.fav_id.split("::")
            srv_elem = doc.createElement("webtv")
            srv_elem.setAttribute("title", srv.service)
            srv_elem.setAttribute("url", url)

            if description != "None":
                srv_elem.setAttribute("description", description)
            if urlkey != "None":
                srv_elem.setAttribute("urlkey", urlkey)
            if account != "None":
                srv_elem.setAttribute("account", account)
            if usrname != "None":
                srv_elem.setAttribute("usrname", usrname)
            if psw != "None":
                srv_elem.setAttribute("psw", psw)
            if s_type != "None":
                srv_elem.setAttribute("type", s_type)
            if iconsrc != "None":
                srv_elem.setAttribute("iconsrc", iconsrc)
            if iconsrc_b != "None":
                srv_elem.setAttribute("iconsrc_b", iconsrc_b)
            if group != "None":
                srv_elem.setAttribute("group", group)

            root.appendChild(srv_elem)

    doc.writexml(open(file, "w"), addindent="    ", newl="\n", encoding="UTF-8")


if __name__ == "__main__":
    pass

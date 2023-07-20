# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2023 Dmitriy Yefremov
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Author: Dmitriy Yefremov
#


import os

from app.commons import log
from app.eparser.iptv import NEUTRINO_FAV_ID_FORMAT
from app.eparser.neutrino import KSP, SP, get_xml_attributes, get_attributes, API_VER
from app.eparser.neutrino.nxml import XmlHandler, NeutrinoDocument
from ..ecommons import Bouquets, Bouquet, BouquetService, BqServiceType, PROVIDER, BqType

_FILE = "bouquets.xml"
_U_FILE = "ubouquets.xml"
_W_FILE = "webtv_usr.xml"

_COMMENT = " File was created in DemonEditor. Enjoy watching! "


def get_bouquets(path):
    return (parse_bouquets(path + _FILE, "Providers", BqType.BOUQUET.value),
            parse_bouquets(path + _U_FILE, "FAV", BqType.TV.value),
            parse_webtv(path + _W_FILE, "WEBTV", BqType.WEBTV.value))


def parse_bouquets(file, name, bq_type):
    bouquets = Bouquets(name=name, type=bq_type, bouquets=[])
    if not os.path.exists(file):
        return bouquets

    dom = XmlHandler.parse(file)

    for elem in dom.getElementsByTagName("Bouquet"):
        if elem.hasAttributes():
            bq_attrs = get_xml_attributes(elem)
            bq_name = bq_attrs.get("name", "")
            hidden = bq_attrs.get("hidden", "0")
            locked = bq_attrs.get("locked", "0")
            services = []

            for srv_elem in elem.getElementsByTagName("S"):
                if srv_elem.hasAttributes():
                    s_attrs = get_xml_attributes(srv_elem)
                    if "i" in s_attrs:
                        ssid = s_attrs.get("i", "0")
                        on = s_attrs.get("on", "0")
                        tr_id = s_attrs.get("t", "0")
                        fav_id = f"{tr_id}:{on}:{ssid}"
                        services.append(BouquetService(None, BqServiceType.DEFAULT, fav_id, 0))
                    elif "u" in s_attrs:
                        services.append(BouquetService(s_attrs.get("n"), BqServiceType.IPTV, s_attrs.get("u"), 0))
                    else:
                        log(f"Parse bouquets [Neutrino] error: Unknown service type. -> {s_attrs}")

            bouquets[2].append(Bouquet(name=bq_name,
                                       type=bq_type,
                                       services=services,
                                       locked=locked == "1",
                                       hidden=hidden == "1",
                                       file=SP.join(f"{k}{KSP}{v}" for k, v in bq_attrs.items())))

    if BqType(bq_type) is BqType.BOUQUET:
        for bq in bouquets.bouquets:
            if bq.services:
                key = int(bq.services[0].data.split(":")[1], 16)
                if key not in PROVIDER:
                    pos, sep, name = bq.name.partition("]")
                    PROVIDER[key] = name

    return bouquets


def parse_webtv(path, name, bq_type):
    bouquets = Bouquets(name=name, type=bq_type, bouquets=[])
    if not os.path.exists(path):
        return bouquets

    dom = XmlHandler.parse(path)
    services = []
    for elem in dom.getElementsByTagName("webtv"):
        if elem.hasAttributes():
            web_attrs = get_xml_attributes(elem)
            title = web_attrs.get("title", "")
            url = web_attrs.get("url", "")
            description = web_attrs.get("description", "")
            urlkey = web_attrs.get("urlkey", None)
            account = web_attrs.get("account", None)
            usrname = web_attrs.get("usrname", None)
            psw = web_attrs.get("psw", None)
            s_type = web_attrs.get("type", None)
            iconsrc = web_attrs.get("iconsrc", None)
            iconsrc_b = web_attrs.get("iconsrc_b", None)
            group = web_attrs.get("group", None)
            fav_id = NEUTRINO_FAV_ID_FORMAT.format(url, description, urlkey, account, usrname, psw, s_type, iconsrc,
                                                   iconsrc_b, group)
            services.append(BouquetService(name=title, type=BqServiceType.IPTV, data=fav_id, num=0))

    bouquet = Bouquet(name="default", type=bq_type, services=services, locked=None, hidden=None, file=None)
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
    doc = NeutrinoDocument()
    root = doc.createElement("zapit")
    root.setAttribute("api", API_VER)
    doc.appendChild(root)
    comment = doc.createComment(_COMMENT)
    doc.appendChild(comment)

    for bq in bouquet.bouquets:
        attrs = get_attributes(bq.file) if bq.file else {}
        attrs["name"] = bq.name
        if bq.hidden:
            attrs["hidden"] = "1"
        else:
            attrs.pop("hidden", None)
        if bq.locked:
            attrs["locked"] = "1"
        else:
            attrs.pop("locked", None)

        bq_elem = doc.createElement("Bouquet")
        for k, v in attrs.items():
            bq_elem.setAttribute(k, v)

        root.appendChild(bq_elem)

        for srv in bq.services:
            srv_elem = doc.createElement("S")
            srv_elem.setAttribute("n", srv.service)
            s_type = BqServiceType(srv.service_type)

            if s_type is BqServiceType.DEFAULT:
                tr_id, on, ssid = srv.fav_id.split(":")
                srv_elem.setAttribute("i", ssid)
                srv_elem.setAttribute("t", tr_id)
                srv_elem.setAttribute("on", on)
                srv_elem.setAttribute("frq", srv.freq)
                srv_elem.setAttribute("s", get_attributes(srv.flags_cas).get("position", "0"))
            elif s_type is BqServiceType.IPTV:
                s_data = srv.fav_id.split("::")
                if s_data:
                    srv_elem.setAttribute("n", srv.service)
                    srv_elem.setAttribute("u", s_data[0])
            else:
                log(f"Write bouquet [Neutrino] error: Unsupported service type. -> {s_type.value}")

            bq_elem.appendChild(srv_elem)

    doc.write_xml(file)


def write_webtv(file, bouquet):
    doc = NeutrinoDocument()
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

    doc.write_xml(file)


if __name__ == "__main__":
    pass

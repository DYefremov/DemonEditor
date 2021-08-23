# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2021 Dmitriy Yefremov
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


import re
from collections import defaultdict
from xml.dom.minidom import Document, parseString

from app.commons import log
from app.eparser.ecommons import (Service, POLARIZATION, FEC, SYSTEM, SERVICE_TYPE, PROVIDER, T_SYSTEM, TrType,
                                  SystemCable)

_FILE = "services.xml"
SP = "_:::_"
KSP = "_::_"


def write_services(path, services):
    NeutrinoServiceWriter(path, services).write()


def get_services(path):
    return NeutrinoServicesReader(path).get_services()


class NeutrinoServiceWriter:

    def __init__(self, path, services):
        self._path = path
        self._services = services

        self._api = "4"
        self._doc = Document()
        self._root = self._doc.createElement("zapit")
        self._root.setAttribute("api", self._api)
        self._doc.appendChild(self._root)
        self._doc.appendChild(self._doc.createComment(" File was created in DemonEditor. Enjoy watching! "))

    def write(self):
        srvs = defaultdict(list)
        for s in self._services:
            srvs[s.transponder_type].append(s)
        self.append_services(srvs.get(TrType.Satellite.value), "sat")
        self.append_services(srvs.get(TrType.Terrestrial.value), "terrestrial")
        self.append_services(srvs.get(TrType.Cable.value), "cable")

        self._doc.writexml(open(self._path + _FILE, "w"), addindent="    ", newl="\n", encoding="UTF-8")
        self._doc.unlink()

    def append_services(self, services, s_type):
        if not services:
            return

        sats = defaultdict(list)
        for srv in services:
            sats[srv[0]].append(srv)

        for sat in sats:
            sat_elem = self._doc.createElement(s_type)
            attrs = self.get_attributes(sat)
            for k, v in attrs.items():
                sat_elem.setAttribute(k, v)

            self._root.appendChild(sat_elem)

            transponders = defaultdict(list)
            for srv in sats.get(sat):
                transponders[srv[-1]].append(srv)

            for tr in transponders:
                tr_elem = self._doc.createElement("TS")
                for k, v in self.get_attributes(tr).items():
                    tr_elem.setAttribute(k, v)
                sat_elem.appendChild(tr_elem)

                for srv in transponders.get(tr):
                    srv_elem = self._doc.createElement("S")
                    s_attrs = self.get_attributes(srv.data_id)
                    api = s_attrs.pop("api", self._api)
                    if api != self._api:
                        self._root.setAttribute("api", api)

                    for k, v in s_attrs.items():
                        srv_elem.setAttribute(k, v)

                    tr_elem.appendChild(srv_elem)

    @staticmethod
    def get_attributes(data):
        return {el[0]: el[1] for el in (e.split(KSP) for e in data.split(SP))}


class NeutrinoServicesReader:

    def __init__(self, path):
        self._path = path
        self._attrs = None
        self._tr = None
        self._api = "4"
        self._services = []

    def get_services(self):
        with open(self._path + _FILE, "rb") as f:
            # Pre-processing is required to replace the '&' character.
            dom = parseString(re.sub("&", "&amp;", f.read().decode(encoding="utf-8", errors="ignore")))

            for root in dom.getElementsByTagName("zapit"):
                if root.hasAttributes():
                    api = root.attributes["api"]
                    self._api = api.value if api else self._api

                for elem in root.getElementsByTagName("sat"):
                    if elem.hasAttributes():
                        sat_attrs = self.get_attributes(elem)
                        sat_attrs["name"] = re.sub("&amp;", "&", sat_attrs.get("name", ""))
                        sat_pos = 0
                        try:
                            sat_pos = int(sat_attrs.get("position", "0"))
                            sat_pos = "{:0.1f}{}".format(abs(sat_pos / 10), "W" if sat_pos < 0 else "E")
                        except ValueError as e:
                            log("Neutrino parsing error [parse sat position]: {}".format(e))
                        sat = SP.join("{}{}{}".format(k, KSP, v) for k, v in sat_attrs.items())
                        for tr_elem in elem.getElementsByTagName("TS"):
                            if tr_elem.hasAttributes():
                                self.parse_sat_transponder(sat, sat_pos, tr_elem)

                # Terrestrial DVB-T[2].
                for elem in root.getElementsByTagName("terrestrial"):
                    if elem.hasAttributes():
                        terr_attrs = self.get_attributes(elem)
                        terr_attrs["name"] = re.sub("&amp;", "&", terr_attrs.get("name", ""))
                        terr = SP.join("{}{}{}".format(k, KSP, v) for k, v in terr_attrs.items())

                        for tr_elem in elem.getElementsByTagName("TS"):
                            if tr_elem.hasAttributes():
                                self.parse_ct_transponder(terr, tr_elem, TrType.Terrestrial)

                # Cable.
                for elem in root.getElementsByTagName("cable"):
                    if elem.hasAttributes():
                        cable_attrs = self.get_attributes(elem)
                        terr_attrs["name"] = re.sub("&amp;", "&", cable_attrs.get("name", ""))
                        cable = SP.join("{}{}{}".format(k, KSP, v) for k, v in cable_attrs.items())

                        for tr_elem in elem.getElementsByTagName("TS"):
                            if tr_elem.hasAttributes():
                                self.parse_ct_transponder(cable, tr_elem, TrType.Cable)

            return self._services

    def parse_sat_transponder(self, sat, sat_pos, tr_elem):
        tr_attr = self.get_attributes(tr_elem)
        tr = SP.join("{}{}{}".format(k, KSP, v) for k, v in tr_attr.items())
        tr_id = tr_attr.get("id", "0").lstrip("0")
        on = tr_attr.get("on", "0")
        freq = tr_attr.get("frq", "0")
        rate = tr_attr.get("sr", "0")
        fec = tr_attr.get("fec", "0")

        pol = POLARIZATION.get(tr_attr.get("pol", "0"))
        # Formatting displayed values.
        try:
            freq = "{}".format(int(freq) // 1000)
            rate = "{}".format(int(rate) // 1000)
        except ValueError as e:
            log("Neutrino parsing error [parse_transponder]: {}".format(e))

        for srv_elem in tr_elem.getElementsByTagName("S"):
            if srv_elem.hasAttributes():
                at = self.get_attributes(srv_elem)
                at["api"] = self._api
                ssid, name, s_type, sys = at.get("i", "0"), at.get("n", ""), at.get("t", "3"), at.get("s", "0")
                name = re.sub("amp;", "", name)
                at["n"] = name
                data_id = SP.join("{}{}{}".format(k, KSP, v) for k, v in at.items())
                fav_id = "{}:{}:{}".format(tr_id, on.lstrip("0"), ssid.lstrip("0"))
                picon_id = "{}{}{}.png".format(tr_id, on, ssid)
                prv = PROVIDER.get(int(on, 16), "")
                st = SERVICE_TYPE.get(str(int(s_type, 16)), SERVICE_TYPE.get("-2"))

                srv = Service(sat, TrType.Satellite.value, None, name, None, None, prv, st, None, picon_id, ssid, freq,
                              rate, pol, FEC.get(fec), SYSTEM.get(sys), sat_pos, data_id, fav_id, tr)
                self._services.append(srv)

    def parse_ct_transponder(self, terr, tr_elem, tr_type):
        attrs = self.get_attributes(tr_elem)
        tr = SP.join("{}{}{}".format(k, KSP, v) for k, v in attrs.items())
        tr_id, on, freq = attrs.get("id", "0").lstrip("0"), attrs.get("on", "0"), attrs.get("frq", "0")

        for srv_elem in tr_elem.getElementsByTagName("S"):
            if srv_elem.hasAttributes():
                s_at = self.get_attributes(srv_elem)
                s_at["api"] = self._api
                ssid, name, s_type, sys = s_at.get("i", "0"), s_at.get("n", ""), s_at.get("t", "3"), s_at.get("s", "0")
                name = re.sub("amp;", "", name)
                s_at["n"] = name
                data_id = SP.join("{}{}{}".format(k, KSP, v) for k, v in s_at.items())
                fav_id = "{}:{}:{}".format(tr_id, on.lstrip("0"), ssid.lstrip("0"))
                picon_id = "{}{}{}.png".format(tr_id, on, ssid)
                prv = PROVIDER.get(int(on, 16), "")
                st = SERVICE_TYPE.get(str(int(s_type, 16)), SERVICE_TYPE.get("-2"))

                if tr_type is TrType.Terrestrial:
                    sys = T_SYSTEM.get(sys)
                    pos = "T"
                elif tr_type is TrType.Cable:
                    sys = SystemCable(sys).name
                    pos = "C"
                else:
                    log("Parse transponder error: Not supported type [{}]".format(tr_type))
                    break

                srv = Service(terr, tr_type.value, None, name, None, None, prv, st, None, picon_id, ssid,
                              freq, "0", None, None, sys, pos, data_id, fav_id, tr)
                self._services.append(srv)

    @staticmethod
    def get_attributes(attr):
        attrs = attr.attributes
        return {t: attrs[t].value for t in attrs.keys()}


if __name__ == "__main__":
    pass

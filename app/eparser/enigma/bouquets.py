# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2022 Dmitriy Yefremov
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


""" Module for working with Enigma2 bouquets. """
import re
from collections import Counter
from enum import Enum
from pathlib import Path

from app.commons import log
from app.eparser.ecommons import BqServiceType, BouquetService, Bouquets, Bouquet, BqType

_TV_FILE = "bouquets.tv"
_RADIO_FILE = "bouquets.radio"
_DEFAULT_BOUQUET_NAME = "favourites"
_MARKER_PREFIX = "[MARKER!] "


class BouquetsWriter:
    """ Class for creating and writing bouquet files.

        If "force_bq_names" then naming the files using the name of the bouquet.
        Some images may have problems displaying the favorites list!
     """
    _SERVICE = '#SERVICE 1:7:{}:0:0:0:0:0:0:0:FROM BOUQUET "userbouquet.{}.{}" ORDER BY bouquet\n'
    _MARKER = "#SERVICE 1:64:{:X}:0:0:0:0:0:0:0::{}\n"
    _SPACE = "#SERVICE 1:832:D:{}:0:0:0:0:0:0:\n"
    _ALT = '#SERVICE 1:134:1:0:0:0:0:0:0:0:FROM BOUQUET "{}" ORDER BY bouquet\n'
    _ALT_PAT = r"[<>:\"/\\|?*\-\s]"

    def __init__(self, path, bouquets, force_bq_names=False):
        self._path = path
        self._bouquets = bouquets
        self._force_bq_names = force_bq_names
        self._marker_index = 1
        self._space_index = 0
        self._alt_names = set()
        self._NAME_PATTERN = re.compile("[^\\w_()]+")

    def write(self):
        line = []

        for bqs in self._bouquets:
            line.clear()
            line.append(f"#NAME {bqs.name}\n")
            bq_file_names = {b.file for b in bqs.bouquets}
            count = 1
            m_count = 0

            for bq in bqs.bouquets:
                bq_name = bq.file
                if not bq_name:
                    if self._force_bq_names:
                        bq_name = re.sub(self._NAME_PATTERN, "_", bq.name)
                    else:
                        bq_name = f"de{count:02d}"
                        while bq_name in bq_file_names:
                            count += 1
                            bq_name = f"de{count:02d}"
                        bq_file_names.add(bq_name)

                bq_type = BqType(bq.type)
                if bq_type is BqType.MARKER:
                    m_data = bq.file.split(":") if bq.file else None
                    b_name = m_data[-1].strip() if m_data else bq.name.lstrip(_MARKER_PREFIX)
                    line.append(self._MARKER.format(m_count, b_name))
                    m_count += 1
                else:
                    if bq_type is BqType.BOUQUET:
                        bq_name = re.sub(self._NAME_PATTERN, "_", bq.name)
                        self.write_sub_bouquet(self._path, bq_name, bq, bqs.type)
                    else:
                        self.write_bouquet(f"{self._path}userbouquet.{bq_name}.{bqs.type}", bq.name, bq.services)
                    line.append(self._SERVICE.format(2 if bqs.type == BqType.RADIO.value else 1, bq_name, bqs.type))

            with open(f"{self._path}bouquets.{bqs.type}", "w", encoding="utf-8", newline="\n") as file:
                file.writelines(line)

    def write_bouquet(self, path, name, services):
        """ Writes single bouquet file. """
        bouquet = [f"#NAME {name}\n"]
        for srv in services:
            s_type = srv.service_type
            if s_type == BqServiceType.IPTV.name:
                bouquet.append(f"#SERVICE {srv.fav_id.strip()}\n")
            elif s_type == BqServiceType.MARKER.name:
                m_data = srv.fav_id.strip().split(":")
                m_data[2] = self._marker_index
                self._marker_index += 1
                bouquet.append(self._MARKER.format(m_data[2], m_data[-1]))
            elif s_type == BqServiceType.SPACE.name:
                bouquet.append(self._SPACE.format(self._space_index))
                self._space_index += 1
            elif s_type == BqServiceType.ALT.name:
                services = srv.transponder
                if services:
                    p = Path(path)
                    alt_name = srv.data_id
                    f_name = f"alternatives.{alt_name}{p.suffix}"

                    if self._force_bq_names:
                        alt_name = re.sub(self._ALT_PAT, "_", srv.service).lower()
                        f_name = f"alternatives.{alt_name}{p.suffix}"

                    bouquet.append(self._ALT.format(f_name))
                    self.write_bouquet(f"{p.parent}/{f_name}", srv.service, services)
            else:
                data = to_bouquet_id(srv)
                if srv.service:
                    bouquet.append(f"#SERVICE {data}:{srv.service}\n#DESCRIPTION {srv.service}\n")
                else:
                    bouquet.append(f"#SERVICE {data}\n")

        with open(path, "w", encoding="utf-8", newline="\n") as file:
            file.writelines(bouquet)

    def write_sub_bouquet(self, path, file_name, bq, bq_type):
        bouquet = [f"#NAME {bq.name}\n"]
        sb_type = 2 if bq_type == BqType.RADIO.value else 1

        for sb in bq.services:
            bq_name = f"subbouquet.{re.sub(self._NAME_PATTERN, '_', sb.name)}.{sb.type}"
            self.write_bouquet(f"{path}{bq_name}", sb.name, sb.services)
            bouquet.append(f"#SERVICE 1:7:{sb_type}:0:0:0:0:0:0:0:FROM BOUQUET \"{bq_name}\" ORDER BY bouquet\n")

        with open(f"{self._path}userbouquet.{file_name}.{bq_type}", "w", encoding="utf-8", newline="\n") as file:
            file.writelines(bouquet)


class ServiceType(Enum):
    SERVICE = "0"
    BOUQUET = "7"  # Sub bouquet.
    MARKER = "64"
    SPACE = "832"  # Hidden marker.
    ALT = "134"  # Alternatives.
    UDP = "256"

    @classmethod
    def _missing_(cls, value):
        log("Error. No matching service type [{} {}] was found.".format(cls.__name__, value))
        return cls.SERVICE


class BouquetsReader:
    """ Class for reading and parsing bouquets. """
    _ALT_PAT = re.compile(r".*alternatives\.+(.*)\.([tv|radio]+).*")
    _BQ_PAT = re.compile(r".*\s+\W(.*bouquet)\.+(.*)\.+[tv|radio].*")
    _SUB_BQ_PAT = re.compile(r".*subbouquet\.+(.*)\.([tv|radio]+).*")
    _STREAM_TYPES = {"4097", "5001", "5002", "8193", "8739"}

    __slots__ = ["_path"]

    def __init__(self, path):
        self._path = path

    def get(self):
        """ Returns a tuple of TV and Radio bouquets. """
        return self.parse_bouquets(_TV_FILE, BqType.TV.value), self.parse_bouquets(_RADIO_FILE, BqType.RADIO.value)

    def parse_bouquets(self, bq_name, bq_type):
        with open(self._path + bq_name, encoding="utf-8", errors="replace") as file:
            line = file.readline()
            _, _, bqs_name = line.partition("#NAME")
            if not bqs_name:
                log(f"No bouquets name found in '{bq_name}'")
                bqs_name = "Bouquets (TV)" if bq_type == BqType.TV.value else "Bouquets (Radio)"
            bouquets = Bouquets(bqs_name.strip(), bq_type, [])

            b_names = set()
            real_b_names = Counter()

            for line in file.readlines():
                if "#SERVICE" in line:
                    name = re.match(self._BQ_PAT, line)
                    if name:
                        prefix, b_name = name.group(1), name.group(2)
                        if b_name in b_names:
                            log(f"The list of bouquets contains duplicate [{b_name}] names!")
                        else:
                            b_names.add(b_name)

                        rb_name, services = self.get_bouquet(self._path, b_name, bq_type, prefix)
                        if rb_name in real_b_names:
                            log(f"Bouquet file '{prefix}.{b_name}.{bq_type}' has duplicate name: {rb_name}")
                            real_b_names[rb_name] += 1
                            rb_name = f"{rb_name} {real_b_names[rb_name]}"
                        else:
                            real_b_names[rb_name] = 0

                        bouquets[2].append(Bouquet(rb_name, bq_type, services, None, None, b_name))
                    else:
                        s_data = line.split(":")
                        if len(s_data) == 12 and s_data[1] == ServiceType.MARKER.value:
                            b_name = f"{_MARKER_PREFIX}{s_data[-1].strip()}"
                            bouquets[2].append(Bouquet(b_name, BqType.MARKER.value, [], None, None, line.strip()))
                        else:
                            log(f"Unsupported or invalid data format: [{line}].")
                else:
                    log(f"Unsupported or invalid line format: [{line}].")

        return bouquets

    @staticmethod
    def get_bouquet(path, bq_name, bq_type, prefix="userbouquet"):
        """ Parsing services ids from bouquet file. """
        with open(f"{path}{prefix}.{bq_name}.{bq_type}", encoding="utf-8", errors="replace") as file:
            chs_list = file.read()
            services = []
            srvs = list(filter(None, chs_list.split("\n#SERVICE")))  # filtering ['']
            # May come across empty[wrong] files!
            if not srvs:
                log(f"Bouquet file 'userbouquet.{bq_name}.{bq_type}' is empty or wrong!")
                return f"{bq_name} [empty]", services

            bq_name = srvs.pop(0)

            for num, srv in enumerate(srvs, start=1):
                srv_data = srv.strip().split(":")
                data_len = len(srv_data)
                if data_len < 10:
                    log(f"The bouquet [{bq_name}] service [{num}] has the wrong data format: [{srv}]")
                    continue

                s_type = ServiceType(srv_data[1])
                if s_type is ServiceType.MARKER:
                    m_data, sep, desc = srv.partition("#DESCRIPTION")
                    services.append(BouquetService(desc.strip() if desc else "", BqServiceType.MARKER, srv, num))
                elif s_type is ServiceType.SPACE:
                    m_data, sep, desc = srv.partition("#DESCRIPTION")
                    services.append(BouquetService(desc.strip() if desc else "", BqServiceType.SPACE, srv, num))
                elif s_type is ServiceType.ALT:
                    alt = re.match(BouquetsReader._ALT_PAT, srv)
                    if alt:
                        alt_name, alt_type = alt.group(1), alt.group(2)
                        alt_bq_name, alt_srvs = BouquetsReader.get_bouquet(path, alt_name, alt_type, "alternatives")
                        services.append(BouquetService(alt_bq_name, BqServiceType.ALT, alt_name, tuple(alt_srvs)))
                elif s_type is ServiceType.BOUQUET:
                    sub = re.match(BouquetsReader._SUB_BQ_PAT, srv)
                    if sub:
                        sub_name, sub_type = sub.group(1), sub.group(2)
                        sub_bq_name, sub_srvs = BouquetsReader.get_bouquet(path, sub_name, sub_type, "subbouquet")
                        bq = Bouquet(sub_bq_name, sub_type, tuple(sub_srvs), None, None, sub_name)
                        services.append(BouquetService(sub_bq_name, BqServiceType.BOUQUET, bq, num))
                elif srv_data[0].strip() in BouquetsReader._STREAM_TYPES or srv_data[10].startswith(("http", "rtsp")):
                    stream_data, sep, desc = srv.partition("#DESCRIPTION")
                    desc = desc.lstrip(":").strip() if desc else srv_data[-1].strip()
                    services.append(BouquetService(desc, BqServiceType.IPTV, srv, num))
                else:
                    fav_id = f"{srv_data[3]}:{srv_data[4]}:{srv_data[5]}:{srv_data[6]}"
                    name = None
                    if data_len == 12:
                        name, sep, desc = str(srv_data[-1]).partition("\n#DESCRIPTION")
                    services.append(BouquetService(name, BqServiceType.DEFAULT, fav_id.upper(), num))

        return bq_name.lstrip("#NAME").strip(), services


def to_bouquet_id(srv):
    """ Creates bouquet channel id. """
    data_type = srv.data_id
    if data_type and len(data_type) > 4:
        data_type = int(srv.data_id.split(":")[4])

        return "{}:0:{:X}:{}:0:0:0:".format(1, data_type, srv.fav_id)


if __name__ == "__main__":
    pass

# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2025 Dmitriy Yefremov
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
import os.path
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


class ServiceType(Enum):
    SERVICE = "0"
    BOUQUET = "7"  # Sub bouquet.
    MARKER = "64"
    SPACE = "832"
    ALT = "134"  # Alternatives.
    UDP = "256"
    HIDDEN = "519"  # Skip, hide.

    @classmethod
    def _missing_(cls, value):
        log("Error. No matching service type [{} {}] was found.".format(cls.__name__, value))
        return cls.SERVICE

    def __str__(self):
        return self.value


class BouquetsWriter:
    """ Class for creating and writing bouquet files.

        If "force_bq_names" then naming the files using the name of the bouquet.
        Some images may have problems displaying the favorites list!
     """
    _SERVICE = '#SERVICE 1:{}:{}:0:0:0:0:0:0:0:FROM BOUQUET "{}" ORDER BY bouquet\n'
    _MARKER = "#SERVICE 1:64:{:X}:0:0:0:0:0:0:0::{}\n"
    _SPACE = "#SERVICE 1:832:D:{}:0:0:0:0:0:0:\n"
    _LOCKED = '1:{}:{}:0:0:0:0:0:0:0:FROM BOUQUET "{}" ORDER BY bouquet'
    _ALT = '#SERVICE 1:134:1:0:0:0:0:0:0:0:FROM BOUQUET "{}" ORDER BY bouquet\n'
    _ALT_PAT = r"[<>:\"/\\|?*\-\s]"

    def __init__(self, path, bouquets, force_bq_names=False, blacklist=None):
        self._path = path
        self._bouquets = bouquets
        self._force_bq_names = force_bq_names
        self._black_list = set() if blacklist is None else blacklist

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
                f_name = bq.file
                bq_type = BqType(bq.type)
                if not f_name:
                    if self._force_bq_names or bq_type is BqType.BOUQUET:
                        f_name = f"userbouquet.{re.sub(self._NAME_PATTERN, '_', bq.name)}.{bqs.type}"
                    else:
                        f_name = f"userbouquet.de{count:02d}.{bqs.type}"
                        while f_name in bq_file_names:
                            count += 1
                            f_name = f"userbouquet.de{count:02d}.{bqs.type}"
                        bq_file_names.add(f_name)

                if bq_type is BqType.MARKER:
                    m_data = bq.file.split(":") if bq.file else None
                    b_name = m_data[-1].strip() if m_data else bq.name.lstrip(_MARKER_PREFIX)
                    line.append(self._MARKER.format(m_count, b_name))
                    m_count += 1
                else:
                    if bq_type is BqType.BOUQUET:
                        self.write_sub_bouquet(self._path, f_name, bq, bqs.type)
                    else:
                        self.write_bouquet(f"{self._path}{f_name}", bq.name, bq.services)
                    bq_type = 2 if bqs.type == BqType.RADIO.value else 1
                    # Parental lock.
                    locked = self._LOCKED.format(ServiceType.SERVICE, bq_type, f_name)
                    self._black_list.add(locked) if bq.locked else self._black_list.discard(locked)
                    # Hiding.
                    s_type = ServiceType.HIDDEN if bq.hidden else ServiceType.BOUQUET
                    line.append(self._SERVICE.format(s_type, bq_type, f_name))

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
                if srv.service:
                    bouquet.append(f"#SERVICE {srv.fav_id}:{srv.service}\n#DESCRIPTION {srv.service}\n")
                else:
                    bouquet.append(f"#SERVICE {srv.fav_id}\n")

        with open(path, "w", encoding="utf-8", newline="\n") as file:
            file.writelines(bouquet)

    def write_sub_bouquet(self, path, file_name, bq, bq_type):
        bouquet = [f"#NAME {bq.name}\n"]
        sb_type = 2 if bq_type == BqType.RADIO.value else 1

        for sb in bq.services:
            sb_file = sb.file or f"subbouquet.{re.sub(self._NAME_PATTERN, '_', sb.name)}.{sb.type}"
            self.write_bouquet(f"{path}{sb_file}", sb.name, sb.services)
            bouquet.append(f"#SERVICE 1:7:{sb_type}:0:0:0:0:0:0:0:FROM BOUQUET \"{sb_file}\" ORDER BY bouquet\n")

        with open(f"{self._path}{file_name}", "w", encoding="utf-8", newline="\n") as file:
            file.writelines(bouquet)


class BouquetsReader:
    """ Class for reading and parsing bouquets. """
    _BQ_PAT = re.compile(r".*FROM BOUQUET\s+\"((.*bouquet|alternatives)?\.?([\w-]+)\.?(\w+)?)\"\s+.*$", re.IGNORECASE)
    _BQ_PAT2 = re.compile(r"#SERVICE:+\s+(?:[0-9a-f]+:+)+([^:]+[.](?:tv|radio))$", re.IGNORECASE)
    _BQ_POST_PAT = re.compile(r".*FROM BOUQUET\s+\"((.*bouquet|alternatives)?\.?(.*)\.?(\w+)?)\"\s+.*$", re.IGNORECASE)
    _STREAM_TYPES = {"4097", "5001", "5002", "8193", "8739"}

    __slots__ = ["_path", "_has_errors"]

    def __init__(self, path=""):
        self._path = path
        self._has_errors = False

    @property
    def has_errors(self):
        return self._has_errors

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
                    s_data = line.split(":")
                    s_type = ServiceType.BOUQUET

                    mt = re.match(self._BQ_PAT, line) or re.match(self._BQ_PAT2, line)
                    if not mt:
                        # Additional file name checking.
                        mt = re.match(self._BQ_POST_PAT, line)
                        if mt:
                            log(f"Warning: The bouquet file name may be formed incorrectly. -> {mt.group(1)}")

                    if mt:
                        if len(mt.groups()) > 1:
                            file_name, prefix, b_name = mt.group(1), mt.group(2), mt.group(3)
                            s_type = ServiceType(s_data[1])
                            s_data[:2] = "10"
                        else:
                            file_name, prefix, b_name = mt.group(1), "", ""
                            s_type = ServiceType(s_data[2])

                        if b_name in b_names:
                            log(f"The list of bouquets contains duplicate [{b_name}] names!")
                        else:
                            b_names.add(b_name)

                        rb_name, services = self.get_bouquet(self._path, file_name, b_name)
                        if rb_name in real_b_names:
                            log(f"Bouquet file '{file_name}' has duplicate name: {rb_name}")
                            real_b_names[rb_name] += 1
                            rb_name = f"{rb_name} {real_b_names[rb_name]}"
                        else:
                            real_b_names[rb_name] = 0
                        # Locked, hidden.
                        locked = ":".join(s_data).rstrip()
                        hidden = s_type is ServiceType.HIDDEN
                        bouquets[2].append(Bouquet(rb_name, bq_type, services, locked, hidden, file_name))
                    else:
                        if len(s_data) == 12 and s_type is ServiceType.MARKER:
                            b_name = f"{_MARKER_PREFIX}{s_data[-1].strip()}"
                            bouquets[2].append(Bouquet(b_name, BqType.MARKER.value, [], None, None, line.strip()))
                        else:
                            log(f"Unsupported or invalid data format: [{line}].")
                else:
                    log(f"Unsupported or invalid line format: [{line}].")

        return bouquets

    def get_bouquet(self, path, f_name, bq_name):
        """ Parsing services ids from bouquet file. """
        bq_file = f"{path}{f_name}"
        services = []

        if not os.path.isfile(bq_file):
            log(f"Bouquet reading error: No such bouquet [{bq_name}] file -> '{f_name}'.")
            return f"{bq_name}", services

        with open(bq_file, encoding="utf-8", errors="replace") as file:
            chs_list = file.read()
            srvs = list(filter(None, chs_list.split("\n#SERVICE")))  # filtering ['']
            # May come across empty[wrong] files!
            if not srvs:
                log(f"Bouquet file '{f_name}' is empty or wrong!")
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
                    m_data, sep, desc = srv_data[-1].partition("#DESCRIPTION")
                    services.append(BouquetService(desc.strip() if desc else m_data, BqServiceType.MARKER, srv, num))
                elif s_type is ServiceType.SPACE:
                    m_data, sep, desc = srv.partition("#DESCRIPTION")
                    services.append(BouquetService(desc.strip() if desc else "", BqServiceType.SPACE, srv, num))
                elif s_type is ServiceType.ALT:
                    alt = re.match(self._BQ_PAT, srv)
                    if alt:
                        af_name, alt_name = alt.group(1), alt.group(3)
                        alt_bq_name, alt_srvs = self.get_bouquet(path, af_name, alt_name)
                        services.append(BouquetService(alt_bq_name, BqServiceType.ALT, alt_name, tuple(alt_srvs)))
                elif s_type is ServiceType.BOUQUET:
                    sub = re.match(self._BQ_PAT, srv)
                    if sub:
                        sf_name, sub_name, sub_type = sub.group(1), sub.group(3), sub.group(4)
                        sub_bq_name, sub_srvs = self.get_bouquet(path, sf_name, sub_name)
                        bq = Bouquet(sub_bq_name, sub_type, tuple(sub_srvs), None, None, sf_name)
                        services.append(BouquetService(sub_bq_name, BqServiceType.BOUQUET, bq, num))
                elif srv_data[0].strip() in self._STREAM_TYPES or srv_data[10].startswith(("http", "rtsp")):
                    stream_data, sep, desc = srv.partition("#DESCRIPTION")
                    desc = desc.lstrip(":").strip() if desc else srv_data[-1].strip()
                    services.append(BouquetService(desc, BqServiceType.IPTV, srv, num))
                else:
                    fav_id = srv.strip().upper()
                    name = None
                    if data_len == 12:
                        fav_id = f":".join(srv_data[:11])
                        name, sep, desc = str(srv_data[-1]).partition("\n#DESCRIPTION")
                    services.append(BouquetService(name, BqServiceType.DEFAULT, fav_id, num))

        return bq_name.lstrip("#NAME").strip(), services


if __name__ == "__main__":
    pass

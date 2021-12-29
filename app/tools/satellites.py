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


""" Module for downloading satellites, transponders and services from the Web.

    Sources: www.flysat.com, www.lyngsat.com, www.kingofsat.net.
    Replaces or updates the current satellites.xml file.
"""
import re
from enum import Enum
from html.parser import HTMLParser

import requests

from app.commons import log
from app.eparser import Satellite, Transponder, is_transponder_valid
from app.eparser.ecommons import (PLS_MODE, get_key_by_value, FEC, SYSTEM, POLARIZATION, MODULATION, SERVICE_TYPE,
                                  Service, CAS)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Linux x86_64; rv:92.0) Gecko/20100101 Firefox/92.0"}
_TIMEOUT = 10


class SatelliteSource(Enum):
    FLYSAT = ("https://www.flysat.com/en/satellitelist",)
    LYNGSAT = ("https://www.lyngsat.com/asia.html", "https://www.lyngsat.com/europe.html",
               "https://www.lyngsat.com/atlantic.html", "https://www.lyngsat.com/america.html")
    KINGOFSAT = ("https://en.kingofsat.net/satellites.php",)

    @staticmethod
    def get_sources(src):
        return src.value


class Cell:
    """ Cell representation for table parsers. """
    __slots__ = ["_text", "_url", "_img"]

    def __init__(self, text=None, link=None, img=None):
        self._text = text
        self._url = link
        self._img = img

    def __repr__(self):
        return f"Cell({self._text}, {self._url}, {self._img})"

    def __str__(self):
        return f"<Cell(text={self._text}, link={self._url}, img={self._img})>"

    def __iter__(self):
        return (x for x in (self._text, self._url, self._img))

    def __len__(self):
        return 3

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value

    @property
    def url(self):
        return self._url

    @url.setter
    def url(self, value):
        self._url = value

    @property
    def img(self):
        return self._img

    @img.setter
    def img(self, value):
        self._img = value


class SatellitesParser(HTMLParser):
    """ Parser for satellite html page. """

    POS_PAT = re.compile(r".*?(\d+\.\d°?[EW]).*")

    def __init__(self, source=SatelliteSource.FLYSAT, entities=False, separator=' '):

        HTMLParser.__init__(self)

        self._parse_html_entities = entities
        self._separator = separator
        self._is_td = False
        self._is_th = False
        self._is_provider = False
        self._current_row = []
        self._current_cell = []
        self._rows = []
        self._source = source

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self._is_td = True
        if tag == "tr":
            self._is_th = True
        if tag == "a":
            for atr in attrs:
                if atr[0] == "href":
                    self._current_row.append(atr[1])

    def handle_data(self, data):
        """ Save content to a cell """
        if self._is_td or self._is_th:
            self._current_cell.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "td":
            self._is_td = False
        elif tag == "tr":
            self._is_th = False

        if tag in ("td", "th"):
            final_cell = self._separator.join(self._current_cell).strip()
            self._current_row.append(final_cell)
            self._current_cell = []
        elif tag == "tr":
            row = self._current_row
            self._rows.append(row)
            self._current_row = []

    def error(self, message):
        pass

    def get_satellites_list(self, source):
        """ Getting complete list of satellites. """
        self.reset()
        self._rows.clear()
        self._source = source

        for src in SatelliteSource.get_sources(self._source):
            try:
                request = requests.get(url=src, headers=_HEADERS, timeout=_TIMEOUT)
            except requests.exceptions.RequestException as e:
                log(f"Getting satellite list error: {repr(e)}")
                return []
            else:
                reason = request.reason
                if reason == "OK":
                    self.feed(request.text)
                else:
                    log(reason)

        if self._rows:
            if self._source is SatelliteSource.FLYSAT:
                return self.get_satellites_for_fly_sat()
            elif self._source is SatelliteSource.LYNGSAT:
                return self.get_satellites_for_lyng_sat()
            elif source is SatelliteSource.KINGOFSAT:
                return self.get_satellites_for_king_of_sat()

    def get_satellite(self, sat):
        pos = sat[1]
        return Satellite(name=f"{pos} {sat[0]}", flags="0",
                         position=self.get_position(pos.replace(".", "")),
                         transponders=self.get_transponders(sat[3]))

    def get_satellites_for_fly_sat(self):
        sat_pat = re.compile(r"https://.*/satellite/.+")
        pos_pat = re.compile(r"https://.*/satellite/position/.+")
        names = []
        pos = ""
        pos_url = ""

        def normalize_pos(p):
            return f"{float(p[:-1])}{p[-1]}" if "." not in p else p

        def get_sat(r):
            nonlocal pos
            nonlocal pos_url
            # Uniting satellites in position.
            if re.match(pos_pat, r[2]):
                pos_url = r[2]
                name = r[1]
                pos = normalize_pos(self.parse_position(r[3]))

                names.append(name)
                return name, pos, r[5], r[0], False

            r_size = len(r)
            if r_size == 5:
                name = r[1]
                names.append(name)
                return name, pos, r[3], r[0], False
            if r_size == 6:
                if names:
                    name = "/".join(names)
                    names.clear()
                    return name, pos, None, pos_url, False

                return r[1], normalize_pos(self.parse_position(r[2])), r[4], r[0], False

        return list(filter(None, map(get_sat, filter(lambda row: row and re.match(sat_pat, row[0]), self._rows))))

    def get_satellites_for_lyng_sat(self):
        base_url = "https://www.lyngsat.com/"
        sats = []
        cur_pos = "0"
        for row in filter(lambda x: 3 < len(x) < 8, self._rows):
            if not row[0]:
                row = row[1:]

            pos = self.parse_position(row[1])
            if not self.POS_PAT.match(pos):
                if len(row) == 4 and row[0].endswith(".html"):
                    sats.append((row[1], cur_pos, row[-2], base_url + row[0], False))
                continue

            sats.append((row[-3], pos, row[-2], base_url + row[0], False))
            cur_pos = pos
        return sats

    def get_satellites_for_king_of_sat(self):
        def get_sat(r):
            return r[3], self.parse_position(r[1]), None, r[2], False

        return list(map(get_sat, filter(lambda x: len(x) == 17, self._rows)))

    @staticmethod
    def parse_position(pos_str):
        return "".join(c for c in pos_str if c.isdigit() or c.isalpha() or c == ".")

    @staticmethod
    def get_position(pos):
        return f"{'-' if pos[-1] == 'W' else ''}{pos[:-1]}"

    def get_transponders(self, sat_url):
        """ Getting transponders(sorted by frequency). """
        self._rows.clear()
        trs = []

        if self._source is SatelliteSource.KINGOFSAT:
            sat_url = "https://en.kingofsat.net/" + sat_url

        try:
            request = requests.get(url=sat_url, headers=_HEADERS, timeout=_TIMEOUT)
        except requests.exceptions.RequestException as e:
            log(f"Getting transponders error: {e}")
        else:
            if request.status_code == 200:
                self.feed(request.text)
                if self._source is SatelliteSource.FLYSAT:
                    self.get_transponders_for_fly_sat(trs)
                elif self._source is SatelliteSource.LYNGSAT:
                    self.get_transponders_for_lyng_sat(trs)
                elif self._source is SatelliteSource.KINGOFSAT:
                    self.get_transponders_for_king_of_sat(trs)
            else:
                log(f"SatellitesParser [get transponders] error: {sat_url}  {request.reason}")

        return sorted(trs, key=lambda x: int(x.frequency))

    def get_transponders_for_fly_sat(self, trs):
        """ Parsing transponders for FlySat. """
        frq_pol_pattern = re.compile(r"(\d{4,5})+\s+([RLHV]).*(DVB-S[2]?)/(.+PSK)?.*")
        pls_pattern = re.compile(r".*PLS\s+(Root|Gold|Combo)+\s(\d+)?")
        is_id_pattern = re.compile(r"Stream\s(\d+)")
        sr_fec_pattern = re.compile(r"(\d{4,5})+\s+(\d+/\d+).*")
        pls_modes = {v: k for k, v in PLS_MODE.items()}
        n_trs = []

        if self._rows:
            zeros = "000"
            is_ids = []
            for r in self._rows:
                row_len = len(r)
                if row_len == 1:
                    is_ids.extend(re.findall(is_id_pattern, r[0]))
                    continue
                if row_len < 12:
                    continue

                freq = re.findall(frq_pol_pattern, r[2])
                if not freq:
                    continue

                freq, pol, sys, mod = freq[0]

                sr_fec = re.match(sr_fec_pattern, r[3])
                if not sr_fec:
                    continue

                sr, fec = sr_fec.group(1), sr_fec.group(2)

                pls = re.match(pls_pattern, r[2])
                pls_code = None
                pls_mode = None
                if pls:
                    pls_mode = pls_modes.get(pls.group(1), None)
                    pls_code = pls.group(2)

                if is_ids:
                    tr = trs.pop()
                    for index, is_id in enumerate(is_ids):
                        tr = tr._replace(is_id=is_id)
                        if is_transponder_valid(tr):
                            n_trs.append(tr)
                else:
                    tr = Transponder(freq + zeros, sr + zeros, pol, fec, sys, mod, pls_mode, pls_code, None)
                    if is_transponder_valid(tr):
                        trs.append(tr)

                is_ids.clear()
            trs.extend(n_trs)

    def get_transponders_for_lyng_sat(self, trs):
        """ Parsing transponders for LyngSat. """
        frq_pol_pattern = re.compile("(\\d{4,5})\\s+([RLHV]).*")
        sr_fec_pattern = re.compile(r"(DVB-S[2]?)\s+(.+PSK)?.*?(\d+)\s+(\d/\d)\s*(?:T2-MI\s+PLP\s+(\d+))?.*")
        zeros = "000"
        pls_mode, pls_code, pls_id = None, None, None

        for row in filter(lambda x: len(x) > 8, self._rows):
            for frq in row[1], row[2], row[3]:
                freq = re.match(frq_pol_pattern, frq)
                if freq:
                    break
            if not freq:
                continue

            frq, pol = freq.group(1), freq.group(2)
            srf = " ".join(row[3:5])
            sr_fec = re.search(sr_fec_pattern, srf)
            if not sr_fec:
                continue

            sys, mod, sr, fec = sr_fec.group(1), sr_fec.group(2), sr_fec.group(3), sr_fec.group(4)
            mod = mod.strip() if mod else "Auto"
            pls_id = sr_fec.group(5)

            tr = Transponder(frq + zeros, sr + zeros, pol, fec, sys, mod, pls_mode, pls_code, pls_id)
            if is_transponder_valid(tr):
                trs.append(tr)

    def get_transponders_for_king_of_sat(self, trs):
        """ Getting transponders for KingOfSat source.

            Since the *.ini file contains incomplete information, it is not used.
        """
        sys_pat = re.compile(r"(DVB-S[2]?)\s?(?:T2-MI,\s+PLP\s+(\d+))?.*?(?:PLS:\s+(Root|Gold|Combo)\+(\d+))?")
        mod_pat = re.compile(r"(.*PSK).*?(?:.*Stream\s+(\d+))?.*")
        sr_fec_pattern = re.compile(r"(\d{4,5})+\s+(\d+/\d+).*")
        pls_modes = {v: k for k, v in PLS_MODE.items()}

        for row in filter(lambda r: len(r) == 16 and self.POS_PAT.match(r[0]), self._rows):
            freq, pol = row[2].replace(".", "0"), row[3]
            if not freq.isdigit() or pol not in "VHLR":
                continue

            res = re.match(sys_pat, row[8])
            if not res:
                continue
            sys, t2_mi, pls_id, pls_code = res.group(1), res.group(2), pls_modes.get(res.group(3), None), res.group(4)

            res = re.match(mod_pat, row[9])
            if not res:
                continue
            mod, is_id = res.group(1), res.group(2)

            res = re.match(sr_fec_pattern, row[10])
            if not res:
                continue
            sr, fec = res.group(1), res.group(2)

            if t2_mi:
                log(f"Detected T2-MI transponder! [{freq} {sr} {pol}] ")

            tr = Transponder(freq, f"{sr}000", pol, fec, sys, mod, pls_id, pls_code, is_id)
            if is_transponder_valid(tr):
                trs.append(tr)


class ServicesParser(HTMLParser):
    """ Services parser for LYNGSAT source. """

    def __init__(self, source=SatelliteSource.LYNGSAT, entities=False, separator=' '):

        HTMLParser.__init__(self)

        self._S_TYPES = {"": "2", "MPEG-2 SD": "1", "MPEG-2/SD": "1", "SD": "1", "MPEG-4 SD": "22", "MPEG-4/SD": "22",
                         "MPEG-4": "22", "HEVC SD": "22", "MPEG-4/HD": "25", "MPEG-4 HD": "25", "MPEG-4 HD 1080": "25",
                         "MPEG-4 HD 720": "25", "HEVC HD": "25", "HEVC/HD": "25", "HEVC": "31", "HEVC/UHD": "31",
                         "HEVC UHD": "31", "HEVC UHD 4K": "31", "3": "Data"}
        self._TR_PAT = re.compile(
            r".*?(\d+)\s+([RLHV]).*(DVB-S[2]?)/?(.*PSK)?\s(T2-MI)?\s?SR-FEC:\s(\d+)-(\d/\d)\s+.*ONID-TID:\s+(\d+)-(\d+).*")
        self._POS_PAT = re.compile(r".*?(\d+\.\d°[EW]).*")
        self._TR = "s {}000:{}000:{}:{}:{}:{}:{}:{}"
        self._S2_TR = "{}:{}:{}:{}"

        self._parse_html_entities = entities
        self._separator = separator
        self._is_td = False
        self._is_th = False
        self._current_row = []
        self._current_cell_text = []
        self._current_cell = Cell()
        self._rows = []
        self._source = source
        self._t_url = ""
        self._use_short_names = True

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, value):
        self._source = value
        self.reset()

    @property
    def use_short_names(self):
        return self._use_short_names

    @use_short_names.setter
    def use_short_names(self, value):
        self._use_short_names = value

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self._is_td = True
        elif tag == "tr":
            self._is_th = True
        elif tag == "a" and not self._current_cell.url:
            if attrs:
                for a in attrs:
                    if a[0] == "href":
                        self._current_cell.url = a[1]

                    if self._source is SatelliteSource.KINGOFSAT and self._use_short_names:
                        if a[0] != "title":
                            continue
                        txt = a[1]
                        if txt and txt.startswith("Id: "):
                            # Saving the 'short' name.
                            self._current_cell.text = txt.lstrip("Id: ")
        elif tag == "img":
            img_link = attrs[0][1]
            if self._source is SatelliteSource.LYNGSAT:
                if img_link.startswith("/logo/"):
                    self._current_cell.img = img_link
            elif self._source is SatelliteSource.KINGOFSAT:
                self._current_cell.img = img_link

    def handle_data(self, data):
        """ Save content to a cell """
        if self._is_td or self._is_th:
            self._current_cell_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "td":
            self._is_td = False
        elif tag == "tr":
            self._is_th = False

        if tag in ("td", "th"):
            if not self._current_cell.text:
                txt = self._separator.join(self._current_cell_text).strip()
                self._current_cell.text = txt
            self._current_row.append(self._current_cell)
            self._current_cell_text = []
            self._current_cell = Cell()
        elif tag == "tr":
            row = self._current_row
            self._rows.append(row)
            self._current_row = []

    def error(self, message):
        log(f"ServicesParser error: {message}")

    def init_data(self, url):
        """ Initializes data for the given URL. """
        if self._source not in (SatelliteSource.LYNGSAT, SatelliteSource.KINGOFSAT):
            raise ValueError(f"Unsupported source: {self._source.name}!")

        self._rows.clear()
        try:
            request = requests.get(url=url, headers=_HEADERS, timeout=_TIMEOUT)
        except requests.exceptions.RequestException as e:
            raise ValueError(e)
        else:
            reason = request.reason
            if reason == "OK":
                self.feed(request.text)
            else:
                raise ValueError(reason)

    def get_transponders_links(self, sat_url):
        """ Returns transponder links. """
        try:
            if self._source is SatelliteSource.KINGOFSAT:
                sat_url = "https://en.kingofsat.net/" + sat_url
            self.init_data(sat_url)
        except ValueError as e:
            log(e)
        else:
            if self._source is SatelliteSource.LYNGSAT:
                url = "https://www.lyngsat.com/muxes/"
                return [row[0] for row in
                        filter(lambda x: x and len(x) > 8 and x[0].url and x[0].url.startswith(url), self._rows)]
            elif self._source is SatelliteSource.KINGOFSAT:
                trs = []
                for r in self._rows:
                    if len(r) == 13 and SatellitesParser.POS_PAT.match(r[0].text):
                        t_cell = r[4]
                        if t_cell.url and t_cell.url.startswith("tp.php?tp="):
                            t_cell.url = f"https://en.kingofsat.net/{t_cell.url}"
                            t_cell.text = f"{r[2].text} {r[3].text} {r[6].text} {r[8].text}"
                            trs.append(t_cell)
                return trs
        return []

    def get_transponder_services(self, tr_url, sat_position=None, use_pids=False):
        """ Returns services for given transponder.

            @param tr_url: transponder URL.
            @param sat_position: custom satellite position. Sometimes required to adjust the namespace.
            @param use_pids: if possible use additional pids [video, audio].
        """
        try:
            self._t_url = tr_url
            self.init_data(tr_url)
        except ValueError as e:
            log(e)
        else:
            if self._source is SatelliteSource.LYNGSAT:
                return self.get_lyngsat_services(sat_position, use_pids)
            elif self._source is SatelliteSource.KINGOFSAT:
                return self.get_kingofsat_services(sat_position, use_pids)
            else:
                return []

    def get_lyngsat_services(self, sat_position=None, use_pids=False):
        services = []
        pos, freq, sr, fec, pol, nsp, tid, nid = sat_position or 0, 0, 0, 0, 0, 0, 0, 0
        sys = "DVB-S"
        pos_found = False
        tr = None
        # Transponder
        for r in filter(lambda x: x and 6 < len(x) < 9, self._rows):
            if not pos_found:
                pos_tr = re.match(self._POS_PAT, r[0].text)
                if not pos_tr:
                    continue

                if not sat_position:
                    pos = self.get_position(pos_tr.group(1))

                pos_found = True

            if pos_found:
                text = " ".join(c.text for c in r[1:])
                td = re.match(self._TR_PAT, text)
                if td:
                    freq, pol = int(td.group(1)), get_key_by_value(POLARIZATION, td.group(2))
                    if td.group(5):
                        log("Detected T2-MI transponder!")
                        continue

                    sys, mod, sr, _fec, = td.group(3), td.group(4), td.group(6), td.group(7)
                    nid, tid = td.group(8), td.group(9)
                    sys, mod, fec, nsp, s2_flags, roll_off, pilot, inv = self.get_transponder_data(pos, _fec, sys, mod)
                    nid, tid = int(nid), int(tid)
                    tr = self._TR.format(freq, sr, pol, fec, pos, inv, sys, s2_flags)

        if not tr:
            er = f"Transponder [{freq}] not found or its type [T2-MI, etc] not supported yet."
            log(f"ServicesParser error [get transponder services]: {er}")
            return services

        # Services
        for r in filter(lambda x: x and len(x) == 12 and (x[0].text.isdigit()), self._rows):
            sid, name, s_type, v_pid, a_pid, cas, pkg = r[0].text, r[2].text, r[4].text, r[
                5].text.strip(), r[6].text.split(), r[9].text, r[10].text.strip()
            try:
                s_type = self._S_TYPES.get(s_type, "3")  # 3 = Data
                _s_type = SERVICE_TYPE.get(s_type, SERVICE_TYPE.get("3"))  # str repr
                flags, sid, fav_id, picon_id, data_id = self.get_service_data(s_type, pkg, sid, tid, nid, nsp,
                                                                              v_pid, a_pid, cas, use_pids)
                services.append(Service(flags, "s", None, name, None, None, pkg, _s_type, r[1].img, picon_id,
                                        sid, freq, sr, pol, fec, sys, pos, data_id, fav_id, tr))
            except ValueError as e:
                log(f"ServicesParser error [get transponder services]: {e}")

        return services

    def get_kingofsat_services(self, sat_position=None, use_pids=False):
        services = []
        # Transponder
        tr = list(filter(lambda r: len(r) == 13 and r[4].url and r[4].url.startswith("tp.php?tp="), self._rows))
        if not tr:
            log(f"ServicesParser error [get transponder services]: Transponder [{self._t_url}] not found!")
            return services

        tr = tr[0]
        s_pos, freq, pol, sys, mod, sr_fec = tr[0].text, tr[2].text, tr[3].text, tr[6].text, tr[7].text, tr[8].text
        nid, tid = tr[10].text, tr[11].text

        pos = sat_position
        if not sat_position:
            pos_tr = re.match(self._POS_PAT, s_pos)
            if pos_tr:
                pos = self.get_position(pos_tr.group(1))

        sr, fec = sr_fec.split()
        pol = get_key_by_value(POLARIZATION, pol)
        sys, mod, fec, nsp, s2_flags, roll_off, pilot, inv = self.get_transponder_data(pos, fec, sys, mod)
        freq, nid, tid = int(float(freq)), int(nid), int(tid)
        tr = self._TR.format(freq, sr, pol, fec, pos, inv, sys, s2_flags)

        for r in filter(lambda x: len(x) == 14 and not x[1].text and x[7].text and x[7].text.isdigit(), self._rows):
            if r[1].img == "/radio.gif":
                s_type = ""
            elif r[8].img == "/hd.gif":
                s_type = "HEVC HD"
            elif r[1].img == "/data.gif":
                s_type = "Data"
            else:
                s_type = "SD"

            s_type = self._S_TYPES.get(s_type, "3")
            _s_type = SERVICE_TYPE.get(s_type, SERVICE_TYPE.get("3"))

            name, pkg, cas, sid, v_pid, a_pid = r[2].text, r[5].text, r[6].text, r[7].text, None, None
            flags, sid, fav_id, picon_id, data_id = self.get_service_data(s_type, pkg, sid, tid, nid, nsp,
                                                                          v_pid, a_pid, cas, use_pids)
            services.append(Service(flags, "s", None, name, None, None, pkg, _s_type, None, picon_id,
                                    sid, str(freq), sr, pol, fec, sys, pos, data_id, fav_id, tr))

        return services

    def get_transponder_data(self, pos, fec, sys, mod):
        """ Returns converted transponder data. """
        sys = get_key_by_value(SYSTEM, sys)
        mod = get_key_by_value(MODULATION, mod)
        fec = get_key_by_value(FEC, fec)
        # For negative (West) positions: 3600 - numeric position value!!!
        namespace = f"{3600 - pos if pos < 0 else pos:04x}0000"
        tr_flag = 1
        roll_off = 0  # 35% DVB-S2/DVB-S (default)
        pilot = 2  # Auto
        s2_flags = "" if sys == "DVB-S" else self._S2_TR.format(tr_flag, mod or 0, roll_off, pilot)
        inv = 2  # Default

        return sys, mod, fec, namespace, s2_flags, roll_off, pilot, inv

    @staticmethod
    def get_service_data(s_type, pkg, sid, tid, nid, namespace, v_pid, a_pid, cas, use_pids=False):
        sid = int(sid)
        data_id = f"{sid:04x}:{namespace}:{tid:04x}:{nid:04x}:{s_type}:0:0"
        fav_id = f"{sid}:{tid}:{nid}:{namespace}"
        picon_id = f"1_0_{int(s_type):X}_{sid}_{tid}_{nid}_{namespace}_0_0_0.png"
        # Flags.
        flags = f"p:{pkg}"
        cas = ",".join(get_key_by_value(CAS, c) or "C:0000" for c in cas.split()) if cas else None
        if use_pids:
            v_pid = f"c:00{int(v_pid):04x}" if v_pid else None
            a_pid = ",".join([f"c:01{int(p):04x}" for p in a_pid]) if a_pid else None
            flags = ",".join(filter(None, (flags, v_pid, a_pid, cas)))
        else:
            flags = ",".join(filter(None, (flags, cas)))

        return flags, sid, fav_id, picon_id, data_id

    @staticmethod
    def get_position(pos):
        return int(SatellitesParser.get_position("".join(c for c in pos if c.isdigit() or c.isalpha())))


if __name__ == "__main__":
    pass

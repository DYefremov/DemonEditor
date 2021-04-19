""" Module for downloading satellites, transponders ans services from the web.

    Sources: www.flysat.com, www.lyngsat.com.
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

_HEADERS = {"User-Agent": "Mozilla/5.0 (Linux x86_64; rv:85.0) Gecko/20100101 Firefox/85.0"}


class SatelliteSource(Enum):
    FLYSAT = ("https://www.flysat.com/satlist.php",)
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
        return "Cell({}, {}, {})".format(self._text, self._url, self._img)

    def __str__(self):
        return "<Cell(text={}, link={}, img={})>".format(self._text, self._url, self._img)

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
                request = requests.get(url=src, headers=_HEADERS)
            except requests.exceptions.ConnectionError as e:
                log(repr(e))
                return []
            else:
                reason = request.reason
                if reason == "OK":
                    self.feed(request.text)
                else:
                    log(reason)

        if self._rows:
            if self._source is SatelliteSource.FLYSAT:
                def get_sat(r):
                    return r[1], self.parse_position(r[2]), r[3], r[0], False

                return list(map(get_sat, filter(lambda x: all(x) and len(x) == 5, self._rows)))
            elif self._source is SatelliteSource.LYNGSAT:
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
            elif source is SatelliteSource.KINGOFSAT:
                def get_sat(r):
                    return r[3], self.parse_position(r[1]), None, r[0], False

                return list(map(get_sat, filter(lambda x: len(x) == 17, self._rows)))

    def get_satellite(self, sat):
        pos = sat[1]
        return Satellite(name="{} {}".format(pos, sat[0]),
                         flags="0",
                         position=self.get_position(pos.replace(".", "")),
                         transponders=self.get_transponders(sat[3]))

    @staticmethod
    def parse_position(pos_str):
        return "".join(c for c in pos_str if c.isdigit() or c.isalpha() or c == ".")

    @staticmethod
    def get_position(pos):
        return "{}{}".format("-" if pos[-1] == "W" else "", pos[:-1])

    def get_transponders(self, sat_url):
        """ Getting transponders(sorted by frequency). """
        self._rows.clear()
        trs = []

        url = sat_url
        if self._source is SatelliteSource.FLYSAT:
            url = "https://www.flysat.com/" + sat_url
        elif self._source is SatelliteSource.KINGOFSAT:
            url = "https://en.kingofsat.net/" + sat_url

        try:
            request = requests.get(url=url, headers=_HEADERS)
        except requests.exceptions.ConnectionError as e:
            log("Getting transponders error: {}".format(e))
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
                log("SatellitesParser [get transponders] error: {}  {}".format(url, request.reason))

        return sorted(trs, key=lambda x: int(x.frequency))

    def get_transponders_for_fly_sat(self, trs):
        """ Parsing transponders for FlySat """
        pls_pattern = re.compile("(PLS:)+ (Root|Gold|Combo)+ (\\d+)?")
        is_id_pattern = re.compile("(Stream) (\\d+)")
        pls_modes = {v: k for k, v in PLS_MODE.items()}
        n_trs = []

        if self._rows:
            zeros = "000"
            is_ids = []
            for r in self._rows:
                if len(r) == 1:
                    is_ids.extend(re.findall(is_id_pattern, r[0]))
                    continue
                if len(r) < 3:
                    continue
                data = r[2].split(" ")
                if len(data) != 2:
                    continue
                sr, fec = data
                data = r[1].split(" ")
                if len(data) < 3:
                    continue
                freq, pol, sys = data[0], data[1], data[2]
                sys = sys.split("/")
                if len(sys) != 2:
                    continue
                sys, mod = sys
                mod = "QPSK" if sys == "DVB-S" else mod

                pls = re.findall(pls_pattern, r[1])
                pls_code = None
                pls_mode = None

                if pls:
                    pls_code = pls[0][2]
                    pls_mode = pls_modes.get(pls[0][1], None)

                if is_ids:
                    tr = trs.pop()
                    for index, is_id in enumerate(is_ids):
                        tr = tr._replace(is_id=is_id[1])
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
        zeros = "000"
        pat = re.compile(
            r"(\d+).00\s+([RLHV])\s+(DVB-S[2]?)\s+(?:T2-MI, PLP (\d+)\s+)?(.*PSK).*?(?:Stream\s+(\d+))?\s+(\d+)\s+(\d+/\d+)$")

        for row in filter(lambda r: len(r) == 16 and self.POS_PAT.match(r[0]), self._rows):
            res = pat.search(" ".join((row[0], row[2], row[3], row[8], row[9], row[10])))
            if res:
                freq, sr, pol, fec, sys = res.group(1), res.group(7), res.group(2), res.group(8), res.group(3)
                mod, pls_id, pls_code = res.group(5), res.group(4), res.group(6)

                tr = Transponder(freq + zeros, sr + zeros, pol, fec, sys, mod, None, pls_code, pls_id)
                if is_transponder_valid(tr):
                    trs.append(tr)


class ServicesParser(HTMLParser):
    """ Services parser for LYNGSAT source. """

    def __init__(self, source=SatelliteSource.LYNGSAT, entities=False, separator=' '):

        HTMLParser.__init__(self)

        self._S_TYPES = {"": "2", "MPEG-2 SD": "1", "MPEG-2/SD": "1", "SD": "1", "MPEG-4 SD": "22", "MPEG-4/SD": "22",
                         "MPEG-4": "22", "HEVC SD": "22", "MPEG-4/HD": "25", "MPEG-4 HD": "25", "MPEG-4 HD 1080": "25",
                         "MPEG-4 HD 720": "25", "HEVC HD": "25", "HEVC/HD": "25", "HEVC": "31", "HEVC/UHD": "31",
                         "HEVC UHD": "31", "HEVC UHD 4K": "31"}
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

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self._is_td = True
        elif tag == "tr":
            self._is_th = True
        elif tag == "a" and not self._current_cell.url:
            self._current_cell.url = attrs[0][1]
        elif tag == "img":
            img_link = attrs[0][1]
            if img_link.startswith("/logo/"):
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
            final_cell = self._separator.join(self._current_cell_text).strip()
            self._current_cell.text = final_cell
            self._current_row.append(self._current_cell)
            self._current_cell_text = []
            self._current_cell = Cell()
        elif tag == "tr":
            row = self._current_row
            self._rows.append(row)
            self._current_row = []

    def error(self, message):
        log("ServicesParser error: {}".format(message))

    def init_data(self, url):
        """ Initializes data for the given URL. """
        if self._source is not SatelliteSource.LYNGSAT:
            raise ValueError("Unsupported source: {}!".format(self._source.name))

        self._rows.clear()
        request = requests.get(url=url, headers=_HEADERS)
        reason = request.reason

        if reason == "OK":
            self.feed(request.text)
        else:
            raise ValueError(reason)

    def get_transponders_links(self, sat_url):
        """ Returns transponder links. """
        try:
            self.init_data(sat_url)
        except ValueError as e:
            log(e)
        else:
            url = "https://www.lyngsat.com/muxes/"
            return [row[0] for row in
                    filter(lambda x: x and len(x) > 8 and x[0].url and x[0].url.startswith(url), self._rows)]
        return []

    def get_transponder_services(self, tr_url, sat_position=None, use_pids=False):
        """ Returns services for given transponder.

            @param tr_url: transponder URL.
            @param sat_position: custom satellite position. Sometimes required to adjust the namespace.
            @param use_pids: if possible use additional pids [video, audio].
        """
        services = []
        try:
            self.init_data(tr_url)
        except ValueError as e:
            log(e)
        else:
            pos, freq, sr, fec, pol, namespace, tid, nid = sat_position or 0, 0, 0, 0, 0, 0, 0, 0
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
                        pos = int(SatellitesParser.get_position(
                            "".join(c for c in pos_tr.group(1) if c.isdigit() or c.isalpha())))

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

                        neg_pos = False  # POS = W
                        # For negative (West) positions: 3600 - numeric position value!!!
                        namespace = "{:04x}0000".format(3600 - pos if neg_pos else pos)
                        inv = 2  # Default
                        fec = get_key_by_value(FEC, _fec)
                        sys = get_key_by_value(SYSTEM, sys)
                        tr_flag = 1
                        mod = get_key_by_value(MODULATION, mod)
                        roll_off = 0  # 35% DVB-S2/DVB-S (default)
                        pilot = 2  # Auto
                        s2_flags = "" if sys == "DVB-S" else self._S2_TR.format(tr_flag, mod or 0, roll_off, pilot)
                        nid, tid = int(nid), int(tid)
                        tr = self._TR.format(freq, sr, pol, fec, pos, inv, sys, s2_flags)

            if not tr:
                msg = "ServicesParser error [get transponder services]: {}"
                er = "Transponder [{}] not found or its type [T2-MI, etc] not supported yet.".format(freq)
                log(msg.format(er))
                return []

            # Services
            for r in filter(lambda x: x and len(x) == 12 and (x[0].text.isdigit()), self._rows):
                sid, name, s_type, v_pid, a_pid, cas, pkg = r[0].text, r[2].text, r[4].text, r[
                    5].text.strip(), r[6].text.split(), r[9].text, r[10].text.strip()

                try:
                    s_type = self._S_TYPES.get(s_type, "3")  # 3 = Data
                    _s_type = SERVICE_TYPE.get(s_type, SERVICE_TYPE.get("3"))  # str repr
                    sid = int(sid)
                    data_id = "{:04x}:{}:{:04x}:{:04x}:{}:0:0".format(sid, namespace, tid, nid, s_type)
                    fav_id = "{}:{}:{}:{}".format(sid, tid, nid, namespace)
                    picon_id = "1_0_{:X}_{}_{}_{}_{}_0_0_0.png".format(int(s_type), sid, tid, nid, namespace)
                    # Flags.
                    flags = "p:{}".format(pkg)
                    cas = ",".join(get_key_by_value(CAS, c) or "C:0000" for c in cas.split()) if cas else None
                    if use_pids:
                        v_pid = "c:00{:04x}".format(int(v_pid)) if v_pid else None
                        a_pid = ",".join(["c:01{:04x}".format(int(p)) for p in a_pid]) if a_pid else None
                        flags = ",".join(filter(None, (flags, v_pid, a_pid, cas)))
                    else:
                        flags = ",".join(filter(None, (flags, cas)))

                    services.append(Service(flags, "s", None, name, None, None, pkg, _s_type, r[1].img, picon_id,
                                            sid, freq, sr, pol, fec, sys, pos, data_id, fav_id, tr))
                except ValueError as e:
                    log("ServicesParser error [get transponder services]: {}".format(e))

        return services


if __name__ == "__main__":
    pass

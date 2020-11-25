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

_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux i586; rv:31.0) Gecko/20100101 Firefox/69.0"}


class SatelliteSource(Enum):
    FLYSAT = ("https://www.flysat.com/satlist.php",)
    LYNGSAT = ("https://www.lyngsat.com/asia.html", "https://www.lyngsat.com/europe.html",
               "https://www.lyngsat.com/atlantic.html", "https://www.lyngsat.com/america.html")

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
            self._current_row.append(attrs[0][1])

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
                extra_pattern = re.compile(r"^https://www\.lyngsat\.com/[\w-]+\.html")
                base_url = "https://www.lyngsat.com/"
                sats = []
                names = set()
                current_pos = "0"
                for row in filter(lambda x: len(x) in (5, 7, 8), self._rows):
                    r_len = len(row)
                    if r_len == 7:
                        current_pos = self.parse_position(row[2])
                        name = row[1].rsplit("/")[-1].rstrip(".html").replace("-", " ")
                        if name not in names:
                            # [all in one] satellites
                            sats.append((name, current_pos, row[5], base_url + row[1], False))
                            names.add(name)
                        name = row[4]
                        if name not in names:
                            sats.append((name, current_pos, row[5], base_url + row[3], False))
                            names.add(name)
                    if r_len == 8:  # for a very limited number of satellites
                        data = list(filter(None, row))
                        urls = set()
                        sat_type = ""
                        for d in data:
                            url = re.match(extra_pattern, d)
                            if url:
                                urls.add(url.group(0))
                            if d in ("C", "Ku", "CKu"):
                                sat_type = d
                        current_pos = self.parse_position(data[1])
                        for url in urls:
                            name = url.rsplit("/")[-1].rstrip(".html").replace("-", " ")
                            sats.append((name, current_pos, sat_type, base_url + url, False))
                    elif r_len == 5:
                        sats.append((row[2], current_pos, row[3], base_url + row[1], False))
                return sats

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
        url = "https://www.flysat.com/" + sat_url if self._source is SatelliteSource.FLYSAT else sat_url
        request = requests.get(url=url, headers=_HEADERS)
        reason = request.reason
        trs = []
        if reason == "OK":
            self.feed(request.text)
            if self._source is SatelliteSource.FLYSAT:
                self.get_transponders_for_fly_sat(trs)
            elif self._source is SatelliteSource.LYNGSAT:
                self.get_transponders_for_lyng_sat(trs)

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
        """ Parsing transponders for LyngSat """
        frq_pol_pattern = re.compile("(\\d{4,5})\\s+([RLHV]).*")
        sr_fec_pattern = re.compile("^(\\d{4,5})-(\\d/\\d)(.+PSK)?(.*)?$")
        sys_pattern = re.compile("(DVB-S[2]?) ?(PLS+ (Root|Gold|Combo)+ (\\d+))* ?(multistream stream (\\d+))?",
                                 re.IGNORECASE)
        zeros = "000"
        pls_modes = {v: k for k, v in PLS_MODE.items()}

        for r in filter(lambda x: len(x) > 8, self._rows):
            for frq in r[1], r[2], r[3]:
                freq = re.match(frq_pol_pattern, frq)
                if freq:
                    break
            if not freq:
                continue
            frq, pol = freq.group(1), freq.group(2)
            sr_fec = re.match(sr_fec_pattern, r[-3])
            if not sr_fec:
                continue
            sr, fec, mod = sr_fec.group(1), sr_fec.group(2), sr_fec.group(3)
            mod = mod.strip() if mod else "Auto"

            res = re.match(sys_pattern, r[-4])
            if not res:
                continue

            sys = res.group(1)
            pls_mode = res.group(3)
            pls_mode = pls_modes.get(pls_mode.capitalize(), None) if pls_mode else pls_mode
            pls_code = res.group(4)
            pls_id = res.group(6)

            tr = Transponder(frq + zeros, sr + zeros, pol, fec, sys, mod, pls_mode, pls_code, pls_id)
            if is_transponder_valid(tr):
                trs.append(tr)


class ServicesParser(HTMLParser):
    """ Services parser for LYNGSAT source. """

    def __init__(self, source=SatelliteSource.LYNGSAT, entities=False, separator=' '):

        HTMLParser.__init__(self)

        self._S_TYPES = {"": "2", "MPEG-2 SD": "1", "MPEG-4 SD": "22", "MPEG-4 HD": "25", "HEVC UHD": "31"}
        self._TR_PAT = re.compile(r"(DVB-S[2]?)/?(.*PSK)?\s+SR\s+(\d+)\s+FEC\s+(\d/\d)\s+ONID/TID:\s+(\d+)/(\d+)\s+.*")
        self._PTR_PAT = re.compile(r".*?(\d+\.\d°[EW]):\s+(\d+)\s+([RLHV]).*")
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
            return [row[1] for row in
                    filter(lambda x: x and len(x) > 8 and x[1].url and x[1].url.startswith(url), self._rows)]
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
            tr_found = False
            pos_found = False
            tr = None
            # Transponder
            for r in filter(lambda x: x and len(x) == 2, self._rows):
                if not pos_found:
                    pos_tr = re.match(self._PTR_PAT, r[1].text)
                    if pos_tr:
                        if not sat_position:
                            pos = int(SatellitesParser.get_position(
                                "".join(c for c in pos_tr.group(1) if c.isdigit() or c.isalpha())))
                        freq = int(pos_tr.group(2))
                        pol = get_key_by_value(POLARIZATION, pos_tr.group(3))
                        pos_found = True

                if pos_found and not tr_found:
                    td = re.match(self._TR_PAT, r[1].text) or re.match(self._TR_PAT, r[0].text)
                    if td:
                        sys, mod, sr, _fec, nid, tid = td.group(1), td.group(2), td.group(3), td.group(4), td.group(
                            5), td.group(6)
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
                        tr_found = True

            if not tr:
                msg = "ServicesParser error [get transponder services]: {}"
                er = "Transponder [{}] not found or its type [T2-MI, etc] not supported yet.".format(freq)
                log(msg.format(er))
                return []

            # Services
            for r in filter(lambda x: x and len(x) == 12 and (x[0].text.isdigit()), self._rows):
                sid, name, cas, pkg, s_type, v_pid, a_pid = r[0].text, r[2].text, r[4].text, r[5].text, r[
                    6].text.strip(), r[7].text, r[8].text.split()

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

                    srv = Service(flags_cas=flags,
                                  transponder_type="s",
                                  coded=None,
                                  service=name,
                                  locked=None,
                                  hide=None,
                                  package=pkg,
                                  service_type=_s_type,
                                  picon=r[1].img,
                                  picon_id=picon_id,
                                  ssid=sid,
                                  freq=freq,
                                  rate=sr,
                                  pol=pol,
                                  fec=fec,
                                  system=sys,
                                  pos=pos,
                                  data_id=data_id,
                                  fav_id=fav_id,
                                  transponder=tr)
                    services.append(srv)
                except ValueError as e:
                    log("ServicesParser error [get transponder services]: {}".format(e))

        return services


if __name__ == "__main__":
    pass

""" Module for download satellites from internet ("flysat.com")
    for  replace or update current satellites.xml file.
"""
import re
import requests
from enum import Enum
from html.parser import HTMLParser

from app.eparser import Satellite, Transponder


class SatelliteSource(Enum):
    FLYSAT = ("https://www.flysat.com/satlist.php",)
    LYNGSAT = ("https://www.lyngsat.com/asia.html", "https://www.lyngsat.com/europe.html",
               "https://www.lyngsat.com/atlantic.html", "https://www.lyngsat.com/america.html")

    @staticmethod
    def get_sources(src):
        return src.value


class SatellitesParser(HTMLParser):
    """ Parser for satellite html page. """

    _HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:45.0) Gecko/20100101 Firefox/59.02"}

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
        if tag == 'td':
            self._is_td = True
        if tag == 'tr':
            self._is_th = True
        if tag == "a":
            self._current_row.append(attrs[0][1])

    def handle_data(self, data):
        """ Save content to a cell """
        if self._is_td or self._is_th:
            self._current_cell.append(data.strip())

    def handle_endtag(self, tag):
        if tag == 'td':
            self._is_td = False
        elif tag == 'tr':
            self._is_th = False

        if tag in ('td', 'th'):
            final_cell = self._separator.join(self._current_cell).strip()
            self._current_row.append(final_cell)
            self._current_cell = []
        elif tag == 'tr':
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
            request = requests.get(url=src, headers=self._HEADERS)
            reason = request.reason
            if reason == "OK":
                self.feed(request.text)
            else:
                print(reason)

        if self._rows:
            if self._source is SatelliteSource.FLYSAT:
                def get_sat(r):
                    return r[1], self.parse_position(r[2]), r[3], r[0], False

                return list(map(get_sat, filter(lambda x: all(x) and len(x) == 5, self._rows)))
            elif self._source is SatelliteSource.LYNGSAT:
                rows = filter(lambda x: len(x) in (5, 7), self._rows)
                sats = []
                current_pos = "0"
                for row in rows:
                    r_len = len(row)
                    if r_len == 7:
                        current_pos = self.parse_position(row[2])
                        sats.append((row[4], current_pos, row[5], row[1], False))
                    elif r_len == 5:
                        sats.append((row[2], current_pos, row[3], row[1], False))
                return sats

    def get_satellite(self, sat):
        pos = sat[1]
        return Satellite(name=sat[0] + " ({})".format(pos),
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
        self._rows.clear()
        url = "https://www.flysat.com/" + sat_url if self._source is SatelliteSource.FLYSAT else sat_url
        request = requests.get(url=url, headers=self._HEADERS)
        reason = request.reason
        trs = []
        if reason == "OK":
            self.feed(request.text)
            if self._source is SatelliteSource.FLYSAT:
                self.get_transponders_for_fly_sat(trs)
            elif self._source is SatelliteSource.LYNGSAT:
                self.get_transponders_for_lyng_sat(trs)
        return trs

    def get_transponders_for_fly_sat(self, trs):
        """ Parsing transponders for FlySat """
        if self._rows:
            zeros = "000"
            for r in self._rows:
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
                trs.append(Transponder(freq + zeros, sr + zeros, pol, fec, sys, mod, None, None, None))

    def get_transponders_for_lyng_sat(self, trs):
        """ Parsing transponders for LyngSat """
        frq_pol_pattern = re.compile("(\d{4,5}).*([RLHV])(.*\d$)")
        sr_fec_pattern = re.compile("^(\d{4,5})-(\d/\d)(.+PSK)?(.*)?$")
        sys_pattern = re.compile("(DVB-S[2]?)(.*)?")
        zeros = "000"
        for r in filter(lambda x: len(x) > 8, self._rows):
            freq = re.match(frq_pol_pattern, r[2])
            if not freq:
                continue
            frq, pol = freq.group(1), freq.group(2)
            sr_fec = re.match(sr_fec_pattern, r[-3])
            if not sr_fec:
                continue
            sr, fec, mod = sr_fec.group(1), sr_fec.group(2), sr_fec.group(3)
            mod = mod.strip() if mod else "Auto"
            sys = re.match(sys_pattern, r[-4])
            if not sys:
                continue
            sys = sys.group(1)
            trs.append(Transponder(frq + zeros, sr + zeros, pol, fec, sys, mod, None, None, None))


if __name__ == "__main__":
    pass

""" Module for download satellites from internet ("flysat.com")
    for  replace or update current satellites.xml file.
"""
import requests
from html.parser import HTMLParser

from app.eparser import Satellite, Transponder


class SatellitesParser(HTMLParser):
    """ Parser for satellite html page. """

    _HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:45.0) Gecko/20100101 Firefox/59.02"}

    def __init__(self, url="https://www.flysat.com/satlist.php", entities=False, separator=' '):

        HTMLParser.__init__(self)

        self._parse_html_entities = entities
        self._separator = separator
        self._is_td = False
        self._is_th = False
        self._is_provider = False
        self._current_row = []
        self._current_cell = []
        self._rows = []
        self._url = url

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

    def get_satellites_list(self):
        self.reset()
        request = requests.get(url=self._url, headers=self._HEADERS)
        reason = request.reason
        if reason == "OK":
            self.feed(request.text)
            if self._rows:
                def get_sat(r):
                    return r[1], "".join(c for c in r[2] if c.isdigit() or c.isalpha() or c == "."), r[3], r[0], False
                return list(map(get_sat, filter(lambda x: all(x) and len(x) == 5, self._rows)))
        else:
            print(reason)

    def get_satellite(self, sat):
        pos = sat[1]
        return Satellite(name=sat[0] + " ({})".format(pos),
                         flags="0",
                         position=self.get_position(pos.replace(".", "")),
                         transponders=self.get_transponders(sat[3]))

    @staticmethod
    def get_position(pos):
        return "{}{}".format("-" if pos[-1] == "W" else "", pos[:-1])

    def get_transponders(self, sat_url):
        self._rows.clear()
        url = "https://www.flysat.com/" + sat_url
        request = requests.get(url=url, headers=self._HEADERS)
        reason = request.reason
        trs = []
        if reason == "OK":
            self.feed(request.text)
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
                    freq, pol, tr_type = data[0], data[1], data[2]
                    tr_type = tr_type.split("/")
                    if len(tr_type) != 2:
                        continue
                    tr_type, mod = tr_type
                    mod = "QPSK" if tr_type == "DVB-S" else mod
                    trs.append(Transponder(freq + zeros, sr + zeros, pol, fec, tr_type, mod, None, None, None))

        return trs


if __name__ == "__main__":
    pass



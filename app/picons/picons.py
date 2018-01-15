import os
import shutil
from collections import namedtuple
from html.parser import HTMLParser

from app.properties import Profile

Provider = namedtuple("Provider", ["logo", "name", "url", "on_id", "selected"])
Picon = namedtuple("Picon", ["ref", "ssid", "v_pid"])


class PiconsParser(HTMLParser):
    """ Parser for package html page. (https://www.lyngsat.com/packages/*provider-name*.html) """

    def __init__(self, entities=False, separator=' '):

        HTMLParser.__init__(self)

        self._parse_html_entities = entities
        self._separator = separator
        self._is_td = False
        self._is_th = False
        self._current_row = []
        self._current_cell = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == 'td':
            self._is_td = True
        if tag == 'th':
            self._is_th = True
        if tag == "img":
            self._current_row.append(attrs[0][1])

    def handle_data(self, data):
        """ Save content to a cell """
        if self._is_td or self._is_th:
            self._current_cell.append(data.strip())

    def handle_endtag(self, tag):
        if tag == 'td':
            self._is_td = False
        elif tag == 'th':
            self._is_th = False

        if tag in ('td', 'th'):
            final_cell = self._separator.join(self._current_cell).strip()
            self._current_row.append(final_cell)
            self._current_cell = []
        elif tag == 'tr':
            row = self._current_row
            ln = len(row)
            if ln == 10 and row[0].startswith("../logo/"):
                self.rows.append((row[0], row[-4]))
            elif ln == 11:
                self.rows.append((row[0] if row[0].startswith("../logo/") else row[1], row[-4]))
            self._current_row = []

    def error(self, message):
        pass

    @staticmethod
    def parse(open_path, picons_path, tmp_path):
        with open(open_path, encoding="utf-8", errors="replace") as f:
            parser = PiconsParser()
            parser.reset()
            parser.feed(f.read())
            rows = parser.rows

            if rows:
                os.makedirs(picons_path, exist_ok=True)
                for r in rows:
                    shutil.copyfile(tmp_path + "www.lyngsat.com/" + r[0].lstrip("."),
                                    picons_path + PiconsParser.format(r[1], Profile.ENIGMA_2))

    @staticmethod
    def format(ssid, profile: Profile):
        if profile is Profile.ENIGMA_2:
            tr_id = int(ssid[:-2] if len(ssid) < 4 else ssid[:2])
            return "1_0_1_{:X}_{:X}_{}_1680000_0_0_0.png".format(int(ssid), tr_id, "70")
        elif profile is Profile.NEUTRINO_MP:
            return "{:x}{}{:x}".format(int(ssid[:-2]), "0070", int(ssid))
        else:
            return "{}.png".format(ssid)


class ProviderParser(HTMLParser):
    """ Parser for satellite html page. (https://www.lyngsat.com/*sat-name*.html) """

    def __init__(self, entities=False, separator=' '):

        HTMLParser.__init__(self)

        self._ON_ID_BLACK_LIST = ("65535", "?", "0", "1")
        self._parse_html_entities = entities
        self._separator = separator
        self._is_td = False
        self._is_th = False
        self._is_provider = False
        self._current_row = []
        self._current_cell = []
        self.rows = []
        self._ids = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'td':
            self._is_td = True
        if tag == 'tr':
            self._is_th = True
        if tag == "img":
            if attrs[0][1].startswith("logo/"):
                self._current_row.append(attrs[0][1])
        if tag == "a":
            if "https://www.lyngsat.com/packages/" in attrs[0][1]:
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
            if len(row) == 12:
                on_id, sep, tid = str(row[-2]).partition("-")
                if tid and on_id not in self._ON_ID_BLACK_LIST and on_id not in self._ids:
                    self.rows.append(row)
                    self._ids.add(on_id)
            self._current_row = []

    def error(self, message):
        pass


def parse_providers(open_path):
    with open(open_path, encoding="utf-8", errors="replace") as f:
        parser = ProviderParser()
        parser.reset()
        parser.feed(f.read())
        rows = parser.rows

        if rows:
            return [Provider(logo=r[2], name=r[5], url=r[6], on_id=r[-2], selected=True) for r in rows]


if __name__ == "__main__":
    pass

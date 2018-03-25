import glob
import os
import shutil
from collections import namedtuple
from html.parser import HTMLParser

import re

from app.commons import log, run_task
from app.properties import Profile

_ENIGMA2_PICON_KEY = "{:X}:{:X}:{:X}0000"
_NEUTRINO_PICON_KEY = "{:x}{:04x}{:04x}.png"

Provider = namedtuple("Provider", ["logo", "name", "pos", "url", "on_id", "selected"])
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
        self.picons = []

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
            if 9 < ln < 13:
                url = None
                if row[0].startswith("../logo/"):
                    url = row[0]
                elif row[1].startswith("../logo/"):
                    url = row[1]

                ssid = row[-4]
                if url and len(ssid) > 2:
                    self.picons.append(Picon(url, ssid, row[-3]))

            self._current_row = []

    def error(self, message):
        pass

    @staticmethod
    def parse(open_path, picons_path, tmp_path, on_id, pos, picon_ids, profile=Profile.ENIGMA_2):
        with open(open_path, encoding="utf-8", errors="replace") as f:
            parser = PiconsParser()
            parser.reset()
            parser.feed(f.read())
            picons = parser.picons
            if picons:
                os.makedirs(picons_path, exist_ok=True)
                for p in picons:
                    try:
                        name = PiconsParser.format(p.ssid, on_id, p.v_pid, pos, picon_ids, profile)
                        p_name = picons_path + (name if name else os.path.basename(p.ref))
                        shutil.copyfile(tmp_path + "www.lyngsat.com/" + p.ref.lstrip("."), p_name)
                    except (TypeError, ValueError) as e:
                        log("Picons format parse error: {}".format(p) + "\n" + str(e))
                        print(e)

    @staticmethod
    def format(ssid, on_id, v_pid, pos, picon_ids, profile: Profile):
        tr_id = int(ssid[:-2] if len(ssid) < 4 else ssid[:2])
        if profile is Profile.ENIGMA_2:
            return picon_ids.get(_ENIGMA2_PICON_KEY.format(int(ssid), int(on_id), int(pos)), None)
        elif profile is Profile.NEUTRINO_MP:
            return _NEUTRINO_PICON_KEY.format(tr_id, int(on_id), int(ssid))
        else:
            return "{}.png".format(ssid)


class ProviderParser(HTMLParser):
    """ Parser for satellite html page. (https://www.lyngsat.com/*sat-name*.html) """

    _POSITION_PATTERN = re.compile("at\s\d+\..*(?:E|W)']")

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
        self._positon = None

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
            # Satellite position
            if not self._positon:
                pos = re.findall(self._POSITION_PATTERN, str(row))
                if pos:
                    self._positon = "".join(c for c in str(pos) if c.isdigit() or c in ".EW")

            if len(row) == 12:
                on_id, sep, tid = str(row[-2]).partition("-")
                if tid and on_id not in self._ON_ID_BLACK_LIST and on_id not in self._ids:
                    row[-2] = on_id
                    self.rows.append(row)
                    self._ids.add(on_id)
                row[0] = self._positon
            self._current_row = []

    def error(self, message):
        pass

    def reset(self):
        super().reset()


def parse_providers(open_path):
    parser = ProviderParser()
    parser.reset()

    with open(open_path, encoding="utf-8", errors="replace") as f:
        parser.feed(f.read())
        rows = parser.rows

        if rows:
            return [Provider(logo=r[2], name=r[5], pos=r[0], url=r[6], on_id=r[-2], selected=True) for r in rows]


@run_task
def convert_to(src_path, dest_path, profile, callback, done_callback):
    """ Converts names format of picons.

        Copies resulting files from src to dest and writes state to callback.
    """
    pattern = "/*_0_0_0.png" if profile is Profile.ENIGMA_2 else "/*.png"
    for file in glob.glob(src_path + pattern):
        base_name = os.path.basename(file)
        pic_data = base_name.rstrip(".png").split("_")
        dest_file = _NEUTRINO_PICON_KEY.format(int(pic_data[4], 16), int(pic_data[5], 16), int(pic_data[3], 16))
        dest = "{}/{}".format(dest_path, dest_file)
        callback('Converting "{}" to "{}"\n'.format(base_name, dest_file))
        shutil.copyfile(file, dest)

    done_callback()


if __name__ == "__main__":
    pass

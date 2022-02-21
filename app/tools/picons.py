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


import glob
import os
import re
import shutil
import subprocess
from collections import namedtuple
from html.parser import HTMLParser

import requests

from app.commons import run_task, log
from app.settings import SettingsType, IS_LINUX, IS_WIN, IS_DARWIN, GTK_PATH
from .satellites import _HEADERS

_ENIGMA2_PICON_KEY = "{:X}:{:X}:{}"
_NEUTRINO_PICON_KEY = "{:x}{:04x}{:04x}.png"

Provider = namedtuple("Provider", ["logo", "name", "pos", "url", "on_id", "ssid", "single", "selected"])
Picon = namedtuple("Picon", ["ref", "ssid"])


class PiconsError(Exception):
    pass


class PiconsCzDownloader:
    """ The main class for loading picons from the https://picon.cz/ source (by Chocholoušek). """

    _PERM_URL = "https://picon.cz/download/7337"
    _BASE_URL = "https://picon.cz/download/"
    _BASE_LOGO_URL = "https://picon.cz/picon/0/"
    _HEADER = {"User-Agent": "DemonEditor/2.2.0", "Referer": ""}
    _LINK_PATTERN = re.compile(r"((.*)-\d+x\d+)-(.*)_by_chocholousek.7z$")
    _FILE_PATTERN = re.compile(b"\\s+(1_.*\\.png).*")

    def __init__(self, picon_ids=set(), appender=log):
        self._perm_links = {}
        self._providers = {}
        self._provider_logos = {}
        self._picon_ids = picon_ids
        self._appender = appender

    def init(self):
        """ Initializes dict with values: download_id -> perm link and provider data.  """
        if self._perm_links:
            return

        self._HEADER["Referer"] = self._PERM_URL

        with requests.get(url=self._PERM_URL, headers=self._HEADER, stream=True) as request:
            if request.reason == "OK":
                logo_map = self.get_logos_map()
                name_map = self.get_name_map()

                for line in request.iter_lines():
                    data = line.decode(encoding="utf-8", errors="ignore").split(maxsplit=1)
                    if len(data) != 2:
                        continue

                    l_id, perm_link = data
                    self._perm_links[str(l_id)] = str(perm_link)
                    data = re.match(self._LINK_PATTERN, perm_link)
                    if data:
                        sat_pos = data.group(3)
                        # Logo url.
                        logo = logo_map.get(data.group(2), None)
                        l_name = name_map.get(sat_pos, None) or sat_pos.replace(".", "")
                        logo_url = f"{self._BASE_LOGO_URL}{logo}/{l_name}.png" if logo else None

                        prv = Provider(None, data.group(1), sat_pos, self._BASE_URL + l_id, l_id, logo_url, None, False)
                        if sat_pos in self._providers:
                            self._providers[sat_pos].append(prv)
                        else:
                            self._providers[sat_pos] = [prv]
            else:
                log(f"{self.__class__.__name__} [get permalinks] error: {request.reason}")
                raise PiconsError(request.reason)

    @property
    def providers(self):
        return self._providers

    def get_sat_providers(self, url):
        return self._providers.get(url, [])

    def download(self, provider, picons_path, picon_ids=None):
        self._HEADER["Referer"] = provider.url
        with requests.get(url=provider.url, headers=self._HEADER, stream=True) as request:
            if request.reason == "OK":
                dest = f"{picons_path}{provider.on_id}.7z"
                self._appender(f"Downloading: {provider.url}\n")
                with open(dest, mode="bw") as f:
                    for data in request.iter_content(chunk_size=1024):
                        f.write(data)
                self._appender(f"Extracting: {provider.on_id}\n")
                self.extract(dest, picons_path, picon_ids)
            else:
                log(f"{self.__class__.__name__} [download] error: {request.reason}")

    def extract(self, src, dest, picon_ids=None):
        """ Extracts 7z archives. """
        # TODO: think about https://github.com/miurahr/py7zr
        exe = "7z"
        if IS_DARWIN and GTK_PATH:
            exe = "./7zr"

        if IS_LINUX and not os.path.isfile(f"/usr/bin/{exe}"):
            raise PiconsError("7-zip [7z] archiver not found!")

        if IS_WIN:
            exe = f"C:{os.sep}Program Files{os.sep}7-Zip{os.sep}{exe}.exe"
            if not os.path.isfile(exe):
                raise PiconsError("7-Zip executable not found!")

        cmd = [exe, "l", src]
        try:
            out, err = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
            if err:
                log(f"{self.__class__.__name__} [extract] error: {err}")
                raise PiconsError(err)
        except OSError as e:
            log(f"{self.__class__.__name__} [extract] error: {e}")
            raise PiconsError(e)

        is_filter = bool(picon_ids)
        ids = picon_ids or self._picon_ids
        to_extract = []

        for o in re.finditer(self._FILE_PATTERN, out):
            p_id = o.group(1).decode("utf-8", errors="ignore")
            if p_id in ids:
                to_extract.append(p_id)

        if is_filter and not to_extract:
            if os.path.isfile(src):
                os.remove(src)
            raise PiconsError("No matching picons found!")

        cmd = [exe, "e", src, "-o{}".format(dest), "-y", "-r"]
        cmd.extend(to_extract)
        try:
            out, err = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
            if err:
                log(f"{self.__class__.__name__} [extract] error: {err}")
                raise PiconsError(err)
            else:
                if os.path.isfile(src):
                    os.remove(src)
        except OSError as e:
            log(e)
            raise PiconsError(e)

    def get_logo_data(self, url):
        """ Returns the logo data if present. """
        return self._provider_logos.get(url, None)

    def get_provider_logo(self, url):
        """ Retrieves package logo. """
        # Getting package logo.
        logo = self._provider_logos.get(url, None)
        if logo:
            return logo

        try:
            with requests.get(url=url, stream=True) as logo_request:
                if logo_request.reason == "OK":
                    data = logo_request.content
                    self._provider_logos[url] = data
                    return data
                else:
                    log(f"Downloading package logo error: {logo_request.reason}")
        except requests.exceptions.ConnectionError as e:
            log(f"{self.__class__.__name__} error [get provider logo]: {e}")

    def get_logos_map(self):
        return {"piconblack": "b50",
                "picontransparent": "t50",
                "piconwhite": "w50",
                "piconmirrorglass": "mr100",
                "piconnoName": "n100",
                "piconsrhd": "srhd100",
                "piconfreezeframe": "ff220",
                "piconfreezewhite": "fw100",
                "piconpoolrainbow": "r100",
                "piconsimpleblack": "s220",
                "piconjustblack": "jb220",
                "picondirtypaper": "dp220",
                "picongray": "g400",
                "piconmonochrom": "m220",
                "picontransparentwhite": "tw100",
                "picontransparentdark": "td220",
                "piconoled": "o96",
                "piconblack80": "b50",
                "piconblack3d": "b50",
                "piconwin11": "win11220"
                }

    def get_name_map(self):
        return {"antiksat": "ANTIK",
                "digiczsk": "DIGI",
                "DTTitaly": "picon_trs-it",
                "dvbtCZSK": "picon_trs",
                "PolandDTT": "picon_trs-pl",
                "freeSAT": "UPC DIRECT",
                "orangesat": "ORANGE TV",
                "skylink": "M7 GROUP",
                }


class PiconsParser(HTMLParser):
    """ Parser for package html page. (https://www.lyngsat.com/packages/*provider-name*.html) """
    _BASE_URL = "https://www.lyngsat.com"

    def __init__(self, entities=False, separator=' ', single=None):

        HTMLParser.__init__(self)

        self._parse_html_entities = entities
        self._separator = separator
        self._single = single
        self._is_td = False
        self._is_th = False
        self._current_row = []
        self._current_cell = []
        self.picons = []

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self._is_td = True
        if tag == "th":
            self._is_th = True
        if tag == "img":
            self._current_row.append(attrs[0][1])

    def handle_data(self, data):
        """ Save content to a cell """
        if self._is_td or self._is_th:
            self._current_cell.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "td":
            self._is_td = False
        elif tag == "th":
            self._is_th = False

        if tag in ("td", "th"):
            final_cell = self._separator.join(self._current_cell).strip()
            self._current_row.append(final_cell)
            self._current_cell = []
        elif tag == "tr":
            row = self._current_row
            ln = len(row)

            if self._single and ln == 4 and row[0].startswith("/logo/"):
                self.picons.append(Picon(row[0].strip(), "0"))
            else:
                if ln > 8:
                    url = None
                    if row[2].startswith("/logo/"):
                        url = row[2]

                    if url and row[0].isdigit():
                        self.picons.append(Picon(url, row[0]))

            self._current_row = []

    def error(self, message):
        pass

    @staticmethod
    def parse(provider, picons_path, picon_ids, s_type=SettingsType.ENIGMA_2):
        """ Returns tuple(url, picon file name) list. """
        req = requests.get(provider.url, timeout=5)
        if req.status_code == 200:
            logo_data = req.text
        else:
            log("Provider picons downloading error: {} {}".format(provider.url, req.reason))
            return

        on_id, pos, ssid, single = provider.on_id, provider.pos, provider.ssid, provider.single
        neg_pos = pos.endswith("W")
        pos = int("".join(c for c in pos if c.isdigit()))
        # For negative (West) positions 3600 - numeric position value!!!
        if neg_pos:
            pos = 3600 - pos

        parser = PiconsParser(single=provider.single)
        parser.reset()
        parser.feed(logo_data)
        picons = parser.picons
        picons_data = []

        if picons:
            for p in picons:
                try:
                    if single:
                        on_id, freq = on_id.strip().split("::")
                        namespace = "{:X}{:X}".format(int(pos), int(freq))
                    else:
                        namespace = "{:X}0000".format(int(pos))

                    if single and not ssid.isdigit():
                        ssid = "".join(c for c in ssid if c.isdigit()) or "0"
                    name = PiconsParser.format(ssid if single else p.ssid, on_id, namespace, picon_ids, s_type)
                    p_name = picons_path + (name if name else os.path.basename(p.ref))
                    picons_data.append(("{}{}".format(PiconsParser._BASE_URL, p.ref), p_name))
                except (TypeError, ValueError) as e:
                    msg = "Picons format parse error: {}".format(p) + "\n" + str(e)
                    log(msg)

        return picons_data

    @staticmethod
    def format(ssid, on_id, namespace, picon_ids, s_type):
        if s_type is SettingsType.ENIGMA_2:
            return picon_ids.get(_ENIGMA2_PICON_KEY.format(int(ssid), int(on_id), namespace), None)
        elif s_type is SettingsType.NEUTRINO_MP:
            tr_id = int(ssid[:-2] if len(ssid) < 4 else ssid[:2])
            return _NEUTRINO_PICON_KEY.format(tr_id, int(on_id), int(ssid))
        else:
            return "{}.png".format(ssid)


class ProviderParser(HTMLParser):
    """ Parser for satellite html page. (https://www.lyngsat.com/*sat-name*.html) """

    _POSITION_PATTERN = re.compile("at\s\d+\..*(?:E|W)']")
    _ONID_TID_PATTERN = re.compile("^\d+-\d+.*")
    _TRANSPONDER_FREQUENCY_PATTERN = re.compile("^\d+ [HVLR]+")
    _DOMAINS = {"/tvchannels/", "/radiochannels/", "/packages/", "/logo/"}
    _BASE_URL = "https://www.lyngsat.com"

    def __init__(self, entities=False, separator=' '):

        HTMLParser.__init__(self)
        self.convert_charrefs = False

        self._parse_html_entities = entities
        self._separator = separator
        self._is_td = False
        self._is_th = False
        self._is_onid_tid = False
        self._is_provider = False
        self._current_row = []
        self._current_cell = []
        self.rows = []
        self._ids = set()
        self._prv_names = set()
        self._positon = None
        self._on_id = None
        self._freq = None

    def handle_starttag(self, tag, attrs):
        if tag == 'td':
            self._is_td = True
        if tag == 'tr':
            self._is_th = True
        if tag == "img":
            if attrs[0][1].startswith("/logo/"):
                self._current_row.append(attrs[0][1])
        if tag == "a":
            url = attrs[0][1]
            if any(d in url for d in self._DOMAINS):
                self._current_row.append(url)

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

            len_row = len(row)
            if len_row > 2:
                m = self._TRANSPONDER_FREQUENCY_PATTERN.match(row[0])
                if m:
                    self._freq = m.group().split()[0]

            if len_row > 12:
                # Providers
                name = row[5]
                self._prv_names.add(name)
                m = self._ONID_TID_PATTERN.match(str(row[-5]))
                if m:
                    on_id, tid = m.group().split("-")
                    if on_id not in self._ids:
                        self._on_id = on_id
                        row[-2] = on_id
                        self._ids.add(on_id)
                        row[0] = self._positon
                    if name + on_id not in self._prv_names:
                        self._prv_names.add(name + on_id)
                        logo_data = None
                        if row[2].startswith("/logo/"):
                            req = requests.get(self._BASE_URL + row[2], timeout=5)
                            if req.status_code == 200:
                                logo_data = req.content
                            else:
                                log("Downloading provider logo error: {}".format(req.reason))
                        self.rows.append(Provider(logo=logo_data, name=name, pos=self._positon, url=row[6], on_id=on_id,
                                                  ssid=None, single=False, selected=True))
            elif 6 < len_row < 12:
                # Single services
                name, url, ssid = None, None, None
                if row[0].startswith("http"):
                    name, url, ssid = row[1], row[0], row[0]
                elif row[1].startswith("http"):
                    name, url, ssid = row[2], row[1], row[0]

                if name and url:
                    on_id = "{}::{}".format(self._on_id if self._on_id else "1", self._freq)
                    self.rows.append(Provider(logo=None, name=name, pos=self._positon, url=url, on_id=on_id,
                                              ssid=ssid, single=True, selected=False))

            self._current_row = []

    def error(self, message):
        pass

    def reset(self):
        super().reset()


def parse_providers(url):
    """ Returns a list of providers sorted by logo [single channels after providers]. """
    parser = ProviderParser()

    request = requests.get(url=url, headers=_HEADERS)
    if request.status_code == 200:
        parser.feed(request.text)
    else:
        log("Parse providers error [{}]: {}".format(url, request.reason))

    def srt(p):
        if p.logo is None:
            return 1
        return 0

    providers = parser.rows
    providers.sort(key=srt)

    return providers


def download_picon(src_url, dest_path, callback):
    """ Downloads and saves the picon to file.  """
    err_msg = "Picon download error: {}  [{}]"
    timeout = (3, 5)  # connect and read timeouts

    if callback:
        callback("Downloading: {}.\n".format(os.path.basename(dest_path)))

    req = requests.get(src_url, timeout=timeout, stream=True)
    if req.status_code != 200:
        err_msg = err_msg.format(src_url, req.reason)
        log(err_msg)
        if callback:
            callback(err_msg + "\n")
    else:
        try:
            with open(dest_path, "wb") as f:
                for chunk in req:
                    f.write(chunk)
        except OSError as e:
            err_msg = "Saving picon [{}] error: {}".format(dest_path, e)
            log(err_msg)
            if callback:
                callback(err_msg + "\n")


@run_task
def convert_to(src_path, dest_path, s_type, callback, done_callback):
    """ Converts names format of picons.

        Copies resulting files from src to dest and writes state to callback.
    """
    pattern = "/*_0_0_0.png" if s_type is SettingsType.ENIGMA_2 else "/*.png"
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

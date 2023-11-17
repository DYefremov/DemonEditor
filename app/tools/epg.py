# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2023 Dmitriy Yefremov
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


"""  Module for working with epg.dat file. """
import abc
import os
import re
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
from collections import namedtuple
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
from xml.dom.minidom import parse, Node, Document

import requests

from app.commons import log
from app.eparser.ecommons import BqServiceType, BouquetService
from app.settings import IS_WIN

ENCODING = "utf-8"
DETECT_ENCODING = False
try:
    import chardet
except ModuleNotFoundError:
    pass
else:
    DETECT_ENCODING = True

EpgEvent = namedtuple("EpgEvent", ["service_name", "title", "start", "end", "length", "desc", "event_data"])
EpgEvent.__new__.__defaults__ = ("N/A", "N/A", 0, 0, 0, "N/A", None)  # For Python3 < 3.7


class Reader(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def download(self, clb=None): pass

    @abc.abstractmethod
    def get_current_events(self, ids: set) -> dict: pass


class EPG:
    """ Base EPG class. """
    # DVB/EPG count days with a 'modified Julian calendar' where day 1 is 17 November 1858.
    # datetime.datetime.toordinal(1858,11,17) => 678576
    ZERO_DAY = 678576

    Event = namedtuple("EpgEvent", ["id", "data", "start", "duration", "title", "desc", "ext_desc"])

    class EventData:
        """ Event data representation class. """
        __slots__ = ["raw_data", "crc", "size", "type"]

        def __init__(self, size=0, e_type=0):
            self.raw_data = None
            self.crc = None
            self.size = size
            self.type = e_type

        def get_event_id(self):
            return self.raw_data[0] << 8 | self.raw_data[1]

        def get_start_time(self):
            """ Returns start time [sec.]. """
            # Date
            start_date = datetime.fromordinal((self.raw_data[2] << 8 | self.raw_data[3]) + EPG.ZERO_DAY).timestamp()
            # Time
            tm_hour = EPG.get_from_bcd(self.raw_data[4])
            tm_min = EPG.get_from_bcd(self.raw_data[5])
            tm_sec = EPG.get_from_bcd(self.raw_data[6])
            # UTC.
            s_time = start_date + tm_hour * 3600 + tm_min * 60 + tm_sec
            # Time zone correction.
            s_time += datetime.now(timezone.utc).astimezone().utcoffset().seconds

            return s_time

        def get_duration(self):
            """ Returns duration [sec.]."""
            return EPG.get_from_bcd(self.raw_data[7]) * 3600 + EPG.get_from_bcd(
                self.raw_data[8]) * 60 + EPG.get_from_bcd(self.raw_data[9])

    class DatReader(Reader):
        """ The epd.dat file reading class.

            The read algorithm was taken from the eEPGCache::load() function from this source:
            https://github.com/OpenPLi/enigma2/blob/44d9b92f5260c7de1b3b3a1b9a9cbe0f70ca4bf0/lib/dvb/epgcache.cpp#L1300
        """

        def __init__(self, path):
            self._path = path
            self._refs = {}
            self._desc = {}

        def download(self, clb=None):
            pass

        def get_current_events(self, ids: set) -> dict:
            pass

        def get_refs(self):
            return self._refs.keys()

        def get_services(self):
            return self._refs

        def get_event(self, evd):
            title, desc, ext_desc = None, None, None
            e_id, start, duration = evd.get_event_id(), evd.get_start_time(), evd.get_duration()

            for c in evd.crc:
                data = self._desc.get(c, None)
                if not data:
                    continue

                encoding = ENCODING
                if DETECT_ENCODING:
                    # May be slow.
                    encoding = chardet.detect(data).get("encoding", "utf-8") or encoding

                desc_type = data[0]
                if desc_type == 77:  # Short event descriptor -> 0x4d -> 77
                    size = data[6]
                    txt = data[7:-1].decode(encoding, errors="ignore")
                    t_len = len(txt)
                    st = 0

                    if size and size < t_len:
                        st = abs(size - t_len)

                    if size < 32:
                        title = txt
                    else:
                        desc = txt[st:]
                elif desc_type == 78:  # Extended event descriptor -> 0x4e -> 78
                    ext_desc = data[9:].decode(encoding, errors="ignore") if data[7] and data[8] < 32 else None

            return EPG.Event(e_id, evd, start, duration, title, desc, ext_desc)

        def get_events(self, ref):
            return self._refs.get(ref, {})

        def read(self):
            with open(self._path, mode="rb") as f:
                crc = struct.unpack("I", f.read(4))[0]
                if crc != int(0x98765432):
                    raise ValueError("Epg file has incorrect byte order!")

                header = f.read(13).decode()
                if header == "ENIGMA_EPG_V7":
                    epg_ver = 7
                elif header == "ENIGMA_EPG_V8":
                    epg_ver = 8
                else:
                    raise ValueError("Unsupported format of epd.dat file!")

                channels_count = struct.unpack("I", f.read(4))[0]
                _len_read_size = 3 if epg_ver == 8 else 2
                _type_read_str = f"{'H' if epg_ver == 8 else 'B'}B"

                for i in range(channels_count):
                    sid, nid, tsid, events_size = struct.unpack("IIII", f.read(16))
                    service_id = f"{sid:X}:{tsid:X}:{nid:X}"
                    events = {}

                    for j in range(events_size):
                        _type, _len = struct.unpack(_type_read_str, f.read(_len_read_size))
                        event = EPG.EventData(size=_len, e_type=_type)
                        event.raw_data = f.read(10)

                        n_crc = (_len - 10) // 4
                        if n_crc > 0:
                            event.crc = [struct.unpack("I", f.read(4))[0] for n in range(n_crc)]
                            events[event.get_event_id()] = event

                    self._refs[service_id] = events

                for i in range(struct.unpack("I", f.read(4))[0]):
                    _id, ref_count = struct.unpack("II", f.read(8))
                    header = struct.unpack("BB", f.read(2))
                    _bytes = header[1] + 2
                    f.seek(-2, os.SEEK_CUR)
                    self._desc[_id] = f.read(_bytes)

    @staticmethod
    def get_from_bcd(value: int):
        """  Converts a BCD to an integer. """
        if ((value & 0xF0) >= 0xA0) or ((value & 0xF) >= 0xA):
            return -1
        return ((value & 0xF0) >> 4) * 10 + (value & 0xF)


class XmlTvReader(Reader):
    PR_TAG = "programme"
    CH_TAG = "channel"
    DSP_NAME_TAG = "display-name"
    ICON_TAG = "icon"
    TITLE_TAG = "title"
    DESC_TAG = "desc"

    TIME_FORMAT_STR = "%Y%m%d%H%M%S %z"

    SUFFIXES = {".gz", ".xz", ".lzma", ".xml"}

    Service = namedtuple("Service", ["id", "names", "logo", "events"])
    Event = namedtuple("EpgEvent", ["start", "duration", "title", "desc"])

    def __init__(self, path, url):
        self._path = path
        self._url = url
        self._ids = {}

    def download(self, clb=None):
        """ Downloads an XMLTV file. """
        res = urlparse(self._url)
        if not all((res.scheme, res.netloc)):
            log(f"{self.__class__.__name__} [download] error: Invalid URL {self._url}")
            return

        with requests.get(url=self._url, stream=True) as request:
            if request.reason == "OK":
                suf = self._url[self._url.rfind("."):]
                if suf not in self.SUFFIXES:
                    log(f"{self.__class__.__name__} [download] error: Unsupported file extension.")
                    return

                data_len = request.headers.get("content-length")

                with NamedTemporaryFile(suffix=suf, delete=not IS_WIN) as tf:
                    downloaded = 0
                    data_len = int(data_len)
                    log("Downloading XMLTV file...")
                    for data in request.iter_content(chunk_size=1024):
                        downloaded += len(data)
                        tf.write(data)
                        done = int(50 * downloaded / data_len)
                        sys.stdout.write(f"\rDownloading XMLTV file [{'=' * done}{' ' * (50 - done)}]")
                        sys.stdout.flush()
                    tf.seek(0)
                    sys.stdout.write("\n")

                    os.makedirs(os.path.dirname(self._path), exist_ok=True)

                    if suf.endswith(".gz"):
                        try:
                            shutil.copyfile(tf.name, self._path)
                        except OSError as e:
                            log(f"{self.__class__.__name__} [download *.gz] error: {e}")
                    elif self._url.endswith((".xz", ".lzma")):
                        import lzma

                        try:
                            with lzma.open(tf, "rb") as lzf:
                                shutil.copyfileobj(lzf, self._path)
                        except (lzma.LZMAError, OSError) as e:
                            log(f"{self.__class__.__name__} [download *.xz] error: {e}")
                    else:
                        try:
                            import gzip
                            with gzip.open(self._path, "wb") as f_out:
                                shutil.copyfileobj(tf, f_out)
                        except OSError as e:
                            log(f"{self.__class__.__name__} [download *.xml] error: {e}")

                    if IS_WIN and os.path.isfile(tf.name):
                        tf.close()
                        os.remove(tf.name)
            else:
                log(f"{self.__class__.__name__} [download] error: {request.reason}")

        if clb:
            clb()

    def get_current_events(self, names: set) -> dict:
        events = {}

        dt = datetime.utcnow()
        utc = dt.timestamp()
        offset = datetime.now() - dt

        for srv in filter(lambda s: any(name in names for name in s.names), self._ids.values()):
            ev = max(filter(lambda s: s.start < utc, srv.events), key=lambda x: x.start, default=None)
            if ev:
                start = datetime.fromtimestamp(ev.start) + offset
                end_time = datetime.fromtimestamp(ev.duration) + offset
                start = start.timestamp()
                end_time = end_time.timestamp()

                for n in srv.names:
                    events[n] = EpgEvent(n, ev.title, start, end_time, int(ev.duration), ev.desc, ev)

        return events

    def parse(self):
        """ Parses XML. """
        try:
            import gzip

            with gzip.open(self._path, "rb") as gzf:
                log("Processing XMLTV data...")
                list(map(self.process_node, ET.iterparse(gzf)))
                log("XMLTV data parsing is complete.")
        except OSError as e:
            log(f"{self.__class__.__name__} [parse] error: {e}")

    def process_node(self, node):
        event, element = node
        if element.tag == self.CH_TAG:
            ch_id = element.get("id", None)
            logo = None  # Currently not in use.
            # Since a service can have several names, we will store a set of names in the "names" field!
            self._ids[ch_id] = self.Service(ch_id, {c.text for c in element if c.tag == self.DSP_NAME_TAG}, logo, [])
        elif element.tag == self.PR_TAG:
            channel = self._ids.get(element.get(self.CH_TAG, None), None)
            if channel:
                events = channel[-1]
                start = element.get("start", None)
                if start:
                    start = self.get_utc_time(start)

                stop = element.get("stop", None)
                if stop:
                    stop = self.get_utc_time(stop)

                title, desc = None, None
                for c in element:
                    if c.tag == self.TITLE_TAG:
                        title = c.text
                    elif c.tag == self.DESC_TAG:
                        desc = c.text

                if all((start, stop, title)):
                    events.append(self.Event(start, stop, title, desc))

    def to_epg_dat(self):
        """ Converts and saves imported data to 'epg.dat' file. """
        raise ValueError("Not implemented yet!")

    @staticmethod
    def get_utc_time(time_str):
        """ Returns the UTC time in seconds. """
        t, sep, delta = time_str.partition(" ")
        t = datetime(*map(int, (t[:4], t[4:6], t[6:8], t[8:10], t[10:12], t[12:]))).timestamp()
        if delta:
            t -= (3600 * int(delta) // 100)
        return t


class ChannelsParser:
    _COMMENT = "File was created in DemonEditor"

    @staticmethod
    def get_refs_from_xml(path):
        """ Returns tuple from references and description. """
        refs = []
        dom = parse(path)
        description = "".join(n.data + "\n" for n in dom.childNodes if n.nodeType == Node.COMMENT_NODE)
        pos_pat = re.compile(r"^\d+\.\d+[EW]$")

        for elem in dom.getElementsByTagName("channels"):
            c_count = 0
            comment_count = 0
            data = ""
            ch_id = None
            pos = None
            ch_type = BqServiceType.DEFAULT

            if elem.hasChildNodes():
                for n in elem.childNodes:
                    if n.nodeType == Node.ELEMENT_NODE:
                        ch_id = n.getAttribute("id")

                    if n.nodeType == Node.COMMENT_NODE:
                        c_count += 1
                        comment_count += 1
                        txt = n.data.strip()

                        if re.match(pos_pat, txt):
                            pos = txt

                        if comment_count:
                            comment_count -= 1
                        else:
                            refs.append(BouquetService(name=txt, type=ch_type, data=data.upper(), num=(pos, ch_id)))

                    if n.hasChildNodes():
                        for s_node in n.childNodes:
                            if s_node.nodeType == Node.TEXT_NODE:
                                comment_count -= 1
                                data = s_node.data
        return refs, description

    @staticmethod
    def write_refs_to_xml(path, services):
        header = '<?xml version="1.0" encoding="utf-8"?>\n<!--  {} -->\n<!-- {} -->\n<channels>\n'.format(
            "Created in DemonEditor.", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        doc = Document()
        lines = [header]

        for srv in services:
            srv_type = srv.type
            if srv_type is BqServiceType.IPTV:
                channel_child = doc.createElement("channel")
                channel_child.setAttribute("id", srv.name)
                data = srv.data.strip().split(":")
                channel_child.appendChild(doc.createTextNode(":".join(data[:10])))
                comment = doc.createComment(srv.name)
                lines.append(f"{channel_child.toxml()} {comment.toxml()}\n")
            elif srv_type is BqServiceType.MARKER:
                comment = doc.createComment(srv.name)
                lines.append(f"{comment.toxml()}\n")

        lines.append("</channels>")
        doc.unlink()

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)


if __name__ == "__main__":
    pass

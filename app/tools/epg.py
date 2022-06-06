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


"""  Module for working with epg.dat file. """
import os
import struct
from collections import namedtuple
from datetime import datetime, timezone
from xml.dom.minidom import parse, Node, Document

from app.eparser.ecommons import BqServiceType, BouquetService

ENCODING = "utf-8"
DETECT_ENCODING = False
try:
    import chardet
except ModuleNotFoundError:
    pass
else:
    DETECT_ENCODING = True


class EPG:
    """ Base EPG class. """
    # DVB/EPG count days with a 'modified Julian calendar' where day 1 is 17 November 1858.
    # datetime.datetime.toordinal(1858,11,17) => 678576
    ZERO_DAY = 678576

    EpgEvent = namedtuple("EpgEvent", ["id", "data", "start", "duration", "title", "desc", "ext_desc"])

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

    class Reader:
        """ The epd.dat file reading class.

            The read algorithm was taken from the eEPGCache::load() function from this source:
            https://github.com/OpenPLi/enigma2/blob/44d9b92f5260c7de1b3b3a1b9a9cbe0f70ca4bf0/lib/dvb/epgcache.cpp#L1300
        """

        def __init__(self, path):
            self._path = path
            self._refs = {}
            self._desc = {}

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

            return EPG.EpgEvent(e_id, evd, start, duration, title, desc, ext_desc)

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


class ChannelsParser:
    _COMMENT = "File was created in DemonEditor"

    @staticmethod
    def get_refs_from_xml(path):
        """ Returns tuple from references and description. """
        refs = []
        dom = parse(path)
        description = "".join(n.data + "\n" for n in dom.childNodes if n.nodeType == Node.COMMENT_NODE)

        for elem in dom.getElementsByTagName("channels"):
            c_count = 0
            comment_count = 0
            current_data = ""

            if elem.hasChildNodes():
                for n in elem.childNodes:
                    if n.nodeType == Node.COMMENT_NODE:
                        c_count += 1
                        comment_count += 1
                        txt = n.data.strip()
                        if comment_count:
                            comment_count -= 1
                        else:
                            ref_data = current_data.split(":")
                            refs.append(BouquetService(name=txt,
                                                       type=BqServiceType.DEFAULT,
                                                       data="{}:{}:{}:{}".format(*ref_data[3:7]).upper(),
                                                       num="{}:{}:{}".format(*ref_data[3:6]).upper()))

                    if n.hasChildNodes():
                        for s_node in n.childNodes:
                            if s_node.nodeType == Node.TEXT_NODE:
                                comment_count -= 1
                                current_data = s_node.data
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

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
import struct
from datetime import datetime
from xml.dom.minidom import parse, Node, Document

from app.eparser.ecommons import BqServiceType, BouquetService


class EPG:

    @staticmethod
    def get_epg_refs(path):
        """ The read algorithm was taken from the eEPGCache::load() function from this source:
            https://github.com/OpenPLi/enigma2/blob/develop/lib/dvb/epgcache.cpp#L955
        """
        refs = set()

        with open(path, mode="rb") as f:
            crc = struct.unpack("<I", f.read(4))[0]
            if crc != int(0x98765432):
                raise ValueError("Epg file has incorrect byte order!")

            header = f.read(13).decode()
            if header == "ENIGMA_EPG_V7":
                epg_ver = 7
            elif header == "ENIGMA_EPG_V8":
                epg_ver = 8
            else:
                raise ValueError("Unsupported format of epd.dat file!")

            channels_count = struct.unpack("<I", f.read(4))[0]
            _len_read_size = 3 if epg_ver == 8 else 2
            _type_read_str = f"<{'H' if epg_ver == 8 else 'B'}B"

            for i in range(channels_count):
                sid, nid, tsid, events_size = struct.unpack("<IIII", f.read(16))
                service_id = f"{sid:X}:{tsid:X}:{nid:X}"

                for j in range(events_size):
                    _type, _len = struct.unpack(_type_read_str, f.read(_len_read_size))
                    f.read(10)
                    n_crc = (_len - 10) // 4
                    if n_crc > 0:
                        [f.read(4) for n in range(n_crc)]

                refs.add(service_id)

        return refs


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

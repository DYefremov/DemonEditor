"""  Module for working with epg.dat file """

import struct
from xml.dom.minidom import parse, Node, Document

from app.eparser.ecommons import BqServiceType


class EPG:

    @staticmethod
    def get_epg_refs(path):
        """ The read algorithm was taken from the eEPGCache::load() function from this source:
            https://github.com/OpenPLi/enigma2/blob/44d9b92f5260c7de1b3b3a1b9a9cbe0f70ca4bf0/lib/dvb/epgcache.cpp#L1300
        """
        refs = []

        with open(path, mode="rb") as f:
            crc = struct.unpack("<I", f.read(4))[0]
            if crc != int(0x98765432):
                raise ValueError("Epg file has incorrect byte order!")

            header = f.read(13).decode()
            if header != "ENIGMA_EPG_V7":
                raise ValueError("Unsupported format of epd.dat file!")

            channels_count = struct.unpack("<I", f.read(4))[0]

            for i in range(channels_count):
                sid, nid, tsid, events_size = struct.unpack("<IIII", f.read(16))
                service_id = "{:X}:{:X}:{:X}".format(sid, tsid, nid)

                for j in range(events_size):
                    _type, _len = struct.unpack("<BB", f.read(2))
                    f.read(10)
                    n_crc = (_len - 10) // 4
                    if n_crc > 0:
                        [f.read(4) for n in range(n_crc)]

                refs.append(service_id)

        return refs


class ChannelsParser:
    _COMMENT = "File was created in DemonEditor"

    @staticmethod
    def get_refs_from_xml(path):
        """ Returns tuple from references dict and list description. """
        refs = {}
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
                            refs["{}:{}:{}".format(*ref_data[3:6])] = (txt, "{}:{}:{}:{}".format(*ref_data[3:7]))

                    if n.hasChildNodes():
                        for s_node in n.childNodes:
                            if s_node.nodeType == Node.TEXT_NODE:
                                comment_count -= 1
                                current_data = s_node.data
        return refs, description

    @staticmethod
    def write_refs_to_xml(path, services):
        header = '<?xml version="1.0" encoding="utf-8"?>\n<!--  Created in DemonEditor.  -->\n<channels>\n'
        ind = "    "
        doc = Document()
        lines = [header]

        for srv in services:
            srv_type = srv.type
            if srv_type is BqServiceType.IPTV:
                channel_child = doc.createElement("channel")
                channel_child.setAttribute("id", str(srv.num))
                data = srv.data.strip().split(":")
                channel_child.appendChild(doc.createTextNode(":".join(data[:10])))
                comment = doc.createComment(srv.name)
                lines.append("{}{}{}\n".format(ind, str(channel_child.toxml()), str(comment.toxml())))
            elif srv_type is BqServiceType.MARKER:
                comment = doc.createComment(srv.name)
                lines.append("{}{}\n".format(ind, str(comment.toxml())))

        lines.append("</channels>")
        doc.unlink()

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)


if __name__ == "__main__":
    pass

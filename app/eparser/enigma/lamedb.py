# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2021 Dmitriy Yefremov
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


"""   This module used for parsing and write lamedb file   """
import re

from app.commons import log
from app.ui.uicommons import CODED_ICON, LOCKED_ICON, HIDE_ICON
from .blacklist import get_blacklist
from ..ecommons import Service, POLARIZATION, FEC, SERVICE_TYPE, Flag, T_FEC, TrType, FEC_DEFAULT, T_SYSTEM

_HEADER = "eDVB services /{}/"
_SEP = ":"  # separator
_FILE_NAME = "lamedb"
_END_LINE = "# File was created in DemonEditor.\n# ....Enjoy watching!....\n"


def get_services(path, format_version):
    return LameDbReader(path, format_version).parse()


def write_services(path, services, format_version=4):
    LameDbWriter(path, services, format_version).write()


class LameDbReader:
    """ Lamedb parser class.

        Reads and parses the Enigma2 lamedb[5] file.
        Supports versions 3, 4 and 5..
    """
    __slots__ = ["_path", "_fmt"]

    def __init__(self, path, fmt=4):
        self._path = path
        self._fmt = fmt

    def parse(self):
        """ Parsing lamedb. """
        if self._fmt == 4:
            return self.parse_v4()
        elif self._fmt == 5:
            return self.parse_v5()
        raise SyntaxError("Unsupported version of the format.")

    def parse_v3(self, services, transponders):
        """ Parsing version 3. """
        for t in transponders:
            tr = transponders[t].lower()
            tr_type = tr[0:1]
            if tr_type == "c":
                tr += ":0:0:0"
            elif tr_type == "t" or tr_type == "a":
                tr += ":0:0"
            else:
                tr_data = tr.split(_SEP)
                len_data = len(tr_data)
                if len_data == 6:
                    tr_data.append("0")
                elif len_data == 9:
                    tr_data.insert(6, "0")
                    tr_data.append("0")
                    tr_data.append("2")

                tr = _SEP.join(tr_data)

            transponders[t] = tr

        return self.parse_services(services, transponders)

    def parse_v4(self):
        """ Parsing version 4. """
        with open(self._path + _FILE_NAME, "r", encoding="utf-8", errors="replace") as file:
            try:
                data = str(file.read())
            except UnicodeDecodeError as e:
                log("lamedb parse error: " + str(e))
            else:
                return self.get_services_list(data)

    def parse_v5(self):
        """ Parsing version 5. """
        with open(self._path + "lamedb5", "r", encoding="utf-8", errors="replace") as file:
            lns = file.readlines()

            if lns and not lns[0].endswith("/5/\n"):
                raise SyntaxError("lamedb ver.5 parsing error: unsupported format.")

            trs, srvs = {}, [""]
            for line in lns:
                if line.startswith("s:"):
                    srv_data = line.strip("s:").split(",", 2)
                    srv_data[1] = srv_data[1].strip("\"")
                    data_len = len(srv_data)
                    if data_len == 3:
                        srv_data[2] = srv_data[2].strip()
                    elif data_len == 2:
                        srv_data.append("p:")
                    srvs.extend(srv_data)
                elif line.startswith("t:"):
                    data = line.split(",")
                    len_data = len(data)
                    if len_data > 1:
                        tr, srv = data[0].strip("t:"), data[1].strip().replace(":", " ", 1)
                        trs[tr] = srv
                    else:
                        log("Error while parsing transponder data [ver. 5] for line: {}".format(line))

            return self.parse_services(srvs, trs)

    def parse_services(self, services, transponders):
        """ Parsing services. """
        services_list = []
        blacklist = get_blacklist(self._path) if self._path else {}
        srvs = self.split(services, 3)
        if srvs[0][0] == "":  # Remove first empty element.
            srvs.remove(srvs[0])

        for srv in srvs:
            data_id = str(srv[0]).lower()  # Lower is for lamedb ver.3.
            data = data_id.split(_SEP)
            sp = "0"
            tid = data[2]
            nid = data[3]
            # For lamedb ver.3
            is_v3 = False
            if len(tid) < 4:
                is_v3 = True
                tid = "{:0>4}".format(tid)
                data[2] = tid
            if len(nid) < 4:
                is_v3 = True
                nid = "{:0>4}".format(nid)
                data[3] = nid
            if is_v3:
                data[0] = "{:0>4}".format(data[0])
                data_id = _SEP.join(data)

            srv_type = int(data[4])
            transponder_id = "{}:{}:{}".format(data[1], tid, nid)
            transponder = transponders.get(transponder_id, None)

            tid = tid.lstrip(sp).upper()
            nid = nid.lstrip(sp).upper()
            ssid = str(data[0]).lstrip(sp).upper()
            onid = str(data[1]).lstrip(sp).upper()
            # For comparison in bouquets. Needed in upper case!!!
            fav_id = "{}:{}:{}:{}".format(ssid, tid, nid, onid)
            picon_id = "1_0_{:X}_{}_{}_{}_{}_0_0_0.png".format(srv_type, ssid, tid, nid, onid)
            s_id = "1:0:{:X}:{}:{}:{}:{}:0:0:0:".format(srv_type, ssid, tid, nid, onid)

            all_flags = srv[2].split(",")
            coded = CODED_ICON if list(filter(lambda x: x.startswith("C:"), all_flags)) else None
            flags = list(filter(lambda x: x.startswith("f:"), all_flags))
            hide = HIDE_ICON if flags and Flag.is_hide(int(flags[0][2:])) else None
            locked = LOCKED_ICON if s_id in blacklist else None

            package = list(filter(lambda x: x.startswith("p:"), all_flags))
            package = package[0][2:] if package else ""

            if transponder is not None:
                tr_type, sp, tr = str(transponder).partition(" ")
                tr_type = TrType(tr_type)
                tr = tr.split(_SEP)
                service_type = SERVICE_TYPE.get(data[4], SERVICE_TYPE["-2"])
                # Removing all non printable symbols!
                srv_name = "".join(c for c in srv[1] if c.isprintable())
                freq = tr[0]
                rate = tr[1]
                pol = None
                fec = None
                system = None
                pos = None

                if tr_type is TrType.Satellite:
                    pol = POLARIZATION.get(tr[2], None)
                    fec = FEC.get(tr[3], None)
                    system = "DVB-S2" if len(tr) > 7 else "DVB-S"
                    pos = tr[4]
                if tr_type is TrType.Terrestrial:
                    system = T_SYSTEM.get(tr[9], None)
                    pos = "T"
                    fec = T_FEC.get(tr[3], None)
                elif tr_type is TrType.Cable:
                    system = "DVB-C"
                    pos = "C"
                    fec = FEC_DEFAULT.get(tr[4])
                elif tr_type is TrType.ATSC:
                    system = "ATSC"
                    pos = "T"
                    fec = FEC_DEFAULT.get("0")

                # Formatting displayed values.
                try:
                    freq = "{}".format(int(freq) // 1000)
                    rate = "{}".format(int(rate) // 1000)
                    if tr_type is TrType.Satellite:
                        pos = int(pos)
                        pos = "{:0.1f}{}".format(abs(pos / 10), "W" if pos < 0 else "E")
                except ValueError as e:
                    log("Parse error [parse_services]: {}".format(e))

                s = Service(srv[2], tr_type.value, coded, srv_name, locked, hide, package, service_type, None,
                            picon_id, data[0], freq, rate, pol, fec, system, pos, data_id, fav_id, transponder)

                services_list.append(s)
        return services_list

    def get_services_list(self, data):
        """ Returns a list of services from a string data representation. """
        transponders, sep, services = data.partition("transponders")  # 1 step
        pattern = re.compile("/[34]/$")
        match = re.search(pattern, transponders)
        if not match:
            msg = "lamedb parsing error: unsupported format."
            log(msg)
            raise SyntaxError(msg)

        transponders, sep, services = services.partition("services")  # 2 step
        services, sep, _ = services.partition("\nend")  # 3 step

        if match.group() == "/3/":
            return self.parse_v3(services.split("\n"), self.parse_transponders(transponders.split("/")))

        return self.parse_services(services.split("\n"), self.parse_transponders(transponders.split("/")))

    @staticmethod
    def get_services_lines(services):
        """ Returns a list of strings from services for lamedb [v.4]. """
        lines = [_HEADER.format(4), "\ntransponders\n"]
        tr_lines = []
        services_lines = ["end\nservices\n"]
        tr_set = set()
        for srv in services:
            data_id = str(srv.data_id).split(_SEP)
            tr_id = "{}:{}:{}".format(data_id[1], data_id[2], data_id[3])
            if tr_id not in tr_set:
                transponder = "{}\n\t{}\n/\n".format(tr_id, srv.transponder)
                tr_lines.append(transponder)
                tr_set.add(tr_id)
            # Services
            services_lines.append("{}\n{}\n{}\n".format(srv.data_id, srv.service, srv.flags_cas))

        tr_lines.sort()
        lines.extend(tr_lines)
        lines.extend(services_lines)
        lines.append("end\n" + _END_LINE)

        return lines

    def parse_transponders(self, arg):
        """ Parsing transponders. """
        transponders = {}
        for ar in arg:
            tr = ar.replace("\n", "").split("\t")
            if len(tr) == 2:
                transponders[tr[0]] = tr[1]

        return transponders

    def split(self, itr, size):
        """ Divide the iterable. """
        srv = []
        tmp = []
        for i, line in enumerate(itr):
            tmp.append(line)
            if i % size == 0:
                srv.append(tuple(tmp))
                tmp.clear()

        return srv


class LameDbWriter:
    """ Writes the Enigma2 lamedb[5] file.

        Version 4 will be used instead of version 3!
    """
    __slots__ = ["_path", "_fmt", "_services"]

    def __init__(self, path, services, fmt=4):
        self._path = path
        self._fmt = fmt
        self._services = services

    def write(self):
        if self._fmt == 4:
            # Writing lamedb file ver.4
            with open(self._path + _FILE_NAME, "w", encoding="utf-8") as file:
                file.writelines(LameDbReader.get_services_lines(self._services))
        elif self._fmt == 5:
            self.write_to_lamedb5()

    def write_to_lamedb5(self):
        """ Writing lamedb5 file. """
        lines = [_HEADER.format(5) + "\n"]
        services_lines = []
        tr_set = set()

        for srv in self._services:
            data_id = str(srv.data_id).split(_SEP)
            tr_id = "{}:{}:{}".format(data_id[1], data_id[2], data_id[3])
            tr_set.add("t:{},{}\n".format(tr_id, srv.transponder.replace(" ", ":", 1)))
            # Removing empty packages
            flags = list(filter(lambda x: x != "p:", srv.flags_cas.split(",")))
            flags = ",".join(flags)
            flags = "," + flags if flags else ""
            services_lines.append("s:{},\"{}\"{}\n".format(srv.data_id, srv.service, flags))

        lines.extend(sorted(tr_set))
        lines.extend(services_lines)
        lines.append(_END_LINE)

        with open(self._path + "lamedb5", "w", encoding="utf-8") as file:
            file.writelines(lines)


if __name__ == "__main__":
    pass

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
    return parse(path, format_version)


def write_services(path, services, format_version=4):
    if format_version == 4:
        write_to_lamedb(path, services)
    elif format_version == 5:
        write_to_lamedb5(path, services)


def write_to_lamedb(path, services):
    """ Writing lamedb file ver.4  """
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
    with open(path + _FILE_NAME, "w") as file:
        file.writelines(lines)


def write_to_lamedb5(path, services):
    """ Writing lamedb5 file """
    lines = [_HEADER.format(5) + "\n"]
    services_lines = []
    tr_set = set()

    for srv in services:
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

    with open(path + "lamedb5", "w") as file:
        file.writelines(lines)


def parse(path, version=4):
    """ Parsing lamedb """
    if version == 4:
        return parse_v4(path)
    elif version == 5:
        return parse_v5(path)
    raise SyntaxError("Unsupported version of the format.")


def parse_v3(services, transponders, path):
    """ Parsing version 3 """
    for t in transponders:
        tr = transponders[t].lower()
        tr_type = tr[0:1]
        if tr_type == "c":
            tr += ":0:0:0"
        elif tr_type == "t":
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

    return parse_services(services, transponders, path)


def parse_v4(path):
    """ Parsing version 4 """
    with open(path + _FILE_NAME, "r", encoding="utf-8", errors="replace") as file:
        try:
            data = str(file.read())
        except UnicodeDecodeError as e:
            log("lamedb parse error: " + str(e))
        else:
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
                return parse_v3(services.split("\n"), parse_transponders(transponders.split("/")), path)

        return parse_services(services.split("\n"), parse_transponders(transponders.split("/")), path)


def parse_v5(path):
    """ Parsing version 5 """
    with open(path + "lamedb5", "r", encoding="utf-8", errors="replace") as file:
        lns = file.readlines()

        if lns and not lns[0].endswith("/5/\n"):
            raise SyntaxError("lamedb v.5 parsing error: unsupported format.")

        trs, srvs = {}, [""]
        for l in lns:
            if l.startswith("s:"):
                srv_data = l.strip("s:").split(",", 2)
                srv_data[1] = srv_data[1].strip("\"")
                data_len = len(srv_data)
                if data_len == 3:
                    srv_data[2] = srv_data[2].strip()
                elif data_len == 2:
                    srv_data.append("p:")
                srvs.extend(srv_data)
            elif l.startswith("t:"):
                tr, srv = l.split(",")
                trs[tr.strip("t:")] = srv.strip().replace(":", " ", 1)

        return parse_services(srvs, trs, path)


def parse_transponders(arg):
    """ Parsing transponders """
    transponders = {}
    for ar in arg:
        tr = ar.replace("\n", "").split("\t")
        if len(tr) == 2:
            transponders[tr[0]] = tr[1]

    return transponders


def parse_services(services, transponders, path):
    """ Parsing services """
    services_list = []
    blacklist = str(get_blacklist(path))
    srvs = split(services, 3)
    if srvs[0][0] == "":  # remove first empty element
        srvs.remove(srvs[0])

    for srv in srvs:
        data_id = str(srv[0]).lower()  # lower is for lamedb ver.3
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

        all_flags = srv[2].split(",")
        coded = CODED_ICON if list(filter(lambda x: x.startswith("C:"), all_flags)) else None
        flags = list(filter(lambda x: x.startswith("f:"), all_flags))
        hide = HIDE_ICON if flags and Flag.is_hide(int(flags[0][2:])) else None
        locked = LOCKED_ICON if fav_id in blacklist else None

        package = list(filter(lambda x: x.startswith("p:"), all_flags))
        package = package[0][2:] if package else ""

        if transponder is not None:
            tr_type, sp, tr = str(transponder).partition(" ")
            tr_type = TrType(tr_type)
            tr = tr.split(_SEP)
            service_type = SERVICE_TYPE.get(data[4], SERVICE_TYPE["-2"])
            # removing all non printable symbols!
            srv_name = "".join(c for c in srv[1] if c.isprintable())
            pol = None
            fec = None
            system = None
            pos = None

            if tr_type is TrType.Satellite:
                pol = POLARIZATION.get(tr[2], None)
                fec = FEC.get(tr[3], None)
                system = "DVB-S2" if len(tr) > 7 else "DVB-S"
                pos = "{}.{}".format(tr[4][:-1], tr[4][-1:])
            if tr_type is TrType.Terrestrial:
                system = T_SYSTEM.get(tr[9], None)
                pos = "T"
                fec = T_FEC.get(tr[3], None)
            elif tr_type is TrType.Cable:
                system = "DVB-C"
                pos = "C"
                fec = FEC_DEFAULT.get(tr[4])

            services_list.append(Service(flags_cas=srv[2],
                                         transponder_type=tr_type.value,
                                         coded=coded,
                                         service=srv_name,
                                         locked=locked,
                                         hide=hide,
                                         package=package,
                                         service_type=service_type,
                                         picon=None,
                                         picon_id=picon_id,
                                         ssid=data[0],
                                         freq=tr[0],
                                         rate=tr[1],
                                         pol=pol,
                                         fec=fec,
                                         system=system,
                                         pos=pos,
                                         data_id=data_id,
                                         fav_id=fav_id,
                                         transponder=transponder))
    return services_list


def split(itr, size):
    """ Divide the iterable. """
    srv = []
    tmp = []
    for i, line in enumerate(itr):
        tmp.append(line)
        if i % size == 0:
            srv.append(tuple(tmp))
            tmp.clear()

    return srv


if __name__ == "__main__":
    pass

"""   This module used for parsing lamedb file

      Currently implemented only for satellite channels!!!
     Description of format taken from here: http://www.satsupreme.com/showthread.php/194074-Lamedb-format-explained
"""
from app.commons import log
from app.ui import CODED_ICON, LOCKED_ICON, HIDE_ICON
from .blacklist import get_blacklist
from ..ecommons import Service, POLARIZATION, SYSTEM, FEC, SERVICE_TYPE, FLAG

_HEADER = "eDVB services /4/"
_SEP = ":"  # separator
_FILE_NAME = "lamedb"


def get_services(path):
    return parse(path)


def write_services(path, services):
    lines = [_HEADER, "\ntransponders\n"]
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
    lines.append("end\nFile was created in DemonEditor.\n....Enjoy watching!....\n")

    with open(path + _FILE_NAME, "w") as file:
        file.writelines(lines)


def parse(path):
    """ Parsing lamedb """
    with open(path + _FILE_NAME, "r", encoding="utf-8", errors="replace") as file:
        try:
            data = str(file.read())
        except UnicodeDecodeError as e:
            log("lamedb parse error: " + str(e))
        else:
            transponders, sep, services = data.partition("transponders")  # 1 step
            if not transponders.endswith("/4/\n"):
                msg = "lamedb parsing error: unsupported format.\n Only version 4 is supported!"
                log(msg)
                raise SyntaxError(msg)
            transponders, sep, services = services.partition("services")  # 2 step
            services, sep, _ = services.partition("end")  # 3 step

            return parse_services(services.split("\n"), transponders.split("/"), path)


def parse_transponders(arg):
    """ Parsing transponders """
    transponders = {}
    for ar in arg:
        tr = ar.replace("\n", "").split("\t")
        if len(tr) == 2:
            transponders[tr[0]] = tr[1]

    return transponders


def parse_services(services, transponders, path):
    """ Parsing channels """
    channels = []
    transponders = parse_transponders(transponders)
    blacklist = str(get_blacklist(path))

    srv = split(services, 3)
    if srv[0][0] == "":  # remove first empty element
        srv.remove(srv[0])

    for ch in srv:
        data = str(ch[0]).split(_SEP)
        sp = "0"
        tid = data[2]
        nid = data[3]
        transponder_id = "{}:{}:{}".format(data[1], tid, nid)
        transponder = transponders.get(transponder_id, None)

        tid = tid.lstrip(sp).upper()
        nid = nid.lstrip(sp).upper()
        ssid = str(data[0]).lstrip(sp).upper()
        onid = str(data[1]).lstrip(sp).upper()
        # For comparison in bouquets. Needed in upper case!!!
        fav_id = "{}:{}:{}:{}".format(ssid, tid, nid, onid)
        picon_id = "1_0_{}_{}_{}_{}_{}_0_0_0.png".format(1, ssid, tid, nid, onid)

        all_flags = ch[2].split(",")
        coded = CODED_ICON if list(filter(lambda x: x.startswith("C:"), all_flags)) else None
        flags = list(filter(lambda x: x.startswith("f:"), all_flags))
        hide = HIDE_ICON if flags and int(flags[0][2:]) in FLAG.hide_values() else None
        locked = LOCKED_ICON if fav_id in blacklist else None

        package = list(filter(lambda x: x.startswith("p:"), all_flags))
        package = package[0][2:] if package else None

        if transponder is not None:
            tr_type, sp, tr = str(transponder).partition(" ")
            tr = tr.split(_SEP)
            service_type = SERVICE_TYPE.get(data[4], SERVICE_TYPE["-2"])
            channels.append(Service(flags_cas=ch[2],
                                    transponder_type=tr_type,
                                    coded=coded,
                                    service=ch[1],
                                    locked=locked,
                                    hide=hide,
                                    package=package,
                                    service_type=service_type,
                                    picon=None,
                                    picon_id=picon_id,
                                    ssid=data[0],
                                    freq=tr[0],
                                    rate=tr[1],
                                    pol=POLARIZATION[tr[2]],
                                    fec=FEC[tr[3]],
                                    system=SYSTEM[tr[6]],
                                    pos="{}.{}".format(tr[4][:-1], tr[4][-1:]),
                                    data_id=ch[0],
                                    fav_id=fav_id,
                                    transponder=transponder))
    return channels


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

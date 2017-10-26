"""   This module used for parsing lamedb file

      Currently implemented only for satellite channels!!!
     Description of format taken from here: http://www.satsupreme.com/showthread.php/194074-Lamedb-format-explained
"""
from collections import namedtuple

from main.eparser.__constants import POLARIZATION, SYSTEM, FEC, SERVICE_TYPE

_HEADER = "eDVB services /4/"
_FILE_PATH = "../data/lamedb"
_SEP = ":"  # separator

Channel = namedtuple("Channel", ["flags_cas", "transponder_type", "service", "package", "service_type",
                                 "ssid", "freq", "rate", "pol", "fec",
                                 "system", "pos", "data_id", "fav_id", "transponder"])


def get_channels(path):
    return parse(path)


def write_channels(path, channels):
    lines = [_HEADER, "\ntransponders\n"]
    tr_lines = []
    services_lines = ["end\nservices\n"]
    tr_set = set()

    for ch in channels:
        data_id = str(ch.data_id).split(_SEP)
        tr_id = "{}:{}:{}".format(data_id[1], data_id[2], data_id[3])
        if tr_id not in tr_set:
            transponder = "{}\n\t{}\n/\n".format(tr_id, ch.transponder)
            tr_lines.append(transponder)
            tr_set.add(tr_id)
        # Services
        flags = "," + ch.flags_cas if ch.flags_cas else ""
        services_lines.append("{}\n{}\np:{}{}".format(ch.data_id, ch.service, ch.package, flags))

    tr_lines.sort()
    lines.extend(tr_lines)
    lines.extend(services_lines)
    lines.append("\nend\nFile was created in DemonEditor.\n....Enjoy watching!....\n")

    with open(path + "lamedb", "w") as file:
        file.writelines(lines)


def parse(path):
    """ Parsing lamedb """
    with open(path, "r") as file:
        data = str(file.read())
    transponders, sep, services = data.partition("transponders")  # 1 step
    transponders, sep, services = services.partition("services")  # 2 step
    services, sep, _ = services.partition("end")  # 3 step

    return parse_channels(services.split("\n"), transponders.split("/"))


def parse_transponders(arg):
    """ Parsing transponders """
    transponders = {}
    for ar in arg:
        tr = ar.replace("\n", "").split("\t")
        if len(tr) == 2:
            transponders[tr[0]] = tr[1]

    return transponders


def parse_channels(*args):
    """ Parsing channels """
    channels = []
    transponders = parse_transponders(args[1])

    srv = split(args[0], 3)
    if srv[0][0] == "":  # remove first empty element
        srv.remove(srv[0])

    for ch in srv:
        data = str(ch[0]).split(_SEP)
        sp = "0"
        # For comparison in bouquets. Needed in upper case!!!
        fav_id = "{}:{}:{}:{}".format(str(data[0]).lstrip(sp), str(data[2]).lstrip(sp),
                                      str(data[3]).lstrip(sp), str(data[1]).lstrip(sp))

        package, sp, cas = str(ch[2]).partition(",")
        _, sp, package = package.partition(_SEP)

        transponder_id = "{}:{}:{}".format(data[1], data[2], data[3])
        transponder = transponders.get(transponder_id, None)

        if transponder is not None:
            tr_type, sp, tr = str(transponder).partition(" ")
            tr = tr.split(_SEP)
            service_type = SERVICE_TYPE.get(data[4], SERVICE_TYPE["-2"])
            channels.append(Channel(flags_cas=cas,
                                    transponder_type=tr_type,
                                    service=ch[1],
                                    package=package,
                                    service_type=service_type,
                                    ssid=data[0],
                                    freq=tr[0],
                                    rate=tr[1],
                                    pol=POLARIZATION[tr[2]],
                                    fec=FEC[tr[3]],
                                    system=SYSTEM[tr[6]],
                                    pos="{}{}.{}".format(*list(tr[4])),
                                    data_id=ch[0],
                                    fav_id=fav_id.upper(),
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

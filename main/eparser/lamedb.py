"""   This module used for parsing lamedb file

      Currently implemented only for satellite channels!!!
     Description of format taken from here: http://www.satsupreme.com/showthread.php/194074-Lamedb-format-explained
"""
from main.eparser.__constants import Polarization, SYSTEM, FEC, Channel, SERVICE_TYPE

_HEADER = "eDVB services /4/"
_FILE_PATH = "../data/lamedb"
_SEP = ":"  # separator


def get_channels(path):
    return parse(path)


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
    transponders = parse_transponders(args[1])

    srv = split(args[0], 3)
    if srv[0][0] == "":  # remove first empty element
        srv.remove(srv[0])

    channels = []
    for ch in srv:
        data = str(ch[0]).split(_SEP)
        sp = "0"
        # For comparison in bouquets. Needed in upper case!!!
        fav_id = "{}:{}:{}:{}".format(str(data[0]).lstrip(sp), str(data[2]).lstrip(sp),
                                      str(data[3]).lstrip(sp), str(data[1]).lstrip(sp))
        pack = str(ch[2])
        transponder = transponders.get(str(data[1] + _SEP + data[2] + _SEP + data[3]), None)
        if transponder is not None:
            tr = str(transponder)[2:].split(_SEP)  # Removing type of DVB transponders (s , t, c) and split
            pack = pack[2:] if pack.find(",") < 0 else pack[2:pack.find(",")]
            channels.append(Channel(ch[1], pack, SERVICE_TYPE.get(int(data[4]), SERVICE_TYPE[-2]), data[0], tr[0],
                                    tr[1], Polarization(int(tr[2])).name, FEC[int(tr[3])], SYSTEM[int(tr[6])],
                                    "{}{}.{}".format(*list(tr[4])), ch[0], fav_id.upper()))
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

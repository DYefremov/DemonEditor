"""
    This module used for parsing lamedb file

    Currently implemented only for satellite channels!!!
    Description of format taken from here: http://www.satsupreme.com/showthread.php/194074-Lamedb-format-explained
"""
from collections import namedtuple
from enum import Enum

Channel = namedtuple("Channel", ["service", "package", "ssid", "freq", "rate", "pol", "fec", "system"])

_HEADER = "eDVB services /4/"
_FILE_PATH = "../data/lamedb_example"
_SEP = ":"  # separator


class Type(Enum):
    """ Types of DVB transponders """
    Satellite = "s"
    Terestrial = "t"
    Cable = "c"


class Polarization(Enum):
    H = 0
    V = 1
    L = 2
    R = 3


# Symbol rate
FEC = {0: "None", 1: "Auto", 2: "1/2",
       3: "2/3", 4: "3/4", 5: "5/6",
       6: "7/8", 7: "3/5", 8: "4/5",
       9: "8/9", 10: "9/10"}

System = {0: "DVB-S", 1: "DVB_S2"}


def parse(path):
    """ For test """
    with open(path, "r") as file:
        data = str(file.read())
    transponders, sep, services = data.partition("transponders")  # 1 step
    transponders, sep, services = services.partition("services")  # 2 step

    return get_channels(services.split("\n"), transponders.split("/"))


def get_transponders(arg):
    """ Parsing transponders """
    transponders = {}
    for ar in arg:
        tr = ar.replace("\n", "").split("\t")
        if len(tr) == 2:
            transponders[tr[0]] = tr[1]

    return transponders


def get_channels(*args):
    """ Parsing channels """
    transponders = get_transponders(args[1])

    srv = split(args[0], 3)
    if srv[0][0] == "":  # remove first empty element
        srv.remove(srv[0])

    channels = []
    for ch in srv:
        data = str(ch[0]).split(_SEP)
        pack = str(ch[2])
        transponder = transponders.get(str(data[1] + _SEP + data[2] + _SEP + data[3]), None)
        if transponder is not None:
            tr = str(transponder)[2:].split(_SEP)  # Removing type of DVB transponders (s , t, c) and split
        pack = pack[2:pack.find(",")]
        channels.append(Channel(ch[1], pack, data[0], tr[0],
                                tr[1], Polarization(int(tr[2])).name,
                                FEC[int(tr[3])], System[int(tr[6])]))

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

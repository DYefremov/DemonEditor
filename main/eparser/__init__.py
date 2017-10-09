from enum import Enum


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


class Plsmode(Enum):
    Root = 0
    Gold = 1
    Combo = 2


# Symbol rate
Fec = {0: "None", 1: "Auto", 2: "1/2",
       3: "2/3", 4: "3/4", 5: "5/6",
       6: "7/8", 7: "3/5", 8: "4/5",
       9: "8/9", 10: "9/10"}

System = {0: "DVB-S", 1: "DVB_S2"}

Modulation = {0: "Auto", 1: "QPSK", 2: "8PSK", 3: "16APSK", 5: "32APSK"}


if __name__ == "__main__":
    pass


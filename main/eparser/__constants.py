""" This module only for common constants """
from enum import Enum


class Type(Enum):
    """ Types of DVB transponders """
    Satellite = "s"
    Terestrial = "t"
    Cable = "c"


POLARIZATION = {"0": "H", "1": "V", "2": "L", "3": "R"}

PLS_MODE = {"0": "Root", "1": "Gold", "2": "Combo"}

FEC = {"0": "None", "1": "Auto", "2": "1/2",
       "3": "2/3", "4": "3/4", "5": "5/6",
       "6": "7/8", "7": "3/5", "8": "4/5",
       "9": "8/9", "10": "9/10"}

SYSTEM = {"0": "DVB-S", "1": "DVB-S2"}

MODULATION = {"0": "Auto", "1": "QPSK", "2": "8PSK", "3": "16APSK", "5": "32APSK"}

SERVICE_TYPE = {-2: "Unknown", 1: "TV", 2: "Radio", 3: "Data",
                10: "Radio", 12: "Data", 22: "TV", 25: "TV (HD)",
                136: "Data", 139: "Data"}

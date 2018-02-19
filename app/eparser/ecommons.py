""" Common elements module """
from collections import namedtuple
from enum import Enum

Service = namedtuple("Service", ["flags_cas", "transponder_type", "coded", "service", "locked", "hide", "package",
                                 "service_type", "picon", "picon_id", "ssid", "freq", "rate", "pol", "fec",
                                 "system", "pos", "data_id", "fav_id", "transponder"])


# ***************** Bouquets *******************#

class BqServiceType(Enum):
    DEFAULT = "DEFAULT"
    IPTV = "IPTV"
    MARKER = "MARKER"  # 64


Bouquet = namedtuple("Bouquet", ["name", "type", "services", "locked", "hidden"])
Bouquets = namedtuple("Bouquets", ["name", "type", "bouquets"])
BouquetService = namedtuple("BouquetService", ["name", "type", "data", "num"])

# ***************** Satellites *******************#

Satellite = namedtuple("Satellite", ["name", "flags", "position", "transponders"])

Transponder = namedtuple("Transponder", ["frequency", "symbol_rate", "polarization", "fec_inner",
                                         "system", "modulation", "pls_mode", "pls_code", "is_id"])


class Type(Enum):
    """ Types of DVB transponders """
    Satellite = "s"
    Terestrial = "t"
    Cable = "c"


class Flag(Enum):
    """ Service flags

        K - last bit (1)
        H - second from end (10)
        P -  third (100)
        N - seventh (1000000)
    """
    KEEP = 1  # Do not automatically update the services parameters.
    HIDE = 2
    PIDS = 4  # Always use the cached instead of current pids.
    LOCK = 8
    NEW = 40  # Marked as new at the last scan

    @staticmethod
    def is_hide(value: int):
        return value & 1 << 1

    @staticmethod
    def is_keep(value: int):
        return value & 1 << 0

    @staticmethod
    def is_pids(value: int):
        return value & 1 << 2

    @staticmethod
    def is_new(value: int):
        return value & 1 << 5


class Inversion(Enum):
    Off = "0"
    On = "1"
    Auto = "2"


class Pilot(Enum):
    Off = "0"
    On = "1"
    Auto = "2"


ROLL_OFF = {"0": "35%", "1": "25%", "2": "20%", "3": "Auto"}

POLARIZATION = {"0": "H", "1": "V", "2": "L", "3": "R"}

PLS_MODE = {"0": "Root", "1": "Gold", "2": "Combo"}

FEC = {"0": "Auto", "1": "1/2", "2": "2/3", "3": "3/4", "4": "5/6", "5": "7/8", "6": "8/9", "7": "3/5", "8": "4/5",
       "9": "9/10", "10": "1/2", "11": "2/3", "12": "3/4", "13": "5/6", "14": "7/8", "15": "8/9", "16": "3/5",
       "17": "4/5", "18": "9/10", "19": "1/2", "20": "2/3", "21": "3/4", "22": "5/6", "23": "7/8", "24": "8/9",
       "25": "3/5", "26": "4/5", "27": "9/10", "28": "Auto"}

SYSTEM = {"0": "DVB-S", "1": "DVB-S2"}

MODULATION = {"0": "Auto", "1": "QPSK", "2": "8PSK", "3": "16APSK", "5": "32APSK"}

SERVICE_TYPE = {"-2": "Unknown", "1": "TV", "2": "Radio", "3": "Data",
                "10": "Radio", "12": "Data", "22": "TV", "25": "TV (HD)", "31": "TV (UHD)",
                "136": "Data", "139": "Data"}

CAS = {"C:2600": "BISS", "C:0b00": "Conax", "C:0b01": "Conax", "C:0b02": "Conax", "C:0baa": "Conax", "C:0602": "Irdeto",
       "C:0604": "Irdeto", "C:0606": "Irdeto", "C:0608": "Irdeto", "C:0622": "Irdeto", "C:0626": "Irdeto",
       "C:0664": "Irdeto", "C:0614": "Irdeto", "C:0692": "Irdeto", "C:1801": "Nagravision", "C:0500": "Viaccess",
       "C:0E00": "PowerVu", "C:4ae0": "DRE-Crypt", "C:4ae1": "DRE-Crypt", "C:7be1": "DRE-Crypt"}

# 'on' attribute  0070(hex) = 112(int) =  ONID(ONID-TID on www.lyngsat.com)
PROVIDER = {112: "HTB+", 253: "Tricolor TV"}

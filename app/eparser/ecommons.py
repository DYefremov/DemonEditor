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


class TrType(Enum):
    """ Transponders type """
    Satellite = "s"
    Terrestrial = "t"
    Cable = "c"


class BqType(Enum):
    """ Bouquet type"""
    BOUQUET = "bouquet"
    TV = "tv"
    RADIO = "radio"
    WEBTV = "webtv"


class Flag(Enum):
    """ Service flags

        K - last bit (1)
        H - second from end (10)
        P - third (100)
        N - sixth (100000)
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


class Pids(Enum):
    VIDEO = "c:00"
    AUDIO = "c:01"
    TELETEXT = "c:02"
    PCR = "c:03"
    AC3 = "c:04"
    VIDEO_TYPE = "c:05"
    AUDIO_CHANNEL = "c:06"
    BIT_STREAM_DELAY = "c:07"  # in ms
    PCM_DELAY = "c:08"  # in ms
    SUBTITLE = "c:09"


class Inversion(Enum):
    Off = "0"
    On = "1"
    Auto = "2"


class Pilot(Enum):
    Off = "0"
    On = "1"
    Auto = "2"


class SystemCable(Enum):
    """  System of cable service """
    ANNEX_A = "0"
    ANNEX_C = "1"


ROLL_OFF = {"0": "35%", "1": "25%", "2": "20%", "3": "Auto"}

POLARIZATION = {"0": "H", "1": "V", "2": "L", "3": "R"}

PLS_MODE = {"0": "Root", "1": "Gold", "2": "Combo"}

FEC = {"0": "Auto", "1": "1/2", "2": "2/3", "3": "3/4", "4": "5/6", "5": "7/8", "6": "8/9", "7": "3/5", "8": "4/5",
       "9": "9/10", "10": "1/2", "11": "2/3", "12": "3/4", "13": "5/6", "14": "7/8", "15": "8/9", "16": "3/5",
       "17": "4/5", "18": "9/10", "19": "1/2", "20": "2/3", "21": "3/4", "22": "5/6", "23": "7/8", "24": "8/9",
       "25": "3/5", "26": "4/5", "27": "9/10", "28": "Auto"}

FEC_DEFAULT = {"0": "Auto", "1": "1/2", "2": "2/3", "3": "3/4", "4": "5/6", "5": "7/8", "6": "8/9", "7": "3/5",
               "8": "4/5", "9": "9/10", "10": "6/7", "15": "None"}

SYSTEM = {"0": "DVB-S", "1": "DVB-S2"}

MODULATION = {"0": "Auto", "1": "QPSK", "2": "8PSK", "4": "16APSK", "5": "32APSK"}

SERVICE_TYPE = {"-2": "Data", "1": "TV", "2": "Radio", "3": "Data", "10": "Radio", "22": "TV (H264)",
                "25": "TV (HD)", "31": "TV (UHD)"}

# Terrestrial
BANDWIDTH = {"0": "Auto", "1": "8Mhz", "2": "7Mhz", "3": "6Mhz"}

T_MODULATION = {"0": "Auto", "1": "QPSK", "2": "QAM16", "3": "QAM64"}

TRANSMISSION_MODE = {"0": "Auto", "1": "2k", "3": "8k"}

GUARD_INTERVAL = {"0": "Auto", "1": "1/32", "2": "1/16", "3": "1/8", "4": "1/4"}

HIERARCHY = {"0": "Auto", "1": "None", "2": "1", "3": "2", "4": "4"}

T_FEC = {"0": "1/2", "1": "2/3", "2": "3/4", "3": "5/6", "4": "7/8", "5": "Auto", "6": "6/7", "7": "8/9"}

T_SYSTEM = {"0": "DVB-T", "1": "DVB-T2", "2": "DVB-T/T2"}

# Cable
C_MODULATION = {"0": "Auto", "1": "QAM16", "2": "QAM32", "3": "QAM64", "4": "QAM128", "5": "QAM256"}

# CAS
CAS = {"C:2600": "BISS", "C:0b00": "Conax", "C:0b01": "Conax", "C:0b02": "Conax", "C:0baa": "Conax", "C:0602": "Irdeto",
       "C:0604": "Irdeto", "C:0606": "Irdeto", "C:0608": "Irdeto", "C:0622": "Irdeto", "C:0626": "Irdeto",
       "C:0664": "Irdeto", "C:0614": "Irdeto", "C:0692": "Irdeto", "C:1801": "Nagravision", "C:0500": "Viaccess",
       "C:0E00": "PowerVu", "C:4ae0": "DRE-Crypt", "C:4ae1": "DRE-Crypt", "C:7be1": "DRE-Crypt"}

# 'on' attribute  0070(hex) = 112(int) =  ONID(ONID-TID on www.lyngsat.com)
PROVIDER = {112: "HTB+", 253: "Tricolor TV"}


# ************* subsidiary functions ****************

def get_key_by_value(dc: dict, value):
    """ Returns key from dict by value """
    for k, v in dc.items():
        if v == value:
            return k


def get_value_by_name(en, name):
    """ Returns value by name from enums """
    for n in en:
        if n.name == name:
            return n.value


def is_transponder_valid(tr: Transponder):
    """ Checks  transponder validity """
    try:
        int(tr.frequency)
        int(tr.symbol_rate)
        tr.pls_mode is None or int(tr.pls_mode)
        tr.pls_code is None or int(tr.pls_code)
        tr.is_id is None or int(tr.is_id)
    except TypeError:
        return False

    if tr.polarization not in POLARIZATION.values():
        return False
    if tr.fec_inner not in FEC.values():
        return False
    if tr.system not in SYSTEM.values():
        return False
    if tr.modulation not in MODULATION.values():
        return False

    return True

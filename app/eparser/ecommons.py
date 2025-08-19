# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2025 Dmitriy Yefremov
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


""" Common elements module. """
from collections import namedtuple
from enum import Enum

from app.commons import log

Service = namedtuple("Service", ["flags_cas", "transponder_type", "coded", "service", "locked", "hide", "package",
                                 "service_type", "picon", "picon_id", "ssid", "freq", "rate", "pol", "fec",
                                 "system", "pos", "data_id", "fav_id", "transponder"])


# ***************** Bouquets *******************#

class BqServiceType(Enum):
    DEFAULT = "DEFAULT"
    IPTV = "IPTV"
    MARKER = "MARKER"  # 64
    SPACE = "SPACE"  # 832 [hidden marker]
    ALT = "ALT"  # Service with alternatives
    BOUQUET = "BOUQUET"  # Sub bouquet.

    @classmethod
    def _missing_(cls, value):
        return cls.DEFAULT


Bouquet = namedtuple("Bouquet", ["name", "type", "services", "locked", "hidden", "file"])
Bouquet.__new__.__defaults__ = (None, BqServiceType.DEFAULT, [], None, None, None)  # For Python3 < 3.7
Bouquets = namedtuple("Bouquets", ["name", "type", "bouquets"])
BouquetService = namedtuple("BouquetService", ["name", "type", "data", "num"])

# *************** *.xml [Satellites, Terrestrial, Cable] ***************** #

Satellite = namedtuple("Satellite", ["name", "flags", "position", "transponders"])
Terrestrial = namedtuple("Terrestrial", ["name", "flags", "countrycode", "transponders"])
Cable = namedtuple("Cable", ["name", "flags", "satfeed", "countrycode", "transponders"])

Transponder = namedtuple("Transponder", ["frequency", "symbol_rate", "polarization", "fec_inner", "system",
                                         "modulation", "pls_mode", "pls_code", "is_id", "t2mi_plp_id"])
TerTransponder = namedtuple("TerTransponder", ["centre_frequency", "system", "bandwidth", "constellation",
                                               "code_rate_hp", "code_rate_lp", "guard_interval", "transmission_mode",
                                               "hierarchy_information", "inversion", "plp_id"])
CableTransponder = namedtuple("CableTransponder", ["frequency", "symbol_rate", "fec_inner", "modulation"])


class TrType(Enum):
    """ Transponders type. """
    Satellite = "s"
    Terrestrial = "t"
    Cable = "c"
    ATSC = "a"

    @classmethod
    def _missing_(cls, value):
        return cls.Satellite


class BqType(Enum):
    """ Bouquet type. """
    BOUQUET = "bouquet"
    TV = "tv"
    RADIO = "radio"
    WEBTV = "webtv"
    MARKER = "marker"

    @classmethod
    def _missing_(cls, value):
        return cls.TV


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

    @staticmethod
    def parse(value: str) -> int:
        """ Returns an int representation of the flag value.

            The flag value is usually represented by the number [int],
            but can also be appear in hex format.
         """
        if len(value) < 3:
            return 0

        value = value[2:]
        if value.isdigit():
            return int(value)
        return int(value, 16)


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

    @classmethod
    def _missing_(cls, value):
        return cls.Auto


class Pilot(Enum):
    Off = "0"
    On = "1"
    Auto = "2"

    @classmethod
    def _missing_(cls, value):
        return cls.Auto


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
BANDWIDTH = {"0": "8MHz", "1": "7MHz", "2": "6MHz", "3": "Auto", "4": "5MHz", "5": "1/712MHz", "6": "10MHz"}

CONSTELLATION = {"0": "QPSK", "1": "16-QAM", "2": "64-QAM", "3": "Auto"}

T_MODULATION = {"0": "QPSK", "1": "QAM16", "2": "QAM64", "3": "Auto", "4": "QAM256"}

TRANSMISSION_MODE = {"0": "2k", "1": "8k", "2": "Auto", "3": "4k", "4": "1k", "5": "16k", "6": "32k"}

GUARD_INTERVAL = {"0": "1/32", "1": "1/16", "2": "1/8", "3": "1/4", "4": "Auto", "5": "1/128", "6": "19/128",
                  "7": "19/256"}

HIERARCHY = {"0": "None", "1": "1", "2": "2", "3": "4", "4": "Auto"}

T_FEC = {"0": "1/2", "1": "2/3", "2": "3/4", "3": "5/6", "4": "7/8", "5": "Auto", "6": "6/7", "7": "8/9"}

T_SYSTEM = {"0": "DVB-T", "1": "DVB-T2", "-1": "DVB-T/T2"}

# Cable
C_MODULATION = {"0": "QPSK", "1": "QAM16", "2": "QAM32", "3": "QAM64", "4": "QAM128", "5": "QAM256", "6": "Auto"}

# ATSC
A_MODULATION = {"0": "Auto", "1": "QAM16", "2": "QAM32", "3": "QAM64", "4": "QAM128", "5": "QAM256", "6": "8VSB",
                "7": "16VSB"}

# CAS
CAS = {"C:26": "BISS", "C:0B": "Conax", "C:06": "Irdeto", "C:18": "Nagravision", "C:05": "Viaccess", "C:01": "SECA",
       "C:0E": "PowerVu", "C:4A": "DRE-Crypt", "C:7B": "DRE-Crypt", "C:56": "Verimatrix", "C:09": "VideoGuard",
       "C:4AFC": "Panaccess"}

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
    """ Checks transponder validity. """
    try:
        int(tr.frequency)
        int(tr.symbol_rate)
        tr.pls_mode is None or int(tr.pls_mode)
        tr.pls_code is None or int(tr.pls_code)
        tr.is_id is None or int(tr.is_id)
        tr.t2mi_plp_id is None or int(tr.t2mi_plp_id)
    except (TypeError, ValueError) as e:
        log(f"Transponder validation error: {e}\n{tr}")
        return False

    if tr.polarization not in POLARIZATION:
        return False
    if tr.fec_inner not in FEC:
        return False
    if tr.system not in SYSTEM:
        return False
    if tr.modulation not in MODULATION:
        return False

    return True

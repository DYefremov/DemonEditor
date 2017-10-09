""" Module foe parsing Satellites.xml

Transponder parameters:
polarization: 0 - Horizontal, 1 - Vertical, 2 - Left Circular, 3 - Right Circular
fec_inner: 0 - Auto, 1 - 1/2, 2 - 2_3, 3 - 3/4, 4 - 5/6, 5 - 6/7, 6 - 7/8, 7 - 8/9, 8 - 3/5, 9 - 4/5, 10 - 9/10
modulation: 0 - Auto, 1 - QPSK, 2 - 8PSK, 3 - 16APSK, 5 - 32APSK
rolloff: 0 - 0.35, 1 - 0.25, 2 - 0.20, 3 - Auto
pilot: 0 - Off, 1 - On, 2 - Auto
inversion: 0 = Off, 1 = On, 2 = Auto (default)
system: 0 = DVB-S, 1 = DVB-S2
is_id: 0 - 255
pls_mode: 0 - Root, 1 - Gold, 2 - Combo
pls_code: 0 - 262142
"""
from collections import namedtuple
from xml.dom.minidom import parse

from main.eparser import Polarization, System, Fec, Modulation, Plsmode

XML_PATH = "../data/satellites.xml"

Satellite = namedtuple("Satellite", ["name", "flags", "position", "transponders"])

Transponder = namedtuple("Transponder", ["frequency", "symbol_rate", "polarization", "fec_inner",
                                         "system", "modulation", "pls_mode", "pls_code", "is_id"])


def get_transponders(elem):
    """ Parsing satellite transponders """
    transponders = []
    for el in elem.getElementsByTagName("transponder"):
        if el.hasAttributes():
            atr = el.attributes
            tr = Transponder(atr["frequency"].value,
                             atr["symbol_rate"].value,
                             Polarization(int(atr["polarization"].value)).name,
                             Fec[int(atr["fec_inner"].value)],
                             System[int(atr["system"].value)],
                             Modulation[int(atr["modulation"].value)],
                             Plsmode(int(atr["pls_mode"].value)).name if "pls_mode" in atr else None,
                             atr["pls_code"].value if "pls_code" in atr else None,
                             atr["is_id"].value if "is_id" in atr else None)
            transponders.append(tr)
    return transponders


def get_sat(elem):
    """ Parsing satellite """
    return Satellite(elem.attributes["name"].value,
                     elem.attributes["flags"].value,
                     elem.attributes["position"].value,
                     get_transponders(elem))


def get_satellites(path):
    """ Parsing satellites from xml"""
    dom = parse(path)
    satellites = []
    for elem in dom.getElementsByTagName("sat"):
        if elem.hasAttributes():
            satellites.append(get_sat(elem))
    return satellites


if __name__ == "__main__":
    pass

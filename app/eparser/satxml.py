""" Module foe parsing Satellites.xml

    For more info see __COMMENT
"""
from collections import namedtuple
from xml.dom.minidom import parse, Document

from app.eparser.__constants import POLARIZATION, FEC, SYSTEM, MODULATION, PLS_MODE

Satellite = namedtuple("Satellite", ["name", "flags", "position", "transponders"])

Transponder = namedtuple("Transponder", ["frequency", "symbol_rate", "polarization", "fec_inner",
                                         "system", "modulation", "pls_mode", "pls_code", "is_id"])

__COMMENT = ("   File was created in DemonEditor\n\n"
             "useable flags are\n"
             "	1: Network Scan\n"
             "	2: use BAT\n"
             "	4: use ONIT\n"
             "	8: skip NITs of known networks\n"
             "	and combinations of this.\n\n"

             "transponder parameters:\n"
             "polarization: 0 - Horizontal, 1 - Vertical, 2 - Left Circular, 3 - Right Circular\n"
             "fec_inner: 0 - Auto, 1 - 1/2, 2 - 2/3, 3 - 3/4, 4 - 5/6, 5 - 7/8, 6 -  8/9, 7 - 3/5,\n"
             "8 - 4/5, 9 - 9/10, 15 - None\n"
             "modulation: 0 - Auto, 1 - QPSK, 2 - 8PSK, 3 - 16APSK, 5 - 32APSK\n"
             "rolloff: 0 - 0.35, 1 - 0.25, 2 - 0.20, 3 - Auto\n"
             "pilot: 0 - Off, 1 - On, 2 - Auto\n"
             "inversion: 0 = Off, 1 = On, 2 = Auto (default)\n"
             "system: 0 = DVB-S, 1 = DVB-S2\n"
             "is_id: 0 - 255\n"
             "pls_mode: 0 - Root, 1 - Gold, 2 - Combo\n"
             "pls_code: 0 - 262142\n\n")


def get_satellites(path):
    return parse_satellites(path)


def write_satellites(satellites, data_path):
    """ Creation satellites.xml file """
    doc = Document()
    comment = doc.createComment(__COMMENT)
    doc.appendChild(comment)
    root = doc.createElement("satellites")
    doc.appendChild(root)

    for sat in satellites:
        #    Create Element
        sat_child = doc.createElement("sat")
        sat_child.setAttribute("name", sat.name)
        sat_child.setAttribute("flags", sat.flags)
        sat_child.setAttribute("position", sat.position)

        for tr in sat.transponders:
            transponder_child = doc.createElement("transponder")
            transponder_child.setAttribute("frequency", tr.frequency)
            transponder_child.setAttribute("symbol_rate", tr.symbol_rate)
            transponder_child.setAttribute("polarization", get_key_by_value(POLARIZATION, tr.polarization))
            transponder_child.setAttribute("fec_inner", get_key_by_value(FEC, tr.fec_inner))
            transponder_child.setAttribute("system", get_key_by_value(SYSTEM, tr.system))
            transponder_child.setAttribute("modulation", get_key_by_value(MODULATION, tr.modulation))
            if tr.pls_mode:
                transponder_child.setAttribute("pls_mode", get_key_by_value(PLS_MODE, tr.pls_mode))
            if tr.pls_code:
                transponder_child.setAttribute("pls_code", tr.pls_code)
            if tr.is_id:
                transponder_child.setAttribute("is_id", tr.is_id)
            sat_child.appendChild(transponder_child)
        root.appendChild(sat_child)
    doc.writexml(open(data_path, "w"),
                 # indent="",
                 addindent="    ",
                 newl='\n',
                 encoding="iso-8859-1")
    doc.unlink()


def parse_transponders(elem):
    """ Parsing satellite transponders """
    transponders = []
    for el in elem.getElementsByTagName("transponder"):
        if el.hasAttributes():
            atr = el.attributes
            tr = Transponder(atr["frequency"].value,
                             atr["symbol_rate"].value,
                             POLARIZATION[atr["polarization"].value],
                             FEC[atr["fec_inner"].value],
                             SYSTEM[atr["system"].value],
                             MODULATION[atr["modulation"].value],
                             PLS_MODE[atr["pls_mode"].value] if "pls_mode" in atr else None,
                             atr["pls_code"].value if "pls_code" in atr else None,
                             atr["is_id"].value if "is_id" in atr else None)
            transponders.append(tr)
    return transponders


def parse_sat(elem):
    """ Parsing satellite """
    return Satellite(elem.attributes["name"].value,
                     elem.attributes["flags"].value,
                     elem.attributes["position"].value,
                     parse_transponders(elem))


def parse_satellites(path):
    """ Parsing satellites from xml"""
    dom = parse(path)
    satellites = []

    for elem in dom.getElementsByTagName("sat"):
        if elem.hasAttributes():
            satellites.append(parse_sat(elem))

    return satellites


def get_key_by_value(dictionary, value):
    for k, v in dictionary.items():
        if v == value:
            return k


if __name__ == "__main__":
    pass

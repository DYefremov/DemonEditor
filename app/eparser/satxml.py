# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2022 Dmitriy Yefremov
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


""" Module for parsing *.xml files.

    For more info see comments.
"""
from xml.dom.minidom import parse, Document

from app.commons import log
from .ecommons import POLARIZATION, FEC, SYSTEM, MODULATION, Transponder, Satellite, get_key_by_value, Terrestrial, \
    Cable

_SAT_COMMENT = ("   File was created in DemonEditor\n\n"
                "usable flags are\n"
                "	1: Network Scan\n"
                "	2: use BAT\n"
                "	4: use ONIT\n"
                "	8: skip NITs of known networks\n"
                "	and combinations of this.\n\n"

                "transponder parameters:\n"
                "polarization: 0 - Horizontal, 1 - Vertical, 2 - Left Circular, 3 - Right Circular\n"
                "fec_inner: 0 - Auto, 1 - 1/2, 2 - 2/3, 3 - 3/4, 4 - 5/6, 5 - 7/8, 6 -  8/9, 7 - 3/5,\n"
                "8 - 4/5, 9 - 9/10, 15 - None\n"
                "modulation: 0 - Auto, 1 - QPSK, 2 - 8PSK, 4 - 16APSK, 5 - 32APSK\n"
                "rolloff: 0 - 0.35, 1 - 0.25, 2 - 0.20, 3 - Auto\n"
                "pilot: 0 - Off, 1 - On, 2 - Auto\n"
                "inversion: 0 = Off, 1 = On, 2 = Auto (default)\n"
                "system: 0 = DVB-S, 1 = DVB-S2\n"
                "is_id: 0 - 255\n"
                "pls_mode: 0 - Root, 1 - Gold, 2 - Combo\n"
                "pls_code: 0 - 262142\n\n")


def get_satellites(path):
    """ Returns data [Satellite] list from *.xml. """
    return [parse_sat(elem) for elem in parse(path).getElementsByTagName("sat") if elem.hasAttributes()]


def get_terrestrial(path):
    """ Returns data [Terrestrial] list from *.xml. """
    return [parse_terrestrial(elem) for elem in parse(path).getElementsByTagName("terrestrial") if elem.hasAttributes()]


def get_cable(path):
    """ Returns data [Cable] list from *.xml. """
    return [parse_cable(elem) for elem in parse(path).getElementsByTagName("cable") if elem.hasAttributes()]


def write_satellites(satellites, data_path):
    """ Creation satellites.xml file """
    doc = Document()
    comment = doc.createComment(_SAT_COMMENT)
    doc.appendChild(comment)
    root = doc.createElement("satellites")
    doc.appendChild(root)

    for sat in satellites:
        # Create Element
        sat_child = doc.createElement("sat")
        sat_child.setAttribute("name", sat.name)
        sat_child.setAttribute("flags", sat.flags)
        sat_child.setAttribute("position", sat.position)

        for tr in sat.transponders:
            transponder_child = doc.createElement("transponder")
            transponder_child.setAttribute("frequency", tr.frequency)
            transponder_child.setAttribute("symbol_rate", tr.symbol_rate)
            transponder_child.setAttribute("polarization", get_key_by_value(POLARIZATION, tr.polarization))
            transponder_child.setAttribute("fec_inner", get_key_by_value(FEC, tr.fec_inner) or "0")
            transponder_child.setAttribute("system", get_key_by_value(SYSTEM, tr.system) or "0")
            transponder_child.setAttribute("modulation", get_key_by_value(MODULATION, tr.modulation) or "0")
            if tr.pls_mode:
                transponder_child.setAttribute("pls_mode", tr.pls_mode)
            if tr.pls_code:
                transponder_child.setAttribute("pls_code", tr.pls_code)
            if tr.is_id:
                transponder_child.setAttribute("is_id", tr.is_id)
            if tr.t2mi_plp_id:
                transponder_child.setAttribute("t2mi_plp_id", tr.t2mi_plp_id)
            sat_child.appendChild(transponder_child)
        root.appendChild(sat_child)
    doc.writexml(open(data_path, "w"),
                 # indent="",
                 addindent="    ",
                 newl='\n',
                 encoding="iso-8859-1")
    doc.unlink()


def parse_transponders(elem, sat_name):
    """ Parsing satellite transponders """
    transponders = []
    for el in elem.getElementsByTagName("transponder"):
        if el.hasAttributes():
            atr = el.attributes
            try:
                tr = Transponder(atr["frequency"].value,
                                 atr["symbol_rate"].value,
                                 POLARIZATION[atr["polarization"].value],
                                 FEC[atr["fec_inner"].value],
                                 SYSTEM[atr["system"].value],
                                 MODULATION[atr["modulation"].value],
                                 atr["pls_mode"].value if "pls_mode" in atr else None,
                                 atr["pls_code"].value if "pls_code" in atr else None,
                                 atr["is_id"].value if "is_id" in atr else None,
                                 atr["t2mi_plp_id"].value if "t2mi_plp_id" in atr else None)
            except Exception as e:
                message = f"Error: can't parse transponder for '{sat_name}' satellite! {repr(e)}"
                log(message)
            else:
                transponders.append(tr)
    return transponders


def parse_sat(elem):
    """ Parsing satellite. """
    sat_name = elem.attributes["name"].value
    return Satellite(sat_name,
                     elem.attributes["flags"].value,
                     elem.attributes["position"].value,
                     parse_transponders(elem, sat_name))


def parse_terrestrial(elem):
    atr = elem.attributes
    return Terrestrial(atr["name"].value, None, None, [])


def parse_cable(elem):
    atr = elem.attributes
    return Cable(atr["name"].value, None, None, None, [])


if __name__ == "__main__":
    pass

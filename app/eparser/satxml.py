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
from xml.dom.minidom import Document
import xml.etree.ElementTree as ETree

from .ecommons import (POLARIZATION, FEC, SYSTEM, MODULATION, Transponder, Satellite, get_key_by_value,
                       Terrestrial, Cable, TerTransponder, CableTransponder, T_SYSTEM, BANDWIDTH, GUARD_INTERVAL,
                       TRANSMISSION_MODE, T_FEC, HIERARCHY, C_MODULATION, FEC_DEFAULT, Inversion, CONSTELLATION)

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
    return [Satellite(e.get("name", None),
                      e.get("flags", None),
                      e.get("position", None) or "0",
                      get_sat_transponders(e)) for e in ETree.parse(path).iter("sat")]


def get_sat_transponders(elem):
    """ Returns satellite transponders list. """
    return [Transponder(e.get("frequency", "0"),
                        e.get("symbol_rate", "0"),
                        POLARIZATION[e.get("polarization", "0")],
                        FEC[e.get("fec_inner", "0")],
                        SYSTEM[e.get("system", "0")],
                        MODULATION[e.get("modulation", "0")],
                        e.get("pls_mode", None),
                        e.get("pls_code", None),
                        e.get("is_id", None),
                        e.get("t2mi_plp_id", None)) for e in elem.iter("transponder")]


def get_terrestrial(path):
    """ Returns data [Terrestrial] list from *.xml. """
    return [Terrestrial(e.get("name", None),
                        e.get("flags", None),
                        e.get("countrycode", None),
                        [get_ter_transponder(e) for e in e.iter("transponder")]
                        ) for e in ETree.parse(path).iter("terrestrial")]


def get_ter_transponder(elem):
    """ Returns terrestrial transponder. """
    return TerTransponder(elem.get("centre_frequency", "0"),
                          T_SYSTEM.get(elem.get("system", None), None),
                          BANDWIDTH.get(elem.get("bandwidth", None), None),
                          CONSTELLATION.get(elem.get("constellation", None), None),
                          T_FEC.get(elem.get("code_rate_hp", None), None),
                          T_FEC.get(elem.get("code_rate_lp", None), None),
                          GUARD_INTERVAL.get(elem.get("guard_interval", None), None),
                          TRANSMISSION_MODE.get(elem.get("transmission_mode", None), None),
                          HIERARCHY.get(elem.get("hierarchy_information", None), None),
                          Inversion(elem.get("inversion")).name if "inversion" in elem.keys() else None,
                          elem.get("plp_id", None))


def get_cable(path):
    """ Returns data [Cable] list from *.xml. """
    return [Cable(e.get("name", None),
                  e.get("flags", None),
                  e.get("satfeed", None),
                  e.get("countrycode", None),
                  get_cable_transponders(e)) for e in ETree.parse(path).iter("cable")]


def get_cable_transponders(elem):
    """ Returns cable transponders list. """
    return [CableTransponder(e.get("frequency", "0"),
                             e.get("symbol_rate", "0"),
                             FEC_DEFAULT[e.get("fec_inner", "0")],
                             C_MODULATION[e.get("modulation", "0")]) for e in elem.iter("transponder")]


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


if __name__ == "__main__":
    pass

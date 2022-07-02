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


""" Module for working with *.xml files.

    For more info see comments.
"""
import xml.etree.ElementTree as ETree

from .ecommons import Satellite, Terrestrial, Cable, Transponder, TerTransponder, CableTransponder

_SAT_COMMENT = ("\tFile was created in DemonEditor.\n\n"
                "Usable flags are:\n"
                "	1: Network Scan\n"
                "	2: use BAT\n"
                "	4: use ONIT\n"
                "	8: skip NITs of known networks\n"
                "   This is a bitmap and combinations can be used.\n\n"
                "Transponder parameters:\n"
                "\tpolarization: 0 - Horizontal, 1 - Vertical, 2 - Left Circular, 3 - Right Circular\n"
                "\tfec_inner: 0 - Auto, 1 - 1/2, 2 - 2/3, 3 - 3/4, 4 - 5/6, 5 - 7/8, 6 -  8/9, 7 - 3/5,\n"
                "\t8 - 4/5, 9 - 9/10, 15 - None\n"
                "\tmodulation: 0 - Auto, 1 - QPSK, 2 - 8PSK, 4 - 16APSK, 5 - 32APSK\n"
                "\trolloff: 0 - 0.35, 1 - 0.25, 2 - 0.20, 3 - Auto\n"
                "\tpilot: 0 - Off, 1 - On, 2 - Auto\n"
                "\tinversion: 0 = Off, 1 = On, 2 = Auto (default)\n"
                "\tsystem: 0 = DVB-S, 1 = DVB-S2\n"
                "\tis_id: 0 - 255\n"
                "\tpls_mode: 0 - Root, 1 - Gold, 2 - Combo\n"
                "\tpls_code: 0 - 262142\n\n")

_TERRESTRIAL_COMMENT = ("\tFile was created in DemonEditor.\n\n"
                        "Usable flags are:\n"
                        "	1: Network Scan\n"
                        "	2: use BAT\n"
                        "	4: use ONIT\n"
                        "	8: skip NITs of known networks\n"
                        "   This is a bitmap and combinations can be used.\n\n")

_CABLE_COMMENT = ("\tFile was created in DemonEditor.\n\n"
                  "Transponder parameters:\n"
                  "\tmodulation:\n"
                  "\t3: QAM64\n"
                  "\t5: QAM256\n")


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
                        e.get("polarization", None),
                        e.get("fec_inner", None),
                        e.get("system", None),
                        e.get("modulation", None),
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
                          elem.get("system", None),
                          elem.get("bandwidth", None),
                          elem.get("constellation", None),
                          elem.get("code_rate_hp", None),
                          elem.get("code_rate_lp", None),
                          elem.get("guard_interval", None),
                          elem.get("transmission_mode", None),
                          elem.get("hierarchy_information", None),
                          elem.get("inversion", None),
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
                             e.get("fec_inner", None),
                             e.get("modulation", None)) for e in elem.iter("transponder")]


def write_satellites(satellites, data_path, encoding="UTF-8"):
    """ Creates satellites.xml file. """
    write_xml("satellites", "sat", satellites, data_path, _SAT_COMMENT, encoding)


def write_terrestrial(terrestrial, data_path, encoding="UTF-8"):
    """ Creates terrestrial.xml file. """
    write_xml("locations", "terrestrial", terrestrial, data_path, _TERRESTRIAL_COMMENT, encoding)


def write_cable(cables, data_path, encoding="UTF-8"):
    """ Creates cables.xml file. """
    write_xml("cables", "cable", cables, data_path, _CABLE_COMMENT, encoding)


def write_xml(root_name, sub_name, data, data_path, comment="", encoding="UTF-8"):
    """ Creates *.xml files. """
    xml = ETree.Element(root_name)
    [write_element(sub_name, "transponder", t, xml) for t in data]

    tree = ETree.ElementTree(xml)
    indent(tree.getroot())

    with open(data_path, "wb") as f:
        # To put comment on top.
        f.write(f'<?xml version="1.0" encoding="{encoding}"?>\n<!--\n{comment}-->\n\n'.encode("utf-8"))
        tree.write(f, encoding=encoding)


def write_element(e_name, ch_name, e_data, root):
    """ Writes element with sub elements.

        @param e_name: Element name.
        @param ch_name: Child element name.
        @param e_data: Element data -> defaultdict
        @param root: Parent of the element.
    """
    t = e_data._asdict()
    subs = t.pop("transponders")
    root_sub = ETree.SubElement(root, e_name, {k: v for k, v in t.items() if v})
    [ETree.SubElement(root_sub, ch_name, {k: v for k, v in tr._asdict().items() if v}) for tr in subs]


def indent(elem, parent=None, index=-1, level=0, space="    "):
    """  Appends whitespace to the subtree to indent the tree visually.

        Since the minimum supported version < 3.9, we will use our own implementation.
    """
    for i, sub in enumerate(elem):
        indent(sub, elem, i, level + 1)
    if parent:
        if index == 0:
            parent.text = f"\n{space * level}"
        else:
            parent[index - 1].tail = f"\n{space * level}"

        if index == len(parent) - 1:
            elem.tail = f"\n{space * (level - 1)}"


if __name__ == "__main__":
    pass

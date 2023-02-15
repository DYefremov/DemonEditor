# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2023 Dmitriy Yefremov
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

from app.commons import run_task
from app.settings import SettingsType
from .ecommons import Service, Satellite, Transponder, Bouquet, Bouquets, is_transponder_valid
from .enigma.blacklist import get_blacklist, write_blacklist
from .enigma.bouquets import to_bouquet_id, BouquetsWriter, BouquetsReader
from .enigma.lamedb import get_services as get_enigma_services, write_services as write_enigma_services
from .iptv import parse_m3u
from .neutrino.bouquets import get_bouquets as get_neutrino_bouquets, write_bouquets as write_neutrino_bouquets
from .neutrino.services import get_services as get_neutrino_services, write_services as write_neutrino_services
from .satxml import get_satellites, write_satellites


def get_services(data_path, s_type, format_version):
    if s_type is SettingsType.ENIGMA_2:
        return get_enigma_services(data_path, format_version)
    elif s_type is SettingsType.NEUTRINO_MP:
        return get_neutrino_services(data_path)


@run_task
def write_services(path, channels, s_type, format_version):
    if s_type is SettingsType.ENIGMA_2:
        write_enigma_services(path, channels, format_version)
    elif s_type is SettingsType.NEUTRINO_MP:
        write_neutrino_services(path, channels)


def get_bouquets(path, s_type):
    if s_type is SettingsType.ENIGMA_2:
        return BouquetsReader(path).get()
    elif s_type is SettingsType.NEUTRINO_MP:
        return get_neutrino_bouquets(path)


def write_bouquet(path, bq, s_type):
    if s_type is SettingsType.ENIGMA_2:
        writer = BouquetsWriter(path, None)
        writer.write_bouquet(f"{path}userbouquet.{bq.name}.{bq.type}", bq.name, bq.services)
    elif s_type is SettingsType.NEUTRINO_MP:
        from .neutrino.bouquets import write_bouquet
        write_bouquet(path, bq)


@run_task
def write_bouquets(path, bouquets, s_type, force_bq_names=False, blacklist=None):
    if s_type is SettingsType.ENIGMA_2:
        BouquetsWriter(path, bouquets, force_bq_names, blacklist).write()
    elif s_type is SettingsType.NEUTRINO_MP:
        write_neutrino_bouquets(path, bouquets)


if __name__ == "__main__":
    pass

# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2024 Dmitriy Yefremov
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


""" Module for IPTV and streams support """
import re
from enum import Enum
from urllib.parse import unquote, quote

from app.commons import log
from app.eparser.ecommons import BqServiceType, Service
from app.settings import SettingsType
from app.ui.uicommons import IPTV_ICON

# url, description, urlkey, account, usrname, psw, s_type, iconsrc, iconsrc_b, group
NEUTRINO_FAV_ID_FORMAT = "{}::{}::{}::{}::{}::{}::{}::{}::{}::{}"
ENIGMA2_FAV_ID_FORMAT = " {}:{}:{:X}:{:X}:{:X}:{:X}:{:X}:0:0:0:{}:{}\n#DESCRIPTION {}\n"
MARKER_FORMAT = " 1:64:{}:0:0:0:0:0:0:0::{}\n#DESCRIPTION {}\n"
PICON_FORMAT = "{}_{}_{:X}_{:X}_{:X}_{:X}_{:X}_0_0_0.png"


class StreamType(Enum):
    DVB_TS = "1"
    NONE_TS = "4097"
    NONE_REC_1 = "5001"
    NONE_REC_2 = "5002"
    E_SERVICE_URI = "8193"
    E_SERVICE_HLS = "8739"
    UNKNOWN = "0"

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


def parse_m3u(path, s_type, detect_encoding=True, params=None):
    """ Parses *m3u* file and returns tuple with EPG src URLs and services list. """
    pattern = re.compile(r'(\S+)="(.*?)"')

    with open(path, "rb") as file:
        data = file.read()
        encoding = "utf-8"

        if detect_encoding:
            try:
                import chardet
            except ModuleNotFoundError:
                pass
            else:
                enc = chardet.detect(data)
                encoding = enc.get("encoding", "utf-8")

        aggr = [None] * 10
        s_aggr = aggr[: -3]
        epg_src = None
        group = None
        groups = set()
        services = []
        marker_counter = 1
        sid_counter = 1
        name = None
        picon = None
        p_id = "1_0_1_0_0_0_0_0_0_0.png"
        st = BqServiceType.IPTV.name
        params = params or [0, 0, 0, 0]
        m_name = BqServiceType.MARKER.name

        for line in str(data, encoding=encoding, errors="ignore").splitlines():
            if line.startswith("#EXTM3U"):
                data = dict(pattern.findall(line))
                epg_src = data.get("x-tvg-url", data.get("url-tvg", None))
                epg_src = epg_src.split(",") if epg_src else None
            if line.startswith("#EXTINF"):
                line, sep, name = line.rpartition(",")
                data = dict(pattern.findall(line))
                name = data.get("tvg-name", name)
                picon = data.get("tvg-logo", None)

                if s_type is SettingsType.ENIGMA_2:
                    group = data.get("group-title", None)
            elif line.startswith("#EXTGRP") and s_type is SettingsType.ENIGMA_2:
                group = line.strip("#EXTGRP:").strip()
            elif not line.startswith("#") and "://" in line:
                url = line.strip()
                params[0] = sid_counter
                sid_counter += 1
                fav_id = get_fav_id(url, name, s_type, params)
                if s_type is SettingsType.ENIGMA_2:
                    p_id = get_picon_id(params)
                    if group not in groups:
                        # Some playlists have "random" of group names.
                        # We will take only the first one we found on the list!
                        groups.add(group)
                        m_id = MARKER_FORMAT.format(marker_counter, group, group)
                        marker_counter += 1
                        services.append(Service(None, None, None, group, *aggr[0:3], m_name, *aggr, m_id, None))

                if all((name, url, fav_id)):
                    services.append(Service(None, None, IPTV_ICON, name, *aggr[0:2], group,
                                            st, picon, p_id, *s_aggr, url, fav_id, None))
                else:
                    log(f"*.m3u* parse error ['{path}']: name[{name}], url[{url}], fav id[{fav_id}]")

    return epg_src, services


def export_to_m3u(path, bouquet, s_type, url=None):
    pattern = re.compile(".*:(http.*).*") if s_type is SettingsType.ENIGMA_2 else re.compile("(http.*?)::::.*")
    lines = ["#EXTM3U\n"]
    current_grp = None

    for s in bouquet.services:
        srv_type = s.type
        if srv_type is BqServiceType.IPTV:
            res = re.match(pattern, s.data)
            if not res:
                continue
            lines.append(f"#EXTINF:-1,{s.name}\n")
            lines.append(current_grp) if current_grp else None
            u = res.group(1)
            lines.append(f"{unquote(u[:u.rfind(':')]) if s_type is SettingsType.ENIGMA_2 else u}\n")
        elif srv_type is BqServiceType.MARKER:
            current_grp = f"#EXTGRP:{s.name}\n"
        elif srv_type is BqServiceType.DEFAULT and url:
            lines.append(f"#EXTINF:-1,{s.name}\n")
            lines.append(current_grp) if current_grp else None
            lines.append(f"{url}{s.data}\n")

    with open(f"{path}{bouquet.name}.m3u", "w", encoding="utf-8") as file:
        file.writelines(lines)


def get_fav_id(url, name, settings_type, params=None, st_type=None, s_id=0, srv_type=1, force_quote=True):
    """ Returns fav id depending on the settings type. """
    if settings_type is SettingsType.ENIGMA_2:
        st_type = st_type or StreamType.NONE_TS.value
        params = params or (0, 0, 0, 0)
        url = quote(url) if force_quote else url
        return ENIGMA2_FAV_ID_FORMAT.format(st_type, s_id, srv_type, *params, url, name, name, None)
    elif settings_type is SettingsType.NEUTRINO_MP:
        return NEUTRINO_FAV_ID_FORMAT.format(url, "", 0, None, None, None, None, "", "", 1)


def get_picon_id(params=None, st_type=None, s_id=0, srv_type=1):
    st_type = st_type or StreamType.NONE_TS.value
    params = params or (0, 0, 0, 0)
    return PICON_FORMAT.format(st_type, s_id, srv_type, *params)


if __name__ == "__main__":
    pass

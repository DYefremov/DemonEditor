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
ENIGMA2_FAV_ID_FORMAT = " {}:0:{}:{:X}:{:X}:{:X}:{:X}:0:0:0:{}:{}\n#DESCRIPTION: {}\n"
MARKER_FORMAT = " 1:64:{}:0:0:0:0:0:0:0::{}\n#DESCRIPTION {}\n"


class StreamType(Enum):
    DVB_TS = "1"
    NONE_TS = "4097"
    NONE_REC_1 = "5001"
    NONE_REC_2 = "5002"
    E_SERVICE_URI = "8193"
    E_SERVICE_HLS = "8739"


def parse_m3u(path, s_type, detect_encoding=True, params=None):
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
        services = []
        groups = set()
        marker_counter = 1
        sid_counter = 1
        name = None
        picon = None
        p_id = "1_0_1_0_0_0_0_0_0_0.png"
        st = BqServiceType.IPTV.name
        params = params or [0, 0, 0, 0]

        for line in str(data, encoding=encoding, errors="ignore").splitlines():
            if line.startswith("#EXTINF"):
                inf, sep, line = line.partition(" ")
                if not line:
                    line = inf
                line, sep, name = line.rpartition(",")

                data = re.split('"', line)
                size = len(data)
                if size < 3:
                    continue
                d = {data[i].lower().strip(" ="): data[i + 1] for i in range(0, len(data) - 1, 2)}
                picon = d.get("tvg-logo", None)

                grp_name = d.get("group-title", None)
                if grp_name not in groups:
                    groups.add(grp_name)
                    fav_id = MARKER_FORMAT.format(marker_counter, grp_name, grp_name)
                    marker_counter += 1
                    mr = Service(None, None, None, grp_name, *aggr[0:3], BqServiceType.MARKER.name, *aggr, fav_id, None)
                    services.append(mr)
            elif line.startswith("#EXTGRP") and s_type is SettingsType.ENIGMA_2:
                grp_name = line.strip("#EXTGRP:").strip()
                if grp_name not in groups:
                    groups.add(grp_name)
                    fav_id = MARKER_FORMAT.format(marker_counter, grp_name, grp_name)
                    marker_counter += 1
                    mr = Service(None, None, None, grp_name, *aggr[0:3], BqServiceType.MARKER.name, *aggr, fav_id, None)
                    services.append(mr)
            elif not line.startswith("#"):
                url = line.strip()
                params[0] = sid_counter
                sid_counter += 1
                fav_id = get_fav_id(url, name, s_type, params)
                if all((name, url, fav_id)):
                    srv = Service(None, None, IPTV_ICON, name, *aggr[0:3], st, picon, p_id, *s_aggr, url, fav_id, None)
                    services.append(srv)
                else:
                    log("*.m3u* parse error ['{}']: name[{}], url[{}], fav id[{}]".format(path, name, url, fav_id))

    return services


def export_to_m3u(path, bouquet, s_type):
    pattern = re.compile(".*:(http.*):.*") if s_type is SettingsType.ENIGMA_2 else re.compile("(http.*?)::::.*")
    lines = ["#EXTM3U\n"]
    current_grp = None

    for s in bouquet.services:
        s_type = s.type
        if s_type is BqServiceType.IPTV:
            res = re.match(pattern, s.data)
            if not res:
                continue
            data = res.group(1)
            lines.append("#EXTINF:-1,{}\n".format(s.name))
            if current_grp:
                lines.append(current_grp)
            lines.append("{}\n".format(unquote(data.strip())))
        elif s_type is BqServiceType.MARKER:
            current_grp = "#EXTGRP:{}\n".format(s.name)

    with open(path + "{}.m3u".format(bouquet.name), "w", encoding="utf-8") as file:
        file.writelines(lines)


def get_fav_id(url, service_name, settings_type, params=None, stream_type=None, s_type=1):
    """ Returns fav id depending on the profile. """
    if settings_type is SettingsType.ENIGMA_2:
        stream_type = stream_type or StreamType.NONE_TS.value
        params = params or (0, 0, 0, 0)
        return ENIGMA2_FAV_ID_FORMAT.format(stream_type, s_type, *params, quote(url), service_name, service_name, None)
    elif settings_type is SettingsType.NEUTRINO_MP:
        return NEUTRINO_FAV_ID_FORMAT.format(url, "", 0, None, None, None, None, "", "", 1)


if __name__ == "__main__":
    pass

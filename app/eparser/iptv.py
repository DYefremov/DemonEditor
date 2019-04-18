""" Module for IPTV and streams support """
import re
import urllib.request
from enum import Enum

from app.properties import Profile
from app.ui.uicommons import IPTV_ICON
from .ecommons import BqServiceType, Service

# url, description, urlkey, account, usrname, psw, s_type, iconsrc, iconsrc_b, group
NEUTRINO_FAV_ID_FORMAT = "{}::{}::{}::{}::{}::{}::{}::{}::{}::{}"
ENIGMA2_FAV_ID_FORMAT = " {}:0:{}:{:X}:{:X}:{:X}:{:X}:0:0:0:{}:{}\n#DESCRIPTION: {}\n"
MARKER_FORMAT = " 1:64:{}:0:0:0:0:0:0:0::{}\n#DESCRIPTION {}\n"


class StreamType(Enum):
    DVB_TS = "1"
    NONE_TS = "4097"
    NONE_REC_1 = "5001"
    NONE_REC_2 = "5002"


def parse_m3u(path, profile):
    with open(path) as file:
        aggr = [None] * 10
        services = []
        groups = set()
        counter = 0
        name = None
        fav_id = None
        for line in file.readlines():
            if line.startswith("#EXTINF"):
                name = line[1 + line.index(","):].strip()
            elif line.startswith("#EXTGRP") and profile is Profile.ENIGMA_2:
                grp_name = line.strip("#EXTGRP:").strip()
                if grp_name not in groups:
                    groups.add(grp_name)
                    fav_id = MARKER_FORMAT.format(counter, grp_name, grp_name)
                    counter += 1
                    mr = Service(None, None, None, grp_name, *aggr[0:3], BqServiceType.MARKER.name, *aggr, fav_id, None)
                    services.append(mr)
            elif not line.startswith("#"):
                url = line.strip()
                if profile is Profile.ENIGMA_2:
                    url = urllib.request.quote(line.strip())
                    stream_type = StreamType.NONE_TS.value
                    fav_id = ENIGMA2_FAV_ID_FORMAT.format(stream_type, 1, 0, 0, 0, 0, url, name, name, None)
                elif profile is Profile.NEUTRINO_MP:
                    fav_id = NEUTRINO_FAV_ID_FORMAT.format(url, "", 0, None, None, None, None, "", "", 1)
                if name and url:
                    srv = Service(None, None, IPTV_ICON, name, *aggr[0:3], BqServiceType.IPTV.name, *aggr, fav_id, None)
                    services.append(srv)

    return services


def export_to_m3u(path, bouquet):
    pattern = re.compile(".*:(http.*):.*")
    lines = ["#EXTM3U\n"]

    for s in bouquet.services:
        bq_type = s.type
        if bq_type is BqServiceType.IPTV:
            res = re.match(pattern, s.data)
            if not res:
                continue
            data = res.group(1)
            lines.append("#EXTINF:-1,{}\n{}\n".format(s.name, urllib.request.unquote(data.strip())))
        elif bq_type is BqServiceType.MARKER:
            pass

    with open(path + "{}.m3u".format(bouquet.name), "w", encoding="utf-8") as file:
        file.writelines(lines)


if __name__ == "__main__":
    pass

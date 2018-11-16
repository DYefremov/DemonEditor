""" Module for IPTV and streams support """
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
                if profile is Profile.ENIGMA_2:
                    fav_id = ENIGMA2_FAV_ID_FORMAT.format(StreamType.NONE_TS.value, 1, 0, 0, 0, 0,
                                                          line.strip().replace(":", "%3a"), name, name, None)
                elif profile is Profile.NEUTRINO_MP:
                    fav_id = NEUTRINO_FAV_ID_FORMAT.format(line.strip(), "", 0, None, None, None, None, "", "", 1)
                srv = Service(None, None, IPTV_ICON, name, *aggr[0:3], BqServiceType.IPTV.name, *aggr, fav_id, None)
                services.append(srv)

    return services


if __name__ == "__main__":
    pass

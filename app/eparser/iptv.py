""" Module for m3u import """
from app.properties import Profile
from app.ui import IPTV_ICON
from .ecommons import BqServiceType, Service

# url, description, urlkey, account, usrname, psw, s_type, iconsrc, iconsrc_b, group
NEUTRINO_FAV_ID_FORMAT = "{}::{}::{}::{}::{}::{}::{}::{}::{}::{}"
ENIGMA2_FAV_ID_FORMAT = " 1:0:1:0:0:0:0:0:0:0:{}:{}\n#DESCRIPTION: {}\n"


def parse_m3u(path, profile):
    with open(path) as file:
        aggr = [None] * 10
        channels = []
        count = 0
        name = None
        fav_id = None
        for line in file.readlines():
            if line.startswith("#EXTINF"):
                name = line[1 + line.index(","):].strip()
                count += 1
            elif count == 1:
                count = 0
                if profile is Profile.ENIGMA_2:
                    fav_id = ENIGMA2_FAV_ID_FORMAT.format(line.strip().replace(":", "%3a"), name, name, None)
                elif profile is Profile.NEUTRINO_MP:
                    fav_id = NEUTRINO_FAV_ID_FORMAT.format(line.strip(), "", 0, None, None, None, None, "", "", 1)
                srv = Service(None, None, IPTV_ICON, name, *aggr[0:3], BqServiceType.IPTV.name, *aggr, fav_id, None)
                channels.append(srv)

    return channels


if __name__ == "__main__":
    pass

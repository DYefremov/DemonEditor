""" Module for working with Enigma2 bouquets. """
import re
from collections import Counter

from app.commons import log
from app.eparser.ecommons import BqServiceType, BouquetService, Bouquets, Bouquet, BqType

_TV_ROOT_FILE_NAME = "bouquets.tv"
_RADIO_ROOT_FILE_NAME = "bouquets.radio"
_DEFAULT_BOUQUET_NAME = "favourites"


def get_bouquets(path):
    return parse_bouquets(path, "bouquets.tv", BqType.TV.value), parse_bouquets(path, "bouquets.radio",
                                                                                BqType.RADIO.value)


def write_bouquets(path, bouquets, force_bq_names=False):
    """ Creating and writing bouquets files.

        If "force_bq_names" then naming the files using the name of the bouquet.
        Some images may have problems displaying the favorites list!
     """
    srv_line = '#SERVICE 1:7:{}:0:0:0:0:0:0:0:FROM BOUQUET "userbouquet.{}.{}" ORDER BY bouquet\n'
    line = []
    pattern = re.compile("[^\\w_()]+")
    m_index = [0]
    s_index = [0]

    for bqs in bouquets:
        line.clear()
        line.append("#NAME {}\n".format(bqs.name))

        for index, bq in enumerate(bqs.bouquets):
            bq_name = bq.name
            if bq_name == "Favourites (TV)" or bq_name == "Favourites (Radio)":
                bq_name = _DEFAULT_BOUQUET_NAME
            else:
                bq_name = re.sub(pattern, "_", bq.name) if force_bq_names else "de{0:02d}".format(index)
            line.append(srv_line.format(2 if bq.type == BqType.RADIO.value else 1, bq_name, bq.type))
            write_bouquet(path + "userbouquet.{}.{}".format(bq_name, bq.type), bq.name, bq.services, m_index, s_index)

        with open(path + "bouquets.{}".format(bqs.type), "w", encoding="utf-8") as file:
            file.writelines(line)


def write_bouquet(path, name, services, current_marker, current_space):
    bouquet = ["#NAME {}\n".format(name)]
    marker = "#SERVICE 1:64:{:X}:0:0:0:0:0:0:0::{}\n"
    space = "#SERVICE 1:832:D:{}:0:0:0:0:0:0:\n"

    for srv in services:
        s_type = srv.service_type

        if s_type == BqServiceType.IPTV.name:
            bouquet.append("#SERVICE {}\n".format(srv.fav_id.strip()))
        elif s_type == BqServiceType.MARKER.name:
            m_data = srv.fav_id.strip().split(":")
            m_data[2] = current_marker[0]
            current_marker[0] += 1
            bouquet.append(marker.format(m_data[2], m_data[-1]))
        elif s_type == BqServiceType.SPACE.name:
            bouquet.append(space.format(current_space[0]))
            current_space[0] += 1
        else:
            data = to_bouquet_id(srv)
            if srv.service:
                bouquet.append("#SERVICE {}:{}\n#DESCRIPTION {}\n".format(data, srv.service, srv.service))
            else:
                bouquet.append("#SERVICE {}\n".format(data))

    with open(path, "w", encoding="utf-8") as file:
        file.writelines(bouquet)


def to_bouquet_id(srv):
    """ Creates bouquet channel id. """
    data_type = srv.data_id
    if data_type and len(data_type) > 4:
        data_type = int(srv.data_id.split(":")[4])

        return "{}:0:{:X}:{}:0:0:0:".format(1, data_type, srv.fav_id)


def get_bouquet(path, bq_name, bq_type):
    """ Parsing services ids from bouquet file. """
    with open(path + "userbouquet.{}.{}".format(bq_name, bq_type), encoding="utf-8", errors="replace") as file:
        chs_list = file.read()
        services = []
        srvs = list(filter(None, chs_list.split("\n#SERVICE")))  # filtering ['']
        # May come across empty[wrong] files!
        if not srvs:
            log("Bouquet file 'userbouquet.{}.{}' is empty or wrong!".format(bq_name, bq_type))
            return "{} [empty]".format(bq_name), services

        bq_name = srvs.pop(0)
        stream_types = {"4097", "5001", "5002", "8193"}

        for num, srv in enumerate(srvs, start=1):
            srv_data = srv.strip().split(":")
            if srv_data[1] == "64":
                m_data, sep, desc = srv.partition("#DESCRIPTION")
                services.append(BouquetService(desc.strip() if desc else "", BqServiceType.MARKER, srv, num))
            elif srv_data[1] == "832":
                m_data, sep, desc = srv.partition("#DESCRIPTION")
                services.append(BouquetService(desc.strip() if desc else "", BqServiceType.SPACE, srv, num))
            elif srv_data[0].strip() in stream_types or srv_data[10].startswith(("http", "rtsp")):
                stream_data, sep, desc = srv.partition("#DESCRIPTION")
                desc = desc.lstrip(":").strip() if desc else srv_data[-1].strip()
                services.append(BouquetService(desc, BqServiceType.IPTV, srv, num))
            else:
                fav_id = "{}:{}:{}:{}".format(srv_data[3], srv_data[4], srv_data[5], srv_data[6])
                name = None
                if len(srv_data) == 12:
                    name, sep, desc = str(srv_data[-1]).partition("\n#DESCRIPTION")
                services.append(BouquetService(name, BqServiceType.DEFAULT, fav_id.upper(), num))

    return bq_name.lstrip("#NAME").strip(), services


def parse_bouquets(path, bq_name, bq_type):
    with open(path + bq_name, encoding="utf-8", errors="replace") as file:
        lines = file.readlines()
        bouquets = None
        nm_sep = "#NAME"
        bq_pattern = re.compile(".*userbouquet\\.+(.*)\\.+[tv|radio].*")
        b_names = set()
        real_b_names = Counter()

        for line in lines:
            if nm_sep in line:
                _, _, name = line.partition(nm_sep)
                bouquets = Bouquets(name.strip(), bq_type, [])
            if bouquets and "#SERVICE" in line:
                name = re.match(bq_pattern, line)
                if name:
                    b_name = name.group(1)
                    if b_name in b_names:
                        log("The list of bouquets contains duplicate [{}] names!".format(b_name))
                    else:
                        b_names.add(b_name)

                    rb_name, services = get_bouquet(path, b_name, bq_type)
                    if rb_name in real_b_names:
                        log("Bouquet file 'userbouquet.{}.{}' has duplicate name: {}".format(b_name, bq_type, rb_name))
                        real_b_names[rb_name] += 1
                        rb_name = "{} {}".format(rb_name, real_b_names[rb_name])
                    else:
                        real_b_names[rb_name] = 0

                    bouquets[2].append(Bouquet(name=rb_name,
                                               type=bq_type,
                                               services=services,
                                               locked=None,
                                               hidden=None))
                else:
                    raise ValueError("No bouquet name found for: {}".format(line))

    return bouquets


if __name__ == "__main__":
    pass

""" Module for parsing bouquets """
import re

from app.eparser.ecommons import BqServiceType, BouquetService, Bouquets, Bouquet, BqType

_TV_ROOT_FILE_NAME = "bouquets.tv"
_RADIO_ROOT_FILE_NAME = "bouquets.radio"
_DEFAULT_BOUQUET_NAME = "favourites"


def get_bouquets(path):
    return parse_bouquets(path, "bouquets.tv", BqType.TV.value), parse_bouquets(path, "bouquets.radio",
                                                                                BqType.RADIO.value)


def write_bouquets(path, bouquets):
    srv_line = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "userbouquet.{}.{}" ORDER BY bouquet\n'
    line = []
    pattern = re.compile("[^\w_()]+")

    for bqs in bouquets:
        line.clear()
        line.append("#NAME {}\n".format(bqs.name))

        for bq in bqs.bouquets:
            bq_name = bq.name
            if bq_name == "Favourites (TV)" or bq_name == "Favourites (Radio)":
                bq_name = _DEFAULT_BOUQUET_NAME
            else:
                bq_name = re.sub(pattern, "_", bq.name)
            line.append(srv_line.format(bq_name, bq.type))
            write_bouquet(path + "userbouquet.{}.{}".format(bq_name, bq.type), bq.name, bq.services)

        with open(path + "bouquets.{}".format(bqs.type), "w", encoding="utf-8") as file:
            file.writelines(line)


def write_bouquet(path, name, channels):
    bouquet = ["#NAME {}\n".format(name)]

    for ch in channels:
        if ch.service_type == BqServiceType.IPTV.name or ch.service_type == BqServiceType.MARKER.name:
            bouquet.append("#SERVICE {}\n".format(ch.fav_id.strip()))
        else:
            data = to_bouquet_id(ch)
            if ch.service:
                bouquet.append("#SERVICE {}:{}\n#DESCRIPTION {}\n".format(data, ch.service, ch.service))
            else:
                bouquet.append("#SERVICE {}\n".format(data))

    with open(path, "w", encoding="utf-8") as file:
        file.writelines(bouquet)


def to_bouquet_id(ch):
    """ Creates bouquet channel id """
    data_type = ch.data_id
    if data_type and len(data_type) > 4:
        data_type = int(ch.data_id.split(":")[4])

        return "{}:0:{:X}:{}:0:0:0:".format(1, data_type, ch.fav_id)


def get_bouquet(path, name, bq_type):
    """ Parsing services ids from bouquet file """
    with open(path + "userbouquet.{}.{}".format(name, bq_type), encoding="utf-8", errors="replace") as file:
        chs_list = file.read()
        services = []
        srvs = list(filter(None, chs_list.split("\n#SERVICE")))  # filtering ['']
        for ch in srvs[1:]:
            ch_data = ch.strip().split(":")
            if ch_data[1] == "64":
                marker_data = ch.split("#DESCRIPTION", 1)
                services.append(BouquetService(marker_data[1].strip(), BqServiceType.MARKER, ch, ch_data[2]))
            elif "http" in ch:
                stream_data = ch.split("#DESCRIPTION", 1)
                services.append(BouquetService(stream_data[-1].strip(":").strip(), BqServiceType.IPTV, ch, 0))
            else:
                fav_id = "{}:{}:{}:{}".format(ch_data[3], ch_data[4], ch_data[5], ch_data[6])
                name = None
                if len(ch_data) == 12:
                    name, desc = str(ch_data[-1]).split("\n#DESCRIPTION")
                services.append(BouquetService(name, BqServiceType.DEFAULT, fav_id.upper(), 0))

    return srvs[0].lstrip("#NAME").strip(), services


def parse_bouquets(path, bq_name, bq_type):
    with open(path + bq_name, encoding="utf-8", errors="replace") as file:
        lines = file.readlines()
        bouquets = None
        nm_sep = "#NAME"
        bq_pattern = re.compile(".*\"userbouquet\\.+(.*)\\.+[tv|radio].*")

        for line in lines:
            if nm_sep in line:
                _, _, name = line.partition(nm_sep)
                bouquets = Bouquets(name.strip(), bq_type, [])
            if bouquets and "#SERVICE" in line:
                name = re.match(bq_pattern, line)
                if name:
                    b_name, services = get_bouquet(path,  name.group(1), bq_type)
                    bouquets[2].append(Bouquet(name=b_name,
                                               type=bq_type,
                                               services=services,
                                               locked=None,
                                               hidden=None))
                else:
                    msg = "No bouquet name found for: {}".format(line)
                    print("No bouquet name found for: {}".format(line))
                    raise ValueError(msg)

    return bouquets


if __name__ == "__main__":
    pass

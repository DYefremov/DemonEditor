""" Module for parsing bouquets """
from app.eparser.ecommons import BqServiceType, BouquetService, Bouquets, Bouquet

_TV_ROOT_FILE_NAME = "bouquets.tv"
_RADIO_ROOT_FILE_NAME = "bouquets.radio"


def get_bouquets(path):
    return parse_bouquets(path, "bouquets.tv", "tv"), parse_bouquets(path, "bouquets.radio", "radio")


def write_bouquets(path, bouquets):
    srv_line = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "userbouquet.{}.{}" ORDER BY bouquet\n'
    line = []

    for bqs in bouquets:
        line.clear()
        line.append("#NAME {}\n".format(bqs.name))

        for bq in bqs.bouquets:
            line.append(srv_line.format(bq.name.replace(" ", "_"), bq.type))
            write_bouquet(path, bq.name, bq.type, bq.services)

        with open(path + "bouquets.{}".format(bqs.type), "w") as file:
            file.writelines(line)


def write_bouquet(path, name, bq_type, channels):
    bouquet = ["#NAME {}\n".format(name)]

    for ch in channels:
        if not ch:  # if was duplicate
            continue

        if ch.service_type == BqServiceType.IPTV.name or ch.service_type == BqServiceType.MARKER.name:
            bouquet.append("#SERVICE {}\n".format(ch.fav_id.strip()))
        else:
            bouquet.append("#SERVICE {}\n".format(to_bouquet_id(ch)))

    with open(path + "userbouquet.{}.{}".format(name.replace(" ", "_"), bq_type), "w") as file:
        file.writelines(bouquet)


def to_bouquet_id(ch):
    """ Creates bouquet channel id """
    data_type = ch.data_id

    if data_type and len(data_type) > 2:
        data_type = int(ch.data_id.split(":")[-2])
        if data_type == 22:
            data_type = 16
        elif data_type == 25:
            data_type = 19
        return "{}:0:{}:{}:0:0:0:".format(1, data_type, ch.fav_id)


def get_bouquet(path, name, bq_type):
    """ Parsing services ids from bouquet file """
    with open(path + "userbouquet.{}.{}".format(name, bq_type)) as file:
        chs_list = file.read()
        services = []
        srvs = list(filter(None, chs_list.split("\n#SERVICE")))  # filtering ['']
        for ch in srvs[1:]:
            ch_data = ch.strip().split(":")
            if ch_data[1] == "64":
                services.append(BouquetService(ch_data[-1].split("\n")[0], BqServiceType.MARKER, ch, ch_data[2]))
            elif "http" in ch:
                services.append(BouquetService(ch_data[-1].split("\n")[0], BqServiceType.IPTV, ch, 0))
            else:
                fav_id = "{}:{}:{}:{}".format(ch_data[3], ch_data[4], ch_data[5], ch_data[6])
                services.append(BouquetService(None, BqServiceType.DEFAULT, fav_id, 0))
    return srvs[0].strip("#NAME").strip(), services


def parse_bouquets(path, bq_name, bq_type):
    with open(path + bq_name) as file:
        lines = file.readlines()
        bouquets = None
        nm_sep = "#NAME"

        for line in lines:
            if nm_sep in line:
                _, _, name = line.partition(nm_sep)
                bouquets = Bouquets(name.strip(), bq_type, [])
            if bouquets and "#SERVICE" in line:
                b_name, services = get_bouquet(path, line.split(".")[1], bq_type)
                bouquets[2].append(Bouquet(name=b_name,
                                           type=bq_type,
                                           services=services,
                                           locked=None,
                                           hidden=None))
    return bouquets


if __name__ == "__main__":
    pass

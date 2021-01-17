""" Module for working with Enigma2 bouquets. """
import re
from collections import Counter
from pathlib import Path

from app.commons import log
from app.eparser.ecommons import BqServiceType, BouquetService, Bouquets, Bouquet, BqType

_TV_FILE = "bouquets.tv"
_RADIO_FILE = "bouquets.radio"
_DEFAULT_BOUQUET_NAME = "favourites"


class BouquetsWriter:
    """ Class for creating and writing bouquet files..

        If "force_bq_names" then naming the files using the name of the bouquet.
        Some images may have problems displaying the favorites list!
     """
    _SERVICE = '#SERVICE 1:7:{}:0:0:0:0:0:0:0:FROM BOUQUET "userbouquet.{}.{}" ORDER BY bouquet\n'
    _MARKER = "#SERVICE 1:64:{:X}:0:0:0:0:0:0:0::{}\n"
    _SPACE = "#SERVICE 1:832:D:{}:0:0:0:0:0:0:\n"
    _ALT = '#SERVICE 1:134:1:0:0:0:0:0:0:0:FROM BOUQUET "{}" ORDER BY bouquet\n'
    _ALT_PAT = r"[<>:\"/\\|?*\-\s]"

    def __init__(self, path, bouquets, force_bq_names=False):
        self._path = path
        self._bouquets = bouquets
        self._force_bq_names = force_bq_names
        self._marker_index = 1
        self._space_index = 0
        self._alt_index = 0

    def write(self):
        line = []
        pattern = re.compile("[^\\w_()]+")

        for bqs in self._bouquets:
            line.clear()
            line.append("#NAME {}\n".format(bqs.name))

            for index, bq in enumerate(bqs.bouquets):
                bq_name = _DEFAULT_BOUQUET_NAME
                if index > 0:
                    bq_name = re.sub(pattern, "_", bq.name) if self._force_bq_names else "de{0:02d}".format(index)
                line.append(self._SERVICE.format(2 if bq.type == BqType.RADIO.value else 1, bq_name, bq.type))
                self.write_bouquet(self._path + "userbouquet.{}.{}".format(bq_name, bq.type), bq.name, bq.services)

            with open(self._path + "bouquets.{}".format(bqs.type), "w", encoding="utf-8") as file:
                file.writelines(line)

    def write_bouquet(self, path, name, services):
        """ Writes single bouquet file. """
        bouquet = ["#NAME {}\n".format(name)]
        for srv in services:
            s_type = srv.service_type
            if s_type == BqServiceType.IPTV.name:
                bouquet.append("#SERVICE {}\n".format(srv.fav_id.strip()))
            elif s_type == BqServiceType.MARKER.name:
                m_data = srv.fav_id.strip().split(":")
                m_data[2] = self._marker_index
                self._marker_index += 1
                bouquet.append(self._MARKER.format(m_data[2], m_data[-1]))
            elif s_type == BqServiceType.SPACE.name:
                bouquet.append(self._SPACE.format(self._space_index))
                self._space_index += 1
            elif s_type == BqServiceType.ALT.name:
                services = srv.transponder
                if services:
                    p = Path(path)
                    if self._force_bq_names:
                        alt_name = re.sub(self._ALT_PAT, "_", srv.service).lower()
                        f_name = "alternatives.{}{}".format(alt_name, p.suffix)
                    else:
                        f_name = "alternatives.de{:02d}{}".format(self._alt_index, p.suffix)
                        self._alt_index += 1
                    alt_path = "{}/{}".format(p.parent, f_name)
                    bouquet.append(self._ALT.format(f_name))
                    self.write_bouquet(alt_path, srv.service, services)
            else:
                data = to_bouquet_id(srv)
                if srv.service:
                    bouquet.append("#SERVICE {}:{}\n#DESCRIPTION {}\n".format(data, srv.service, srv.service))
                else:
                    bouquet.append("#SERVICE {}\n".format(data))

        with open(path, "w", encoding="utf-8") as file:
            file.writelines(bouquet)


class BouquetsReader:
    """ Class for reading and parsing bouquets. """
    _ALT_PAT = re.compile(".*alternatives\\.+(.*)\\.([tv|radio]+).*")
    _BQ_PAT = re.compile(".*userbouquet\\.+(.*)\\.+[tv|radio].*")
    _STREAM_TYPES = {"4097", "5001", "5002", "8193", "8739"}

    __slots__ = ["_path"]

    def __init__(self, path):
        self._path = path

    def get(self):
        """ Returns a tuple of TV and Radio bouquets. """
        return self.parse_bouquets(_TV_FILE, BqType.TV.value), self.parse_bouquets(_RADIO_FILE, BqType.RADIO.value)

    def parse_bouquets(self, bq_name, bq_type):
        with open(self._path + bq_name, encoding="utf-8", errors="replace") as file:
            lines = file.readlines()
            bouquets = None
            nm_sep = "#NAME"
            b_names = set()
            real_b_names = Counter()

            for line in lines:
                if nm_sep in line:
                    _, _, name = line.partition(nm_sep)
                    bouquets = Bouquets(name.strip(), bq_type, [])
                if bouquets and "#SERVICE" in line:
                    name = re.match(self._BQ_PAT, line)
                    if name:
                        b_name = name.group(1)
                        if b_name in b_names:
                            log("The list of bouquets contains duplicate [{}] names!".format(b_name))
                        else:
                            b_names.add(b_name)

                        rb_name, services = self.get_bouquet(self._path, b_name, bq_type)
                        if rb_name in real_b_names:
                            log("Bouquet file 'userbouquet.{}.{}' has duplicate name: {}".format(b_name, bq_type,
                                                                                                 rb_name))
                            real_b_names[rb_name] += 1
                            rb_name = "{} {}".format(rb_name, real_b_names[rb_name])
                        else:
                            real_b_names[rb_name] = 0

                        bouquets[2].append(Bouquet(rb_name, bq_type, services, None, None))
                    else:
                        raise ValueError("No bouquet name found for: {}".format(line))

        return bouquets

    @staticmethod
    def get_bouquet(path, bq_name, bq_type, prefix="userbouquet"):
        """ Parsing services ids from bouquet file. """
        with open(path + "{}.{}.{}".format(prefix, bq_name, bq_type), encoding="utf-8", errors="replace") as file:
            chs_list = file.read()
            services = []
            srvs = list(filter(None, chs_list.split("\n#SERVICE")))  # filtering ['']
            # May come across empty[wrong] files!
            if not srvs:
                log("Bouquet file 'userbouquet.{}.{}' is empty or wrong!".format(bq_name, bq_type))
                return "{} [empty]".format(bq_name), services

            bq_name = srvs.pop(0)

            for num, srv in enumerate(srvs, start=1):
                srv_data = srv.strip().split(":")
                s_type = srv_data[1]
                if s_type == "64":
                    m_data, sep, desc = srv.partition("#DESCRIPTION")
                    services.append(BouquetService(desc.strip() if desc else "", BqServiceType.MARKER, srv, num))
                elif s_type == "832":
                    m_data, sep, desc = srv.partition("#DESCRIPTION")
                    services.append(BouquetService(desc.strip() if desc else "", BqServiceType.SPACE, srv, num))
                elif s_type == "134":
                    alt = re.match(BouquetsReader._ALT_PAT, srv)
                    if alt:
                        alt_name, alt_type = alt.group(1), alt.group(2)
                        alt_bq_name, alt_srvs = BouquetsReader.get_bouquet(path, alt_name, alt_type, "alternatives")
                        services.append(BouquetService(alt_bq_name, BqServiceType.ALT, srv.lstrip(), tuple(alt_srvs)))
                elif srv_data[0].strip() in BouquetsReader._STREAM_TYPES or srv_data[10].startswith(("http", "rtsp")):
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


def to_bouquet_id(srv):
    """ Creates bouquet channel id. """
    data_type = srv.data_id
    if data_type and len(data_type) > 4:
        data_type = int(srv.data_id.split(":")[4])

        return "{}:0:{:X}:{}:0:0:0:".format(1, data_type, srv.fav_id)


if __name__ == "__main__":
    pass

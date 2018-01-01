from xml.dom.minidom import parse, Document

from ..ecommons import Service, POLARIZATION, FEC, SYSTEM

_FILE = "services.xml"


def write_services(path, channels):
    doc = Document()
    # comment = doc.createComment(__COMMENT)
    # doc.appendChild(comment)
    root = doc.createElement("zapit")
    root.setAttribute("api", "4")
    doc.appendChild(root)

    doc.writexml(open(path, "w"),
                 # indent="",
                 addindent="    ",
                 newl="\n",
                 encoding="UTF-8")
    doc.unlink()


def get_services(path):
    return parse_services(path)


def parse_services(path):
    """ Parsing services from xml"""
    dom = parse(path + _FILE)
    services = []

    for elem in dom.getElementsByTagName("sat"):
        sat, sat_pos, sat = None, None, None

        if elem.hasAttributes():
            sat_name = elem.attributes["name"].value
            sat_pos = elem.attributes["position"].value
            sat = "{}:{}:{}:{}".format(sat_name, sat_pos,
                                       elem.attributes["diseqc"].value,
                                       elem.attributes["uncommited"].value)

        for tr_elem in elem.getElementsByTagName("TS"):
            freq, rate, fec, pol, sys, transponder = [None] * 6

            if tr_elem.hasAttributes():
                freq = tr_elem.attributes["frq"].value
                rate = tr_elem.attributes["sr"].value
                fec = tr_elem.attributes["fec"].value
                pol = tr_elem.attributes["pol"].value
                sys = tr_elem.attributes["sys"].value
                transponder = "{}:{}:{}:{}:{}:{}:{}:{}:{}".format(tr_elem.attributes["id"].value,
                                                                  tr_elem.attributes["on"].value,
                                                                  freq,
                                                                  tr_elem.attributes["inv"].value,
                                                                  rate,
                                                                  fec,
                                                                  pol,
                                                                  tr_elem.attributes["mod"].value,
                                                                  sys)
            for srv_elem in tr_elem.getElementsByTagName("S"):
                if srv_elem.hasAttributes():
                    ssid = srv_elem.attributes["i"].value
                    name = srv_elem.attributes["n"].value
                    tr_n = srv_elem.attributes["t"].value
                    data_id = "{}:{}:{}:{}".format(tr_n,
                                                   srv_elem.attributes["s"].value,
                                                   srv_elem.attributes["num"].value,
                                                   srv_elem.attributes["f"].value)
                    # fav_id = "{}:{}".format(tr_n, ssid)
                    srv = Service(flags_cas=sat,
                                  transponder_type=None,
                                  coded=None,
                                  service=name,
                                  locked=None,
                                  hide=None,
                                  package=None,
                                  service_type=None,
                                  ssid=ssid, freq=freq,
                                  rate=rate,
                                  pol=POLARIZATION.get(pol),
                                  fec=FEC.get(fec),
                                  system=SYSTEM.get(sys),
                                  pos="{}.{}".format(sat_pos[:-1], sat_pos[-1:]),
                                  data_id=data_id,
                                  fav_id=name,
                                  transponder=transponder)
                    services.append(srv)

    return services


if __name__ == "__main__":
    pass

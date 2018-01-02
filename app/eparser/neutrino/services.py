from xml.dom.minidom import parse, Document

from ..ecommons import Service, POLARIZATION, FEC, SYSTEM, SERVICE_TYPE, PROVIDER

_FILE = "services.xml"


def write_services(path, services):
    doc = Document()
    root = doc.createElement("zapit")
    root.setAttribute("api", "4")
    doc.appendChild(root)
    comment = doc.createComment(" File was created in DemonEditor. Enjoy watching! ")
    doc.appendChild(comment)

    sats = {}
    for srv in services:
        flag = srv[0]
        if flag in sats:
            sats.get(flag).append(srv)
        else:
            srv_list = [srv]
            sats[flag] = srv_list

    for sat in sats:
        tr_atr = sat.split(":")
        sat_elem = doc.createElement("sat")
        sat_elem.setAttribute("name", tr_atr[0])
        sat_elem.setAttribute("position", tr_atr[1])
        sat_elem.setAttribute("diseqc", tr_atr[2])
        sat_elem.setAttribute("uncommited", tr_atr[3])
        root.appendChild(sat_elem)

        transponers = {}
        for srv in sats.get(sat):
            flag = srv[-1]
            if flag in transponers:
                transponers.get(flag).append(srv)
            else:
                srv_list = [srv]
                transponers[flag] = srv_list

        tr_atr_names = ("id", "on", "frq", "inv", "sr", "fec", "pol", "mod", "sys")  # transponder attributes
        for tr in transponers:
            tr_elem = doc.createElement("TS")
            tr_atr = tr.split(":")
            for i, value in enumerate(tr_atr):
                tr_elem.setAttribute(tr_atr_names[i], value)
            sat_elem.appendChild(tr_elem)

            sr_atr_names = ("t", "s", "num", "f")
            for srv in transponers.get(tr):
                srv_elem = doc.createElement("S")
                srv_elem.setAttribute("i", srv[8])
                srv_elem.setAttribute("n", srv[3])
                srv_atr = srv[15].split(":")
                for i, value in enumerate(srv_atr):
                    srv_elem.setAttribute(sr_atr_names[i], value)
                tr_elem.appendChild(srv_elem)

    doc.writexml(open(path + "_" + _FILE, "w"), addindent="    ", newl="\n", encoding="UTF-8")
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
            if tr_elem.hasAttributes():
                tr_id = tr_elem.attributes["id"].value
                on = tr_elem.attributes["on"].value
                freq = tr_elem.attributes["frq"].value
                rate = tr_elem.attributes["sr"].value
                fec = tr_elem.attributes["fec"].value
                pol = tr_elem.attributes["pol"].value
                sys = tr_elem.attributes["sys"].value
                transponder = "{}:{}:{}:{}:{}:{}:{}:{}:{}".format(tr_id, on, freq, tr_elem.attributes["inv"].value,
                                                                  rate, fec, pol, tr_elem.attributes["mod"].value, sys)
                for srv_elem in tr_elem.getElementsByTagName("S"):
                    if srv_elem.hasAttributes():
                        ssid = srv_elem.attributes["i"].value
                        name = srv_elem.attributes["n"].value
                        srv_type = srv_elem.attributes["t"].value
                        data_id = "{}:{}:{}:{}".format(srv_type,
                                                       srv_elem.attributes["s"].value,
                                                       srv_elem.attributes["num"].value,
                                                       srv_elem.attributes["f"].value)
                        fav_id = "{}:{}".format(on.lstrip("0"), ssid.lstrip("0"))

                        srv = Service(flags_cas=sat,
                                      transponder_type=None,
                                      coded=None,
                                      service=name,
                                      locked=None,
                                      hide=None,
                                      package=PROVIDER.get(int(on, 16)),
                                      service_type=SERVICE_TYPE.get(str(int(srv_type, 16))),
                                      ssid=ssid,
                                      freq=freq,
                                      rate=rate,
                                      pol=POLARIZATION.get(pol),
                                      fec=FEC.get(fec),
                                      system=SYSTEM.get(sys),
                                      pos="{}.{}".format(sat_pos[:-1], sat_pos[-1:]),
                                      data_id=data_id,
                                      fav_id=fav_id,
                                      transponder=transponder)
                        services.append(srv)

    return services


if __name__ == "__main__":
    pass

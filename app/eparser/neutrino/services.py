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

    for root in dom.getElementsByTagName("zapit"):
        api = root.attributes["api"].value

        for elem in root.getElementsByTagName("sat"):
            if elem.hasAttributes():
                sat_name = elem.attributes["name"].value
                sat_pos = elem.attributes["position"].value
                sat_pos = "{}.{}".format(sat_pos[:-1], sat_pos[-1:])
                sat = "{}:{}:{}:{}".format(sat_name, sat_pos,
                                           elem.attributes["diseqc"].value,
                                           elem.attributes["uncommited"].value)

                for tr_elem in elem.getElementsByTagName("TS"):
                    if tr_elem.hasAttributes():
                        parse_transponder(api, sat, sat_pos, services, tr_elem)

        return services


def parse_transponder(api, sat, sat_pos, services, tr_elem):
    tr_id = tr_elem.attributes["id"].value
    on = tr_elem.attributes["on"].value
    freq = tr_elem.attributes["frq"].value
    rate = tr_elem.attributes["sr"].value
    inv = tr_elem.attributes["inv"].value
    fec = tr_elem.attributes["fec"].value
    pol = tr_elem.attributes["pol"].value
    mod = tr_elem.attributes.get("mod")
    mod = mod.value if mod else mod
    sys = tr_elem.attributes.get("sys")
    sys = sys.value if sys else sys

    tr = "{}:{}:{}:{}:{}:{}:{}:{}:{}".format(tr_id, on, freq, inv, rate, fec, pol, mod, sys)

    for srv_elem in tr_elem.getElementsByTagName("S"):
        if srv_elem.hasAttributes():
            ssid = srv_elem.attributes["i"].value
            name = srv_elem.attributes["n"].value
            srv_type = srv_elem.attributes["t"].value
            sys = srv_elem.attributes["s"].value
            num = srv_elem.attributes["num"].value
            f = srv_elem.attributes["f"].value
            v, a, p, pmt, tx, vt = [None] * 6

            # For v3 is possible so: '<S i="0001" n="name" t="1" s="0" num="770" f="4"/>' (equals v4 api)
            if api == "3" and len(srv_elem.attributes) > 6:
                v = srv_elem.attributes["v"].value
                a = srv_elem.attributes["a"].value
                p = srv_elem.attributes["p"].value
                pmt = srv_elem.attributes["pmt"].value
                tx = srv_elem.attributes["tx"].value
                vt = srv_elem.attributes["vt"].value

            data_id = "{}:{}:{}:{}:{}:{}:{}:{}:{}:{}:{}".format(api, srv_type, sys, num, f, v, a, p, pmt, tx, vt)
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
                          pos=sat_pos,
                          data_id=data_id,
                          fav_id=fav_id,
                          transponder=tr)
            services.append(srv)


if __name__ == "__main__":
    pass

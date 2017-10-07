from xml.dom.minidom import parse

XML_PATH = "files/satellites.xml"


class Satellite:
    __slots__ = ["_name", "_flags", "_position", "_transponders"]

    def __init__(self, name, flags=None, position=None, transponders=None):
        self._name = name
        self._flags = flags
        self._position = position
        self._transponders = transponders

    def __repr__(self):
        return str([self._name, self._flags, self._position, self._transponders])


dom = parse(XML_PATH)

satellites = []

for elem in dom.getElementsByTagName("sat"):
    if elem.hasAttributes():
        # print(elem.attributes.keys())
        # print(elem.attributes.values())

        sat = Satellite(elem.attributes["name"].value, elem.attributes["flags"].value, elem.attributes["position"].value)
        satellites.append(sat)
        # for key in elem.attributes.keys():
        # satellites.append(Sat())
        # atr = elem.attributes[key]
        # print(atr.name, atr.value)

for sat in satellites:
    print(sat)


if __name__ == "__main__":
    pass

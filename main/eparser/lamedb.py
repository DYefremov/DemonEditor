from collections import namedtuple

Channel = namedtuple("Channel", ["service", "package", "freq", "fec"])

FILE_PATH = "../data/lamedb_example"


def parse(path):
    with open(path, "r") as file:
        data = str(file.read())
    services, sep, transponders = data.partition("services")  # 1 step
    transponders, sep, services = transponders.partition("transponders")  # 2 step
    transponders, sep, services = services.partition("end")  # 3 step
    services = services.split("\n")

    while len(services) % 3 == 0:
        services.append("\n")

    srv = []
    tmp = []
    for i, line in enumerate(services):
        tmp.append(line)
        if i % 3 == 0:
            srv.append(tuple(tmp))
            tmp.clear()

    if srv[0][0] == "":  # remove first empty element
        srv.remove(srv[0])

    if srv[0][0] == "services":  # building one element from first and last if necessary!
        first = srv.pop(0)
        last = srv.pop()
        srv.insert(0, (last[0], first[1], first[2]))

    channels = []
    for ch in srv:
        pack = str(ch[0])
        pack = pack[2:pack.find(",")]
        channels.append(Channel(ch[2], pack, None, None))

    for ch in channels:
        print(ch)


if __name__ == "__main__":
    parse(FILE_PATH)

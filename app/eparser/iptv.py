from .ecommons import BqServiceType, Service


def parse_m3u(path):
    with open(path) as file:
        aggr = [None] * 10
        channels = []
        count = 0
        name = None
        for line in file.readlines():
            if line.startswith("#EXTINF"):
                name = line[1 + line.index(","):].strip()
                count += 1
            elif count == 1:
                count = 0
                fav_id = " 1:0:1:0:0:0:0:0:0:0:{}:{}\n#DESCRIPTION: {}\n".format(
                    line.strip().replace(":", "%3a"), name, name, None)
                srv = Service(*aggr[0:3], name, *aggr[0:3], BqServiceType.IPTV.name, *aggr, fav_id, None)
                print(srv)
                channels.append(srv)

    return channels


if __name__ == "__main__":
    pass

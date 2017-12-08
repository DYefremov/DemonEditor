from . import Channel


def parse_m3u(path):
    with open(path) as file:
        aggr = [None] * 8
        channels = []
        count = 0
        name = None
        for line in file.readlines():
            if line.startswith("#EXTINF"):
                name = line[1 + line.index(","):].strip()
                count += 1
            elif count == 1:
                count = 0
                fav_id = "#SERVICE 4097:0:1:2:0:0:0:0:0:0:{}#DESCRIPTION:{}".format(line, name)
                channels.append(Channel(*aggr[0:3], name, *aggr[0:3], "IPTV", *aggr, fav_id, None))

    return channels


if __name__ == "__main__":
    pass

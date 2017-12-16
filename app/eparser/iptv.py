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
                fav_id = "IPTV:::1:0:1:0:0:0:0:0:0:0:{}:{}\n#DESCRIPTION: {}\n:::{}".format(
                    line.strip().replace(":", "%3a"), name, name, None)
                channels.append(Channel(*aggr[0:3], name, *aggr[0:3], "IPTV", *aggr, fav_id, None))

    return channels


if __name__ == "__main__":
    pass

from .ecommons import Channel, Satellite, Transponder, Bouquet, Bouquets
from .enigma.blacklist import get_blacklist, write_blacklist
from .enigma.bouquets import get_bouquets, write_bouquets, to_bouquet_id
from .enigma.lamedb import get_channels as get_enigma_channels, write_channels as write_enigma_channels
from .iptv import parse_m3u
from .satxml import get_satellites, write_satellites


def get_channels(data_path, profile=None):
    return get_enigma_channels(data_path)


def write_channels(path, channels, profile=None):
    write_enigma_channels(path, channels)


if __name__ == "__main__":
    pass

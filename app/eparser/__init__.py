from app.commons import run_task
from app.properties import Profile
from .ecommons import Service, Satellite, Transponder, Bouquet, Bouquets
from .enigma.blacklist import get_blacklist, write_blacklist
from .enigma.bouquets import get_bouquets as get_enigma_bouquets, write_bouquets as write_enigma_bouquets, to_bouquet_id
from .enigma.lamedb import get_services as get_enigma_services, write_services as write_enigma_services
from .iptv import parse_m3u
from .neutrino.bouquets import get_bouquets as get_neutrino_bouquets, write_bouquets as write_neutrino_bouquets
from .neutrino.services import get_services as get_neutrino_services, write_services as write_neutrino_services
from .satxml import get_satellites, write_satellites


def get_services(data_path, profile):
    if profile is Profile.ENIGMA_2:
        return get_enigma_services(data_path)
    elif profile is Profile.NEUTRINO_MP:
        return get_neutrino_services(data_path)


@run_task
def write_services(path, channels, profile):
    if profile is Profile.ENIGMA_2:
        write_enigma_services(path, channels)
    elif profile is Profile.NEUTRINO_MP:
        write_neutrino_services(path, channels)


def get_bouquets(path, profile):
    if profile is Profile.ENIGMA_2:
        return get_enigma_bouquets(path)
    elif profile is Profile.NEUTRINO_MP:
        return get_neutrino_bouquets(path)


@run_task
def write_bouquets(path, bouquets, profile):
    if profile is Profile.ENIGMA_2:
        write_enigma_bouquets(path, bouquets)
    elif profile is Profile.NEUTRINO_MP:
        write_neutrino_bouquets(path, bouquets)


if __name__ == "__main__":
    pass

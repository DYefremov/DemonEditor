from app.commons import run_task
from app.settings import SettingsType
from .ecommons import Service, Satellite, Transponder, Bouquet, Bouquets, is_transponder_valid
from .enigma.blacklist import get_blacklist, write_blacklist
from .enigma.bouquets import to_bouquet_id, BouquetsWriter, BouquetsReader
from .enigma.lamedb import get_services as get_enigma_services, write_services as write_enigma_services
from .iptv import parse_m3u
from .neutrino.bouquets import get_bouquets as get_neutrino_bouquets, write_bouquets as write_neutrino_bouquets
from .neutrino.services import get_services as get_neutrino_services, write_services as write_neutrino_services
from .satxml import get_satellites, write_satellites


def get_services(data_path, s_type, format_version):
    if s_type is SettingsType.ENIGMA_2:
        return get_enigma_services(data_path, format_version)
    elif s_type is SettingsType.NEUTRINO_MP:
        return get_neutrino_services(data_path)


@run_task
def write_services(path, channels, s_type, format_version):
    if s_type is SettingsType.ENIGMA_2:
        write_enigma_services(path, channels, format_version)
    elif s_type is SettingsType.NEUTRINO_MP:
        write_neutrino_services(path, channels)


def get_bouquets(path, s_type):
    if s_type is SettingsType.ENIGMA_2:
        return BouquetsReader(path).get()
    elif s_type is SettingsType.NEUTRINO_MP:
        return get_neutrino_bouquets(path)


@run_task
def write_bouquets(path, bouquets, s_type, force_bq_names=False):
    if s_type is SettingsType.ENIGMA_2:
        BouquetsWriter(path, bouquets, force_bq_names).write()
    elif s_type is SettingsType.NEUTRINO_MP:
        write_neutrino_bouquets(path, bouquets)


if __name__ == "__main__":
    pass

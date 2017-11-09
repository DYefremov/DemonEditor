from enum import Enum
from ftplib import FTP

import os


__DATA_FILES_LIST = ("tv", "radio", "lamedb")


class DownloadDataType(Enum):
    ALL = 0
    BOUQUETS = 1
    SATELLITES = 2


def download_data(*, properties, download_type=DownloadDataType.ALL):
    with FTP(properties["host"]) as ftp:
        ftp.login(user=properties["user"], passwd=properties["password"])
        save_path = properties["data_dir_path"]
        files = []
        # bouquets section
        if download_type is DownloadDataType.ALL or download_type is DownloadDataType.BOUQUETS:
            ftp.cwd(properties["services_path"])
            ftp.dir(files.append)

            for file in files:
                name = str(file).strip()
                if name.endswith(__DATA_FILES_LIST):
                    name = name.split()[-1]
                    with open(save_path + name, 'wb') as f:
                        ftp.retrbinary('RETR ' + name, f.write)
        # satellites.xml section
        if download_type is DownloadDataType.ALL or download_type is DownloadDataType.SATELLITES:
            ftp.cwd(properties["satellites_xml_path"])
            files.clear()
            ftp.dir(files.append)

            for file in files:
                name = str(file).strip()
                xml_file = "satellites.xml"
                if name.endswith(xml_file):
                    with open(save_path + xml_file, 'wb') as f:
                        ftp.retrbinary('RETR ' + xml_file, f.write)

        return ftp.voidcmd("NOOP")


def upload_data(*, properties, download_type=DownloadDataType.ALL, remove_unused=False):
    load_path = properties["data_dir_path"]

    for file_name in os.listdir(load_path):
        print(file_name)
        # Open the file for transfer in binary mode
        # f = open(file_name, "rb")
        # transfer the file into receiver
        # send = ftp.storbinary("STOR " + file_name, f)

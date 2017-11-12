import os
import socket
import time
from enum import Enum
from ftplib import FTP
from telnetlib import Telnet

__DATA_FILES_LIST = ("tv", "radio", "lamedb")


class DownloadDataType(Enum):
    ALL = 0
    BOUQUETS = 1
    SATELLITES = 2


def download_data(*, properties, download_type=DownloadDataType.ALL):
    with FTP(host=properties["host"]) as ftp:
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
                    with open(save_path + name, "wb") as f:
                        ftp.retrbinary("RETR " + name, f.write)
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
                        ftp.retrbinary("RETR " + xml_file, f.write)


def upload_data(*, properties, download_type=DownloadDataType.ALL, remove_unused=False):
    data_path = properties["data_dir_path"]
    host = properties["host"]
    # telnet
    tn = telnet(host=host)
    next(tn)
    # terminate enigma
    tn.send("init 4")

    with FTP(host=host) as ftp:
        ftp.login(user=properties["user"], passwd=properties["password"])

        if download_type is DownloadDataType.ALL or download_type is DownloadDataType.SATELLITES:
            ftp.cwd(properties["satellites_xml_path"])
            file_name = "satellites.xml"
            send = send_file(file_name, data_path, ftp)
            if download_type == DownloadDataType.SATELLITES:
                return send

        if download_type is DownloadDataType.ALL or download_type is DownloadDataType.BOUQUETS:
            ftp.cwd(properties["services_path"])
            if remove_unused:
                files = []
                ftp.dir(files.append)
                for file in files:
                    name = str(file).strip()
                    if name.endswith(__DATA_FILES_LIST):
                        name = name.split()[-1]
                        ftp.delete(name)

            for file_name in os.listdir(data_path):
                if file_name == "satellites.xml":
                    continue
                file_name, send_file(file_name, data_path, ftp)
        # resume enigma
        tn.send("init 3")


def send_file(file_name, path, ftp):
    """ Opens the file in binary mode and transfers into receiver """
    with open(path + file_name, "rb") as f:
        return ftp.storbinary("STOR " + file_name, f)


def telnet(host, port=23, user="root", password="root", timeout=1):
    try:
        tn = Telnet(host=host, port=port, timeout=timeout)
    except socket.timeout:
        print("socket timeout")
    else:
        time.sleep(timeout)
        command = yield
        tn.write("{}\r\n".format(command).encode("utf-8"))
        time.sleep(timeout)
        command = yield
        time.sleep(timeout)
        tn.write("{}\r\n".format(command).encode("utf-8"))
        time.sleep(timeout)
        tn.close()
        yield


if __name__ == "__main__":
    pass

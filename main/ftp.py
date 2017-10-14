from ftplib import FTP

import os

__DATA_FILES_LIST = ("tv", "radio", "lamedb")


def download_data(*, properties):
    with FTP(properties["host"]) as ftp:
        ftp.login(user=properties["user"], passwd=properties["password"])
        save_path = properties["data_dir_path"]
        # bouquets section
        ftp.cwd(properties["services_path"])
        files = []
        ftp.dir(files.append)
        for file in files:
            name = str(file).strip()
            if name.endswith(__DATA_FILES_LIST):
                name = name.split()[-1]
                with open(save_path + name, 'wb') as f:
                    ftp.retrbinary('RETR ' + name, f.write)
        # satellites.xml section
        ftp.cwd(properties["satellites_xml_path"])
        files.clear()
        ftp.dir(files.append)
        for file in files:
            name = str(file).strip()
            xml_file = "satellites.xml"
            if name.endswith(xml_file):
                with open(save_path + xml_file, 'wb') as f:
                    ftp.retrbinary('RETR ' + xml_file, f.write)
        for name in os.listdir(save_path):
            print(name)
        return ftp.voidcmd("NOOP")


def upload_data(*, properties):
    load_path = properties["data_dir_path"]
    for file_name in os.listdir(load_path):
        print(file_name)
        # Open the file for transfer in binary mode
        # f = open(file_name, "rb")
        # transfer the file into receiver
        # send = ftp.storbinary("STOR " + file_name, f)

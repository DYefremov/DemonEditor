import json
import os
import socket
import time
import urllib
from enum import Enum
from ftplib import FTP, error_perm
from telnetlib import Telnet
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen, HTTPPasswordMgrWithDefaultRealm, HTTPBasicAuthHandler, build_opener, install_opener

from app.commons import log
from app.properties import Profile

_BQ_FILES_LIST = ("tv", "radio",  # enigma 2
                  "myservices.xml", "bouquets.xml", "ubouquets.xml")  # neutrino

_DATA_FILES_LIST = ("lamedb", "lamedb5", "services.xml", "blacklist", "whitelist",)

_SAT_XML_FILE = "satellites.xml"
_WEBTV_XML_FILE = "webtv.xml"


class DownloadType(Enum):
    ALL = 0
    BOUQUETS = 1
    SATELLITES = 2
    PICONS = 3
    WEBTV = 4
    EPG = 5


class HttpRequestType(Enum):
    ZAP = "zap?sRef="
    INFO = "about"
    SIGNAL = "tunersignal"
    STREAM = "streamcurrentm3u"
    STATUS = "statusinfo"


class TestException(Exception):
    pass


def download_data(*, properties, download_type=DownloadType.ALL, callback=print):
    with FTP(host=properties["host"], user=properties["user"], passwd=properties["password"]) as ftp:
        ftp.encoding = "utf-8"
        callback("FTP OK.\n")
        save_path = properties["data_dir_path"]
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        files = []
        # bouquets
        if download_type is DownloadType.ALL or download_type is DownloadType.BOUQUETS:
            ftp.cwd(properties["services_path"])
            ftp.dir(files.append)
            file_list = _BQ_FILES_LIST + _DATA_FILES_LIST if download_type is DownloadType.ALL else _BQ_FILES_LIST
            for file in files:
                name = str(file).strip()
                if name.endswith(file_list):
                    name = name.split()[-1]
                    download_file(ftp, name, save_path, callback)
        # satellites.xml and webtv
        if download_type in (DownloadType.ALL, DownloadType.SATELLITES, DownloadType.WEBTV):
            ftp.cwd(properties["satellites_xml_path"])
            files.clear()
            ftp.dir(files.append)

            for file in files:
                name = str(file).strip()
                if download_type in (DownloadType.ALL, DownloadType.SATELLITES) and name.endswith(_SAT_XML_FILE):
                    download_file(ftp, _SAT_XML_FILE, save_path, callback)
                if download_type in (DownloadType.ALL, DownloadType.WEBTV) and name.endswith(_WEBTV_XML_FILE):
                    download_file(ftp, _WEBTV_XML_FILE, save_path, callback)
        # epg.dat
        if download_type is DownloadType.EPG:
            stb_path = properties["services_path"]
            epg_options = properties.get("epg_options", None)
            if epg_options:
                stb_path = epg_options.get("epg_dat_stb_path", stb_path)
                save_path = epg_options.get("epg_dat_path", save_path)
            ftp.cwd(stb_path)
            ftp.dir(files.append)
            for file in files:
                name = str(file).strip()
                if name.endswith("epg.dat"):
                    name = name.split()[-1]
                    download_file(ftp, name, save_path, callback)

        callback("\nDone.\n")


def upload_data(*, properties, download_type=DownloadType.ALL, remove_unused=False, profile=Profile.ENIGMA_2,
                callback=print, done_callback=None, use_http=False):
    data_path = properties["data_dir_path"]
    host = properties["host"]
    base_url = "http://{}:{}/api/".format(host, properties.get("http_port", "80"))
    tn, ht = None, None  # telnet, http

    try:
        if profile is Profile.ENIGMA_2 and use_http:
            ht = http(properties.get("http_user", ""), properties.get("http_password", ""), base_url, callback)
            next(ht)
            message = ""
            if download_type is DownloadType.BOUQUETS:
                message = "User bouquets will be updated!"
            elif download_type is DownloadType.ALL:
                message = "All user data will be reloaded!"
            elif download_type is DownloadType.SATELLITES:
                message = "Satellites.xml file will be updated!"

            params = urlencode({"text": message, "type": 2, "timeout": 5})
            url = base_url + "message?{}".format(params)
            ht.send(url)

            if download_type is DownloadType.ALL:
                time.sleep(5)
                ht.send(base_url + "/powerstate?newstate=0")
                time.sleep(2)
        else:
            # telnet
            tn = telnet(host=host, user=properties.get("telnet_user", "root"),
                        password=properties.get("telnet_password", ""),
                        timeout=properties.get("telnet_timeout", 5))
            next(tn)
            # terminate enigma or neutrino
            tn.send("init 4")

        with FTP(host=host, user=properties["user"], passwd=properties["password"]) as ftp:
            ftp.encoding = "utf-8"
            callback("FTP OK.\n")
            sat_xml_path = properties["satellites_xml_path"]
            services_path = properties["services_path"]

            if download_type is DownloadType.SATELLITES:
                upload_xml(ftp, data_path, sat_xml_path, _SAT_XML_FILE, callback)

            if profile is Profile.NEUTRINO_MP and download_type is DownloadType.WEBTV:
                upload_xml(ftp, data_path, sat_xml_path, _WEBTV_XML_FILE, callback)

            if download_type is DownloadType.BOUQUETS:
                ftp.cwd(services_path)
                upload_bouquets(ftp, data_path, remove_unused, callback)

            if download_type is DownloadType.ALL:
                upload_xml(ftp, data_path, sat_xml_path, _SAT_XML_FILE, callback)
                if profile is Profile.NEUTRINO_MP:
                    upload_xml(ftp, data_path, sat_xml_path, _WEBTV_XML_FILE, callback)

                ftp.cwd(services_path)
                upload_bouquets(ftp, data_path, remove_unused, callback)
                upload_files(ftp, data_path, _DATA_FILES_LIST, callback)

            if download_type is DownloadType.PICONS:
                upload_picons(ftp, properties.get("picons_dir_path"), properties.get("picons_path"), callback)

            if tn and not use_http:
                # resume enigma or restart neutrino
                tn.send("init 3" if profile is Profile.ENIGMA_2 else "init 6")
            elif ht and use_http:
                if download_type is DownloadType.BOUQUETS:
                    ht.send(base_url + "/servicelistreload?mode=2")
                elif download_type is DownloadType.ALL:
                    ht.send(base_url + "/servicelistreload?mode=0")
                    ht.send(base_url + "/powerstate?newstate=4")

            if done_callback is not None:
                done_callback()
    finally:
        if tn:
            tn.close()
        if ht:
            ht.close()


def upload_bouquets(ftp, data_path, remove_unused, callback):
    if remove_unused:
        remove_unused_bouquets(ftp, callback)
    upload_files(ftp, data_path, _BQ_FILES_LIST, callback)


def upload_files(ftp, data_path, file_list, callback):
    for file_name in os.listdir(data_path):
        if file_name == _SAT_XML_FILE or file_name == _WEBTV_XML_FILE:
            continue
        if file_name.endswith(file_list):
            send_file(file_name, data_path, ftp, callback)


def remove_unused_bouquets(ftp, callback):
    files = []
    ftp.dir(files.append)
    for file in files:
        name = str(file).strip()
        if name.endswith(("tv", "radio", "bouquets.xml", "ubouquets.xml")):
            name = name.split()[-1]
            callback("Deleting file: {}.   Status: {}\n".format(name, ftp.delete(name)))


def upload_xml(ftp, data_path, xml_path, xml_file, callback):
    """ Used for transfer satellites.xml or webtv.xml files """
    ftp.cwd(xml_path)
    send_file(xml_file, data_path, ftp, callback)


def upload_picons(ftp, src, dest, callback):
    try:
        ftp.cwd(dest)
    except error_perm as e:
        if str(e).startswith("550"):
            ftp.mkd(dest)  # if not exist
            ftp.cwd(dest)
    files = []
    ftp.dir(files.append)
    picons_suf = (".jpg", ".png")
    for file in files:
        name = str(file).strip()
        if name.endswith(picons_suf):
            name = name.split()[-1]
            ftp.delete(name)
    for file_name in os.listdir(src):
        if file_name.endswith(picons_suf):
            send_file(file_name, src, ftp, callback)


def download_file(ftp, name, save_path, callback):
    with open(save_path + name, "wb") as f:
        callback("Downloading file: {}.   Status: {}\n".format(name, str(ftp.retrbinary("RETR " + name, f.write))))


def send_file(file_name, path, ftp, callback):
    """ Opens the file in binary mode and transfers into receiver """
    with open(path + file_name, "rb") as f:
        callback("Uploading file: {}.   Status: {}\n".format(file_name, str(ftp.storbinary("STOR " + file_name, f))))


def http(user, password, url, callback):
    init_auth(user, password, url)
    while True:
        url = yield
        with urlopen(url, timeout=5) as f:
            msg = json.loads(f.read().decode("utf-8")).get("message", None)
            if msg:
                callback("HTTP: {}\n".format(msg))


def telnet(host, port=23, user="", password="", timeout=5):
    try:
        tn = Telnet(host=host, port=port, timeout=timeout)
    except socket.timeout:
        log("telnet error: socket timeout")
    else:
        time.sleep(1)
        command = yield
        if user != "":
            tn.read_until(b"login: ")
            tn.write(user.encode("utf-8") + b"\n")
            time.sleep(timeout)
        if password != "":
            tn.read_until(b"Password: ")
            tn.write(password.encode("utf-8") + b"\n")
            time.sleep(timeout)
        tn.write("{}\r\n".format(command).encode("utf-8"))
        time.sleep(timeout)
        command = yield
        time.sleep(timeout)
        tn.write("{}\r\n".format(command).encode("utf-8"))
        time.sleep(timeout)
        yield


# ***************** http api *******************#

def http_request(host, port, user, password):
    base_url = "http://{}:{}/api/".format(host, port)
    init_auth(user, password, base_url)

    while True:
        req_type, ref = yield
        url = base_url
        if req_type is HttpRequestType.ZAP:
            url = base_url + "zap?sRef={}".format(urllib.parse.quote(ref))
        elif req_type is HttpRequestType.INFO:
            url = base_url + HttpRequestType.INFO.value
        elif req_type is HttpRequestType.SIGNAL:
            url = base_url + HttpRequestType.SIGNAL.value
        elif req_type is HttpRequestType.STREAM:
            url = base_url + HttpRequestType.STREAM.value
        elif req_type is HttpRequestType.STATUS:
            url = base_url + HttpRequestType.STATUS.value

        yield from get_json(req_type, url)


def get_json(req_type, url):
    try:
        with urlopen(url, timeout=5) as f:
            if req_type is HttpRequestType.STREAM:
                yield f.read().decode("utf-8")
            else:
                yield json.loads(f.read().decode("utf-8"))
    except (URLError, HTTPError):
        yield None


# ***************** Connections testing *******************#

def test_ftp(host, port, user, password, timeout=5):
    try:
        with FTP(host=host, user=user, passwd=password, timeout=timeout) as ftp:
            return ftp.getwelcome()
    except (error_perm, ConnectionRefusedError, OSError) as e:
        raise TestException(e)


def test_http(host, port, user, password, timeout=5, skip_message=False):
    try:
        params = urlencode({"text": "Connection test", "type": 2, "timeout": timeout})
        params = "statusinfo" if skip_message else "message?{}".format(params)
        url = "http://{}:{}/api/{}".format(host, port, params)
        # authentication
        init_auth(user, password, url)

        with urlopen(url, timeout=5) as f:
            return json.loads(f.read().decode("utf-8")).get("message", "")
    except (URLError, HTTPError) as e:
        raise TestException(e)


def init_auth(user, password, url):
    """ Init authentication """
    pass_mgr = HTTPPasswordMgrWithDefaultRealm()
    pass_mgr.add_password(None, url, user, password)
    auth_handler = HTTPBasicAuthHandler(pass_mgr)
    opener = build_opener(auth_handler)
    install_opener(opener)


def test_telnet(host, port, user, password, timeout=5):
    try:
        gen = telnet_test(host, port, user, password, timeout)
        res = next(gen)
        print(res)
        res = next(gen)
        return res
    except (socket.timeout, OSError) as e:
        raise TestException(e)


def telnet_test(host, port, user, password, timeout):
    tn = Telnet(host=host, port=port, timeout=timeout)
    time.sleep(1)
    tn.read_until(b"login: ", timeout=2)
    tn.write(user.encode("utf-8") + b"\n")
    time.sleep(timeout)
    tn.read_until(b"Password: ", timeout=2)
    tn.write(password.encode("utf-8") + b"\n")
    time.sleep(timeout)
    yield tn.read_very_eager()
    tn.close()
    yield "Done"


if __name__ == "__main__":
    pass

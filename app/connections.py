import os
import re
import socket
import time
import urllib
import xml.etree.ElementTree as ETree
from enum import Enum
from ftplib import FTP, error_perm
from http.client import RemoteDisconnected
from telnetlib import Telnet
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (urlopen, HTTPPasswordMgrWithDefaultRealm, HTTPBasicAuthHandler, build_opener,
                            install_opener, Request)

from app.commons import log, run_task
from app.settings import SettingsType

BQ_FILES_LIST = ("tv", "radio",  # enigma 2
                 "myservices.xml", "bouquets.xml", "ubouquets.xml")  # neutrino

DATA_FILES_LIST = ("lamedb", "lamedb5", "blacklist", "whitelist",)

STC_XML_FILE = ("satellites.xml", "terrestrial.xml", "cables.xml")
WEB_TV_XML_FILE = ("webtv.xml",)
PICONS_SUF = (".jpg", ".png")


class DownloadType(Enum):
    ALL = 0
    BOUQUETS = 1
    SATELLITES = 2
    PICONS = 3
    WEBTV = 4
    EPG = 5


class TestException(Exception):
    pass


class HttpApiException(Exception):
    pass


def download_data(*, settings, download_type=DownloadType.ALL, callback=print, files_filter=None):
    with FTP(host=settings.host, user=settings.user, passwd=settings.password) as ftp:
        ftp.encoding = "utf-8"
        callback("FTP OK.\n")
        save_path = settings.data_local_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        # bouquets
        if download_type is DownloadType.ALL or download_type is DownloadType.BOUQUETS:
            ftp.cwd(settings.services_path)
            file_list = BQ_FILES_LIST + DATA_FILES_LIST if download_type is DownloadType.ALL else BQ_FILES_LIST
            download_files(ftp, save_path, file_list, callback)
        # *.xml and webtv
        if download_type in (DownloadType.ALL, DownloadType.SATELLITES):
            download_xml(ftp, save_path, settings.satellites_xml_path, STC_XML_FILE, callback)
        if download_type in (DownloadType.ALL, DownloadType.WEBTV):
            download_xml(ftp, save_path, settings.satellites_xml_path, WEB_TV_XML_FILE, callback)

        if download_type is DownloadType.PICONS:
            picons_path = settings.picons_local_path
            os.makedirs(os.path.dirname(picons_path), exist_ok=True)
            download_picons(ftp, settings.picons_path, picons_path, callback, files_filter)
        # epg.dat
        if download_type is DownloadType.EPG:
            stb_path = settings.services_path
            epg_options = settings.epg_options
            if epg_options:
                stb_path = epg_options.get("epg_dat_stb_path", stb_path)
                save_path = epg_options.get("epg_dat_path", save_path)

            ftp.cwd(stb_path)
            download_files(ftp, save_path, "epg.dat", callback)

        callback("\nDone.\n")


def upload_data(*, settings, download_type=DownloadType.ALL, remove_unused=False,
                callback=print, done_callback=None, use_http=False, files_filter=None):
    s_type = settings.setting_type
    data_path = settings.data_local_path
    host = settings.host
    base_url = "http{}://{}:{}".format("s" if settings.http_use_ssl else "", host, settings.http_port)
    url = "{}/web/".format(base_url)
    tn, ht = None, None  # telnet, http

    try:
        if s_type is SettingsType.ENIGMA_2 and use_http:
            ht = http(settings.http_user, settings.http_password, base_url, callback, settings.http_use_ssl)
            next(ht)
            message = ""
            if download_type is DownloadType.BOUQUETS:
                message = "User bouquets will be updated!"
            elif download_type is DownloadType.ALL:
                message = "All user data will be reloaded!"
            elif download_type is DownloadType.SATELLITES:
                message = "Satellites.xml file will be updated!"
            elif download_type is DownloadType.PICONS:
                message = "Picons will be updated!"

            params = urlencode({"text": message, "type": 2, "timeout": 5})
            ht.send((url + "message?{}".format(params), "Sending info message... "))

            if download_type is DownloadType.ALL:
                time.sleep(5)
                ht.send((url + "powerstate?newstate=0", "Toggle Standby "))
                time.sleep(2)
        else:
            if download_type is not DownloadType.PICONS:
                # telnet
                tn = telnet(host=host,
                            user=settings.telnet_user,
                            password=settings.telnet_password,
                            timeout=settings.telnet_timeout)
                next(tn)
                # terminate enigma or neutrino
                tn.send("init 4")

        with FTP(host=host, user=settings.user, passwd=settings.password) as ftp:
            ftp.encoding = "utf-8"
            callback("FTP OK.\n")
            sat_xml_path = settings.satellites_xml_path
            services_path = settings.services_path

            if download_type is DownloadType.SATELLITES:
                upload_xml(ftp, data_path, sat_xml_path, STC_XML_FILE, callback)

            if s_type is SettingsType.NEUTRINO_MP and download_type is DownloadType.WEBTV:
                upload_xml(ftp, data_path, sat_xml_path, WEB_TV_XML_FILE, callback)

            if download_type is DownloadType.BOUQUETS:
                ftp.cwd(services_path)
                upload_bouquets(ftp, data_path, remove_unused, callback)

            if download_type is DownloadType.ALL:
                upload_xml(ftp, data_path, sat_xml_path, STC_XML_FILE, callback)
                if s_type is SettingsType.NEUTRINO_MP:
                    upload_xml(ftp, data_path, sat_xml_path, WEB_TV_XML_FILE, callback)

                ftp.cwd(services_path)
                upload_bouquets(ftp, data_path, remove_unused, callback)
                upload_files(ftp, data_path, DATA_FILES_LIST, callback)

            if download_type is DownloadType.PICONS:
                upload_picons(ftp, settings.picons_local_path, settings.picons_path, callback, files_filter)

            if tn and not use_http:
                # resume enigma or restart neutrino
                tn.send("init 3" if s_type is SettingsType.ENIGMA_2 else "init 6")
            elif ht and use_http:
                if download_type is DownloadType.BOUQUETS:
                    ht.send((url + "servicelistreload?mode=2", "Reloading Userbouquets."))
                elif download_type is DownloadType.ALL:
                    ht.send((url + "servicelistreload?mode=0", "Reloading lamedb and Userbouquets."))
                    ht.send((url + "powerstate?newstate=4", "Wakeup from Standby."))

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
    upload_files(ftp, data_path, BQ_FILES_LIST, callback)


def upload_files(ftp, data_path, file_list, callback):
    for file_name in os.listdir(data_path):
        if file_name in STC_XML_FILE or file_name in WEB_TV_XML_FILE:
            continue
        if file_name.endswith(file_list):
            send_file(file_name, data_path, ftp, callback)


def remove_unused_bouquets(ftp, callback):
    files = []
    ftp.dir(files.append)
    bq_files = ("tv", "radio", "bouquets.xml", "ubouquets.xml")

    for file in filter(lambda f: f.endswith(bq_files), map(lambda f: f.split()[-1], map(str.rstrip, files))):
        callback("Deleting file: {}.   Status: {}\n".format(file, ftp.delete(file)))


def upload_xml(ftp, data_path, xml_path, xml_files, callback):
    """ Used for transfer *.xml files. """
    ftp.cwd(xml_path)
    for xml_file in xml_files:
        send_file(xml_file, data_path, ftp, callback)


def download_xml(ftp, data_path, xml_path, xml_files, callback):
    """ Used for download *.xml files. """
    ftp.cwd(xml_path)
    download_files(ftp, data_path, xml_files, callback)


# ***************** Picons *******************#

def upload_picons(ftp, src, dest, callback, files_filter=None):
    try:
        ftp.cwd(dest)
    except error_perm as e:
        if str(e).startswith("550"):
            ftp.mkd(dest)  # if not exist
            ftp.cwd(dest)

    for file_name in filter(picons_filter_function(files_filter), os.listdir(src)):
        send_file(file_name, src, ftp, callback)


def download_picons(ftp, src, dest, callback, files_filter=None):
    try:
        ftp.cwd(src)
    except error_perm as e:
        callback(str(e))
        return

    files = []
    ftp.dir(files.append)

    for file in filter(picons_filter_function(files_filter), map(lambda f: f.split()[-1], map(str.rstrip, files))):
        download_file(ftp, file, dest, callback)


def delete_picons(ftp, callback, dest=None, files_filter=None):
    if dest:
        try:
            ftp.cwd(dest)
        except error_perm as e:
            callback(str(e))
            return

    files = []
    ftp.dir(files.append)

    for file in filter(picons_filter_function(files_filter), map(lambda f: f.split()[-1], map(str.rstrip, files))):
        callback("Delete file: {}.   Status: {}\n".format(file, ftp.delete(file)))


def remove_picons(*, settings, callback, done_callback=None, files_filter=None):
    with FTP(host=settings.host, user=settings.user, passwd=settings.password) as ftp:
        ftp.encoding = "utf-8"
        callback("FTP OK.\n")
        delete_picons(ftp, callback, settings.picons_path, files_filter)
        if done_callback:
            done_callback()


def picons_filter_function(files_filter=None):
    return lambda f: f in files_filter if files_filter else f.endswith(PICONS_SUF)


def download_files(ftp, save_path, file_list, callback):
    """ Downloads files from the receiver via FTP. """
    files = []
    ftp.dir(files.append)

    for file in map(lambda f: f.split()[-1], filter(lambda s: s.endswith(file_list), map(str.rstrip, files))):
        download_file(ftp, file, save_path, callback)


def download_file(ftp, name, save_path, callback):
    with open(save_path + name, "wb") as f:
        callback("Downloading file: {}.   Status: {}\n".format(name, str(ftp.retrbinary("RETR " + name, f.write))))


def send_file(file_name, path, ftp, callback):
    """ Opens the file in binary mode and transfers into receiver """
    file_src = path + file_name
    if not os.path.isfile(file_src):
        log("Uploading file: '{}'. File not found. Skipping.".format(file_src))
        return

    with open(file_src, "rb") as f:
        callback("Uploading file: {}.   Status: {}\n".format(file_name, str(ftp.storbinary("STOR " + file_name, f))))


def http(user, password, url, callback, use_ssl=False):
    init_auth(user, password, url, use_ssl)
    data = get_post_data(url, password, url)

    while True:
        url, message = yield
        resp = get_response(HttpAPI.Request.TEST, url, data).get("e2statetext", None)
        callback("HTTP: {} {}\n".format(message, "Successful." if resp and message else ""))


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


# ***************** HTTP API *******************#

class HttpAPI:
    __MAX_WORKERS = 4

    class Request(Enum):
        ZAP = "zap?sRef="
        INFO = "about"
        SIGNAL = "signal"
        STREAM = "stream.m3u?ref="
        STREAM_CURRENT = "streamcurrent.m3u"
        CURRENT = "getcurrent"
        TEST = None
        TOKEN = "session"
        # Player
        PLAY = "mediaplayerplay?file="
        PLAYER_LIST = "mediaplayerlist?path=playlist"
        PLAYER_PLAY = "mediaplayercmd?command=play"
        PLAYER_NEXT = "mediaplayercmd?command=next"
        PLAYER_PREV = "mediaplayercmd?command=previous"
        PLAYER_STOP = "mediaplayercmd?command=stop"
        PLAYER_REMOVE = "mediaplayerremove?file="
        # Remote control
        POWER = "powerstate?newstate="
        REMOTE = "remotecontrol?command="
        VOL = "vol?set=set"
        # EPG
        EPG = "epgservice?sRef="
        # Timer
        TIMER = ""
        TIMER_LIST = "timerlist"
        # Screenshot
        GRUB = "grab?format=jpg&"

    class Remote(str, Enum):
        """ Args for HttpRequestType [REMOTE] class. """
        UP = "103"
        LEFT = "105"
        RIGHT = "106"
        DOWN = "108"
        MENU = "139"
        EXIT = "174"
        OK = "352"
        RED = "398"
        GREEN = "399"
        YELLOW = "400"
        BLUE = "401"

    class Power(str, Enum):
        """ Args for HttpRequestType [POWER] class. """
        TOGGLE_STANDBY = "0"
        DEEP_STANDBY = "1"
        REBOOT = "2"
        RESTART_GUI = "3"
        WAKEUP = "4"
        STANDBY = "5"

    def __init__(self, settings):
        from concurrent.futures import ThreadPoolExecutor as PoolExecutor
        self._executor = PoolExecutor(max_workers=self.__MAX_WORKERS)

        self._settings = settings
        self._shutdown = False
        self._session_id = 0
        self._main_url = None
        self._base_url = None
        self._data = None
        self._is_owif = True
        self.init()

    def send(self, req_type, ref, callback=print, ref_prefix=""):
        if self._shutdown:
            return

        url = self._base_url + req_type.value
        data = self._data

        if req_type is self.Request.ZAP or req_type is self.Request.STREAM:
            url += urllib.parse.quote(ref)
        elif req_type is self.Request.PLAY or req_type is self.Request.PLAYER_REMOVE:
            url += "{}{}".format(ref_prefix, urllib.parse.quote(ref).replace("%3A", "%253A"))
        elif req_type is self.Request.GRUB:
            data = None  # Must be disabled for token-based security.
            url = "{}/{}{}".format(self._main_url, req_type.value, ref)
        elif req_type in (self.Request.REMOTE,
                          self.Request.POWER,
                          self.Request.VOL,
                          self.Request.EPG,
                          self.Request.TIMER):
            url += ref

        def done_callback(f):
            callback(f.result())

        future = self._executor.submit(get_response, req_type, url, data)
        future.add_done_callback(done_callback)

    @run_task
    def init(self):
        user, password = self._settings.http_user, self._settings.http_password
        use_ssl = self._settings.http_use_ssl
        self._main_url = "http{}://{}:{}".format("s" if use_ssl else "", self._settings.host, self._settings.http_port)
        self._base_url = "{}/web/".format(self._main_url)
        init_auth(user, password, self._main_url, use_ssl)
        url = "{}/web/{}".format(self._main_url, self.Request.TOKEN.value)
        s_id = get_session_id(user, password, url)
        if s_id != "0":
            self._data = urllib.parse.urlencode({"user": user, "password": password, "sessionid": s_id}).encode("utf-8")

        self.send(self.Request.INFO, None, self.init_callback)

    def init_callback(self, info):
        if info:
            version = info.get("e2webifversion", "").upper()
            self._is_owif = "OWIF" in version
            version_info = "Web Interface version: {}".format(version) if version else ""
            log("HTTP API initialized... {}".format(version_info))

    @property
    def is_owif(self):
        """ Returns true if the web interface is OpenWebif. """
        return self._is_owif

    @run_task
    def close(self):
        self._shutdown = True
        self._executor.shutdown()


def get_response(req_type, url, data=None):
    try:
        with urlopen(Request(url, data=data), timeout=10) as f:
            if req_type is HttpAPI.Request.STREAM or req_type is HttpAPI.Request.STREAM_CURRENT:
                return {"m3u": f.read().decode("utf-8")}
            elif req_type is HttpAPI.Request.GRUB:
                return {"img_data": f.read()}
            elif req_type is HttpAPI.Request.CURRENT:
                for el in ETree.fromstring(f.read().decode("utf-8")).iter("e2event"):
                    return {el.tag: el.text for el in el.iter()}  # return first[current] event from the list
            elif req_type is HttpAPI.Request.PLAYER_LIST:
                return [{el.tag: el.text for el in el.iter()} for el in
                        ETree.fromstring(f.read().decode("utf-8")).iter("e2file")]
            elif req_type is HttpAPI.Request.EPG:
                return {"event_list": [{el.tag: el.text for el in el.iter()} for el in
                                       ETree.fromstring(f.read().decode("utf-8")).iter("e2event")]}
            elif req_type is HttpAPI.Request.TIMER_LIST:
                return {"timer_list": [{el.tag: el.text for el in el.iter()} for el in
                                       ETree.fromstring(f.read().decode("utf-8")).iter("e2timer")]}
            else:
                return {el.tag: el.text for el in ETree.fromstring(f.read().decode("utf-8")).iter()}
    except HTTPError as e:
        if req_type is HttpAPI.Request.TEST:
            raise e
        return {"error_code": e.code}
    except (URLError, RemoteDisconnected, ConnectionResetError) as e:
        if req_type is HttpAPI.Request.TEST:
            raise e
    except ETree.ParseError as e:
        log("Parsing response error: {}".format(e))

    return {"error_code": -1}


def init_auth(user, password, url, use_ssl=False):
    """ Init authentication """
    pass_mgr = HTTPPasswordMgrWithDefaultRealm()
    pass_mgr.add_password(None, url, user, password)
    auth_handler = HTTPBasicAuthHandler(pass_mgr)

    if use_ssl:
        import ssl
        from urllib.request import HTTPSHandler

        opener = build_opener(auth_handler, HTTPSHandler(context=ssl._create_unverified_context()))
    else:
        opener = build_opener(auth_handler)

    install_opener(opener)


def get_session_id(user, password, url):
    data = urllib.parse.urlencode(dict(user=user, password=password)).encode("utf-8")
    return get_response(HttpAPI.Request.TOKEN, url, data=data).get("e2sessionid", "0")


def get_post_data(base_url, password, user):
    s_id = get_session_id(user, password, "{}/web/{}".format(base_url, HttpAPI.Request.TOKEN.value))
    data = None
    if s_id != "0":
        data = urllib.parse.urlencode({"user": user, "password": password, "sessionid": s_id}).encode("utf-8")
    return data


# ***************** Connections testing *******************#

def test_ftp(host, port, user, password, timeout=5):
    try:
        with FTP(host=host, user=user, passwd=password, timeout=timeout) as ftp:
            return ftp.getwelcome()
    except (error_perm, ConnectionRefusedError, OSError) as e:
        raise TestException(e)


def test_http(host, port, user, password, timeout=5, use_ssl=False, skip_message=False):
    params = urlencode({"text": "Connection test", "type": 2, "timeout": timeout})
    params = "statusinfo" if skip_message else "message?{}".format(params)
    base_url = "http{}://{}:{}".format("s" if use_ssl else "", host, port)
    # authentication
    init_auth(user, password, base_url, use_ssl)
    data = get_post_data(base_url, password, user)

    try:
        return get_response(HttpAPI.Request.TEST, "{}/web/{}".format(base_url, params), data).get("e2statetext", "")
    except (RemoteDisconnected, URLError, HTTPError) as e:
        raise TestException(e)


def test_telnet(host, port, user, password, timeout=5):
    try:
        gen = telnet_test(host, port, user, password, timeout)
        res = next(gen)
        msg = str(res, encoding="utf8").strip()
        log(msg)
        next(gen)
        if re.search("password", msg, re.IGNORECASE):
            raise TestException(msg)
        return msg
    except (socket.timeout, OSError) as e:
        raise TestException(e)


def telnet_test(host, port, user, password, timeout):
    tn = Telnet(host=host, port=port, timeout=timeout)
    time.sleep(1)
    tn.read_until(b"login: ", timeout=2)
    tn.write(user.encode("utf-8") + b"\r")
    time.sleep(timeout)
    tn.read_until(b"Password: ", timeout=2)
    tn.write(password.encode("utf-8") + b"\r")
    time.sleep(timeout)
    yield tn.read_very_eager()
    tn.close()
    yield


if __name__ == "__main__":
    pass

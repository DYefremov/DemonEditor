import os
import re
import socket
import time
import urllib
import xml.etree.ElementTree as ETree
from enum import Enum
from ftplib import FTP, CRLF, Error, error_perm
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


class UtfFTP(FTP):
    """ FTP class wrapper. """

    def retrlines(self, cmd, callback=None):
        """ Small modification of the original method.

            It is used to retrieve data in line mode and skip errors related
            to reading file names in encoding other than UTF-8 or Latin-1.
            Decode errors are ignored [UnicodeDecodeError, etc].
         """
        if callback is None:
            callback = log
        self.sendcmd("TYPE A")
        with self.transfercmd(cmd) as conn, conn.makefile("r", encoding=self.encoding, errors="ignore") as fp:
            while 1:
                line = fp.readline(self.maxline + 1)
                if len(line) > self.maxline:
                    msg = "UtfFTP [retrlines] error: got more than {} bytes".format(self.maxline)
                    log(msg)
                    raise Error(msg)
                if self.debugging > 2:
                    log('UtfFTP [retrlines] *retr* {}'.format(repr(line)))
                if not line:
                    break
                if line[-2:] == CRLF:
                    line = line[:-2]
                elif line[-1:] == "\n":
                    line = line[:-1]
                callback(line)
        return self.voidresp()

    # ***************** Download ******************* #

    def download_files(self, save_path, file_list, callback=None):
        """ Downloads files from the receiver via FTP. """
        for file in filter(lambda s: s.endswith(file_list), self.nlst()):
            self.download_file(file, save_path, callback)

    def download_file(self, name, save_path, callback=None):
        with open(save_path + name, "wb") as f:
            msg = "Downloading file: {}.   Status: {}\n"
            try:
                resp = str(self.retrbinary("RETR " + name, f.write))
            except error_perm as e:
                resp = str(e)
                msg = msg.format(name, e)
                log(msg.rstrip())
            else:
                msg = msg.format(name, resp)

            callback(msg) if callback else log(msg.rstrip())

            return resp

    def download_dir(self, path, save_path, callback=None):
        """  Downloads directory from FTP with all contents.

            Creates a leaf directory and all intermediate ones. This is recursive.
         """
        os.makedirs(os.path.join(save_path, path), exist_ok=True)

        files = []
        self.dir(path, files.append)
        for f in files:
            f_data = f.split()
            f_path = os.path.join(path, " ".join(f_data[8:]))

            if f_data[0][0] == "d":
                try:
                    os.makedirs(os.path.join(save_path, f_path), exist_ok=True)
                except OSError as e:
                    msg = "Download dir error: {}".format(e).rstrip()
                    log(msg)
                    return "500 " + msg
                else:
                    self.download_dir(f_path, save_path, callback)
            else:
                try:
                    self.download_file(f_path, save_path, callback)
                except OSError as e:
                    log("Download dir error: {}".format(e).rstrip())

        resp = "226 Transfer complete."
        msg = "Copy directory {}.   Status: {}".format(path, resp)
        log(msg)

        if callback:
            callback(msg)

        return resp

    def download_xml(self, data_path, xml_path, xml_files, callback):
        """ Used for download *.xml files. """
        self.cwd(xml_path)
        self.download_files(data_path, xml_files, callback)

    def download_picons(self, src, dest, callback, files_filter=None):
        try:
            self.cwd(src)
        except error_perm as e:
            callback(str(e))
            return

        for file in filter(picons_filter_function(files_filter), self.nlst()):
            self.download_file(file, dest, callback)

    # ***************** Uploading ******************* #

    def upload_bouquets(self, data_path, remove_unused, callback):
        if remove_unused:
            self.remove_unused_bouquets(callback)
        self.upload_files(data_path, BQ_FILES_LIST, callback)

    def upload_files(self, data_path, file_list, callback):
        for file_name in os.listdir(data_path):
            if file_name in STC_XML_FILE or file_name in WEB_TV_XML_FILE:
                continue
            if file_name.endswith(file_list):
                self.send_file(file_name, data_path, callback)

    def upload_xml(self, data_path, xml_path, xml_files, callback):
        """ Used for transfer *.xml files. """
        self.cwd(xml_path)
        for xml_file in xml_files:
            self.send_file(xml_file, data_path, callback)

    def upload_picons(self, src, dest, callback, files_filter=None):
        try:
            self.cwd(dest)
        except error_perm as e:
            if str(e).startswith("550"):
                self.mkd(dest)  # if not exist
                self.cwd(dest)

        for file_name in filter(picons_filter_function(files_filter), os.listdir(src)):
            self.send_file(file_name, src, callback)

    def remove_unused_bouquets(self, callback):
        bq_files = ("userbouquet.", "bouquets.xml", "ubouquets.xml")

        for file in filter(lambda f: f.startswith(bq_files), self.nlst()):
            self.delete_file(file, callback)

    def send_file(self, file_name, path, callback=None):
        """ Opens the file in binary mode and transfers into receiver """
        file_src = path + file_name
        resp = "500"
        if not os.path.isfile(file_src):
            log("Uploading file: '{}'. File not found. Skipping.".format(file_src))
            return resp + " File not found."

        with open(file_src, "rb") as f:
            msg = "Uploading file: {}.   Status: {}\n"
            try:
                resp = str(self.storbinary("STOR " + file_name, f))
            except Error as e:
                resp = str(e)
                msg = msg.format(file_name, resp)
                log(msg)
            else:
                msg = msg.format(file_name, resp)

            if callback:
                callback(msg)

        return resp

    def upload_dir(self, path, callback=None):
        """ Uploads directory to FTP with all contents.

            Creates a leaf directory and all intermediate ones. This is recursive.
        """
        resp = "200"
        msg = "Uploading directory: {}.   Status: {}"
        try:
            files = os.listdir(path)
        except OSError as e:
            log(e)
        else:
            os.chdir(path)
            for f in files:
                file = r"{}{}".format(path, f)
                if os.path.isfile(file):
                    self.send_file(f, path, callback)
                elif os.path.isdir(file):
                    try:
                        self.mkd(f)
                    except Error:
                        pass  # NOP

                    try:
                        self.cwd(f)
                    except Error as e:
                        resp = str(e)
                        log(msg.format(f, resp))
                    else:
                        self.upload_dir(file + "/")

            self.cwd("..")
            os.chdir("..")

            if callback:
                callback(msg.format(path, resp))

        return resp

    # ****************** Deletion ******************** #

    def delete_picons(self, callback, dest=None, files_filter=None):
        if dest:
            try:
                self.cwd(dest)
            except Error as e:
                callback(str(e))
                return

        for file in filter(picons_filter_function(files_filter), self.nlst()):
            self.delete_file(file, callback)

    def delete_file(self, file, callback=log):
        msg = "Deleting file: {}.   Status: {}\n"
        try:
            resp = self.delete(file)
        except Error as e:
            resp = str(e)
            msg = msg.format(file, resp)
            log(msg)
        else:
            msg = msg.format(file, resp)

        if callback:
            callback(msg)

        return resp

    def delete_dir(self, path, callback=None):
        files = []
        self.dir(path, files.append)
        for f in files:
            f_data = f.split()
            name = " ".join(f_data[8:])
            f_path = path + "/" + name

            if f_data[0][0] == "d":
                self.delete_dir(f_path, callback)
            else:
                self.delete_file(f_path, callback)

        msg = "Remove directory {}.   Status: {}\n"
        try:
            resp = self.rmd(path)
        except Error as e:
            msg = msg.format(path, e)
            log(msg)
            return "500"
        else:
            msg = msg.format(path, resp)
            log(msg.rstrip())

        if callback:
            callback(msg)

        return resp

    def rename_file(self, from_name, to_name, callback=None):
        msg = "File rename: {}.   Status: {}\n"
        try:
            resp = self.rename(from_name, to_name)
        except Error as e:
            resp = str(e)
            msg = msg.format(from_name, resp)
            log(msg)
        else:
            msg = msg.format(from_name, resp)

        if callback:
            callback(msg)

        return resp


def download_data(*, settings, download_type=DownloadType.ALL, callback=log, files_filter=None):
    with UtfFTP(host=settings.host, user=settings.user, passwd=settings.password) as ftp:
        ftp.encoding = "utf-8"
        callback("FTP OK.\n")
        save_path = settings.data_local_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        # bouquets
        if download_type is DownloadType.ALL or download_type is DownloadType.BOUQUETS:
            ftp.cwd(settings.services_path)
            file_list = BQ_FILES_LIST + DATA_FILES_LIST if download_type is DownloadType.ALL else BQ_FILES_LIST
            ftp.download_files(save_path, file_list, callback)
        # *.xml and webtv
        if download_type in (DownloadType.ALL, DownloadType.SATELLITES):
            ftp.download_xml(save_path, settings.satellites_xml_path, STC_XML_FILE, callback)
        if download_type in (DownloadType.ALL, DownloadType.WEBTV):
            ftp.download_xml(save_path, settings.satellites_xml_path, WEB_TV_XML_FILE, callback)

        if download_type is DownloadType.PICONS:
            picons_path = settings.picons_local_path
            os.makedirs(os.path.dirname(picons_path), exist_ok=True)
            ftp.download_picons(settings.picons_path, picons_path, callback, files_filter)
        # epg.dat
        if download_type is DownloadType.EPG:
            stb_path = settings.services_path
            epg_options = settings.epg_options
            if epg_options:
                stb_path = epg_options.get("epg_dat_stb_path", stb_path)
                save_path = epg_options.get("epg_dat_path", save_path)

            ftp.cwd(stb_path)
            ftp.download_files(save_path, "epg.dat", callback)

        callback("\nDone.\n")


def upload_data(*, settings, download_type=DownloadType.ALL, remove_unused=False,
                callback=log, done_callback=None, use_http=False, files_filter=None):
    s_type = settings.setting_type
    data_path = settings.data_local_path
    host = settings.host
    base_url = "http{}://{}:{}".format("s" if settings.http_use_ssl else "", host, settings.http_port)
    url = "{}/web/".format(base_url)
    tn, ht = None, None  # telnet, http

    try:
        if s_type is SettingsType.ENIGMA_2 and use_http:
            ht = http(settings.user, settings.password, base_url, callback, settings.http_use_ssl)
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
                            user=settings.user,
                            password=settings.password,
                            timeout=settings.telnet_timeout)
                next(tn)
                # terminate enigma or neutrino
                callback("Telnet initialization ...\n")
                tn.send("init 4")
                callback("Stopping GUI...\n")

        with UtfFTP(host=host, user=settings.user, passwd=settings.password) as ftp:
            ftp.encoding = "utf-8"
            callback("FTP OK.\n")
            sat_xml_path = settings.satellites_xml_path
            services_path = settings.services_path

            if download_type is DownloadType.SATELLITES:
                ftp.upload_xml(data_path, sat_xml_path, STC_XML_FILE, callback)

            if s_type is SettingsType.NEUTRINO_MP and download_type is DownloadType.WEBTV:
                ftp.upload_xml(data_path, sat_xml_path, WEB_TV_XML_FILE, callback)

            if download_type is DownloadType.BOUQUETS:
                ftp.cwd(services_path)
                ftp.upload_bouquets(data_path, remove_unused, callback)

            if download_type is DownloadType.ALL:
                ftp.upload_xml(data_path, sat_xml_path, STC_XML_FILE, callback)
                if s_type is SettingsType.NEUTRINO_MP:
                    ftp.upload_xml(data_path, sat_xml_path, WEB_TV_XML_FILE, callback)

                ftp.cwd(services_path)
                ftp.upload_bouquets(data_path, remove_unused, callback)
                ftp.upload_files(data_path, DATA_FILES_LIST, callback)

            if download_type is DownloadType.PICONS:
                ftp.upload_picons(settings.picons_local_path, settings.picons_path, callback, files_filter)

            if tn and not use_http:
                # resume enigma or restart neutrino
                tn.send("init 3" if s_type is SettingsType.ENIGMA_2 else "init 6")
                callback("Starting...\n" if s_type is SettingsType.ENIGMA_2 else "Rebooting...\n")
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


# ***************** Picons *******************#

def remove_picons(*, settings, callback, done_callback=None, files_filter=None):
    with UtfFTP(host=settings.host, user=settings.user, passwd=settings.password) as ftp:
        ftp.encoding = "utf-8"
        callback("FTP OK.\n")
        ftp.delete_picons(callback, settings.picons_path, files_filter)
        if done_callback:
            done_callback()


def picons_filter_function(files_filter=None):
    return lambda f: f in files_filter if files_filter else f.endswith(PICONS_SUF)


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
            tn.read_until(b"login: ", timeout)
            tn.write(user.encode("utf-8") + b"\n")
            time.sleep(timeout)
        if password != "":
            tn.read_until(b"Password: ", timeout)
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
        STREAM_TS = "ts.m3u?file="
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
        # Recordings
        RECORDINGS = "movielist?dirname="
        REC_DIRS = "getlocations"
        REC_CURRENT = "getcurrlocation"
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

    PARAM_REQUESTS = {Request.REMOTE,
                      Request.POWER,
                      Request.VOL,
                      Request.EPG,
                      Request.TIMER,
                      Request.RECORDINGS}

    STREAM_REQUESTS = {Request.STREAM,
                       Request.STREAM_CURRENT,
                       Request.STREAM_TS}

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

        if req_type is self.Request.ZAP or req_type in self.STREAM_REQUESTS:
            url += urllib.parse.quote(ref)
        elif req_type is self.Request.PLAY or req_type is self.Request.PLAYER_REMOVE:
            url += "{}{}".format(ref_prefix, urllib.parse.quote(ref).replace("%3A", "%253A"))
        elif req_type is self.Request.GRUB:
            data = None  # Must be disabled for token-based security.
            url = "{}/{}{}".format(self._main_url, req_type.value, ref)
        elif req_type in self.PARAM_REQUESTS:
            url += ref

        def done_callback(f):
            callback(f.result())

        future = self._executor.submit(get_response, req_type, url, data)
        future.add_done_callback(done_callback)

    @run_task
    def init(self):
        user, password = self._settings.user, self._settings.password
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
            if req_type in HttpAPI.STREAM_REQUESTS:
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
            elif req_type is HttpAPI.Request.REC_DIRS:
                return {"rec_dirs": [el.text for el in ETree.fromstring(f.read().decode("utf-8")).iter("e2location")]}
            elif req_type is HttpAPI.Request.RECORDINGS:
                return {"recordings": [{el.tag: el.text for el in el.iter()} for el in
                                       ETree.fromstring(f.read().decode("utf-8")).iter("e2movie")]}
            else:
                return {el.tag: el.text for el in ETree.fromstring(f.read().decode("utf-8")).iter()}
    except HTTPError as e:
        if req_type is HttpAPI.Request.TEST:
            raise e
        return {"error_code": e.code}
    except (URLError, ConnectionResetError) as e:
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
    except (URLError, HTTPError) as e:
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

# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2022 Dmitriy Yefremov
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Author: Dmitriy Yefremov
#


import os
import re
import socket
import time
import urllib
import xml.etree.ElementTree as ETree
from enum import Enum
from ftplib import FTP, CRLF, Error, all_errors
from http.client import RemoteDisconnected
from telnetlib import Telnet
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import (urlopen, HTTPPasswordMgrWithDefaultRealm, HTTPBasicAuthHandler, build_opener,
                            install_opener, Request)

from app.commons import log, run_task
from app.settings import SettingsType

BQ_FILES_LIST = ("tv", "radio",  # Enigma2.
                 "services.xml", "myservices.xml", "bouquets.xml", "ubouquets.xml")  # Neutrino.

DATA_FILES_LIST = ("lamedb", "lamedb5", "blacklist", "whitelist",)

STC_XML_FILE = ("satellites.xml", "terrestrial.xml", "cables.xml")
WEB_TV_XML_FILE = ("webtv.xml",)
PICONS_SUF = (".jpg", ".png")
PICONS_MAX_NUM = 1000  # Maximum picon number for sending without compression.


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
            msg = "Downloading file: {}.   Status: {}"
            resp = self.download_binary(name, f)
            msg = msg.format(name, resp)
            callback(msg) if callback else log(msg.rstrip())

            return resp

    def download_binary(self, src, fo):
        try:
            resp = str(self.retrbinary(f"RETR {src}", fo.write))
        except all_errors as e:
            resp = str(e)
            log(f"Error. {e}")

        return resp

    def download_dir(self, path, save_path, callback=None):
        """  Downloads directory from FTP with all contents.

            Creates a leaf directory and all intermediate ones. This is recursive.
         """
        os.makedirs(os.path.join(save_path, path), exist_ok=True)

        files = []
        self.dir(path, files.append)
        for f in files:
            f_data = self.get_file_data(f)
            f_path = f_data[8]

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
        except all_errors as e:
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
        except all_errors as e:
            if str(e).startswith("550"):
                self.mkd(dest)  # if not exist
                self.cwd(dest)

        for file_name in filter(picons_filter_function(files_filter), os.listdir(src)):
            self.send_file(file_name, src, callback)

    def remove_unused_bouquets(self, callback):
        bq_files = ("userbouquet.", "subbouquet.", "bouquets.xml", "ubouquets.xml")

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
            msg = "Uploading file: {}.   Status: {}"
            try:
                resp = str(self.storbinary("STOR " + file_name, f))
            except all_errors as e:
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
                    except all_errors:
                        pass  # NOP

                    try:
                        self.cwd(f)
                    except all_errors as e:
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
            except all_errors as e:
                callback(str(e))
                return

        for file in filter(picons_filter_function(files_filter), self.nlst()):
            self.delete_file(file, callback)

    def delete_file(self, file, callback=log):
        msg = "Deleting file: {}.   Status: {}"
        try:
            resp = self.delete(file)
        except all_errors as e:
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
            f_data = self.get_file_data(f)
            f_path = f"{path}/{f_data[8]}"

            if f_data[0][0] == "d":
                self.delete_dir(f_path, callback)
            else:
                self.delete_file(f_path, callback)

        msg = "Remove directory {}.   Status: {}"
        try:
            resp = self.rmd(path)
        except all_errors as e:
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
        msg = "File rename: {}.   Status: {}"
        try:
            resp = self.rename(from_name, to_name)
        except all_errors as e:
            resp = str(e)
            msg = msg.format(from_name, resp)
            log(msg)
        else:
            msg = msg.format(from_name, resp)

        if callback:
            callback(msg)

        return resp

    @staticmethod
    def get_file_data(file):
        """ Returns a prepared list of file data from a file string. """
        f_data = file.split()
        # Ignoring space in file name.
        f_data = f_data[0:9]
        f_data[8] = file[file.index(f_data[8]):]
        return f_data


def download_data(*, settings, download_type=DownloadType.ALL, callback=log, files_filter=None):
    with UtfFTP(host=settings.host, user=settings.user, passwd=settings.password) as ftp:
        ftp.encoding = "utf-8"
        callback("FTP OK.")
        save_path = settings.profile_data_path
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
            picons_path = settings.profile_picons_path
            os.makedirs(os.path.dirname(picons_path), exist_ok=True)
            ftp.download_picons(settings.picons_path, picons_path, callback, files_filter)
        # epg.dat
        if download_type is DownloadType.EPG:
            ftp.cwd(settings.epg_dat_path)
            ftp.download_files(f"{settings.profile_data_path}epg{os.sep}", "epg.dat", callback)

        callback("*** Done. ***")


def upload_data(*, settings, download_type=DownloadType.ALL, callback=log, done_callback=None,
                files_filter=None, ext_host=None):
    s_type = settings.setting_type
    use_http = s_type is SettingsType.ENIGMA_2 and settings.use_http
    data_path = settings.profile_data_path
    host, port, use_ssl = ext_host or settings.host, settings.http_port, settings.http_use_ssl
    user, password = settings.user, settings.password
    base_url = f"http{'s' if use_ssl else ''}://{host}:{port}"
    base = "web" if s_type is SettingsType.ENIGMA_2 else "control"
    url = f"{base_url}/{base}/"
    tn, ht = None, None  # Telnet, HTTP.

    try:
        use_http = use_http and test_http(host, port, user, password, use_ssl=use_ssl, skip_message=True, s_type=s_type)
    except TestException:
        log("HTTP test failed.")
        use_http = False

    try:
        if use_http:
            ht = http(user, password, base_url, callback, use_ssl, s_type)
            next(ht)
            message = get_upload_info_message(download_type)

            if s_type is SettingsType.ENIGMA_2:
                params = urlencode({"text": message, "type": 2, "timeout": 5})
            else:
                params = urlencode({"nmsg": message, "timeout": 5}, quote_via=quote)

            ht.send((f"{url}message?{params}", "Sending info message... "))

            if s_type is SettingsType.ENIGMA_2 and download_type is DownloadType.ALL:
                time.sleep(5)
                if not settings.keep_power_mode:
                    ht.send((f"{url}powerstate?newstate=0", "Toggle Standby "))
                time.sleep(2)
        else:
            if download_type is not DownloadType.PICONS:
                # Telnet
                tn = telnet(host=host, user=user, password=password, timeout=settings.telnet_timeout)
                next(tn)
                # Terminate Enigma2 or Neutrino.
                callback("Telnet initialization ...")
                tn.send("init 4")
                callback("Stopping GUI...")

        with UtfFTP(host=host, user=user, passwd=password) as ftp:
            ftp.encoding = "utf-8"
            callback("FTP OK.")
            sat_xml_path = settings.satellites_xml_path
            services_path = settings.services_path

            if download_type is DownloadType.SATELLITES:
                ftp.upload_xml(data_path, sat_xml_path, STC_XML_FILE, callback)

            if s_type is SettingsType.NEUTRINO_MP and download_type is DownloadType.WEBTV:
                ftp.upload_xml(data_path, sat_xml_path, WEB_TV_XML_FILE, callback)

            if download_type is DownloadType.BOUQUETS:
                ftp.cwd(services_path)
                ftp.upload_bouquets(data_path, settings.remove_unused_bouquets, callback)

            if download_type is DownloadType.ALL:
                ftp.upload_xml(data_path, sat_xml_path, STC_XML_FILE, callback)
                if s_type is SettingsType.NEUTRINO_MP:
                    ftp.upload_xml(data_path, sat_xml_path, WEB_TV_XML_FILE, callback)

                ftp.cwd(services_path)
                ftp.upload_bouquets(data_path, settings.remove_unused_bouquets, callback)
                ftp.upload_files(data_path, DATA_FILES_LIST, callback)

            if download_type is DownloadType.PICONS:
                p_src, p_dst = settings.profile_picons_path, settings.picons_path
                compress = all((settings.compress_picons, files_filter, len(files_filter) > PICONS_MAX_NUM))
                if compress:
                    from zipfile import ZipFile

                    z_name = "picons.zip"
                    zip_file = f"{p_src}{z_name}"
                    p_dst = os.path.abspath(os.path.join(p_dst, os.pardir))

                    if files_filter and z_name in files_filter:
                        files_filter.remove(z_name)

                    if os.path.isfile(zip_file):
                        try:
                            os.unlink(zip_file)
                        except OSError:
                            pass  # NOP

                    log("Compressing picons...")
                    with ZipFile(zip_file, "w") as zf:
                        list(map(lambda p: zf.write(os.path.join(p_src, p), arcname=p), files_filter))

                    files_filter = {z_name}

                log("Uploading...")
                ftp.upload_picons(p_src, p_dst, callback, files_filter)

                if compress:
                    if not tn:
                        callback("Telnet initialization...")
                        tn = telnet(host=host, user=user, password=password, timeout=settings.telnet_timeout)
                        next(tn)

                    callback("Extracting...")
                    cmd = f"mkdir -p {settings.picons_path} && unzip -o -q {p_dst}/{z_name} -d {settings.picons_path}"
                    tn.send(cmd)
                    ftp.delete_file(z_name)

                    try:
                        os.unlink(zip_file)
                    except OSError:
                        pass  # NOP

            if all((tn, download_type is not DownloadType.PICONS, not use_http)):
                # Resume Enigma2 or restart Neutrino.
                tn.send("init 3" if s_type is SettingsType.ENIGMA_2 else "init 6")
                callback("Starting..." if s_type is SettingsType.ENIGMA_2 else "Rebooting...")
            elif ht and use_http:
                if s_type is SettingsType.ENIGMA_2:
                    if download_type is DownloadType.BOUQUETS:
                        ht.send((f"{url}servicelistreload?mode=2", "Reloading Userbouquets."))
                    elif download_type is DownloadType.ALL:
                        ht.send((f"{url}servicelistreload?mode=0", "Reloading lamedb and Userbouquets."))
                        if not settings.keep_power_mode:
                            ht.send((f"{url}powerstate?newstate=4", "Wakeup from Standby."))
                else:
                    ht.send((f"{url}reloadchannels", "Reloading channels..."))

            if done_callback is not None:
                done_callback()
    finally:
        if tn:
            tn.close()
        if ht:
            ht.close()


def get_upload_info_message(download_type):
    if download_type is DownloadType.BOUQUETS:
        return "User bouquets will be updated!"
    elif download_type is DownloadType.ALL:
        return "All user data will be reloaded!"
    elif download_type is DownloadType.SATELLITES:
        return "Satellites.xml file will be updated!"
    elif download_type is DownloadType.PICONS:
        return "Picons will be updated!"
    return ""


# ***************** Picons *******************#

def remove_picons(*, settings, callback=log, done_callback=None, files_filter=None):
    with UtfFTP(host=settings.host, user=settings.user, passwd=settings.password) as ftp:
        ftp.encoding = "utf-8"
        callback("FTP OK.")
        ftp.delete_picons(callback, settings.picons_path, files_filter)
        if done_callback:
            done_callback()


def picons_filter_function(files_filter=None):
    return lambda f: f in files_filter if files_filter else f.endswith(PICONS_SUF)


def http(user, password, url, callback, use_ssl=False, s_type=SettingsType.ENIGMA_2):
    HttpAPI.init_auth(user, password, url, use_ssl)
    data = HttpAPI.get_post_data(url, password, url) if s_type is SettingsType.ENIGMA_2 else None

    while True:
        url, message = yield
        resp = HttpAPI.get_response(HttpAPI.Request.TEST, url, data, s_type)
        if s_type is SettingsType.ENIGMA_2:
            resp = resp.get("e2statetext", None)

        callback(f"HTTP: {message} {'Successful.' if resp and message else ''}")


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

        command = f"{command}\r\n".encode("utf-8")
        tn.write(command)

        msg = tn.read_until(command, timeout)
        while msg.endswith(command) or not msg:
            time.sleep(timeout)
            msg = tn.read_until(command, timeout)

        command = yield
        time.sleep(timeout)
        tn.write(f"{command}\r\n".encode("utf-8"))
        time.sleep(timeout)
        yield


# ***************** HTTP API ******************* #

class HttpAPI:
    _MAX_WORKERS = 4
    _TIMEOUT = 10

    class Request(str, Enum):
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
        EPG_NOW = "epgnow?bRef="
        EPG_MULTI = "epgmulti?bRef="
        # Timer
        TIMER = ""
        TIMER_LIST = "timerlist"
        # Recordings
        RECORDINGS = "movielist?dirname="
        REC_DIRS = "getlocations"
        REC_CURRENT = "getcurrlocation"
        # Screenshot
        GRUB = "grab?format=jpg&"
        # Neutrino requests.
        N_INFO = "info"
        N_ZAP = "zapto"
        N_STREAM = "build_playlist?id="

    class Remote(str, Enum):
        """ Args for HttpRequestType [REMOTE] class. """
        UP = "103"
        LEFT = "105"
        RIGHT = "106"
        DOWN = "108"
        MENU = "139"
        EXIT = "174"
        OK = "352"
        INFO = "358"
        TV = "377"
        RADIO = "385"
        AUDIO = "392"
        FAV = "393"
        RED = "398"
        GREEN = "399"
        YELLOW = "400"
        BLUE = "401"
        CH_UP = "402"
        CH_DOWN = "403"
        BACK = "412"

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
                      Request.EPG_NOW,
                      Request.EPG_MULTI,
                      Request.TIMER,
                      Request.RECORDINGS,
                      Request.N_ZAP}

    STREAM_REQUESTS = {Request.STREAM,
                       Request.STREAM_CURRENT,
                       Request.STREAM_TS,
                       Request.N_STREAM}

    def __init__(self, settings):
        from concurrent.futures import ThreadPoolExecutor as PoolExecutor
        self._executor = PoolExecutor(max_workers=self._MAX_WORKERS)

        self._settings = settings
        self._shutdown = False
        self._session_id = 0
        self._main_url = None
        self._base_url = None
        self._data = None
        self._is_owif = True
        self._s_type = SettingsType.ENIGMA_2
        self.init()

    def send(self, req_type, ref, callback=print, ref_prefix="", timeout=_TIMEOUT):
        if self._shutdown:
            return

        url = self._base_url + req_type
        data = self._data

        if req_type is self.Request.ZAP or req_type in self.STREAM_REQUESTS:
            url += quote(ref)
        elif req_type is self.Request.PLAY or req_type is self.Request.PLAYER_REMOVE:
            url = f"{url}{ref_prefix}{quote(ref).replace('%3A', '%253A')}"
        elif req_type is self.Request.GRUB:
            data = None  # Must be disabled for token-based security.
            url = f"{self._main_url}/{req_type}{ref}"
        elif req_type in self.PARAM_REQUESTS:
            url += ref

        def done_callback(f):
            callback(f.result())

        future = self._executor.submit(self.get_response, req_type, url, data, self._s_type, timeout)
        future.add_done_callback(done_callback)

    @run_task
    def init(self):
        self._s_type = self._settings.setting_type
        user, password, use_ssl = self._settings.user, self._settings.password, self._settings.http_use_ssl
        self._main_url = f"http{'s' if use_ssl else ''}://{self._settings.host}:{self._settings.http_port}"
        self._base_url = f"{self._main_url}/{'web' if self._s_type is SettingsType.ENIGMA_2 else 'control'}/"
        self.init_auth(user, password, self._main_url, use_ssl)

        self._data = None
        if self._s_type is SettingsType.ENIGMA_2:
            s_id = self.get_session_id(user, password, f"{self._main_url}/web/{self.Request.TOKEN}")
            if s_id != "0":
                self._data = urlencode({"user": user, "password": password, "sessionid": s_id}).encode("utf-8")

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

    @staticmethod
    def get_response(req_type, url, data=None, s_type=SettingsType.ENIGMA_2, timeout=_TIMEOUT):
        try:
            with urlopen(Request(url, data=data), timeout=timeout) as f:
                if s_type is SettingsType.ENIGMA_2:
                    return HttpAPI.get_e2_response_data(req_type, f)
                elif s_type is SettingsType.NEUTRINO_MP:
                    return HttpAPI.get_neutrino_response_data(req_type, f)
                else:
                    return f.read().decode("utf-8")
        except HTTPError as e:
            if req_type is HttpAPI.Request.TEST:
                raise e
            return {"error_code": e.code}
        except OSError as e:
            if req_type is HttpAPI.Request.TEST:
                raise e
        except ETree.ParseError as e:
            log("Parsing response error: {}".format(e))

        return {"error_code": -1}

    @staticmethod
    def get_e2_response_data(req_type, f):
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
        elif req_type in (HttpAPI.Request.EPG, HttpAPI.Request.EPG_NOW, HttpAPI.Request.EPG_MULTI):
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

    @staticmethod
    def get_neutrino_response_data(req_type, f):
        if req_type is HttpAPI.Request.N_INFO:
            return {"info": f.read().decode("utf-8").strip()}
        elif req_type is HttpAPI.Request.N_STREAM:
            return {"m3u": f.read().decode("utf-8")}
        return {"data": f.read().decode("utf-8")}

    @staticmethod
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

    @staticmethod
    def get_session_id(user, password, url):
        data = urllib.parse.urlencode(dict(user=user, password=password)).encode("utf-8")
        return HttpAPI.get_response(HttpAPI.Request.TOKEN, url, data=data).get("e2sessionid", "0")

    @staticmethod
    def get_post_data(base_url, password, user):
        s_id = HttpAPI.get_session_id(user, password, "{}/web/{}".format(base_url, HttpAPI.Request.TOKEN))
        data = None
        if s_id != "0":
            data = urllib.parse.urlencode({"user": user, "password": password, "sessionid": s_id}).encode("utf-8")
        return data


# ***************** Connections testing *******************#

def test_ftp(host, port, user, password, timeout=5):
    try:
        with FTP(host=host, user=user, passwd=password, timeout=timeout) as ftp:
            return ftp.getwelcome()
    except all_errors as e:
        raise TestException(e)


def test_http(host, port, user, password, timeout=5, use_ssl=False, skip_message=False, s_type=SettingsType.ENIGMA_2):
    t_msg = "Connection test!"
    if s_type is SettingsType.ENIGMA_2:
        params = urlencode({"text": t_msg, "type": 2, "timeout": timeout})
        params = "deviceinfo" if skip_message else f"message?{params}"
    elif s_type is SettingsType.NEUTRINO_MP:
        params = urlencode({"nmsg": t_msg, "timeout": 5}, quote_via=quote)
        params = "info" if skip_message else f"message?{params}"
    else:
        raise TestException("This type of settings is not supported!")

    base_url = f"http{'s' if use_ssl else ''}://{host}:{port}"
    base = "web" if s_type is SettingsType.ENIGMA_2 else "control"
    url = f"{base_url}/{base}/{params}"
    # Authentication
    HttpAPI.init_auth(user, password, base_url, use_ssl)
    data = HttpAPI.get_post_data(base_url, password, user) if s_type is SettingsType.ENIGMA_2 else None

    try:
        log("Testing HTTP connection...")
        resp = HttpAPI.get_response(HttpAPI.Request.TEST, url, data, s_type)

        if s_type is SettingsType.ENIGMA_2:
            return resp.get("e2enigmaversion", "")
        return resp
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

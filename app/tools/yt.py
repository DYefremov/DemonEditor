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


""" Module for working with YouTube service. """
import gzip
import json
import os
import re
import shutil
import sys
from html.parser import HTMLParser
from json import JSONDecodeError
from urllib import parse
from urllib.error import URLError
from urllib.request import Request, urlopen, urlretrieve

from app.commons import log
from app.settings import SEP
from app.ui.uicommons import show_notification

_TIMEOUT = 5
_HEADERS = {"User-Agent": "Mozilla/5.0 (Linux x86_64; rv:92.0) Gecko/20100101 Firefox/92.0",
            "DNT": "1",
            "Accept-Encoding": "gzip, deflate"}
_YT_PATTERN = re.compile(r"https://www.youtube.com/.+(?:v=)([\w-]{11}).*")
_YT_LIST_PATTERN = re.compile(r"https://www.youtube.com/.+?(?:list=)([\w-]{18,})?.*")
_YT_VIDEO_PATTERN = re.compile(r"https://r\d+---sn-[\w]{10}-[\w]{3,5}.googlevideo.com/videoplayback?.*")

Quality = {137: "1080p", 136: "720p", 135: "480p", 134: "360p",
           133: "240p", 160: "144p", 0: "0p", 18: "360p", 22: "720p"}


class YouTubeException(Exception):
    pass


class YouTube:
    """ Helper class for working with YouTube service. """

    _YT_INSTANCE = None
    _VIDEO_INFO_LINK = "https://youtube.com/get_video_info?video_id={}&hl=en"

    VIDEO_LINK = "https://www.youtube.com/watch?v={}"

    def __init__(self, settings, callback):
        self._settings = settings
        self._yt_dl = None
        self._callback = callback

        if self._settings.enable_yt_dl:
            try:
                self._yt_dl = YouTubeDL.get_instance(self._settings, callback=self._callback)
            except YouTubeException:
                pass  # NOP

    @classmethod
    def get_instance(cls, settings, callback=log):
        if not cls._YT_INSTANCE:
            cls._YT_INSTANCE = YouTube(settings, callback)
        return cls._YT_INSTANCE

    @staticmethod
    def is_yt_video_link(url):
        return re.match(_YT_VIDEO_PATTERN, url)

    @staticmethod
    def get_yt_id(url):
        """ Returns video id or None """
        yt = re.search(_YT_PATTERN, url)
        if yt:
            return yt.group(1)

    @staticmethod
    def get_yt_list_id(url):
        """ Returns playlist id or None """
        yt = re.search(_YT_LIST_PATTERN, url)
        if yt:
            return yt.group(1)

    def get_yt_link(self, video_id, url=None, skip_errors=False):
        """  Getting link to YouTube video by id or URL.

            Returns tuple from the video links dict and title.
         """
        if self._settings.enable_yt_dl and url:
            if not self._yt_dl:
                self._yt_dl = YouTubeDL.get_instance(self._settings, self._callback)
                if not self._yt_dl:
                    raise YouTubeException("youtube-dl initialization error.")
            return self._yt_dl.get_yt_link(url, skip_errors)

        return self.get_yt_link_by_id(video_id)

    @staticmethod
    def get_yt_link_by_id(video_id):
        """  Getting link to YouTube video by id.

            Returns tuple from the video links dict and title.
        """
        info = InnerTube().player(video_id)
        det = info.get("videoDetails", None)
        title = det.get("title", None) if det else None
        streaming_data = info.get("streamingData", None)
        fmts = streaming_data.get("formats", None) if streaming_data else None

        if fmts:
            links = {Quality[i["itag"]]: i["url"] for i in filter(
                lambda i: i.get("itag", -1) in Quality, fmts) if "url" in i}

            if links and title:
                return links, title.replace("+", " ")

        cause = None
        status = info.get("playabilityStatus", None)
        if status:
            cause = f"[{status.get('status', '')}] {status.get('reason', '')}"

        log(f"{__class__.__name__}: Getting link to video with id '{video_id}' filed! Cause: {cause}")

        return None, cause

    def get_yt_playlist(self, list_id, url=None):
        """ Returns tuple from the playlist header and list of tuples (title, video id). """
        if self._settings.enable_yt_dl and url:
            try:
                if not self._yt_dl:
                    raise YouTubeException("youtube-dl is not initialized!")

                self._yt_dl.update_options({"noplaylist": False, "extract_flat": True})
                info = self._yt_dl.get_info(url, skip_errors=False)
                if "url" in info:
                    info = self._yt_dl.get_info(info.get("url"), skip_errors=False)

                return info.get("title", ""), [(e.get("title", ""), e.get("id", "")) for e in info.get("entries", [])]
            finally:
                # Restoring default options
                if self._yt_dl:
                    self._yt_dl.update_options({"noplaylist": True, "extract_flat": False})

        return PlayListParser.get_yt_playlist(list_id)


class InnerTube:
    """ Object for interacting with the innertube API.

        Based on InnerTube class from pytube [https://github.com/pytube/pytube] project!
    """
    _BASE_URI = "https://www.youtube.com/youtubei/v1"

    _DEFAULT_CLIENTS = {
        "ANDROID": {
            "context": {"client": {"clientName": "ANDROID", "clientVersion": "16.20"}},
            "api_key": "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
        },
        "ANDROID_EMBED": {
            "context": {"client": {"clientName": "ANDROID", "clientVersion": "16.20", "clientScreen": "EMBED"}},
            "api_key": "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
        }
    }

    def __init__(self, client="ANDROID"):
        """ Initialize an InnerTube object.

            @param client: Client to use for the object. Default to web because it returns the most playback types.
        """
        self.context = self._DEFAULT_CLIENTS[client]["context"]
        self.api_key = self._DEFAULT_CLIENTS[client]["api_key"]

    @property
    def base_data(self):
        """Return the base json data to transmit to the innertube API."""
        return {"context": self.context}

    @property
    def base_params(self):
        """Return the base query parameters to transmit to the innertube API."""
        return {"key": self.api_key, "contentCheckOk": True, "racyCheckOk": True}

    def player(self, video_id):
        """ Make a request to the player endpoint. Returns raw player info results. """
        endpoint = f"{self._BASE_URI}/player"
        query = {"videoId": video_id}
        query.update(self.base_params)
        return self._call_api(endpoint, query, self.base_data) or {}

    @staticmethod
    def _call_api(endpoint, query, data):
        """ Make a request to a given endpoint with the provided query parameters and data."""
        headers = {"Content-Type": "application/json", }
        response = InnerTube._execute(f"{endpoint}?{parse.urlencode(query)}", "POST", headers=headers, data=data)

        try:
            resp = json.loads(response.read())
        except JSONDecodeError as e:
            log(f"{__class__.__name__}: Parsing response error: {e}")
        else:
            return resp

    @staticmethod
    def _execute(url, method=None, headers=None, data=None, timeout=_TIMEOUT):
        base_headers = {"User-Agent": "Mozilla/5.0", "accept-language": "en-US,en"}
        if headers:
            base_headers.update(headers)
        if data:
            # Encoding data for request.
            if not isinstance(data, bytes):
                data = bytes(json.dumps(data), encoding="utf-8")
        return urlopen(Request(url, headers=base_headers, method=method, data=data), timeout=timeout)


class PlayListParser(HTMLParser):
    """ Very simple parser to handle YouTube playlist pages. """

    def __init__(self):
        super().__init__()
        self._is_header = False
        self._header = ""
        self._playlist = []
        self._is_script = False
        self._scr_start = ('var ytInitialData = ', 'window["ytInitialData"] = ')

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._is_script = True

    def handle_data(self, data):
        if self._is_script:
            data = data.lstrip()
            if data.startswith(self._scr_start):
                data = data.split(";")[0]
                for s in self._scr_start:
                    data = data.lstrip(s)

                try:
                    resp = json.loads(data)
                except JSONDecodeError as e:
                    log(f"{__class__.__name__}: Parsing data error: {e}")
                else:
                    sb = resp.get("sidebar", None)
                    if sb:
                        for t in [t["runs"][0] for t in flat("title", sb) if "runs" in t]:
                            txt = t.get("text", None)
                            if txt:
                                self._header = txt
                                break

                    ct = resp.get("contents", None)
                    if ct:
                        for d in [(d.get("title", {}).get("runs", [{}])[0].get("text", ""),
                                   d.get("videoId", "")) for d in flat("playlistVideoRenderer", ct)]:
                            self._playlist.append(d)
            self._is_script = False

    def error(self, message):
        log(f"{__class__.__name__} Parsing error: {message}")

    @property
    def header(self):
        return self._header

    @property
    def playlist(self):
        return self._playlist

    @staticmethod
    def get_yt_playlist(play_list_id):
        """ Getting YouTube playlist by id.

           returns tuple from the playlist header and list of tuples (title, video id)
        """
        request = Request(f"https://www.youtube.com/playlist?list={play_list_id}&hl=en", headers=_HEADERS)

        with urlopen(request, timeout=_TIMEOUT) as resp:
            data = gzip.decompress(resp.read()).decode("utf-8")
            parser = PlayListParser()
            parser.feed(data)
            return parser.header, parser.playlist


class YouTubeDL:
    """ Utility class [experimental] for working with youtube-dl.

         [https://github.com/ytdl-org/youtube-dl]
     """

    _DL_INSTANCE = None
    _DownloadError = None
    _LATEST_RELEASE_URL = "https://api.github.com/repos/ytdl-org/youtube-dl/releases/latest"
    _OPTIONS = {"noplaylist": True,  # Single video instead of a playlist [ignoring playlist in URL].
                "extract_flat": False,  # Do not resolve URLs, return the immediate result.
                "quiet": True,  # Do not print messages to stdout.
                "simulate": True,  # Do not download the video files.
                "cookiefile": "cookies.txt"}  # File name where cookies should be read from and dumped to.

    def __init__(self, settings, callback):
        self._path = f"{settings.default_data_path}tools{SEP}"
        self._update = settings.enable_yt_dl_update
        self._supported = {"22", "18"}
        self._dl = None
        self._callback = callback
        self._download_exception = None
        self._is_update_process = False

        self.init()

    @classmethod
    def get_instance(cls, settings, callback=print):
        if not cls._DL_INSTANCE:
            cls._DL_INSTANCE = YouTubeDL(settings, callback)
        return cls._DL_INSTANCE

    def init(self):
        if not os.path.isfile(f"{self._path}youtube_dl{SEP}version.py"):
            self.get_latest_release()

        if self._path not in sys.path:
            sys.path.append(self._path)

        self.init_dl()

    def init_dl(self):
        try:
            import youtube_dl
        except ModuleNotFoundError as e:
            log(f"YouTubeDLHelper error: {e}")
            raise YouTubeException(e)
        except ImportError as e:
            log(f"YouTubeDLHelper error: {e}")
        else:
            if self._path not in youtube_dl.__file__:
                msg = "Another version of youtube-dl was found on your system!"
                log(msg)
                raise YouTubeException(msg)

            if self._update:
                if hasattr(youtube_dl.version, "__version__"):
                    l_ver = self.get_last_release_id()
                    cur_ver = youtube_dl.version.__version__
                    if l_ver and youtube_dl.version.__version__ < l_ver:
                        msg = f"youtube-dl has new release!\nCurrent: {cur_ver}. Last: {l_ver}."
                        show_notification(msg)
                        log(msg)
                        self._callback(msg, False)
                        self.get_latest_release()

            self._DownloadError = youtube_dl.utils.DownloadError
            self._dl = youtube_dl.YoutubeDL(self._OPTIONS)
            msg = "youtube-dl initialized..."
            show_notification(msg)
            log(msg)

    @staticmethod
    def get_last_release_id():
        """ Getting last release id. """
        url = "https://api.github.com/repos/ytdl-org/youtube-dl/releases/latest"
        try:
            with urlopen(url, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8")).get("tag_name", "0")
        except URLError as e:
            log(f"YouTubeDLHelper error [get last release id]: {e}")

    def get_latest_release(self):
        try:
            self._is_update_process = True
            log("Getting the last youtube-dl release...")

            with urlopen(YouTubeDL._LATEST_RELEASE_URL, timeout=10) as resp:
                r = json.loads(resp.read().decode("utf-8"))
                zip_url = r.get("zipball_url", None)
                if zip_url:
                    if os.path.isdir(self._path):
                        shutil.rmtree(self._path)

                    zip_file = self._path + "yt.zip"
                    os.makedirs(os.path.dirname(self._path), exist_ok=True)
                    f_name, headers = urlretrieve(zip_url, filename=zip_file)

                    import zipfile

                    with zipfile.ZipFile(f_name) as arch:
                        for info in arch.infolist():
                            pref, sep, f = info.filename.partition("/youtube_dl/")
                            if sep:
                                arch.extract(info.filename)
                                shutil.move(info.filename, f"{self._path}{sep}{f}")
                        shutil.rmtree(pref)
                        msg = "Getting the last youtube-dl release is done!"
                        show_notification(msg)
                        log(msg)
                        self._callback(msg, False)

                    if os.path.isfile(zip_file):
                        os.remove(zip_file)
                    return True
        except URLError as e:
            log(f"YouTubeDLHelper error: {e}")
            raise YouTubeException(e)
        finally:
            self._is_update_process = False

    def get_yt_link(self, url, skip_errors=False):
        """ Returns tuple from the video links [dict] and title. """
        if self._is_update_process:
            self._callback("Update process. Please wait.", False)
            return {}, ""

        info = self.get_info(url, skip_errors)
        fmts = info.get("formats", None)
        if fmts:
            return {Quality.get(int(fm["format_id"])): fm.get("url", "") for fm in fmts if
                    fm.get("format_id", "") in self._supported}, info.get("title", "")

        return {}, info.get("title", "")

    def get_info(self, url, skip_errors=False):
        try:
            return self._dl.extract_info(url, download=False)
        except URLError as e:
            log(f"YouTubeDLHelper error [get info]: {e}")
            raise YouTubeException(e)
        except self._DownloadError as e:
            log(f"YouTubeDLHelper error [get info]: {e}")
            if not skip_errors:
                raise YouTubeException(e)

    def update_options(self, options):
        self._dl.params.update(options)

    @property
    def options(self):
        return self._dl.params


def flat(key, d):
    for k, v in d.items():
        if k == key:
            yield v
        elif isinstance(v, dict):
            yield from flat(key, v)
        elif isinstance(v, list):
            for el in v:
                if isinstance(el, dict):
                    yield from flat(key, el)


if __name__ == "__main__":
    pass

""" Module for working with YouTube service """
import gzip
import json
import os
import re
import shutil
import sys
from html.parser import HTMLParser
from json import JSONDecodeError
from urllib.error import URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen, urlretrieve

from app.commons import log
from app.ui.uicommons import show_notification

_YT_PATTERN = re.compile(r"https://www.youtube.com/.+(?:v=)([\w-]{11}).*")
_YT_LIST_PATTERN = re.compile(r"https://www.youtube.com/.+?(?:list=)([\w-]{18,})?.*")
_YT_VIDEO_PATTERN = re.compile(r"https://r\d+---sn-[\w]{10}-[\w]{3,5}.googlevideo.com/videoplayback?.*")
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux i586; rv:31.0) Gecko/20100101 Firefox/69.0",
            "DNT": "1",
            "Accept-Encoding": "gzip, deflate"}

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
            return self._yt_dl.get_yt_link(url, skip_errors)

        return self.get_yt_link_by_id(video_id)

    @staticmethod
    def get_yt_link_by_id(video_id):
        """  Getting link to YouTube video by id.

            Returns tuple from the video links dict and title.
        """
        req = Request(YouTube._VIDEO_INFO_LINK.format(video_id), headers=_HEADERS)

        with urlopen(req, timeout=2) as resp:
            data = unquote(gzip.decompress(resp.read()).decode("utf-8")).split("&")
            out = {k: v for k, sep, v in (str(d).partition("=") for d in map(unquote, data))}
            player_resp = out.get("player_response", None)

            if player_resp:
                try:
                    resp = json.loads(player_resp)
                except JSONDecodeError as e:
                    log("{}: Parsing player response error: {}".format(__class__.__name__, e))
                else:
                    det = resp.get("videoDetails", None)
                    title = det.get("title", None) if det else None
                    streaming_data = resp.get("streamingData", None)
                    fmts = streaming_data.get("formats", None) if streaming_data else None

                    if fmts:
                        urls = {Quality[i["itag"]]: i["url"] for i in
                                filter(lambda i: i.get("itag", -1) in Quality, fmts) if "url" in i}

                        if urls and title:
                            return urls, title.replace("+", " ")

            stream_map = out.get("url_encoded_fmt_stream_map", None)
            if stream_map:
                s_map = {k: v for k, sep, v in (str(d).partition("=") for d in stream_map.split("&"))}
                url, title = s_map.get("url", None), out.get("title", None)
                url, title = unquote(url) if url else "", title.replace("+", " ") if title else ""
                if url and title:
                    return {Quality[0]: url}, title.replace("+", " ")

            rsn = out.get("reason", None)
            rsn = rsn.replace("+", " ") if rsn else ""
            log("{}: Getting link to video with id {} filed! Cause: {}".format(__class__.__name__, video_id, rsn))

            return None, rsn


class PlayListParser(HTMLParser):
    """ Very simple parser to handle YouTube playlist pages. """

    def __init__(self):
        super().__init__()
        self._is_header = False
        self._header = ""
        self._playlist = []
        self._is_script = False

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._is_script = True

    def handle_data(self, data):
        if self._is_script:
            data = data.lstrip()
            if data.startswith('window["ytInitialData"] = '):
                data = data.split(";")[0].lstrip('window["ytInitialData"] = ')
                try:
                    resp = json.loads(data)
                except JSONDecodeError as e:
                    log("{}: Parsing data error: {}".format(__class__.__name__, e))
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
        log("{} Parsing error: {}".format(__class__.__name__, message))

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
        request = Request("https://www.youtube.com/playlist?list={}&hl=en".format(play_list_id), headers=_HEADERS)

        with urlopen(request, timeout=2) as resp:
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
                "quiet": True,  # Do not print messages to stdout.
                "simulate": True,  # Do not download the video files.
                "cookiefile": "cookies.txt"}  # File name where cookies should be read from and dumped to.

    def __init__(self, settings, callback):
        self._path = settings.default_data_path + "tools/"
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
        if not os.path.isfile(self._path + "youtube_dl/version.py"):
            self.get_latest_release()

        if self._path not in sys.path:
            sys.path.append(self._path)

        self.init_dl()

    def init_dl(self):
        try:
            import youtube_dl
        except ModuleNotFoundError as e:
            log("YouTubeDLHelper error: {}".format(str(e)))
            raise YouTubeException(e)
        except ImportError as e:
            log("YouTubeDLHelper error: {}".format(str(e)))
        else:
            if self._update:
                if hasattr(youtube_dl.version, "__version__"):
                    l_ver = self.get_last_release_id()
                    cur_ver = youtube_dl.version.__version__
                    if l_ver and youtube_dl.version.__version__ < l_ver:
                        msg = "youtube-dl has new release!\nCurrent: {}. Last: {}.".format(cur_ver, l_ver)
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
            log("YouTubeDLHelper error [get last release id]: {}".format(e))

    def get_latest_release(self):
        try:
            self._is_update_process = True
            log("Getting the last youtube-dl release...")

            with urlopen(YouTubeDL._LATEST_RELEASE_URL, timeout=10) as resp:
                r = json.loads(resp.read().decode("utf-8"))
                zip_url = r.get("zipball_url", None)
                if zip_url:
                    zip_file = self._path + "yt.zip"
                    os.makedirs(os.path.dirname(self._path), exist_ok=True)
                    f_name, headers = urlretrieve(zip_url, filename=zip_file)

                    import zipfile

                    with zipfile.ZipFile(f_name) as arch:

                        if os.path.isdir(self._path):
                            shutil.rmtree(self._path)
                        else:
                            os.makedirs(os.path.dirname(self._path), exist_ok=True)

                        for info in arch.infolist():
                            pref, sep, f = info.filename.partition("/youtube_dl/")
                            if sep:
                                arch.extract(info.filename)
                                shutil.move(info.filename, "{}{}{}".format(self._path, sep, f))
                        shutil.rmtree(pref)
                        msg = "Getting the last youtube-dl release is done!"
                        show_notification(msg)
                        log(msg)
                        self._callback(msg, False)
                        return True
        except URLError as e:
            log("YouTubeDLHelper error: {}".format(e))
            raise YouTubeException(e)
        finally:
            self._is_update_process = False

    def get_yt_link(self, url, skip_errors=False):
        """ Returns tuple from the video links [dict] and title. """
        if self._is_update_process:
            self._callback("Update process. Please wait.", False)
            return {}, ""

        try:
            info = self._dl.extract_info(url, download=False)
        except URLError as e:
            log(str(e))
            raise YouTubeException(e)
        except self._DownloadError as e:
            log(str(e))
            if not skip_errors:
                raise YouTubeException(e)
        else:
            fmts = info.get("formats", None)
            if fmts:
                return {Quality.get(int(fm["format_id"])): fm.get("url", "") for fm in fmts if
                        fm.get("format_id", "") in self._supported}, info.get("title", "")

            return {}, info.get("title", "")


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

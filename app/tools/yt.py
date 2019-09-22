""" Module for working with YouTube service """
import json
import re
import urllib
from html.parser import HTMLParser
from json import JSONDecodeError
from urllib.request import Request

from app.commons import log

_YT_PATTERN = re.compile(r"https://www.youtube.com/.+(?:v=)([\w-]{11}).*")
_YT_LIST_PATTERN = re.compile(r"https://www.youtube.com/.+?(?:list=)([\w-]{23,})?.*")
_YT_VIDEO_PATTERN = re.compile(r"https://r\d+---sn-[\w]{10}-[\w]{3,5}.googlevideo.com/videoplayback?.*")
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux i586; rv:31.0) Gecko/20100101 Firefox/69.0"}

Quality = {137: "1080p", 136: "720p", 135: "480p", 134: "360p",
           133: "240p", 160: "144p", 0: "0p", 18: "360p", 22: "720p"}


class YouTube:
    """ Helper class for working with YouTube service. """

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

    @staticmethod
    def get_yt_link(video_id):
        """ Getting link to YouTube video by id.

            returns tuple from the video links dict and title
         """
        req = Request("https://youtube.com/get_video_info?video_id={}".format(video_id), headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = urllib.request.unquote(resp.read().decode("utf-8")).split("&")
            out = {k: v for k, sep, v in (str(d).partition("=") for d in map(urllib.request.unquote, data))}
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
                                filter(lambda i: i.get("itag", -1) in Quality, fmts)}

                        if urls and title:
                            return urls, title.replace("+", " ")

            stream_map = out.get("url_encoded_fmt_stream_map", None)
            if stream_map:
                s_map = {k: v for k, sep, v in (str(d).partition("=") for d in stream_map.split("&"))}
                url, title = s_map.get("url", None), out.get("title", None)
                url, title = urllib.request.unquote(url) if url else "", title.replace("+", " ") if title else ""
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
                        for d in [(d["title"]["simpleText"], d["videoId"]) for d in flat("playlistVideoRenderer", ct)]:
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

        with urllib.request.urlopen(request, timeout=2) as resp:
            data = resp.read().decode("utf-8")
            parser = PlayListParser()
            parser.feed(data)
            return parser.header, parser.playlist


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
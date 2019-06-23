""" Module for working with YouTube service """
import re
import urllib
from html.parser import HTMLParser
from urllib.request import Request

_YT_PATTERN = re.compile(r"https://www.youtube.com/.+(?:v=)([\w-]{11}).*")
_YT_LIST_PATTERN = re.compile(r"https://www.youtube.com/.+?(?:list=)([\w-]{34})?.*")
_YT_VIDEO_PATTERN = re.compile(r"https://r\d+---sn-[\w]{10}-[\w]{3,5}.googlevideo.com/videoplayback?.*")
_HEADERS = {"User-Agent": "Mozilla/5.0"}


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

            returns tuple from the video link and title
         """
        req = Request("https://youtube.com/get_video_info?video_id={}".format(video_id), headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = resp.read().decode("utf-8").split("&")
            out = {k: v for k, sep, v in (str(d).partition("=") for d in map(urllib.request.unquote, data))}
            stream_map = out.get("url_encoded_fmt_stream_map", None)
            if stream_map:
                s_map = {k: v for k, sep, v in (str(d).partition("=") for d in stream_map.split("&"))}
                url, title = s_map.get("url", None), out.get("title", None)
                return urllib.request.unquote(url) if url else "", title.replace("+", " ") if title else ""
            return "", ""


class PlayListParser(HTMLParser):
    """ Very simple parser to handle YouTube playlist pages. """

    def __init__(self):
        super().__init__()
        self._is_header = False
        self._header = ""
        self._playlist = []

    def handle_starttag(self, tag, attrs):
        if tag == "h1" and ("class", "pl-header-title") in attrs:
            self._is_header = True

        elif tag == "tr" and ("class", "pl-video yt-uix-tile ") in attrs:
            p_data = {k: v for k, v in attrs}
            self._playlist.append((p_data.get("data-title", None), p_data.get("data-video-id", None)))

    def handle_data(self, data):
        if self._is_header:
            self._header = data.strip()

    def handle_endtag(self, tag):
        if self._is_header:
            self._is_header = False

    def error(self, message):
        pass

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
        request = Request("https://www.youtube.com/playlist?list={}".format(play_list_id), headers=_HEADERS)

        with urllib.request.urlopen(request, timeout=2) as resp:
            data = resp.read().decode("utf-8")
            parser = PlayListParser()
            parser.feed(data)
            return parser.header, parser.playlist


if __name__ == "__main__":
    pass

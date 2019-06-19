""" Module for working with YouTube service """
import re
import urllib
from urllib.request import Request

_YT_PATTERN = re.compile(r"https://www.youtube.com/.+(?:v=|\/)([\w-]{11})&?(list=)?([\w-]{34})?.*")
_YT_VIDEO_PATTERN = re.compile(r"https://r\d+---sn-[\w]{10}-[\w]{3,5}.googlevideo.com/videoplayback?.*")


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
    def get_yt_link(video_id):
        """ Getting link to YouTube video by id.

            returns tuple from the video link and title
         """
        headers = {"User-Agent": "Mozilla/5.0"}
        req = Request("https://youtube.com/get_video_info?video_id={}".format(video_id), headers=headers)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = resp.read().decode('utf-8').split("&")
            out = {k: v for k, sep, v in (str(d).partition("=") for d in map(urllib.request.unquote, data))}
            stream_map = out.get("url_encoded_fmt_stream_map", None)
            if stream_map:
                s_map = {k: v for k, sep, v in (str(d).partition("=") for d in stream_map.split("&"))}
                url, title = s_map.get("url", None), out.get("title", None)
                return urllib.request.unquote(url) if url else "", title.replace("+", " ") if title else ""
            return "", ""

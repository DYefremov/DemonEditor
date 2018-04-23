""" Module for download satellites from internet ("flysat.com")
    for  replace or update current satellites.xml file.
"""
import requests

from html.parser import HTMLParser


class SatellitesParser(HTMLParser):
    """ Parser for satellite html page. (https://www.lyngsat.com/*sat-name*.html) """

    _HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:45.0) Gecko/20100101 Firefox/59.02"}

    def __init__(self, url, entities=False, separator=' '):

        HTMLParser.__init__(self)

        self._parse_html_entities = entities
        self._separator = separator
        self._is_td = False
        self._is_th = False
        self._is_provider = False
        self._current_row = []
        self._current_cell = []
        self._rows = []
        self._url = url

    def handle_starttag(self, tag, attrs):
        if tag == 'td':
            self._is_td = True
        if tag == 'tr':
            self._is_th = True
        if tag == "a":
            self._current_row.append(attrs[0][1])

    def handle_data(self, data):
        """ Save content to a cell """
        if self._is_td or self._is_th:
            self._current_cell.append(data.strip())

    def handle_endtag(self, tag):
        if tag == 'td':
            self._is_td = False
        elif tag == 'tr':
            self._is_th = False

        if tag in ('td', 'th'):
            final_cell = self._separator.join(self._current_cell).strip()
            self._current_row.append(final_cell)
            self._current_cell = []
        elif tag == 'tr':
            row = self._current_row
            self._rows.append(row)
            self._current_row = []

    def error(self, message):
        pass

    def get_satellites(self):
        self.reset()
        request = requests.get(url=self._url, headers=self._HEADERS)
        reason = request.reason
        if reason == "OK":
            print(reason)
            self.feed(request.text)
            if self._rows:
                for num, sat in enumerate(filter(lambda x: all(x) and len(x) == 5, self._rows)):
                    print(num + 1, sat)
        else:
            print(reason)


if __name__ == "__main__":
    parser = SatellitesParser(url="https://www.flysat.com/satlist.php")
    parser.get_satellites()

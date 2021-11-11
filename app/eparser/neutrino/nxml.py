# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2018-2021 Dmitriy Yefremov
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


""" Additional module for working with Neutrino xml files. """
import re
from xml.dom.minidom import parseString, Document, Element, Node
from xml.parsers.expat import ExpatError

from app.commons import log


class XmlHandler:
    """ Utility class for handling Neutrino xml files. """
    __slots__ = ()

    ERROR_MESSAGE = "The file [{}] is not formatted correctly or contains invalid characters! Cause: {}"

    @staticmethod
    def parse(path):
        """ Parses a file into the DOM by filename. """
        try:
            return parseString(open(path, "r", encoding="utf-8", errors="ignore").read())
        except ExpatError as e:
            # Some neutrino configuration files may contain text data with invalid character ['&'].
            # https://www.w3.org/TR/xml/#syntax
            # Apparently there is an error in Neutrino itself and the document is not initially formed correctly.
            log(XmlHandler.ERROR_MESSAGE.format(path, e))

            return XmlHandler.preprocess(path)

    @staticmethod
    def preprocess(path):
        """ Pre-processing xml [for '&' symbol] for correct parsing. """
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            pat = re.compile("&([^;\\W]*([^;\\w]|$))")
            log("Processing the file '{}'...".format(path))
            try:
                dom = parseString(re.sub(pat, "&amp;", f.read()))
            except ExpatError as e:
                msg = XmlHandler.ERROR_MESSAGE.format(path, e)
                log(msg)
                raise ValueError(e)
            else:
                log("Done!")
                return dom


class NeutrinoDocument(Document):

    def createElement(self, tag_name):
        e = NElement(tag_name)
        e.ownerDocument = self
        return e

    def write_xml(self, path):
        self.writexml(open(path, "w", encoding="utf-8"), addindent="    ", newl="\n", encoding="UTF-8")


class NElement(Element):

    def writexml(self, writer, indent="", add_indent="", new_line=""):
        """ Overridden specifically for neutrino for more correct [&apos; -> optional] xml attrs generation. """
        writer.write(indent + "<" + self.tagName)
        attrs = self._get_attributes()

        for a_name in attrs.keys():
            writer.write(" %s=\"" % a_name)
            self.write_data(writer, attrs[a_name].value)
            writer.write("\"")
        if self.childNodes:
            writer.write(">")
            if len(self.childNodes) == 1 and self.childNodes[0].nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE):
                self.childNodes[0].writexml(writer, '', '', '')
            else:
                writer.write(new_line)
                for node in self.childNodes:
                    node.writexml(writer, indent + add_indent, add_indent, new_line)
                writer.write(indent)
            writer.write("</%s>%s" % (self.tagName, new_line))
        else:
            writer.write("/>%s" % new_line)

    @staticmethod
    def write_data(writer, data):
        """ Writes data chars to writer."""
        if data:
            data = data.replace("&", "&amp;").replace("<", "&lt;").replace("\"", "&quot;").replace(">", "&gt;")
            data = data.replace("'", "&apos;")
            writer.write(data)

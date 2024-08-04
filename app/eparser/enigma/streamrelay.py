# -*- coding: utf-8 -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2024 Dmitriy Yefremov
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


"""  Additional module to use stream relay functionality.

     Reads/Writes 'whitelist_streamrelay' file.
 """
import os.path
from contextlib import suppress

from app.commons import log

_FILE_NAME = "whitelist_streamrelay"


class StreamRelay(dict):
    """ Class to hold/process service references used by a stream relay. """

    def refresh(self, path):
        self.clear()
        f_path = f"{path}{_FILE_NAME}"
        if os.path.isfile(f_path):
            log("Updating stream relay cache...")
            with suppress(FileNotFoundError):
                with open(f"{path}{_FILE_NAME}", "r", encoding="utf-8") as file:
                    refs = filter(None, (x.rstrip("\n") for x in file.readlines()))
                    self.update(self.get_ref_data(ref) for ref in refs)

    def get_ref_data(self, ref):
        """ Returns tuple from FAV ID and ref or ref and None for comments. """
        data = ref.split(":")
        if len(data) == 10:
            return f"{data[3]}:{data[4]}:{data[5]}:{data[6]}", ref
        elif len(data) > 10:
            return ref.replace("%3a", "%3A"), ref
        return ref, None

    def save(self, path):
        """ Saves current refs to a file.

            If no refs is present, delites current relay file.
        """
        f_name = f"{path}{_FILE_NAME}"
        if len(self):
            with open(f_name, "w", encoding="utf-8") as file:
                file.writelines([f"{v if v else k}\n\n" for k, v in self.items()])
        else:
            if os.path.exists(f_name):
                os.remove(f_name)


if __name__ == "__main__":
    pass

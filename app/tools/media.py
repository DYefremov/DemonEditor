import concurrent.futures
import os
import shutil
import signal
import subprocess
import sys
import urllib
from enum import Enum

from urllib.request import Request, urlopen
from app.commons import run_task


class MediaException(Exception):
    pass


class Commands(Enum):
    STATUS = "http://127.0.0.1:{}/requests/status.xml"
    PLAY = "http://127.0.0.1:{}/requests/status.xml?command=in_play&input={}"
    STOP = "http://127.0.0.1:{}/requests/status.xml?command=pl_stop"


class Player:
    is_darwin = sys.platform.startswith("darwin")
    _VLC_EXEC = "/Applications/VLC.app/Contents/MacOS/VLC" if is_darwin else "vlc"
    _START_COMMAND = [_VLC_EXEC, "--extraintf", "http", "--intf", "dummy", "--quiet"]
    if not is_darwin:
        _START_COMMAND.append("--no-xlib")

    _current_process = None

    def __init__(self, port="8080"):
        if shutil.which(self._VLC_EXEC) is None:
            raise MediaException("No VLC is found. Check that it is installed!")

        self._port = port
        self._state = Commands.STOP
        self._player = None
        self._mrl = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    @run_task
    def new_instance(self):
        if not self._current_process:
            self._current_process = subprocess.Popen(self._START_COMMAND, preexec_fn=os.setsid)
            self._current_process.communicate()

    def play(self, mrl=None):
        if mrl:
            self.set_mrl(mrl)
        self._executor.submit(self.open_command, Commands.PLAY)

    def open_command(self, command):
        url = Commands.STOP.value.format(self._port)
        if command is Commands.PLAY:
            url = Commands.PLAY.value.format(self._port, self._mrl)
        try:
            with urlopen(url, timeout=5) as f:
                self._state = command
        except Exception:
            pass
        else:
            print("Opening url: {}".format(url))

    def stop(self):
        if self._state is Commands.PLAY:
            self._executor.submit(self.open_command, Commands.STOP)

    def pause(self):
        pass

    def set_time(self, time):
        pass

    @run_task
    def release(self):
        if self._current_process and self._current_process.poll() is None:
            # Good explanation here: https://stackoverflow.com/a/4791612
            os.killpg(os.getpgid(self._current_process.pid), signal.SIGTERM)

    def set_mrl(self, mrl):
        self._mrl = urllib.request.quote(mrl)

    def is_playing(self):
        return self._state

    def set_full_screen(self, full):
        pass


if __name__ == "__main__":
    pass

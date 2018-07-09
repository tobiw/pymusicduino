from pythonosc import udp_client
from subprocess import check_call


class Looper:
    PORT = 9951

    def __init__(self):
        self._osc = udp_client.SimpleUDPClient('127.0.0.1', self.PORT)
        self._current_loop = 0

    def _send_osc(self, cmd):
        self._osc.send_message('/sl/{:d}/hit'.format(self._current_loop), cmd)

    def enable(self, enable):
        check_call(['systemctl', 'start' if enable else 'stop', 'sooperlooper'])

    def undo(self):
        self._send_osc('undo')

    def redo(self):
        self._semd_osc('redo')

    def record(self, insert=False):
        self._send_osc('insert' if insert else 'record')

    def overdub(self, multiply=False):
        self._send_osc('multiply' if multiply else 'overdub')

    def mute(self, trigger=False):
        self._send_osc('mute_trigger' if trigger else 'mute')

    def pause(self):
        self._send_osc('pause')

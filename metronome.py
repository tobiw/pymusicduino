import subprocess
import time

from threading import Thread
from pythonosc import udp_client, dispatcher, osc_server


class Metronome:
    PORT = 9959

    def __init__(self):
        self._bpm = 120
        subprocess.call(['killall', 'klick'])

        # Start klick process in background
        self._klick_process = subprocess.Popen(['klick', '-o', str(self.PORT), '-P'])
        time.sleep(1)

        self._running = True

        # Communicate with klick via OSC
        self._klick_osc = udp_client.SimpleUDPClient('127.0.0.1', self.PORT)

        # Set sensible default volume and max bpm
        self._klick_osc.send_message('/klick/config/set_volume', 0.5)
        self._klick_osc.send_message('/klick/simple/set_tempo_limit', 300)

        # Start OSC server for receiving responses
        self._dispatcher = dispatcher.Dispatcher()
        self._dispatcher.map('/*', self._osc_response)
        self._server = osc_server.ThreadingOSCUDPServer(('0.0.0.0', self.PORT + 1), self._dispatcher)
        self._thread = Thread(target=self._server.serve_forever)
        self._thread.start()

    def quit(self):
        self._server.shutdown()
        self._klick_osc.send_message('/klick/quit', [])
        self._klick_process.kill()

    def ping(self):
        self._klick_osc.send_message('/klick/ping', str(self.PORT + 1))

    def _osc_response(self, uri, *args):
        if uri == '/klick/pong':
            pass
        elif uri == '/klick/simple/tempo':
            self._bpm = int(args[0])

    def _query_klick(self):
        self._klick_osc.send_message('/klick/simple/query', str(self.PORT + 1))

    def get_bpm(self):
        """Query klick for current bpm"""
        self._query_klick()
        return self._bpm

    @property
    def bpm(self):
        """Return stored bpm"""
        return self._bpm

    @property
    def is_running(self):
        return self._running

    def tap(self):
        self._klick_osc.send_message('/klick/simple/tap', [])

    def set_bpm(self, bpm):
        if bpm < 10 or bpm > 300:
            raise ValueError('bpm has to be within 10 and 300')
        self._bpm = bpm
        self._klick_osc.send_message('/klick/simple/set_tempo', bpm)

    def enable(self, enable):
        self._running = enable
        self._klick_osc.send_message('/klick/metro/' + ('start' if enable else 'stop'), [])

    def set_volume(self, volume):
        self._klick_osc.send_message('/klick/config/set_volume', volume)

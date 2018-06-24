import subprocess
import time

from pythonosc import udp_client


class Metronome:
    PORT = 9959

    def __init__(self):
        self._bpm = 120
        subprocess.call(['killall', 'klick'])

        # Start klick process in background
        self._klick_process = subprocess.Popen(['klick', '-o', str(self.PORT), '-P'])
        time.sleep(1)

        # Communicate with klick via OSC
        self._klick_osc = udp_client.SimpleUDPClient('127.0.0.1', self.PORT)

        # Set sensible default volume
        self._klick_osc.send_message('/klick/config/set_volume', 0.5)

    def quit(self):
        self._klick_process.kill()

    @property
    def bpm(self):
        return self._bpm

    def tap(self):
        self._klick_osc.send_message('/klick/simple/tap', [])

    def set_bpm(self, bpm):
        if bpm < 10 or bpm > 300:
            raise ValueError('bpm has to be within 10 and 300')
        self._bpm = bpm
        self._klick_osc.send_message('/klick/simple/set_tempo', bpm)

    def enable(self, enable):
        self._klick_osc.send_message('/klick/metro/' + ('start' if enable else 'stop'), [])

    def set_volume(self, volume):
        self._klick_osc.send_message('/klick/config/set_volume', volume)

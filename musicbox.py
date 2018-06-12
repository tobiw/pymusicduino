import time

from footpedal import MidiToOsc
from osc_server import FootpedalOscServer


class MusicBox:
    MODE_PRESET = 'preset'
    MODE_STOMP = 'stomp'
    MODE_LOOPER = 'looper'
    MODE_TUNER = 'tuner'

    def __init__(self):
        self._current_mode = self.MODE_PRESET
        self._selected_stompbox = 0  # 0 = global parameters, 1-8 = actual stompboxes
        self._last_tap_time = 0
        self._tap_tempo = 0

        self._midi_to_osc = MidiToOsc('Arduino Micro')  # works via callbacks, so not blocking

        self._osc_server = FootpedalOscServer(self.cb_mode, self.cb_preset,
                                              self.cb_stomp_enable, self.cb_stomp_select,
                                              self.cb_looper, self.cb_tap, self.cb_slider)

    def run(self):
        self._osc_server.start()
        self._osc_server._thread.join()

    def cb_mode(self, uri, msg=None):
        mode = uri.rsplit('/', 1)[-1]
        assert mode in [self.MODE_PRESET, self.MODE_STOMP, self.MODE_LOOPER, self.MODE_TUNER]
        print("MODE {}".format(mode))
        self._current_mode = mode

    def cb_preset(self, uri, msg=None):
        preset_id = int(uri.rsplit('/', 1)[-1])
        assert 0 < preset_id < 100
        print("PRESET {:d}".format(preset_id))
        # TODO: tell mod-host to load preset x
        # TODO: if preset contains looper: start sooperlooper

    def cb_stomp_enable(self, uri, msg=None):
        stomp_id = int(uri.split('/')[2])
        assert 0 < stomp_id < 10
        print("STOMP ENABLE {:d}".format(stomp_id))
        # TODO: communicate bypass enable/disable to mod-host

    def cb_stomp_select(self, uri, msg=None):
        stomp_id = int(uri.split('/')[2])
        assert 0 < stomp_id < 10
        print("STOMP select {:d}".format(stomp_id))
        self._selected_stompbox = stomp_id

    def cb_looper(self, uri, msg=None):
        _, command = uri.rsplit('/', 1)
        if command in ['undo', 'record', 'overdub']:
            self._looper_osc.send_message("/sl/0/hit", command)
            print("Sent /sl/0/hit s:{:s} to sooperlooper".format(command))
        else:
            print("Invalid sooperlooper command {:s}".format(command))

    def cb_tap(self, uri, msg=None):
        tap_tempo = msg if msg else uri.rsplit('/', 1)[-1]
        tap_tempo = int(tap_tempo)
        print("received tap value {}".format(str(tap_tempo)))
        if tap_tempo < 30:
            # Calculate tap tempo
            now = time.time()
            if self._last_tap_time == 0:
                self._tap_tempo = 0
            else:
                self._tap_tempo = 60 / (now - self._last_tap_time)
                print("TAP TEMPO: {:d}".format(int(self._tap_tempo)))
            self._last_tap_time = now
        else:
            self._tap_tempo = tap_tempo

    def cb_slider(self, uri, msg=None):
        _, slider_id, value = uri.rsplit('/', 2)
        slider_id = int(slider_id)
        value = float(value)
        print("SLIDER {:d} = {:f}".format(slider_id, value))
        # TODO: tell mod-host/sooperlooper to set param x


if __name__ == '__main__':
    MusicBox().run()

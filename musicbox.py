import enum
import subprocess
import time
import yaml

from footpedal import MidiToOsc
from pedalboard import Graph, Plugin
from osc_server import FootpedalOscServer


def create_graph_from_config(filename):
    """
    Loads a YAML file (could easily support JSON as well) and creates
    a graph for defined plugins and connections. Also returns
    other settings separately.
    """
    with open(filename, 'r') as f:
        data = yaml.safe_load(f)

    settings = {
        'name': data['preset']['name'],
        'author': data['preset']['author'],
        'global_parameters': data['preset']['global_parameters']
    }

    plugins = [Plugin(sb['lv2'], i) for i, sb in enumerate(data['preset']['stompboxes'])]
    connections = [sb['connections'] or [] for sb in data['preset']['stompboxes']]

    graph = Graph(plugins)
    for i, c in enumerate(connections):
        graph.add_edges_to_index(i, c)

    return graph


class Mode(enum.Enum):
    PRESET = 0
    STOMP = 1
    LOOPER = 2
    METRONOME = 3


class MusicBox:
    OSC_MODES = { 'preset': Mode.PRESET, 'stomp': Mode.STOMP, 'looper': Mode.LOOPER, 'metronome': Mode.METRONOME }

    def __init__(self):
        self._current_mode = Mode.PRESET
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
        """Handle incoming /mode/... OSC message"""
        mode = uri.rsplit('/', 1)[-1]
        assert mode in self.OSC_MODES.keys()
        print("MODE {} -> {}".format(mode, self.OSC_MODES[mode]))
        self._current_mode = self.OSC_MODES[mode]
        subprocess.call(['./midisend', '0', str(self._current_mode.value)])

    def cb_preset(self, uri, msg=None):
        """Handle incoming /preset/<N> OSC message"""
        preset_id = int(uri.rsplit('/', 1)[-1])
        assert 0 < preset_id < 100
        print("PRESET {:d}".format(preset_id))
        self._pedalboard = create_graph_from_config('preset0{:d}.yaml'.format(preset_id))
        # TODO: tell mod-host to load graph: go through graph nodes and tell mod-host, then go through connections (VIA ModHostClient!)
        for node in self._pedalboard.nodes:
            print("mod-host: add effect " + str(node))
        for node in self._pedalboard.nodes:
            print("mod-host: add connection {!s} -> [{!s}] -> {!s}".format(str(self._pedalboard.get_incoming_edges(node)), str(node), str(self._pedalboard.get_outgoing_edges(node))))
        # TODO: if preset contains looper: start sooperlooper

    def cb_stomp_enable(self, uri, msg=None):
        """Handle incoming /stomp/<N>/enable OSC message"""
        stomp_id = int(uri.split('/')[2])
        assert 0 < stomp_id < 10
        print("STOMP ENABLE {:d}".format(stomp_id))
        # TODO: communicate bypass enable/disable to mod-host

    def cb_stomp_select(self, uri, msg=None):
        """Handle incoming /stomp/<N>/select OSC message"""
        stomp_id = int(uri.split('/')[2])
        assert 0 < stomp_id < 10
        print("STOMP select {:d}".format(stomp_id))
        self._selected_stompbox = stomp_id

    def cb_looper(self, uri, msg=None):
        """Handle incoming /looper OSC messages to be proxied to sooperlooper"""
        _, command = uri.rsplit('/', 1)
        if command in ['undo', 'record', 'overdub']:
            self._osc_server.send_looper_osc("/sl/0/hit", command)
            print("Sent /sl/0/hit s:{:s} to sooperlooper".format(command))
        else:
            print("Invalid sooperlooper command {:s}".format(command))

    def cb_tap(self, uri, msg=None):
        """Handle incoming /tap/<N> OSC message and set or calculate tap tempo"""
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
        """Handle incoming /slider/<N> OSC message"""
        _, slider_id, value = uri.rsplit('/', 2)
        slider_id = int(slider_id)
        value = float(value)
        print("SLIDER {:d} = {:f}".format(slider_id, value))
        # TODO: tell mod-host/sooperlooper to set param x


if __name__ == '__main__':
    MusicBox().run()

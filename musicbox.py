import enum
import logging
import subprocess
import time
import yaml

from footpedal import MidiToOsc
from mod_host import ModHostClient, Plugin
from osc_server import FootpedalOscServer
from pedalboard_graph import PedalboardGraph


MIDISEND_BIN = '/home/tobiw/code/rust/midisend/target/release/midisend'


logger = logging.getLogger('musicbox')
logger.setLevel(logging.DEBUG)
con_handler = logging.StreamHandler()
con_handler.setLevel(logging.DEBUG)
con_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(con_handler)


class Mode(enum.Enum):
    PRESET = 0
    STOMP = 1
    LOOPER = 2
    METRONOME = 3


class MusicBox:
    OSC_MODES = {'preset': Mode.PRESET, 'stomp': Mode.STOMP, 'looper': Mode.LOOPER, 'metronome': Mode.METRONOME}

    def __init__(self):
        self._log = logging.getLogger('musicbox.MusicBox')

        self._selected_stompbox = 0  # 0 = global parameters, 1-8 = actual stompboxes
        self._last_tap_time = 0
        self._tap_tempo = 0

        self._midi_to_osc = MidiToOsc('Arduino Micro')  # works via callbacks, so not blocking

        self._osc_server = FootpedalOscServer(self.cb_mode, self.cb_preset,
                                              self.cb_stomp_enable, self.cb_stomp_enable,
                                              self.cb_looper, self.cb_tap, self.cb_slider)

        self._modhost = ModHostClient()

    def run(self):
        self._osc_server.start()
        self._osc_server._thread.join()

    def _create_graph_from_config(self, filename):
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

        self._log.debug('yaml preset data: ' + str(data['preset']))

        plugins = [Plugin(sb['lv2'], sb['connections']) for sb in data['preset']['stompboxes']]
        pb = PedalboardGraph(plugins)

        # Assign index to each node
        for p in pb.nodes:
            p._index = pb.get_index(p)

        # Add graph edges (connections between effects)
        for p in pb.nodes:
            self._log.debug('Adding edges {!s} for node {!s}'.format(p._connections, p))
            effect_connections = []
            for i, c in enumerate(p._connections):  # go through outgoing connections
                p_in = pb.get_node_from_index(c)
                assert p_in is not None
                if p_in.has_stereo_input:
                    effect_connections.append('effect_{}'.format(p_in.index) + ('in_l' if i == 0 else 'in_r'))
                else:
                    effect_connections.append('effect_{}:in'.format(p_in.index))
            pb.add_edges(p, effect_connections)

        self._log.debug("Graph with edges:\n" + str(pb))
        pb.settings = settings
        return pb

    def _load_preset(self, yaml_file):
        # Cleanup existing pedalboard in mod-host
        self._modhost.remove_all_effects()

        # Create plugins which will add them to the board
        self._pedalboard = self._create_graph_from_config(yaml_file)

        # Add nodes (effects) to mod-host
        for node in self._pedalboard.nodes:
            self._log.info("mod-host: add effect " + str(node))
            self._modhost.add_effect(node)

        # Add edges (connections) to mod-host
        for node in self._pedalboard.nodes:
            self._log.info("mod-host: add connection {!s} -> [{!s}] -> {!s}".format(str(self._pedalboard.get_incoming_edges(node)), str(node), str(self._pedalboard.get_outgoing_edges(node))))
            self._modhost.connect_effect(node, self._pedalboard.get_incoming_edges(node), self._pedalboard.get_outgoing_edges(node))

        if self._pedalboard.nodes[0].name == 'GxTubeScreamer':
            self._modhost.set_parameter(self._pedalboard.nodes[0], 'fslider0_', 0)

    def cb_mode(self, uri, msg=None):
        """Handle incoming /mode/... OSC message"""
        mode = uri.rsplit('/', 1)[-1]
        assert mode in self.OSC_MODES.keys()
        self._log.info("MODE {} -> {}".format(mode, self.OSC_MODES[mode]))
        subprocess.call([MIDISEND_BIN, '0', str(self.OSC_MODES[mode].value)])

        if self.OSC_MODES[mode] == Mode.PRESET:
            pass
        elif self.OSC_MODES[mode] == Mode.STOMP:
            self._load_preset('preset_stompboxes.yaml')
        elif self.OSC_MODES[mode] == Mode.LOOPER:
            # TODO: connect sooperlooper
            pass
        elif self.OSC_MODES[mode] == Mode.METRONOME:
            # TODO: play metronome
            pass

    def cb_preset(self, uri, msg=None):
        """Handle incoming /preset/<N> OSC message"""
        preset_id = int(uri.rsplit('/', 1)[-1])
        assert 0 < preset_id < 100
        self._log.info("PRESET {:d}".format(preset_id))
        self._load_preset('preset0{:d}.yaml'.format(preset_id))

    def cb_stomp_enable(self, uri, msg=None):
        """Handle incoming /stomp/<N>/enable OSC message"""
        _, _, stomp_id, op = uri.split('/')
        stomp_id = int(stomp_id)
        self._log.debug('cb_stomp_{}: {:d}'.format(op, stomp_id))
        assert 0 < stomp_id < 10
        assert op in ['enable', 'select']

        if op == 'select':
            self._selected_stompbox = stomp_id
        elif op == 'enable':
            assert self._pedalboard
            p = self._pedalboard.get_node_from_index(stomp_id - 1)
            if p:
                assert p.index == stomp_id - 1
                p.is_enabled = not p.is_enabled
                self._log.info('STOMP {} "{}" ENABLE {:d}'.format(p.index, p.name, p.is_enabled))
                self._modhost.bypass_effect(p)

    def cb_looper(self, uri, msg=None):
        """Handle incoming /looper OSC messages to be proxied to sooperlooper"""
        _, command = uri.rsplit('/', 1)
        if command in ['undo', 'record', 'overdub']:
            self._osc_server.send_looper_osc("/sl/0/hit", command)
            self._log.info("Sent /sl/0/hit s:{:s} to sooperlooper".format(command))
        else:
            self._log.error("Invalid sooperlooper command {:s}".format(command))

    def cb_tap(self, uri, msg=None):
        """Handle incoming /tap/<N> OSC message and set or calculate tap tempo"""
        tap_tempo = msg if msg else uri.rsplit('/', 1)[-1]
        tap_tempo = int(tap_tempo)
        self._log.info("received tap value {}".format(str(tap_tempo)))
        if tap_tempo < 30:
            # Calculate tap tempo
            now = time.time()
            if self._last_tap_time == 0:
                self._tap_tempo = 0
            else:
                self._tap_tempo = 60 / (now - self._last_tap_time)
                self._log.debug("TAP TEMPO: {:d}".format(int(self._tap_tempo)))
            self._last_tap_time = now
        else:
            self._tap_tempo = tap_tempo

    def cb_slider(self, uri, msg=None):
        """Handle incoming /slider/<N> OSC message"""
        _, slider_id, value = uri.rsplit('/', 2)
        slider_id = int(slider_id)
        value = float(value)
        self._log.info("SLIDER {:d} = {:f}".format(slider_id, value))
        # TODO: tell mod-host/sooperlooper to set param x


if __name__ == '__main__':
    MusicBox().run()

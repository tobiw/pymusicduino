import enum
import logging
import time
import yaml

from footpedal import MidiToOsc
from looper import Looper
from metronome import Metronome
from midisend import midisend
from mod_host import ModHostClient, Plugin
from osc_server import FootpedalOscServer
from pedalboard_graph import PedalboardGraph


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

        # Internal attributes
        self._selected_stompbox = 1  # 0 = global parameters, 1-8 = actual stompboxes
        self._current_mode = Mode.PRESET
        self._last_slider_update_time = 0

        # OSC inputs (footpedal)
        self._midi_to_osc = MidiToOsc('Arduino Micro')  # works via callbacks, so not blocking

        # OSC server (receives inputs)
        self._osc_server = FootpedalOscServer(self.cb_mode, self.cb_preset,
                                              self.cb_stomp_enable, self.cb_stomp_enable,
                                              self.cb_looper, self.cb_metronome, self.cb_slider)

        # mod-host LV2 host (output)
        ModHostClient.restart()
        time.sleep(1)
        self._modhost = ModHostClient()

        # Metronome output (using klick)
        self._metronome = Metronome()

        # Looper object (using sooperlooper)
        self._looper = Looper()

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

        # Disable stompboxes if configured
        for i, sb in enumerate(data['preset']['stompboxes']):
            if 'enabled' in sb:
                plugins[i].is_enabled = sb['enabled']

        # Assign index to each node
        for p in pb.nodes:
            p._index = pb.get_index(p)

        # Add graph edges (connections between effects as index to node - mod_host module will do conversion to "effect_:in" string)
        for p in pb.nodes:
            self._log.debug('Adding edges {!s} for node {!s}'.format(p._connections, p))
            pb.add_edges(p, p._connections)

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

        # Disable (bypass) plugins if set to not enabled
        for node in self._pedalboard.nodes:
            if not node.is_enabled:
                self._modhost.bypass_effect(node)

        # Store info about stereo connections of neighbouring nodes
        output_stereo = [n.has_stereo_output for n in self._pedalboard.nodes]
        input_stereo = [n.has_stereo_input for n in self._pedalboard.nodes]

        # Add edges (connections) to mod-host
        for node in self._pedalboard.nodes:
            incoming = self._pedalboard.get_incoming_edges(node)
            outgoing = self._pedalboard.get_outgoing_edges(node)
            self._log.info('mod-host: add connection {!s} -> [{:d}] "{:s}" -> {!s}'.format(incoming, node.index, node.name, outgoing))
            self._modhost.connect_effect(node, incoming, outgoing, output_stereo, input_stereo)

        if self._pedalboard.nodes[0].name == 'GxTubeScreamer':
            self._modhost.set_parameter(self._pedalboard.nodes[0], 'fslider0_', 0)

    def _handle_slider_stompbox(self, slider_id, value):
        stompbox = self._pedalboard.nodes[self._selected_stompbox - 1]
        param_name, param_info = stompbox.get_parameter_info_by_index(slider_id - 1)
        if param_name is None:
            self._log.info('{!s} has no parameter for slider {:d}'.format(stompbox, slider_id))
            return

        self._log.debug('{:s} param_info {!s}'.format(param_name, param_info))

        # Convert slider value (0-1023) to parameters (min, max) range
        min_max_ratio = 1024 / (param_info['Maximum'] - param_info['Minimum'])
        value /= min_max_ratio
        value += param_info['Minimum']
        value = int(value)

        self._log.info('Setting stomp #{:d} param #{:d} "{:s}" [{:s}] to {} (ratio {})'.format(self._selected_stompbox, slider_id, param_name, param_info['Symbol'], value, min_max_ratio))
        self._modhost.set_parameter(stompbox, param_info['Symbol'], value)

    def cb_mode(self, uri, msg=None):
        """Handle incoming /mode/... OSC message"""
        mode = uri.rsplit('/', 1)[-1]
        assert mode in self.OSC_MODES.keys()
        self._log.info("MODE {} -> {}".format(mode, self.OSC_MODES[mode]))
        midisend(1, self.OSC_MODES[mode].value)

        # Action when leaving mode
        if self.OSC_MODES[mode] != Mode.LOOPER:
            self._looper.enable(False)
        if self.OSC_MODES[mode] != Mode.METRONOME:
            self._metronome.enable(False)

        # Action based on activated mode
        if self.OSC_MODES[mode] == Mode.PRESET:
            pass
        elif self.OSC_MODES[mode] == Mode.STOMP:
            self._load_preset('preset_stompboxes.yaml')
        elif self.OSC_MODES[mode] == Mode.LOOPER:
            self._looper.enable(True)
        elif self.OSC_MODES[mode] == Mode.METRONOME:
            self._metronome.enable(True)

        self._current_mode = self.OSC_MODES[mode]

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
        cmd_fn = {
            'undo': self._looper.undo,
            'record': self._looper.record,
            'overdub': self._looper.overdub,
        }
        if command in cmd_fn:
            cmd_fn[command]()
            self._log.info("Sent /sl/0/hit s:{:s} to sooperlooper".format(command))
        else:
            self._log.error("Invalid sooperlooper command {:s}".format(command))

    def cb_metronome(self, uri, msg=None):
        """Handle incoming /metronome/ OSC messages"""
        uri_splits = uri.split('/')
        assert uri_splits[0] == ''
        assert uri_splits[1] == 'metronome'
        command = uri_splits[2]

        self._log.info("METRONOME {}".format(command))

        if command == 'pause':
            self._metronome.enable(not self._metronome.is_running)
        elif command == 'inc_bpm':
            self._metronome.set_bpm(self._metronome.bpm + 8)
        elif command == 'dec_bpm':
            self._metronome.set_bpm(self._metronome.bpm - 8)
        elif command == 'tap':
            self._metronome.tap()

        midisend(2, self._metronome.get_bpm())

    def cb_slider(self, uri, msg=None):
        """Handle incoming /slider/<N> OSC message"""
        now = time.time()
        if now - self._last_slider_update_time < 0.2:
            return
        self._last_slider_update_time = now

        uri_splits = uri.split('/')
        assert uri_splits[0] == ''
        assert uri_splits[1] == 'slider'
        slider_id = int(uri_splits[2])
        value = float(msg) if msg is not None else float(uri_splits[3])
        self._log.info("SLIDER {:d} = {:f}".format(slider_id, value))

        if self._current_mode in [Mode.PRESET, Mode.STOMP]:
            # Adjust currently selected stompbox (default 1)
            self._handle_slider_stompbox(slider_id, value)
        elif self._current_mode == Mode.LOOPER:
            # Adjust looper parameters
            pass
        elif self._current_mode == Mode.METRONOME:
            if slider_id == 1:
                self._metronome.set_bpm(value)
            elif slider_id == 2:
                self._metronome.set_volume(value)


if __name__ == '__main__':
    MusicBox().run()

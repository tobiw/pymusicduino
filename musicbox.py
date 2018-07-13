import enum
import json
import logging
import time
import yaml

from footpedal import MidiToOsc
from looper import Looper
from metronome import Metronome
from midisend import midisend
from notifier import TcpNotifier
from osc_server import FootpedalOscServer
from pedalboard_graph import PedalboardGraph
from plugin import Lv2Plugin

from pluginsmanager.banks_manager import BanksManager
from pluginsmanager.observer.mod_host.mod_host import ModHost  # TODO: add other observers
from pluginsmanager.model.bank import Bank
from pluginsmanager.model.pedalboard import Pedalboard
from pluginsmanager.model.lv2.lv2_effect_builder import Lv2EffectBuilder
from pluginsmanager.model.system.system_effect import SystemEffect


logger = logging.getLogger('musicbox')
logger.setLevel(logging.DEBUG)
filehandler = logging.FileHandler('/var/log/musicbox.log')
filehandler.setLevel(logging.DEBUG)
filehandler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(filehandler)
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
        try:
            self._midi_to_osc = MidiToOsc('Arduino Micro')  # works via callbacks, so not blocking
        except ValueError as e:
            self._log.error('Failed to start Midi Footpedal: ' + str(e))

        # OSC server (receives inputs)
        self._osc_server = FootpedalOscServer(self.cb_mode, self.cb_preset,
                                              self.cb_stomp_enable, self.cb_stomp_enable,
                                              self.cb_looper, self.cb_metronome, self.cb_slider)

        # mod-host LV2 host (output)
        self._banks_manager = BanksManager()
        self._banks_manager.append(Bank('Bank 1'))  # TODO: load banks from stored files
        self._modhost = ModHost('localhost')
        self._modhost.connect()
        self._banks_manager.register(self._modhost)
        self._pedalboard = None
        self._log.info("STARTED mod-host client")

        # Metronome output (using klick)
        self._metronome = Metronome()
        self._log.info("STARTED Metronome")

        # Looper object (using sooperlooper)
        self._looper = Looper()
        self._log.info("STARTED Looper")

        # Notifiers
        self._notifier = TcpNotifier()
        self._log.info("STARTED TcpNotifier")

        # Initialize: set mode PRESET and load preset1
        time.sleep(2)
        self._set_mode(Mode.PRESET)
        for preset_id in range(4):
            self._load_preset('preset{:02d}.yaml'.format(preset_id))

    def run(self):
        try:
            self._osc_server.start()
            self._osc_server._thread.join()
        except KeyboardInterrupt:
            self._log.warn('KeyboardInterrupt: shutting down')
            self._osc_server.stop()
            self._notifier.close()

    def _set_mode(self, mode):
        midisend(1, mode.value)

        # Action when leaving mode
        if mode != Mode.LOOPER:
            self._looper.enable(False)
        if mode != Mode.METRONOME:
            self._metronome.enable(False)

        # Action based on activated mode
        if mode == Mode.PRESET:
            pass
        elif mode == Mode.STOMP:
            self._activate_preset(0)  # special preset 0 = stompbox mode
        elif mode == Mode.LOOPER:
            self._looper.enable(True)
        elif mode == Mode.METRONOME:
            self._metronome.enable(True)

        self._current_mode = mode

        self._notifier.update("MODE:{:d}".format(int(self._current_mode.value)))

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

        plugins = [Lv2Plugin(sb['lv2'], sb['connections']) for sb in data['preset']['stompboxes']]
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

    def _activate_preset(self, preset_id):
        # Store current pedalboard in attribute
        self._pedalboard = self._banks_manager.banks[0].pedalboards[preset_id]

        # Load new pedalboard into mod-host
        self._modhost.pedalboard = self._pedalboard
        self._log.info('Activated pedalboard {!s}'.format(self._pedalboard))

        # Notifications
        self._preset_info_notifier_update(preset_id)

        for e in self._pedalboard.effects:
            e.toggle()
            self._notifier.update("STOMPEN:{:d}:{:d}".format(e.index, int(e.active)))

    def _load_preset(self, yaml_file, remove_previous=False):
        # Create graph with effect plugin objects
        graph = self._create_graph_from_config(yaml_file)

        # Cleanup existing pedalboard in mod-host
        if remove_previous and self._pedalboard is not None:
            for e in list(self._pedalboard.effects):
                for c in list(e.connections):
                    self._pedalboard.disconnect(c.output, c.input)
                self._pedalboard.effects.remove(e)
            self._banks_manager.banks[0] = []
            del self._pedalboard

        # Create PedalPi pedalboard and add to bank and mod-host
        pedalboard = Pedalboard(graph.settings['name'])
        pedalboard.graph = graph
        self._banks_manager.banks[0].append(pedalboard)

        # Add nodes (effects) to mod-host
        lv2_builder = Lv2EffectBuilder()
        for node in graph.nodes:  # loop over Plugin objects
            self._log.info("mod-host: add effect " + str(node))
            node.effect = lv2_builder.build(node.uri)
            pedalboard.effects.append(node.effect)

        sys_effect = SystemEffect('system', ['capture_1', 'capture_2'], ['playback_1', 'playback_2'])

        # Connect system capture to first effect
        pedalboard.connect(sys_effect.outputs[0], pedalboard.effects[0].inputs[0])

        # Add edges (connections) to mod-host
        for node in graph.nodes:  # looper over Plugin objects
            incoming = graph.get_incoming_edges(node)
            outgoing = graph.get_outgoing_edges(node)
            self._log.info('mod-host: add connection {!s} -> [{:d}] "{:s}" -> {!s}'.format(incoming, node.index, node.name, outgoing))

            # Go through outgoing edges (indices)
            for e in outgoing:  # loop over edge indices
                # Connect current effect to effect given by index e
                neighbor = graph.get_node_from_index(e)
                if node.has_stereo_output and neighbor.has_stereo_input:  # stereo to stereo
                    pedalboard.connect(node.effect.outputs[0], neighbor.effect.inputs[0])
                    pedalboard.connect(node.effect.outputs[1], neighbor.effect.inputs[1])
                elif not node.has_stereo_output and neighbor.has_stereo_input:  # split mono to stereo
                    pedalboard.connect(node.effect.outputs[0], neighbor.effect.inputs[0])
                    pedalboard.connect(node.effect.outputs[0], neighbor.effect.inputs[1])
                elif node.has_stereo_output and not neighbor.has_stereo_input:  # sum stereo to mono
                    pedalboard.connect(node.effect.outputs[0], neighbor.effect.inputs[0])
                    pedalboard.connect(node.effect.outputs[1], neighbor.effect.inputs[0])
                else:  # mono to mono
                    pedalboard.connect(node.effect.outputs[0], neighbor.effect.inputs[0])

            if outgoing == []:
                left_output = node.effect.outputs[0]
                right_output = node.effect.outputs[1 if node.has_stereo_output else 0]
                pedalboard.connect(left_output, sys_effect.inputs[0])
                pedalboard.connect(right_output, sys_effect.inputs[1])

    def _handle_slider_stompbox(self, slider_id, value):
        stompbox = self._pedalboard.graph.nodes[self._selected_stompbox - 1]  # select by index from list of Plugin objects
        param_name, param_info = stompbox.get_parameter_info_by_index(slider_id - 1)
        if param_name is None:
            self._log.info('{!s} has no parameter for slider {:d}'.format(stompbox, slider_id))
            return

        self._log.debug('{:s} param_info {!s}'.format(param_name, param_info))

        # Convert slider value (0-1023) to parameters (min, max) range
        min_max_ratio = 1024 / (param_info['Maximum'] - param_info['Minimum'])
        value /= min_max_ratio
        value += param_info['Minimum']

        self._log.info('Setting stomp #{:d} param #{:d} "{:s}" [{:s}] to {} (ratio {})'.format(self._selected_stompbox, slider_id, param_name, param_info['Symbol'], value, min_max_ratio))
        stompbox.effect.params[slider_id - 1].value = value
        self._notifier.update("SLIDER:{:d}:{:f}".format(slider_id - 1, value))

    def cb_mode(self, uri, msg=None):
        """Handle incoming /mode/... OSC message"""
        mode = uri.rsplit('/', 1)[-1]
        assert mode in self.OSC_MODES.keys()
        self._log.info("MODE {} -> {}".format(mode, self.OSC_MODES[mode]))
        self._set_mode(self.OSC_MODES[mode])

    def _preset_info_notifier_update(self, preset_id):
        # Construct JSON payload for notifiers:
        # current preset, list of stompboxes with parameters
        notifier_data = {
            'preset_id': int(preset_id),
            'preset_name': self._pedalboard.graph.settings['name'],
            'stompboxes': []
        }

        # Loop over all stompboxes (nodes on pedalboard graph)
        for sb in self._pedalboard.graph.nodes:
            sb_data = {
                'name': sb.name,
                'parameters': []
            }

            # Loop over stombox's parameters
            for p in sb.parameters:  # p is { 'NAME': { params } }
                assert len(p.keys()) == 1
                p_name = list(p.keys())[0]
                param_data = {
                    'name': p_name,
                    'symbol': p[p_name]['Symbol'],
                    'min': p[p_name]['Minimum'],
                    'max': p[p_name]['Maximum'],
                    'value': p[p_name]['Default']  # TODO
                }
                sb_data['parameters'].append(param_data)

            notifier_data['stompboxes'].append(sb_data)

        self._log.debug("Sending JSON: " + json.dumps(notifier_data))
        self._notifier.update("PRESET:" + json.dumps(notifier_data))

    def cb_preset(self, uri, msg=None):
        """Handle incoming /preset/<N> OSC message"""
        preset_id = int(uri.rsplit('/', 1)[-1])
        assert 0 < preset_id < 100
        self._log.info("PRESET {:d}".format(preset_id))
        self._activate_preset(preset_id)

    def cb_stomp_enable(self, uri, msg=None):
        """Handle incoming /stomp/<N>/enable OSC message"""
        uri_splits = uri.split('/')[2:]  # throw away leading "/" and "stomp"
        assert 2 <= len(uri_splits) <= 3, uri_splits
        stomp_id = int(uri_splits[0])
        op = uri_splits[1]
        value = int(uri_splits[2]) if len(uri_splits) == 3 else None

        self._log.debug('cb_stomp_{}: {:d} (value {!s})'.format(op, stomp_id, value))
        assert 0 < stomp_id < 10
        assert op in ['enable', 'select']

        if op == 'select':
            self._selected_stompbox = stomp_id
            self._notifier.update("STOMPSEL:{:d}".format(self._selected_stompbox - 1))
        elif op == 'enable':
            assert self._pedalboard
            p = self._pedalboard.graph.get_node_from_index(stomp_id - 1)
            if p:
                assert p.index == stomp_id - 1
                if value is None:  # no value given: toggle internal state
                    p.is_enabled = not p.is_enabled
                else:
                    p.is_enabled = bool(value)

                self._log.info('STOMP {} "{}" ENABLE {:d}'.format(p.index, p.name, p.is_enabled))
                p.effect.active = True if not p.is_enabled else False
                self._notifier.update("STOMPEN:{:d}:{:d}".format(p.index, p.is_enabled))
            else:
                self._log.warn('cb_stomp_enable: node with index {:d} not in pedalboard'.format(stomp_id - 1))

    def cb_looper(self, uri, msg=None):
        """Handle incoming /looper OSC messages to be proxied to sooperlooper"""
        _, command = uri.rsplit('/', 1)
        cmd_fn = {
            'undo': self._looper.undo,
            'redo': self._looper.redo,
            'record': lambda: self._looper.record(insert=False),
            'overdub': lambda: self._looper.overdub(multiply=False),
            'mute_trigger': lambda: self._looper.mute(trigger=True),
            'insert': lambda: self._looper.record(insert=True),
            'multiply': lambda: self._looper.overdub(multiply=True),
            'pause': self._looper.pause,
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
        elif command == 'set_bpm':
            assert len(uri_splits) == 4
            self._metronome.set_bpm(int(uri_splits[3]))
        elif command == 'inc_bpm':
            self._metronome.set_bpm(self._metronome.bpm + 8)
        elif command == 'dec_bpm':
            self._metronome.set_bpm(self._metronome.bpm - 8)
        elif command == 'tap':
            self._metronome.tap()

        bpm = self._metronome.get_bpm()
        midisend(2, bpm)
        self._notifier.update("BPM:{:d}".format(bpm))

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

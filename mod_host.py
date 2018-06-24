import logging
import socket
import subprocess

import jack_connections


"""
mod-host commands from github README:

add <lv2_uri> <instance_number>
    * add an LV2 plugin encapsulated as a jack client
    e.g.: add http://lv2plug.in/plugins/eg-amp 0
    instance_number must be any value between 0 ~ 9999, inclusively

remove <instance_number>
    * remove an LV2 plugin instance (and also the jack client)
    e.g.: remove 0

preset_load <instance_number> <preset_uri>
    * load a preset state to given effect instance
    e.g.: preset_load 0 "http://drobilla.net/plugins/mda/presets#JX10-moogcury-lite"

preset_save <instance_number> <preset_name> <dir> <file_name>
    * save a preset state from given effect instance
    e.g.: preset_save 0 "My Preset" /home/user/.lv2/my-presets.lv2 mypreset.ttl

preset_show <instance_number> <preset_uri>
    * show the preset information of requested instance / URI
    e.g.: preset_show 0 http://drobilla.net/plugins/mda/presets#EPiano-bright

connect <origin_port> <destination_port>
    * connect two effect audio ports
    e.g.: connect system:capture_1 effect_0:in

disconnect <origin_port> <destination_port>
    * disconnect two effect audio ports
    e.g.: disconnect system:capture_1 effect_0:in

bypass <instance_number> <bypass_value>
    * toggle effect processing
    e.g.: bypass 0 1
    if bypass_value = 1 bypass effect
    if bypass_value = 0 process effect

param_set <instance_number> <param_symbol> <param_value>
    * set a value to given control
    e.g.: param_set 0 gain 2.50

param_get <instance_number> <param_symbol>
    * get the value of the request control
    e.g.: param_get 0 gain

param_monitor <instance_number> <param_symbol> <cond_op> <value>
    * do monitoring a effect instance control port according given condition
    e.g: param_monitor 0 gain > 2.50

licensee <instance_number>
    * get the licensee name for a commercial plugin
    e.g.: licensee 0

monitor <addr> <port> <status>
    * open a socket port to monitoring parameters
    e.g: monitor localhost 12345 1
    if status = 1 start monitoring
    if status = 0 stop monitoring

monitor_output <instance_number> <param_symbol>
    * request monitoring of an output control port in the feedback port
    e.g.: monitor_output 0 meter

midi_learn <instance_number> <param_symbol> <minimum> <maximum>
    * start MIDI learn for a parameter
    e.g.: midi_learn 0 gain 0.0 1.0

midi_map <instance_number> <param_symbol> <midi_channel> <midi_cc> <minimum> <maximum>
    * map a MIDI controller to a parameter
    e.g.: midi_map 0 gain 0 7 0.0 1.0

midi_unmap <instance_number> <param_symbol>
    * unmap the MIDI controller from a parameter
    e.g.: unmap 0 gain

midi_program_listen <enable> <midi_channel>
    * listen for MIDI program messages for the specified midi channel in the feedback port
    e.g.: midi_program_listen 1 0

cc_map <instance_number> <param_symbol> <device_id> <actuator_id> <label> <value> <minimum> <maximum> <steps> <unit> <scalepoints_count> <scalepoints...>
    * map a Control Chain actuator to a parameter
    e.g.: midi_map 0 gain 0 1 "Gain" 0.0 -24.0 3.0 33 "dB" 0

cc_unmap <instance_number> <param_symbol>
    * unmap the Control Chain actuator from a parameter
    e.g.: unmap 0 gain

cpu_load
    * return current jack cpu load

load <file_name>
    * load a history command file
    * dummy way to save/load workspace state
    e.g.: load my_setup

save <file_name>
    * saves the history of typed commands
    * dummy way to save/load workspace state
    e.g.: save my_setup

bundle_add <bundle_path>
    * add a bundle to the running lv2 world
    e.g.: bundle_add /path/to/bundle.lv2

bundle_remove <bundle_path>
    * remove a bundle from the running lv2 world
    e.g.: bundle_remove /path/to/bundle.lv2

feature_enable <feature> <enable>
    * enable or disable a feature
    e.g.: feature_enable link 1
    current features are "link" and "processing"

transport <rolling> <beats_per_bar> <beats_per_minute>
    * change the current transport state
    e.g.: transport 1 4 120

output_data_ready
    * report feedback port ready for more messages

help
    * show a help message

quit
    bye!
"""


class ModHostSocket:
    """
    Socket connection to mod-host instance (UDP port 5555).
    """
    def __init__(self):
        self._socket = socket.socket()
        self._log = logging.getLogger('musicbox.ModHostSocket')

    def connect(self):
        self._socket.connect(('localhost', 5555))
        self._socket.settimeout(0.5)

    def close(self):
        self._socket.close()

    def send(self, c):
        c += '\0'  # required for mod-host to recognize the command
        c = c.encode('utf-8')
        self._log.debug('sending command: "{!s}"'.format(c))
        self._socket.send(c)
        resp = self._socket.recv(1024)
        resp = resp.decode('utf-8').strip().replace('\0', '').split()[1:]
        self._log.debug(resp)
        if resp and int(resp[0]) < 0:  # error
            raise RuntimeError('Response from command "{}" was {}'.format(c, str(resp)))
        # resp = self._socket.recv(1024)
        return resp


class Plugin:
    def __init__(self, uri, connections=None):
        self._log = logging.getLogger('musicbox.Plugin')
        self._log.info('Creating new Plugin {}'.format(uri))

        self._uri = uri  # LV2 plugin URI
        self._name = ''  # Name from LV2 plugin information
        self._class = ''  # Class from LV2 plugin information
        self._parameters = []  # Parameters from LV2 plugin information
        self._index = None  # mod-host effect index
        self._connections = connections or []  # outgoing connection indices to other effects
        self._has_stereo_input = self._has_stereo_output = False  # in/out port from LV2 plugin information TODO
        self.is_enabled = True

        self._load_plugin_info()
        # fxparams = self.get_all_parameters()
        # self._log.debug('Plugin "{}" parameters: '.format(self._name) + str(fxparams))

        if self._name == 'Calf Multi Chorus':
            self._has_stereo_output = self._has_stereo_input = True

    @property
    def name(self):
        return self._name

    @property
    def uri(self):
        return self._uri

    @property
    def index(self):
        return self._index

    @property
    def has_stereo_output(self):
        return self._has_stereo_output

    @property
    def has_stereo_input(self):
        return self._has_stereo_input

    def _load_plugin_info(self):
        self._log.info('Getting plugin info for {}'.format(self._uri))
        output = subprocess.check_output(['lv2info', self._uri])
        lines = [l.decode('utf-8').strip() for l in output.splitlines()]
        self._log.debug('lv2info output: ' + str(lines))
        for l in lines:
            if l.startswith('Name:'):
                self._name = l.split(':', 1)[-1].strip()
            if l.startswith('Class:'):
                self._class = l.split(':', 1)[-1].strip()
                break
        self._log.debug('Found plugin class/name: {}/{}'.format(self._class, self._name))

        # Parse ports (parameters)
        parameter_sections = []
        current_port = 0
        while True:
            try:
                current_port_line_index = lines.index('Port {}:'.format(current_port))
            except ValueError:
                break

            try:
                next_port_line_index = lines.index('Port {}:'.format(current_port + 1))
            except ValueError:
                next_port_line_index = -1

            parameter_sections.append(lines[current_port_line_index:next_port_line_index])
            current_port += 1

        self._parameters = []
        for section in parameter_sections:
            if '#ControlPort' not in section[1]:  # skip non-control ports
                continue

            # This port is a control port, start parsing all lines
            port_info = {}
            for line in [l.strip() for l in section]:
                for p in ['Symbol', 'Name', 'Minimum', 'Maximum', 'Default']:
                    if line.startswith(p):
                        port_info[p.lower()] = line.split(':', 1)[-1].strip()
            self._parameters.append(port_info)
        self._log.debug('Found plugin parameters: ' + str(self._parameters))

    def get_all_parameters(self):
        params = {}
        for s in [p['symbol'] for p in self._parameters]:
            try:
                params[s] = self.get_parameter(s)
            except RuntimeError:
                pass
        return params


class ModHostClient:
    """
    A client program making use of the socket connection to mod-host to control and query it.
    """
    def __init__(self):
        """Initialize mod-host socket connection and list of plugins"""
        self._log = logging.getLogger('musicbox.ModHostClient')

        self._socket = ModHostSocket()
        self._socket.connect()
        self._log.info('mod-host socket connected')

        self._available_plugins = self.list_plugins()
        self._log.debug('List of plugins: ' + str(self._available_plugins))
        self._installed_plugins = []

    def close(self):
        """Close socket connection"""
        self._socket.close()
        self._log.info('mod-host socket closed')

    @classmethod
    def restart(cls):
        """Restart the mod-host daemon"""
        subprocess.check_call(['systemctl', 'restart', 'mod-host'])

    def list_plugins(self):
        """Use lv2ls to get dict of all available LV2 plugins (name: uri)"""
        plugins = {}
        output = subprocess.check_output(['lv2ls'])
        for l in [x.decode('utf-8') for x in output.splitlines()]:
            name = l.rsplit('/', 1)[-1]
            if '#' in name:
                name = name.split('#', 1)[0]
            plugins[name] = l
        return plugins

    def disconnect_all_effects(self):
        """Run disconnect command on all ports in mod-host"""
        for outport, inports in jack_connections.get_connections().iteritems():
            if not any(p in outport for p in ['capture', ':out']):  # skip if outport is not actually capture or effect output
                continue
            for inport in inports:
                self._log.info('Disconnecting ports {} {}'.format(outport, inport))
                self._socket.send('disconnect {} {}'.format(outport, inport))

    def remove_all_effects(self):
        """Remove all effects from mod-host (also removes all connections)"""
        for line in [l for l in jack_connections.get_connections().keys() if l.startswith('effect_')]:  # look at effects only
            i = line.split(':', 1)[0].split('_', 1)[-1]  # get index by splitting effect_... name
            self._log.info('Removing effect {}'.format(i))
            self._socket.send('remove {}'.format(i))
        self._installed_plugins = []

    def add_effect(self, p):
        """Load and install effect in mod-host"""
        self._socket.send('add {} {}'.format(p.uri, p.index))
        self._log.info('Plugin "{}" added: index {:d}'.format(p.name, p.index))

    def remove_effect(self, p):
        """Remove effect from mod-host (doesn't affect any existing effect indices)"""
        self._socket.send('remove {}'.format(p.index))
        self._log.info('Plugin "{}" removed'.format(p.name))

    def connect_effect(self, p, connect_from, connect_to):
        """Connect the in and out ports of the effect"""
        self._log.info('Plugin "{}": connecting from {} to {}'.format(p.name, connect_from, connect_to))

        input_suffix = 'in_l' if p.has_stereo_input else 'in'
        output_suffix = 'out_l' if p.has_stereo_output else 'out'

        # If connection is empty, use system capture or playback
        if connect_from is None or connect_from == []:
            connect_from = ['system:capture_1']
        if connect_to is None or connect_to == []:
            connect_to = ['system:playback_1']

        # Connect each incoming port
        for port in connect_from:
            self._socket.send('connect {in_port} effect_{idx}:{in_suffix}'.format(
                in_port=port, idx=p.index, in_suffix=input_suffix))

        # Connect each outgoing port
        for port in connect_to:
            self._socket.send('connect effect_{idx}:{out_suffix} {out_port}'.format(
                idx=p.index, out_port=port, out_suffix=output_suffix))

    def bypass_effect(self, p):
        self._log.info('Plugin "{}": setting bypass {}'.format(p.name, 'enable' if not p.is_enabled else 'disable'))
        self._socket.send('bypass {} {}'.format(p.index, 1 if not p.is_enabled else 0))

    def set_parameter(self, p, symbol, value):
        self._log.info('Plugin "{}": setting "{:s}" to {!s}'.format(p.name, symbol, value))
        return self._socket.send('param_set {} {} {}'.format(p.index, symbol, value))

    def get_parameter(self, p, symbol):
        r = float(self._socket.send('param_get {} {}'.format(p.index, symbol))[1])
        self._log.info('Plugin "{}": "{:s}" is {!s}'.format(p.name, symbol, r))
        return r

import logging
import socket
import subprocess


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
        self._log = logging.getLogger('mod_host.ModHostSocket')

    def connect(self):
        self._socket.connect(('localhost', 5555))
        self._socket.settimeout(0.5)

    def send(self, c):
        c += '\0'  # required for mod-host to recognize the command
        self._log.debug('sending command: "{!s}"'.format(c))
        self._socket.send(c.encode('utf-8'))
        resp = self._socket.recv(1024)
        resp = resp.strip().replace(b'\0', b'').split()[1:]
        self._log.debug(resp)
        if resp and int(resp[0]) < 0:  # error
            raise RuntimeError('Response from command "{}" was {}'.format(c, str(resp)))
        # resp = self._socket.recv(1024)
        return resp


class Plugin:
    MOD = None
    socket = None
    available_plugins = []
    num_installed_plugins = 0

    def __init__(self, uri, pos=-1):
        self._uri = uri
        self._name = ''
        self._class = ''
        self._parameters = []
        self._index = 0
        self._log = logging.getLogger('mod_host.Plugin')

        if pos == -1:
            pos = self.num_installed_plugins

        self._get_plugin_info()
        self._log.debug('Plugin "{}" class {}, info: '.format(self._name, self._class) + str(self._parameters))
        params = self.get_all_parameters()
        self._log.debug('Plugin "{}" parameters: ' + str(params))

        self._index = pos
        self.socket.send('add {} {}'.format(self._uri, self._index))
        self._log.info('Plugin "{}" added: index {:d}'.format(self._name, self._index))

        self.num_installed_plugins += 1

    def remove(self):
        self.socket.send('remove {}'.format(self._installed_plugins.index(self._uri)))
        self._log.info('Plugin "{}" removed'.format(self._name))
        self.num_installed_plugins -= 1
        assert self.num_installed_plugins >= 0

    def connect(self, connect_from, connect_to):
        self._log.info('Plugin "{}": connecting from {} to {}'.format(connect_from, connect_to))
        self.socket.send('connect {} effect_{}:in_l'.format(connect_from, self._index))
        self.socket.send('connect effect_{}:out_l {}'.format(self._index, connect_to))

        # Stereo output
        if connect_to == 'system:playback_1':
            self.socket.send('connect effect_{}:out_l system:playback_2'.format(self._index))

    def _get_plugin_info(self):
        lines = subprocess.check_output(['lv2info', self._uri]).splitlines()
        self._name = lines[2].split(b':', 1)[-1].strip()
        self._class = lines[3].split(b':', 1)[-1].strip()

        # Parse ports (parameters)
        parameter_sections = []
        current_port = 0
        while True:
            try:
                current_port_line_index = lines.index('\tPort {}:'.format(current_port))
            except ValueError:
                break

            try:
                next_port_line_index = lines.index('\tPort {}:'.format(current_port+1))
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

    def set_parameter(self, symbol, value):
        self._log.info('Plugin "{}": setting "{:s}" to {!s}'.format(self._name, symbol, value))
        return self.socket.send('param_set {} {} {}'.format(self._index, symbol, value))

    def get_parameter(self, symbol):
        r = float(self.socket.send('param_get {} {}'.format(self._index, symbol))[1])
        self._log.info('Plugin "{}": "{:s}" is {!s}'.format(self._name, symbol, r))
        return r

    def get_all_parameters(self):
        params = {}
        for s in [p['symbol'] for p in self._parameters]:
            try:
                params[s] = self.get_parameter(s)
            except RuntimeError:
                pass
        return params

    def bypass(self, enable):
        self._log.info('Plugin "{}": setting bypass {}'.format(self._name, 'enable' if enable else 'disable'))
        return self.socket.send('bypass {} {}'.format(self._index, 1 if enable else 0))


class DirectionalGraph:
    """
    >>> g = DirectionalGraph({'a': ['b', 'c'], 'b': ['c', 'd'], 'c': [], 'd': []})
    >>> g.nodes
    ['a', 'b', 'c', 'd']
    >>> sorted(g.get_outgoing_edges('a'))
    ['b', 'c']
    >>> g.get_incoming_edges('b')
    ['a']
    >>> sorted(g.get_incoming_edges('c'))
    ['a', 'b']
    >>> g.get_outgoing_edges('d')
    []
    """
    def __init__(self, graph):
        self._graph = graph

    @property
    def nodes(self):
        return sorted(list(self._graph.keys()))

    def get_outgoing_edges(self, node):
        return self._graph[node]

    def get_incoming_edges(self, node):
        return [n for n, edges in self._graph.items() if node in edges]


class ModHostClient:
    """
    A client program making use of the socket connection to mod-host to control and query it.
    """
    def __init__(self):
        """Initialize mod-host socket connection and list of plugins"""
        self._log = logging.getLogger('mod_host.ModHostClient')
        self._socket = ModHostSocket()
        self._socket.connect()
        Plugin.socket = self._socket
        self._log.info('mod-host socket connected')

        Plugin.available_plugins = self.list_plugins()
        self._log.debug('List of plugins: ' + str(Plugin.available_plugins))
        self._installed_plugins = []
        self.remove_all_plugins()  # cleanup mod-host when starting client

    def close(self):
        """Close socket connection"""
        self._socket.close()
        self._log.info('mod-host socket closed')

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

    def _get_jack_connections_lines(self):
        """Return all jackd connections as a list (output of jack_lsp)"""
        return subprocess.check_output(['jack_lsp', '-c']).splitlines()

    def get_jack_connections(self):
        """Get parsed jackd connections as a list of tuples (port, connected_ports)"""
        connections = []
        lines = self._get_jack_connections_lines()
        for i, line in enumerate(lines):
            if not any(p in line for p in ['capture', ':out']):  # only use outports as first item
                continue

            self._log.debug('outport: ' + line)

            connected_ports = []
            j = 1
            while (i + j) < len(lines):
                next_line = lines[i+j]
                if next_line.startswith(b'   '):  # next line is a connected inport
                    connected_ports.append(next_line.strip())
                    self._log.debug('list of connected ports for "{}": '.format(line) + str(connected_ports))
                else:  # hit the next outport
                    break
                j += 1

            if connected_ports:
                connections.append((line, connected_ports))

        return connections

    def disconnect_all_plugins(self):
        """Run disconnect command on all ports in mod-host"""
        for outport, inports in self.get_jack_connections():
            for inport in inports:
                self._log.info('Disconnecting ports {} {}'.format(outport, inport))
                self._socket.send('disconnect {} {}'.format(outport, inport))

    def remove_all_plugins(self):
        """Remove all plugins from mod-host (also removes all connections)"""
        for line in [l for l in self._get_jack_connections_lines() if l.startswith(b'effect_')]:  # look at effects only
            i = line.split(b':', 1)[0].split(b'_', 1)[-1]  # get index by splitting effect_... name
            self._log.info('Removing effect {}'.format(i))
            self._socket.send('remove {}'.format(i))
        self._installed_plugins = []

    def add_plugin(self, name, pos=-1):
        # Determine and verify position
        if pos == -1:
            pos = len(self._installed_plugins)
        assert pos <= len(self._installed_plugins)

        # Get plugin URL and check if it already exists in signal chain
        plugin_uri = Plugin.available_plugins[name]
        if plugin_uri in self._installed_plugins:
            self._log.warn('Plugin "{}" is already installed'.format(name))
            return

        plugin = Plugin(plugin_uri, pos)

        # Determine signal chain: connect to effects based on position;
        # if first: connect to system:capture;
        # if last: connect to system:playback
        connect_from = None  # to be determined
        connect_to = None  # to be determined
        if pos == 0:
            connect_from = 'system:capture_1'
        elif pos == len(self._installed_plugins):
            connect_to = 'system:playback_1'

        if connect_from is None:
            if len(self._installed_plugins) == 0:
                connect_from = 'system:capture_1'
            else:
                connect_from = 'effect_{}:out_l'.format(pos-1)
        if connect_to is None:
            if len(self._installed_plugins) == 0:
                connect_to = 'system:playback_1'
            else:
                connect_to = 'effect_{}:in_l'.format(pos+1)
        self._log.debug('New connection: {} -> effect -> {}'.format(connect_from, connect_to))

        plugin.connect(connect_from, connect_to)

        self._installed_plugins.insert(pos, plugin)

    def load_preset_string(self, preset_str):
        plugins = preset_str.split(',')
        for p in plugins:
            name = p.split('[')[0]
            # self.disconnect_all()
            self.add_plugin(name)


def chorus_test(m):
    info = m.get_plugin_info('MultiChorus')
    for p in info['parameters']:
        print('{}: {} to {}'.format(p['symbol'], p['minimum'], p['maximum']))
    m.load_preset_string('MultiChorus[0 0 0 0]')
    print(m.get_all_parameters(0, info))
    m.set_parameter(0, 'mod_rate', 1.8)


def reverb_test(m):
    info = m.get_plugin_info('Reverb')
    for p in info['parameters']:
        print('{}: {} to {}'.format(p['symbol'], p['minimum'], p['maximum']))
    m.load_preset_string('Compressor[0 0],Reverb[0 0 0 0]')
    print(m.get_all_parameters(1, info))
    m.set_parameter(1, 'room_size', 3)


if __name__ == '__main__':
    m = ModHostClient()
    # reverb_test(m)

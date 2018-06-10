#!/usr/bin/env python3

import socket
import subprocess
import time


class ModHostSocket:
    """
    Socket connection to mod-host instance (UDP port 5555).
    """
    def __init__(self):
        self._socket = socket.socket()

    def connect(self):
        self._socket.connect(('localhost', 5555))
        self._socket.settimeout(0.5)

    def send(self, c):
        c += '\0'  # required for mod-host to recognize the command
        print('sending command: "{!s}"'.format(c))
        self._socket.send(c.encode('utf-8'))
        resp = self._socket.recv(1024)
        resp = resp.strip().replace(b'\0', b'').split()[1:]
        print(resp)
        if resp and int(resp[0]) < 0:  # error
            raise RuntimeError('Response from command "{}" was {}'.format(c, str(resp)))
        #resp = self._socket.recv(1024)
        return resp


class Plugin:
    MOD = None

    def __init__(self, name):
        self._params = {}
        self.name = name
        self.url = self.MOD.get_plugin_url(name)


class ModHostClient:
    """
    A client program making use of the socket connection to mod-host to control and query it.
    """
    def __init__(self):
        self._socket = ModHostSocket()
        self._socket.connect()
        self._available_plugins = self.list_plugins()
        self._installed_plugins = []
        Plugin.MOD = self
        self.remove_all_plugins()  # cleanup mod-host when starting client

    def close(self):
        self._socket.close()

    def list_plugins(self):
        plugins = {}
        output = subprocess.check_output(['lv2ls'])
        for l in [x.decode('utf-8') for x in output.splitlines()]:
            name = l.rsplit('/', 1)[-1]
            if '#' in name:
                name = name.split('#', 1)[0]
            plugins[name] = l
        return plugins

    def get_plugin_url(self, name):
        return self._available_plugins[name]

    def _get_jack_connections_lines(self):
        return subprocess.check_output(['jack_lsp', '-c']).splitlines()

    def get_connections(self):
        connections = []
        lines = self._get_jack_connections_lines()
        for i, line in enumerate(lines):
            if not any(p in line for p in ['capture', ':out']):  # only use outports as first item
                continue

            connected_ports = []
            j = 1
            while (i + j) < len(lines):
                next_line = lines[i+j]
                if next_line.startswith(b'   '):  # next line is a connected inport
                    connected_ports.append(next_line.strip())
                else:  # hit the next outport
                    break
                j += 1

            if connected_ports:
                connections.append((line, connected_ports))

        return connections

    def disconnect_all(self):
        for outport, inports in self.get_connections():
            for inport in inports:
                print('Disconnecting {} {}'.format(outport, inport))
                self._socket.send('disconnect {} {}'.format(outport, inport))

    def remove_all_plugins(self):
        for line in [l for l in self._get_jack_connections_lines() if l.startswith(b'effect_')]:
            i = line.split(b':', 1)[0].split(b'_', 1)[-1]
            print('Removing effect {}'.format(i))
            self._socket.send('remove {}'.format(i))
        self._installed_plugins = []

    def add_plugin(self, name, pos=-1):
        # Determine and verify position
        if pos == -1:
            pos = len(self._installed_plugins)
        assert pos <= len(self._installed_plugins)

        # Get plugin URL and check if it already exists in signal chain
        plugin_url = self._available_plugins[name]
        assert plugin_url not in self._installed_plugins  # already installed?

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
        print('New connection: {} -> pedal -> {}'.format(connect_from, connect_to))

        self._socket.send('add {} {}'.format(plugin_url, pos))
        self._socket.send('connect {} effect_{}:in_l'.format(connect_from, pos))
        self._socket.send('connect effect_{}:out_l {}'.format(pos, connect_to))

        # Stereo
        if connect_to == 'system:playback_1':
            print('Completeing stereo connection to system:playback')
            self._socket.send('connect effect_{}:out_l system:playback_2'.format(pos))

        self._installed_plugins.insert(pos, plugin_url)

    def remove_plugin(self, name):
        plugin_url = self._available_plugins[name] 
        assert plugin_url in self._installed_plugins

        self._socket.send('remove {}'.format(self._installed_plugins.index(plugin_url)))
        self._installed_plugins.remove(plugin_url)

    def load_preset_string(self, preset_str):
        plugins = preset_str.split(',')
        for p in plugins:
            name = p.split('[')[0]
            #self.disconnect_all()
            self.add_plugin(name)

    def get_plugin_info(self, name):
        plugin_url = self._available_plugins[name] 
        lines = subprocess.check_output(['lv2info', plugin_url]).splitlines()
        info = {
            'url': lines[0],
            'name': lines[2].split(b':', 1)[-1].strip(),
            'class': lines[3].split(b':', 1)[-1].strip(),
            'parameters': None
        }

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

        parameters = []
        for section in parameter_sections:
            if '#ControlPort' not in section[1]:  # skip non-control ports
                continue

            # This port is a control port, start parsing all lines
            port_info = {}
            for line in [l.strip() for l in section]:
                for p in ['Symbol', 'Name', 'Minimum', 'Maximum', 'Default']:
                    if line.startswith(p):
                        port_info[p.lower()] = line.split(':', 1)[-1].strip()
            parameters.append(port_info)

        info['parameters'] = parameters
        return info

    def set_parameter(self, i, symbol, value):
        return self._socket.send('param_set {} {} {}'.format(i, symbol, value))

    def get_parameter(self, i, symbol):
        return float(self._socket.send('param_get {} {}'.format(i, symbol))[1])
        #return self._socket.send('param_get {} {}'.format(i, symbol))

    def get_all_parameters(self, i, info):
        params = {}
        for s in [p['symbol'] for p in info['parameters']]:
            try:
                params[s] = self.get_parameter(i, s)
            except RuntimeError:
                pass
        return params


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
    reverb_test(m)

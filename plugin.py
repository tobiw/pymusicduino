import logging
import subprocess


class Lv2Plugin:
    def __init__(self, uri, connections=None):
        self._log = logging.getLogger('musicbox.Lv2Plugin')
        self._log.info('Creating new Plugin {}'.format(uri))

        self._uri = uri  # LV2 plugin URI
        self._name = ''  # Name from LV2 plugin information
        self._class = ''  # Class from LV2 plugin information
        self._parameters = []  # Parameters from LV2 plugin information
        self._index = None
        self._connections = connections or []  # outgoing connection indices to other effects
        self._has_stereo_input = self._has_stereo_output = False  # in/out port from LV2 plugin information
        self.is_enabled = True

        self._load_plugin_info()

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
    def parameters(self):
        return self._parameters

    @property
    def has_stereo_output(self):
        return self._has_stereo_output

    @property
    def has_stereo_input(self):
        return self._has_stereo_input

    def get_parameter_info_by_index(self, idx):
        """Returns a tuple (name, info) where info is a dict."""
        return list(self._parameters[idx].items())[0]

    def _load_plugin_info(self):
        self._log.info('Getting plugin info for {}'.format(self._uri))
        output = subprocess.check_output(['lv2info', self._uri]).decode('utf-8')
        lines = [l.strip() for l in output.splitlines()]
        # self._log.debug('lv2info output: ' + str(lines))
        for l in lines:
            if l.startswith('Name:'):
                self._name = l.split(':', 1)[-1].strip()
            if l.startswith('Class:'):
                self._class = l.split(':', 1)[-1].strip()
                break
        self._log.debug('Found plugin class/name: {}/{}'.format(self._class, self._name))

        # Determine stereo input and output
        if 'in_l' in output and 'in_r' in output:
            self._has_stereo_input = True
        if 'out_l' in output and 'out_r' in output:
            self._has_stereo_output = True

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
            port_name = None
            for line in [l.strip() for l in section]:
                if line.startswith('Name'):
                    port_name = line.split(':', 1)[-1].strip()
                for p, method in [('Symbol', str), ('Minimum', float), ('Maximum', float), ('Default', float)]:
                    if line.startswith(p):
                        port_info[p] = method(line.split(':', 1)[-1].strip())
            if port_name and port_info:
                self._parameters.append({port_name: port_info})
        self._log.debug('Found plugin parameters: ' + str(self._parameters))


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

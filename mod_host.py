import logging
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

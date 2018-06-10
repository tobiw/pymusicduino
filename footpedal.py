import time
from pythonosc import udp_client
from rtmidi import RtMidiIn, MidiMessage
from subprocess import call


def preset_cb(preset_number):
    print('Loading preset {} in mod-host ...'.format(preset_number))
    if preset_number == 0:
        info = c.get_plugin_info('MultiChorus')
        for p in info['parameters']:
            print('{}: {} to {}'.format(p['symbol'], p['minimum'], p['maximum']))
        c.remove_all_plugins()
        c.load_preset_string('MultiChorus[0 0 0 0]')
        print(c.get_all_parameters(0, info))
        c.set_parameter(0, 'mod_rate', 1.8)
    elif preset_number == 1:
        info = c.get_plugin_info('Reverb')
        for p in info['parameters']:
            print('{}: {} to {}'.format(p['symbol'], p['minimum'], p['maximum']))
        c.remove_all_plugins()
        c.load_preset_string('Compressor[0 0],Reverb[0 0 0 0]')
        print(c.get_all_parameters(1, info))
        c.set_parameter(1, 'room_size', 3)
    print(subprocess.check_output(['jack_lsp', '-c']))


def looper_cb(enable):
    if enable:
        print('Loading the looper ...')
        call(['/root/guitar.sh', 'stop'])
        time.sleep(1)
        call(['/root/looper.sh'])
    else:
        print('Killing the looper.')
        call(['killall', 'sooperlooper'])
        time.sleep(1)
        call(['/root/guitar.sh', 'start'])


class MidiToOsc:
    """
    Translates MIDI messages from a controller to OSC messages for the main program.

    Sets up MIDI and OSC connects, then everything is handled through a callback.
    Uses ALSA/RtMidi to receive MIDI messages. Assumes the OSC server is on localhost at the default port.
    """
    def __init__(self, midi_controller):
        self._midi = RtMidiIn()
        self._connect_midi(midi_controller)
        self._midi.setCallback(self._midi_message_cb)
        self._osc_client = udp_client.SimpleUDPClient('127.0.0.1', 5005)
        self._osc_client.send_message('/ping', '1')

        # This part needs to be configurable per mode/user config/DIP switches/etc
        self._cc_osc_translation = {
            10: '/preset/1',
            11: '/preset/2',
            12: '/preset/3',
            13: '/preset/4',
            14: '/looper/1',
            15: '/looper/undo',
            16: '/looper/record',
            17: '/looper/overdub'
        }

    def _connect_midi(self, midi_controller):
        port_names = [self._midi.getPortName(i) for i in range(self._midi.getPortCount())]
        print(port_names)

        # Find the MIDI port the Arduino Micro is connected to
        arduino_port = None
        for i, p in enumerate(port_names):
            if p.startswith(midi_controller):
                arduino_port = i
                break
        assert arduino_port is not None
        self._midi.openPort(arduino_port)

    def _midi_message_cb(self, msg):
        channel, cc, value = msg.getChannel(), msg.getControllerNumber(), msg.getControllerValue()
        osc_topic = self._cc_osc_translation.get(cc, None)
        print('{} -> {} -> {}'.format(cc, '1' if value > 0 else '0', str(osc_topic)))
        self._osc_client.send_message(osc_topic, '1')
        print('sent.')


def main():
    midi_osc = MidiToOsc('Arduino Micro')
    while True:
        pass


if __name__ == '__main__':
    main()

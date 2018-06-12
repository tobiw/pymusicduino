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
        # At the moment, Arduino Micro MIDI device should do:
        # --------------
        # | 5  6  7  8 |
        # | 1  2  3  4 |
        # --------------
        #    Press         Press         Press         Long        
        #    Preset        Stomp         Looper        Press       
        #    Mode          Mode          Mode                      
        # 1) Preset 1[10]  Stomp1En[20]  Undo[30]     PresetMod[40]
        # 2) Preset 2[11]  Stomp2En[21]  Record[31]   StompMode[41]
        # 3) Preset 3[12]  Stomp3En[22]  Overdub[32]  LooperMod[42]
        # 4) Preset 4[13]  Stomp4En[23]               Tuner[43]
        # 5) Stomp1En[14]  Stomp5En[24]               Stomp1Sel[44]
        # 6) Stomp2En[15]  Stomp6En[25]               Stomp2Sel[45]
        # 7) Stomp3En[16]  Stomp7En[26]               Stomp3Sel[46]
        # 8) Stomp4En[17]  TapTempo[27]               Stomp4Sel[47]
        self._cc_osc_translation = {
            10: '/preset/1', 11: '/preset/2', 12: '/preset/3', 13: '/preset/4',
            14: '/stomp/1/enable', 15: '/stomp/2/enable', 16: '/stomp/3/enable', 17: '/stomp/4/enable',
            20: '/stomp/1/enable', 21: '/stomp/2/enable', 22: '/stomp/3/enable', 23: '/stomp/4/enable',
            24: '/stomp/5/enable', 25: '/stomp/6/enable', 26: '/stomp/7/enable', 27: '/tap/1',
            30: '/looper/undo', 31: '/looper/record', 32: '/looper/overdub', 33: '',
            34: '', 35: '', 36: '', 37: '',
            40: '/mode/preset', 41: '/mode/stomp', 42: '/mode/looper', 43: '/mode/tuner',
            44: '/stomp/1/select', 45: '/stomp/2/select', 46: '/stomp/3/select', 47: '/stomp/4/select'
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
        if osc_topic:
            self._osc_client.send_message(osc_topic, '1')
            print('sent.')

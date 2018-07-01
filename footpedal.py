from pythonosc import udp_client
from rtmidi import RtMidiIn, RtMidiOut


class MidiToOsc:
    """
    Translates MIDI messages from a controller to OSC messages for the main program.

    Sets up MIDI and OSC connects, then everything is handled through a callback.
    Uses ALSA/RtMidi to receive MIDI messages. Assumes the OSC server is on localhost at the default port.
    """
    def __init__(self, midi_controller):
        self._midi_in, self._midi_out = RtMidiIn(), RtMidiOut()
        self._connect_midi(midi_controller)
        self._midi_in.setCallback(self._midi_message_cb)
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
            # Presets
            10: '/preset/1', 11: '/preset/2', 12: '/preset/3', 13: '/preset/4',
            14: '/stomp/1/enable', 15: '/stomp/2/enable', 16: '/stomp/3/enable', 17: '/stomp/4/enable',

            # Stompboxes
            20: '/stomp/1/enable', 21: '/stomp/2/enable', 22: '/stomp/3/enable', 23: '/stomp/4/enable',
            24: '/stomp/5/enable', 25: '/stomp/6/enable', 26: '/stomp/7/enable', 27: '/stomp/8/enable',

            # Looper
            30: '/looper/undo', 31: '/looper/record', 32: '/looper/overdub', 33: '',
            34: '', 35: '', 36: '', 37: '',

            # Metronome
            40: '/metronome/pause', 41: '/metronome/dec_bpm', 42: '/metronome/inc_bpm', 43: '/metronome/tap',
            44: '', 45: '', 46: '', 47: '',

            # Long press
            100: '/mode/preset', 101: '/mode/stomp', 102: '/mode/looper', 103: '/mode/metronome',
            104: '/stomp/1/select', 105: '/stomp/2/select', 106: '/stomp/3/select', 107: '/stomp/4/select'
        }

    def _connect_midi(self, midi_controller):
        def find_port(ports, name):
            for i, p in enumerate(ports):
                if p.startswith(name):
                    return i
            return None

        # Find the MIDI In port the Arduino Micro is connected to
        arduino_port = find_port([self._midi_in.getPortName(i) for i in range(self._midi_in.getPortCount())], midi_controller)
        if arduino_port is None:
            raise ValueError('Could not find "Arduino Micro" MIDI port')

        print("MidiIn connecting to {}".format(arduino_port))
        self._midi_in.openPort(arduino_port)

        # Find the MIDI Out port the Arduino Micro is connected to
        arduino_port = find_port([self._midi_out.getPortName(i) for i in range(self._midi_out.getPortCount())], midi_controller)
        assert arduino_port is not None
        print("MidiOut connecting to {}".format(arduino_port))
        self._midi_out.openPort(arduino_port)

    def _midi_message_cb(self, msg):
        cc, value = msg.getControllerNumber(), msg.getControllerValue()
        osc_topic = self._cc_osc_translation.get(cc, None)
        print('{} -> {} -> {}'.format(cc, '1' if value > 0 else '0', str(osc_topic)))
        if osc_topic:
            self._osc_client.send_message(osc_topic, '1')
            print('sent.')

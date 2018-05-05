#!/usr/bin/env python3

from rtmidi import RtMidiIn, MidiMessage
from subprocess import call
from mod_host import ModHostClient


c = ModHostClient()


def preset_cb(preset_number):
    print('Loading preset {} in mod-host ...'.format(preset_number))
    if preset_number == 0:
        info = c.get_plugin_info('MultiChorus')
        for p in info['parameters']:
            print('{}: {} to {}'.format(p['symbol'], p['minimum'], p['maximum']))
        c.load_preset_string('MultiChorus[0 0 0 0]')
        print(c.get_all_parameters(0, info))
        c.set_parameter(0, 'mod_rate', 1.8)
    elif preset_number == 1:
        info = c.get_plugin_info('Reverb')
        for p in info['parameters']:
            print('{}: {} to {}'.format(p['symbol'], p['minimum'], p['maximum']))
        c.load_preset_string('Compressor[0 0],Reverb[0 0 0 0]')
        print(c.get_all_parameters(1, info))
        c.set_parameter(1, 'room_size', 3)


def looper_cb(enable):
    if enable:
        print('Loading the looper ...')
        call(['/root/looper.sh'])
    else:
        print('Killing the looper.')
        call(['killall', 'sooperlooper'])


def midi_message_cb(msg):
    channel, cc, value = msg.getChannel(), msg.getControllerNumber(), msg.getControllerValue()
    print('{} -> {}'.format(cc, '1' if value > 0 else '0'))

    if value == 127:
        if 60 <= cc <= 63:
            preset_cb(cc - 60)
        elif 64 <= cc <= 65:
            looper_cb(enable=cc == 64)


def main():
    m = RtMidiIn()
    
    port_names = [m.getPortName(i) for i in range(m.getPortCount())]
    print(port_names)
    
    arduino_port = None
    for i, p in enumerate(port_names):
        if p.startswith('Arduino Micro'):
            arduino_port = i
            break
    
    assert arduino_port is not None
    
    m.openPort(arduino_port)
    m.setCallback(midi_message_cb)

    while True:
        pass


if __name__ == '__main__':
    main()

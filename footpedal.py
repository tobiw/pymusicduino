#!/usr/bin/env python3

import time
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


looper_enabled = False


def midi_message_cb(msg):
    global looper_enabled

    channel, cc, value = msg.getChannel(), msg.getControllerNumber(), msg.getControllerValue()
    print('{} -> {}'.format(cc, '1' if value > 0 else '0'))

    if value == 127:
        if 60 <= cc <= 61:
            preset_cb(cc - 60)
        elif cc  == 65:
            looper_enabled = not looper_enabled
            looper_cb(enable=looper_enabled)


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

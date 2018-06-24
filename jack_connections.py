from subprocess import check_call, check_output


def _parse(s):
    """
    Parse a string (e.g. from jack_lsp -c) into a dict.

    >>> _parse('')
    {}
    >>> _parse('a:out\\n   b:in')
    {'a:out': ['b:in']}
    >>> _parse('a:out\\n   b:in\\n   c:in')
    {'a:out': ['b:in', 'c:in']}
    """
    connections = {}

    if s is None or s == []:
        raise ValueError('s must be a string')

    if s == '':
        return connections

    lines = s.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('   '):  # connected port
            assert i > 0

            # Find line above which is originating port
            originating_port = [l for l in lines[:i] if not l.startswith(' ')][-1]
            assert originating_port

            if originating_port not in connections:
                connections[originating_port] = []
            connections[originating_port].append(line.strip())

    assert connections
    return connections


def get_connections():
    """
    system:capture_1
       sooperlooper:loop0_in_1
    system:capture_2
    system:playback_1
       sooperlooper:loop0_out_1
    system:playback_2
    system:playback_3
    system:playback_4
    mod-host:midi_in
    sooperlooper:common_in_1
    sooperlooper:common_out_1
    sooperlooper:common_in_2
    sooperlooper:common_out_2
    sooperlooper:loop0_in_1
       system:capture_1
    sooperlooper:loop0_out_1
       system:playback_1
    sooperlooper:loop0_in_2
    sooperlooper:loop0_out_2
    """
    return _parse(check_output(['jack_lsp', '-c']).decode('utf-8'))


def _jack_connect_disconnect(cmd, port_a, port_b):
    if cmd not in ['connect', 'disconnect']:
        raise ValueError('cmd must be connect or disconnect')

    if not port_a or not port_b:
        raise ValueError('port_a and port_b must be non-empty strings')

    current_ports = check_output(['jack_lsp']).decode('utf-8')
    if port_a not in current_ports or port_b not in current_ports:
        raise ValueError('port_a and port_b must be a valid port')

    check_call(['jack_' + cmd, port_a, port_b])


def connect(port_a, port_b):
    _jack_connect_disconnect('connect', port_a, port_b)


def disconnect(port_a, port_b):
    _jack_connect_disconnect('disconnect', port_a, port_b)

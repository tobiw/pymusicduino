import logging
from socket import socket, AF_INET, SOCK_STREAM
from threading import Thread
from pluginsmanager.observer.updates_observer import UpdatesObserver


def _open_socket_bind_listen(port, max_con=3):
    s = socket(AF_INET, SOCK_STREAM)
    s.bind(('0.0.0.0', port))
    s.listen(max_con)
    return s


class TcpNotifier(UpdatesObserver):
    def __init__(self):
        self._running = True
        self._connection = None
        self._log = logging.getLogger('musicbox.TcpNotifier')

        self._socket = _open_socket_bind_listen(9955)
        self._thread = Thread(target=self._serve)
        self._thread.start()

    def close(self):
        self._running = False
        self._socket.close()
        self._thread.join()

    def _serve(self):
        while self._running:
            self._log.info('Ready to accept connection')
            self._connection, addr = self._socket.accept()
            self._log.info('Incoming connection from ' + str(addr))

            while True:
                try:
                    data = self._connection.recv(128).decode()
                except ConnectionResetError:
                    self._log.error('Connection broken')
                    break

                if not data:
                    self._log.warn('recv() returned empty data')
                    break
                if data == 'QUIT\n':
                    break
            self._connection.close()

    def update(self, msg):
        """Sends datalength packet and as many data packets as required"""
        msg_enc = (msg + '\n').encode()
        datalen_msg = 'DATALEN:{:04d}\n'.format(len(msg_enc))
        self._log.debug('Sending datalen message: ' + datalen_msg)
        if self._connection:
            self._connection.send(datalen_msg.encode())
            self._log.debug('Sending update notification "{:s}..." of length {:d}'.format(msg[:min(20, len(msg))], len(msg_enc)))
            self._connection.sendall(msg_enc)

    def _preset_info_notifier_update(self, preset_id):
        # Construct JSON payload for notifiers:
        # current preset, list of stompboxes with parameters
        notifier_data = {
            'preset_id': int(preset_id),
            'preset_name': self._pedalboard.graph.settings['name'],
            'stompboxes': []
        }

        # Loop over all stompboxes (nodes on pedalboard graph)
        for sb in self._pedalboard.graph.nodes:
            sb_data = {
                'name': sb.name,
                'parameters': []
            }

            # Loop over stombox's parameters
            assert len(sb.parameters) == len(sb.effect.parameters)
            for i, p in enumerate(sb.parameters):  # p is { 'NAME': { params } }
                assert len(p.keys()) == 1
                p_name = list(p.keys())[0]
                param_data = {
                    'name': p_name,
                    'symbol': p[p_name]['Symbol'],
                    'min': p[p_name]['Minimum'],
                    'max': p[p_name]['Maximum'],
                    'value': sb.effect.parameters[i]
                }
                sb_data['parameters'].append(param_data)

            notifier_data['stompboxes'].append(sb_data)

    def on_bank_updated(self, bank, update_type, index, origin, **kwargs):
        self._log.debug('on_bank_updated: bank {} update_type {} index {} origin {} kwargs {}'.format(
                        bank, update_type, index, origin, kwargs))
        self.update('BANK:{:d}'.format(index))

    def on_pedalboard_updated(self, pedalboard, update_type, index, origin, **kwargs):
        self._log.debug('on_pedalboard_updated: pedalboard {} update_type {} index {} origin {} kwargs {}'.format(
                        pedalboard, update_type, index, origin, kwargs))

    def on_effect_status_toggled(self, effect, **kwargs):
        self._log.debug('on_effect_status_toggled: effect {} kwargs {}'.format(effect, kwargs))
        self.update("STOMPEN:{:d}:{:d}".format(effect.index, int(effect.active)))

    def on_effect_updated(self, effect, update_type, index, origin, **kwargs):
        self._log.debug('on_effect_updated: effect {} update_type {} index {} origin {} kwargs {}'.format(
                        effect, update_type, index, origin, kwargs))

    def on_param_value_changed(self, param, **kwargs):
        self._log.debug('on_param_value_changed: param {} kwargs {}'.format(param, kwargs))
        self.update("SLIDER:{:d}:{:f}".format(0, 0))  # TODO

    def on_connection_updated(self, connection, update_type, pedalboard, **kwargs):
        self._log.debug('on_connection_updated: connection {} update_type {} pedalboard {} kwargs {}'.format(
                        connection, update_type, pedalboard, kwargs))

import logging
from socket import socket, AF_INET, SOCK_STREAM
from threading import Thread


def _open_socket_bind_listen(port, max_con=3):
    s = socket(AF_INET, SOCK_STREAM)
    s.bind(('0.0.0.0', port))
    s.listen(max_con)
    return s


class TcpNotifier:
    def __init__(self):
        self._running = True
        self._connection = None
        self._log = logging.getLogger('musicbox.TcpNotifier')

        self._socket = _open_socket_bind_listen(9955)
        self._thread = Thread(target=self._serve)
        self._thread.start()

    def _serve(self):
        while self._running:
            self._log.info('Ready to accept connection')
            self._connection, addr = self._socket.accept()
            self._log.info('Incoming connection from ' + str(addr))

            while True:
                try:
                    data = self._connection.recv(100).decode()
                except ConnectionResetError:
                    self._log.error('Connection broken')
                    break

                if not data:
                    break
                if data == 'PING':
                    self._connection.send('PONG'.encode())
                elif data == 'QUIT':
                    break
            self._connection.close()

    def update(self, msg):
        """Sends datalength packet and as many data packets as required"""
        msg_enc = msg.encode()
        datalen_msg = 'DATALEN:' + str(len(msg_enc))
        self._log.debug('Sending datalen message: ' + datalen_msg)
        if self._connection:
            self._connection.send(datalen_msg.encode())
            self._log.debug('Sending update notification "{:s}..." of length {:d}'.format(msg[:min(20, len(msg))], len(msg_enc)))
            self._connection.sendall(msg_enc)


class Notifier:
    def __init__(self):
        self._observers = []

    def add_observer(self, observer):
        if observer in self._observers:
            raise ValueError('{!r} already in observers'.format(observer))
        self._observers.append(observer)

    def update(self, msg):
        for o in self._observers:
            o.update()

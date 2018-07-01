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

        self._socket = _open_socket_bind_listen(9955)
        self._thread = Thread(target=self._serve)
        self._thread.start()

    def _serve(self):
        while self._running:
            self._connection, addr = self._socket.accept()
            while True:
                data = self._connection.recv(100).decode()
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
        self._connection.send(datalen_msg.encode())
        if self._connection:
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

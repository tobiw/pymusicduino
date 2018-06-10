from threading import Thread
from pythonosc import dispatcher, osc_server, udp_client


class OscServer(object):
    def __init__(self, use_threading=True):
        self._use_threading = use_threading
        self._port = 5005
        self._dispatcher = dispatcher.Dispatcher()

        self.register_uri("/ping", self.cb_ping)
        self.register_uri("/quit", self.cb_quit)

    def register_uri(self, uri, func, *args):
        self._dispatcher.map(uri, func, *args)

    def cb_ping(self, *args):
        print("PING " + str(list(args)))

    def cb_quit(self, *args):
        print("QUIT " + str(list(args)))
        self.stop()

    def start(self):
        self._server = osc_server.ThreadingOSCUDPServer(('0.0.0.0', self._port), self._dispatcher)
        if self._use_threading:
            self._thread = Thread(target=self._server.serve_forever)
            self._thread.start()
        else:
            self._server.serve_forever()

    def stop(self):
        self._server.shutdown()


class FootpedalOscServer(OscServer):
    """
    Central receiver for OSC messages which can control the program itself, mod-host, sooperlooper.

    Messages (/bank/1 == /bank with message "1"):
    - /bank/<N>: loads a preset bank
    - /preset/<N>: loads a preset (mod-host plugins + optional sooperlooper instance)
    - /stompbox/<N>: selects/enables a stompbox
    - /looper/<undo|record|overdub>: passed through to sooperlooper instance
    """
    def __init__(self):
        OscServer.__init__(self)
        self.register_uri("/preset/*", self.cb_preset)
        self.register_uri("/slider/?/*", self.cb_slider)
        self.register_uri("/looper/*", self.cb_looper)

        # OSC connection to sooperlooper
        self._looper_osc = udp_client.SimpleUDPClient('127.0.0.1', 9951)

    def cb_preset(self, uri, msg=None):
        preset_id = int(uri.rsplit('/', 1)[-1])
        print("PRESET {:d}".format(preset_id))
        # TODO: tell mod-host to load preset x
        # TODO: if preset contains looper: start sooperlooper

    def cb_slider(self, uri, msg=None):
        _, slider_id, value = uri.rsplit('/', 2)
        slider_id = int(slider_id)
        value = float(value)
        print("SLIDER {:d} = {:f}".format(slider_id, value))
        # TODO: tell mod-host to set param x

    def cb_looper(self, uri, msg=None):
        _, command = uri.rsplit('/', 1)
        if command in ['undo', 'record', 'overdub']:
            self._looper_osc.send_message("/sl/0/hit", command)
            print("Sent /sl/0/hit s:{:s} to sooperlooper".format(command))
        else:
            print("Invalid sooperlooper command {:s}".format(command))


if __name__ == '__main__':
    s = FootpedalOscServer()
    s.start()
    s._thread.join()

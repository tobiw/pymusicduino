from threading import Thread
from pythonosc import dispatcher, osc_server


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
    - /mode/preset: activates preset mode (load presets, some stompbox control)
    - /mode/stomp: activates stompbox mode (control over 8 stompboxes, no presets)
    - /mode/looper: activates looper mode (all footswitches used for looper control)
    - /mode/tuner: mute sound and display tuner
    - /preset/<N>: loads a preset (mod-host plugins + optional sooperlooper instance)
    - /stompbox/<N>/enable: enables/disables (toggles) a stompbox
    - /stompbox/<N>/select: selects a stompbox for editing
    - /slider/<N>/<V>: set slider <N> to value <V>
    - /looper/<undo|record|overdub>: passed through to sooperlooper instance
    """
    def __init__(self, cb_mode, cb_preset, cb_stomp_enable, cb_stomp_select, cb_looper, cb_metronome, cb_slider):
        OscServer.__init__(self)
        self.register_uri("/mode/*", cb_mode)  # modes as string ("preset", etc)
        self.register_uri("/preset/*", cb_preset)  # preset number (1-4)
        self.register_uri("/stomp/*", cb_stomp_enable)  # enable stompbox (1-8)  TODO FIXUP
        self.register_uri("/stomp/?/select", cb_stomp_select)  # select stompbox for editing (1-8)
        self.register_uri("/looper/*", cb_looper)  # looper commands ("undo", "record", etc)
        self.register_uri("/metronome/*", cb_metronome)  # Send metronome commands (e.g. a tap (1) or tap tempo value (30-300))

        # Extra inputs (not on pedal board; e.g. OSC app)
        self.register_uri("/slider/?/*", cb_slider)  # slider value (0-1023)

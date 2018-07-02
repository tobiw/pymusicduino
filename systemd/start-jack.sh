#!/bin/bash

export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket

PIDFILE=/var/run/jackd.pid

aplay -l | grep -q Saffire
SAFFIRE_MISSING=$?
if [[ $SAFFIRE_MISSING -eq 0 ]]
then
  CARD=1
else
  CARD=0
fi
CARD=1
FRAMES=128
PERIODS=3

function jack_start()
{
  start-stop-daemon --start --oknodo --quiet --make-pidfile --pidfile $PIDFILE --background --startas /usr/bin/jackd -- -P90 -p64 -t1000 -d alsa -d hw:$CARD -D -p${FRAMES} -n${PERIODS} -r 48000 -s
}

function jack_stop()
{
  start-stop-daemon --stop --pidfile $PIDFILE
}

case "$1" in
  start)
    jack_start
    ;;
  stop)
    jack_stop
    ;;
  *)
    echo "Usage: $0 (start|stop)"
    exit 1
    ;;
esac

exit 0

#!/bin/bash

PIDFILE=/var/run/musicbox.pid
PROGPATH=/root/pymusicduino

function musicbox_start()
{
  start-stop-daemon --start --oknodo --quiet --make-pidfile --pidfile $PIDFILE --background --startas $PROGPATH/.venv/bin/python3 -- $PROGPATH/musicbox.py
}

function musicbox_stop()
{
  start-stop-daemon --stop --pidfile $PIDFILE
}

case "$1" in
  start)
    musicbox_start
    ;;
  stop)
    musicbox_stop
    ;;
  *)
    echo "Usage: $0 (start|stop)"
    exit 1
    ;;
esac

exit 0

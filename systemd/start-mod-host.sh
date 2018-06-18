#!/bin/bash

PIDFILE=/var/run/mod-host.pid

function modhost_start()
{
  start-stop-daemon --start --oknodo --make-pidfile --pidfile $PIDFILE --exec /usr/local/bin/mod-host
}

function modhost_stop()
{
  start-stop-daemon --stop --pidfile $PIDFILE
  pkill mod-host
  rm $PIDFILE
}

case "$1" in
  start)
    modhost_start
    ;;
  stop)
    modhost_stop
    ;;
  status)
    cat $PIDFILE
    ;;
  *)
    echo "Usage: $0 (start|stop)"
    exit 1
    ;;
esac

exit 0

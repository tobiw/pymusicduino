#!/bin/bash

PIDFILE=/var/run/sooperlooper.pid

function sooperlooper_start()
{
  # sooperlooper -c 1 -m /root/sooperlooper.slb &
  start-stop-daemon --start -b --oknodo --make-pidfile --pidfile $PIDFILE --exec /usr/bin/sooperlooper
  sleep 3
  /usr/bin/jack_connect system:capture_1 sooperlooper:loop0_in_1
  /usr/bin/jack_connect sooperlooper:loop0_out_1 system:playback_1
}

function sooperlooper_stop()
{
  start-stop-daemon --stop --pidfile $PIDFILE
  rm -f $PIDFILE
}

case "$1" in
  start)
    sooperlooper_start
    ;;
  stop)
    sooperlooper_stop
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

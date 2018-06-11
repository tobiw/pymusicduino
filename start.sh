#!/bin/sh
PY=.venv/bin/python
$PY footpedal.py &
$PY osc_server.py &

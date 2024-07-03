#!/bin/bash
pid_file="/tmp/auto_odm_start.pid"

if [ ! -f "$pid_file" ]; then
    echo "PID file not found."
    exit 1
fi

pid=$(cat "$pid_file")

if ps -p $pid > /dev/null; then
    kill $pid
    rm "$pid_file"
    echo "TERM signal sent."
else
    echo "Process not found."
    exit 1
fi
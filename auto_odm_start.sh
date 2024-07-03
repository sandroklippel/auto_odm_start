#!/bin/bash

if [ -z "$1" ]; then
    echo "Error: Configuration file path not supplied."
    exit 1
fi

/usr/local/bin/auto_odm_start_service --config "$1" &
echo $! > /tmp/auto_odm_start.pid
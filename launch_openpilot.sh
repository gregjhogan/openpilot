#!/usr/bin/bash

#export PASSIVE="0"
export PASSIVE=$(( $(cat /sys/class/switch/tri-state-key/state) == 1 ? 1 : 0 ))
exec ./launch_chffrplus.sh


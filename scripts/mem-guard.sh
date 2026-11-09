#!/bin/bash
# Stop a server process if MemAvailable falls below a floor (default 6 GiB). Checks once a second while it runs.
# usage: mem-guard.sh PID [MIN_GIB]
# On the Spark the GPU and the OS share one pool of memory. If it runs out, the kernel's OOM killer can stop system
# services as well as the server. Stopping the server first is the safer failure.
set -u
PID=$1; MIN=${2:-6}
while kill -0 "$PID" 2>/dev/null; do
  avail=$(awk '$1=="MemAvailable:"{print int($2/1048576)}' /proc/meminfo)
  if [ "$avail" -lt "$MIN" ]; then
    echo "$(date +%T) MemAvailable ${avail} GiB is below ${MIN} GiB: stopping process $PID"
    kill -TERM "$PID"; sleep 5
    kill -0 "$PID" 2>/dev/null && kill -KILL "$PID"
    exit 1
  fi
  sleep 1
done

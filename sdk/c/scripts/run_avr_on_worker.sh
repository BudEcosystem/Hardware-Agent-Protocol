#!/bin/bash
# Ship sdk/c, protocol/serial and the SDK's compact codec (the pty harness loads it by path) to the AMD worker, build the AVR image there and
# run avr_sim_test.sh in a container (nice -n 10, <= 4 CPUs, only under ~/hms-lab; containers are named hms-lab-*).
# Usage: run_avr_on_worker.sh [worker-host]     (default: bmh-worker)
set -eu
HOST=${1:-bmh-worker}
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
LAB='~/hms-lab/bhms9a'
cd "$ROOT"
ssh "$HOST" "mkdir -p $LAB/src && nice -n 10 docker run --rm --name hms-lab-bhms-avr-clean-\$\$ -v $LAB:/lab ubuntu:24.04 rm -rf /lab/src && mkdir -p $LAB/src"
tar --exclude='sdk/c/build*' -cf - sdk/c protocol/serial sdk/python/src/bhms/transport/compact.py | ssh "$HOST" "tar -xf - -C $LAB/src"
# The container runs as the invoking user so no root-owned files appear in the lab.
ssh "$HOST" "cd $LAB/src && nice -n 10 docker build -q -t bhms9a-avr -f sdk/c/scripts/docker/Dockerfile.avr . >/dev/null && \
  nice -n 10 docker run --rm --name hms-lab-bhms-avr-build-\$\$ --cpus=4 --user \$(id -u):\$(id -g) -e HOME=/tmp -v $LAB/src:/work bhms9a-avr \
  /work/sdk/c/scripts/avr_sim_test.sh /work/sdk/c/build-avr"

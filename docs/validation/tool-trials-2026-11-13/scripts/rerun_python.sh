#!/usr/bin/env bash
. "$(dirname "$0")/common.sh"; cd "$LAB/trials"
export ROBOT_DESCRIPTIONS_CACHE="$LAB/cache/robot_descriptions" UV_LOCK_TIMEOUT=1200
run() { local t0=$(date +%s); "$LAB/venvs/$2/bin/python" "$3" > "$LAB/results/$1.json" 2> "$LAB/logs/$1.log"; echo "$1 exit=$? secs=$(( $(date +%s) - t0 )) bytes=$(stat -c %s "$LAB/results/$1.json")"; }
run arm_mujoco arm arm_mujoco.py
venv microscope microscope numpy scipy pillow 2>"$LAB/logs/install-microscope.log" && run microscope_sim microscope microscope_sim.py
venv lab pylabrobot bluesky ophyd pyvisa pyvisa-sim pymodbus asyncua 2>"$LAB/logs/install-lab.log" && run lab_instruments lab lab_instruments.py
echo RERUN_DONE

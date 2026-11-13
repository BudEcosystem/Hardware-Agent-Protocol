#!/usr/bin/env bash
# Runs the pure-Python simulator trials. Each writes results/<name>.json and logs/<name>.log.
. "$(dirname "$0")/common.sh"; cd "$LAB/trials"
export ROBOT_DESCRIPTIONS_CACHE="$LAB/cache/robot_descriptions"
run() { # run <name> <venv> <script>
  local t0=$(date +%s)
  "$LAB/venvs/$2/bin/python" "$3" > "$LAB/results/$1.json" 2> "$LAB/logs/$1.log"
  echo "$1 exit=$? secs=$(( $(date +%s) - t0 )) bytes=$(stat -c %s "$LAB/results/$1.json")"
}
( venv arm mujoco robot_descriptions numpy imageio 2>>"$LAB/logs/install-arm.log" && run arm_mujoco arm arm_mujoco.py ) &
( venv microscope microscope numpy scipy pillow 2>>"$LAB/logs/install-microscope.log" && run microscope_sim microscope microscope_sim.py ) &
( venv lab pylabrobot bluesky ophyd pyvisa pyvisa-sim pymodbus asyncua 2>>"$LAB/logs/install-lab.log" && run lab_instruments lab lab_instruments.py ) &
( venv opentrons opentrons 2>>"$LAB/logs/install-opentrons.log" && run opentrons_sim opentrons opentrons_sim.py ) &
wait; echo ALL_PYTHON_TRIALS_DONE

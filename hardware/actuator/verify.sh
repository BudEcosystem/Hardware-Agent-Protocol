#!/usr/bin/env bash
# Regenerate and verify everything in hardware/actuator.
#
#   CAD_PY   python with build123d + trimesh   (default: python3)
#   SIM_PY   python with mujoco + pillow       (default: python3)
#   KICAD_PY python that can import pcbnew      (default: python3; KiCad env vars set)
#   FREEROUTING  router command line (e.g. "xvfb-run -a java -jar freerouting-1.9.0.jar"); when unset the committed .ses files are imported
#
# Steps that need a tool which is not available fail loudly; nothing is skipped silently.
# The only skip is explicit: ALLOW_NO_KICAD=1 skips the kicad-cli ERC/DRC/Gerber steps and says so in the summary.
#   SKIP_ROUTE=1 (or FREEROUTING unset) imports the committed Freerouting sessions (pcb/*/*.ses) instead of re-routing.
set -euo pipefail
cd "$(dirname "$0")"
CAD_PY=${CAD_PY:-python3}
SIM_PY=${SIM_PY:-python3}
KICAD_PY=${KICAD_PY:-python3}

step() { printf '\n=== %s\n' "$*"; }

step "CAD: build all parts (STL + STEP)";        $CAD_PY cad/build.py
step "CAD: mesh checks (trimesh)";               $CAD_PY cad/check_meshes.py
step "CAD: interference, sweeps + 2500 random poses x 4 tools (slow)"; $CAD_PY cad/check_clearance.py
step "Torque budget";                            python3 cad/torque_budget.py
step "MJCF generation";                          python3 sim/gen_mjcf.py
step "MuJoCo: load, gravity hold, pick & place"; $SIM_PY sim/test_arm.py
step "Renders";                                  MUJOCO_GL=${MUJOCO_GL:-egl} $SIM_PY sim/render.py
step "PCB: generate";                            $KICAD_PY pcb/build.py generate
if [[ -n "${FREEROUTING:-}" && "${SKIP_ROUTE:-0}" != "1" ]]; then
  step "PCB: route (Freerouting)";               $KICAD_PY pcb/build.py route
else
  step "PCB: import committed Freerouting sessions (.ses)"; $KICAD_PY pcb/build.py import
fi
step "PCB: checks (scripted + kicad-cli)";       $KICAD_PY pcb/build.py check
step "PCB: fabrication outputs";                 $KICAD_PY pcb/build.py fab
step "BOM";                                      python3 bom/build_bom.py
step "Summary (anything SKIPPED or open is listed here)"
$KICAD_PY pcb/build.py summary
if [[ "${ALLOW_NO_KICAD:-0}" == "1" ]]; then echo "SKIPPED: KiCad ERC/DRC and Gerber export (ALLOW_NO_KICAD=1)"; fi
echo "verify.sh: all steps completed"

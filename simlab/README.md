# SimLab

One shared simulated laboratory for validating BHMS. The physical side is a `World` (MuJoCo bench with the SO-ARM100, one
clock, an append-only effect log), a material `Ledger`, a `FaultPlane` and an `Oracle` that agents never see. The devices are
BHMS device servers built with the Python SDK; the adapters bridge Modbus TCP, OPC UA, SCPI, Home Assistant, MCP and
Micro-Manager into BHMS.

```
agents / runtimes  --BHMS only-->  twins (DeviceServer)  and  adapters (DeviceServer) -> instrument servers (real protocols)
                                        \                                  /
                                         '------ World + Ledger + FaultPlane ------> Oracle (ground truth)
```

## Layout

| Path | What |
|---|---|
| `src/simlab/world.py` `ledger.py` `faults.py` `oracle.py` `control.py` | the physical world, materials, faults, ground truth, harness control socket |
| `src/simlab/scene/bench.xml` | the bench: sites `hotel slide_rack lh_deck microscope_stage reader balance`, plate and slide, four knob joints, cameras |
| `src/simlab/twins/` | arm, microscope, liquid handler, plate reader, balance, thermal block, centrifuge (each `build_server`) |
| `src/simlab/instruments/` | protocol servers over the shared models: pymodbus 3.8.6 thermal, asyncua centrifuge, scripted SCPI balance |
| `src/simlab/adapters/` | profile-driven BHMS adapters: `modbus opcua scpi home_assistant mcp_client micromanager` |
| `src/simlab/agents/scripted.py` | deterministic agents (autofocus, load-and-image) over direct and BHMS ports |
| `src/simlab/runs/` | `multidevice` (UC4 and a four-device assay), `fault_runs` (10 scenarios), `benchmark`, `judge` |
| `src/simlab/lab.py` | start every device on its own socket (optionally bridged through its protocol) |
| `tests/` | one module per component plus `contract.py`, the device contract every server must meet |

## Running (AMD machine)

```
rsync -a simlab/ bmh-worker:hms-lab/repo/simlab/
ssh bmh-worker 'cd ~/hms-lab/repo/simlab && export MUJOCO_GL=egl ROBOT_DESCRIPTIONS_CACHE=$HOME/hms-lab/cache/robot_descriptions \
  PYTHONPATH=$PWD/src SIMLAB_HA_URL=http://127.0.0.1:18123 SIMLAB_HA_REFRESH=$HOME/hms-lab/cache/ha_refresh.json &&
  ../../venvs/simlab/bin/python -m pytest -q'
python -m simlab.runs.multidevice --scenario uc4 --seed 1 --out DIR      # judged multi-device run
python -m simlab.runs.fault_runs --out DIR                               # fault injection
python -m simlab.runs.benchmark --out DIR                                # realtime factors
```

The venv is `~/hms-lab/venvs/simlab` (Python 3.12, uv, `bhms` from `sdk/python`, mujoco 4.0.1, pymodbus 3.8.6, asyncua, mcp 2.x,
pymmcore-plus). The Home Assistant tests need the demo container (`docker start hms-lab-ha`) and skip without `SIMLAB_HA_URL`.

## Decisions

* **Arm model is a parameter.** `World(arm_model=...)` (or `SIMLAB_ARM_MODEL`) attaches any MJCF that has the SO-ARM100's joint
  and jaw names at `arm_mount` with prefix `arm_`; the BHMS Arm MJCF replaces the Menagerie model without touching a twin.
* **Objects are kinematic.** Plate and slide are mocap bodies placed by the ledger (site, gripper tip, or the floor when lost);
  the arm's joint dynamics are real, the grasp is a rule (close within 3 mm), and the reported jaw width comes from what is held.
* **Microscope face (the plan's spike): yes.** A pymmcore-plus `UniMMCore` accepts Python devices (`loadPyDevice`), so the
  Micro-Manager core API can be backed by the world (`simlab.mmbackend`): focus stage, XY stage, camera over `MicroscopeTwin`.
  The motorized face is therefore reachable three ways: native BHMS twin, Micro-Manager core API, and the BHMS adapter in front
  of that core. The manual face is the four knob joints with backlash and slip.
* **Instruments run in the lab process.** The Modbus, OPC UA and SCPI servers are real network servers, but they share the one
  world with the twins, so they live in the same process (separate processes would need a world server).
* **Evidence labels.** `measured` only where a modelled sensor with its own noise sits between the world and the reading
  (encoders, thermistor, tachometer, load cell, optical detector, tip-volume sensor, lid and plate switches). Adapters label what
  the instrument's profile says; Home Assistant and Micro-Manager values are `reported`; MCP tools complete with `none`.
* **Stepped and realtime clocks.** `World.step` is synchronous; `World.advance` is the awaitable form with one pump shared by
  every device (stepped: instant, realtime: paced). The clock resolution is one 2 ms physics step.

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
| `src/simlab/agents/session.py` `runner.py` `metrics.py` | the agent matrix: SimLab behind a BHMS gateway, one task x one agent x one seed, the five zero-metrics |
| `src/simlab/agents/baseline.py` `hostile.py` `drills.py` `pat.py` `facility.py` | scripted baseline per use case, 140 hostile attempts, UC13 recovery drills, UC6 PAT loop, UC11 Home Assistant truth |
| `tasks/*.yaml` | the tasks (UC1-UC7, UC11, adversarial and unsupported requests, fault variants) |
| `reports/` | the agent-matrix report and its run data |
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

## Agent matrix (validation plan section 4 and 5)

```
python -m simlab.agents.runner --tasks all --agent scripted --seeds 1,2,3 --out DIR            # deterministic baseline
python -m simlab.agents.runner --tasks uc2 --agent gpt-5.4-mini --budget 110000 --out DIR --ledger SPEND.tsv   # OpenAI key from ~/.config/hms/openai.env
python -m simlab.agents.runner --tasks adv --agent local --out DIR                              # llama.cpp server on 127.0.0.1:18080
python -m simlab.agents.hostile --out DIR --leases required                                     # 140 violation attempts
python -m simlab.agents.drills --out DIR                                                        # UC13, every step of UC4 and UC5
python -m simlab.agents.report ROOT --out reports/agent-matrix.md
```

Agents reach the lab only through a `bhms.gateway.Gateway` (principal, scopes and narrowed bounds per agent); the oracle judges
every operation of every principal. `Judged.truth_source` is kept: Home Assistant verdicts are `caller_rule`, never tallied as
world-backed. UC6 uses one `cell` device server (arm, handler, reader) because programs run inside one server and a gateway does
not offer `programs/*`.

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
* **Digest determinism holds only for sequential commands.** The same seed gives the same `World.digest()` when commands are issued one after another (direct runs, a single agent through BHMS with `anonymize_causes`). Concurrent agents interleave on the event loop and on wall-clock timers, so two runs with concurrent commands need not produce identical logs.
* **Judging.** Twins record the achieved truth when a motion or heating ends; `runs/judge.py` compares returned measurements and commanded targets with it, every action has a rule (a missing rule raises), and protocol instruments keep a command journal that the harness joins to the adapters' send records so bridged effects get causes.
* **Every SimLab device is marked simulated** (Ruling R16): device tag `simulated`, server name `simlab-*`, instructions that say so.
* **Stepped and realtime clocks.** `World.step` is synchronous; `World.advance` is the awaitable form with one pump shared by
  every device (stepped: instant, realtime: paced). The clock resolution is one 2 ms physics step.

# The BHMS Arm as a worked device

This guide walks through a complete physical device built for BHMS: the BHMS Arm, a 5-axis desktop arm with a
quick-change tool flange, an RP2040 controller running the C library, and a hardware E-stop. It shows how its description
expresses joints, tools, hazards and stop; how a gateway policy gives an agent motion but not power; and it drives the
arm's real firmware logic (host build, simulated servos) through a gateway, which the docs test executes. Hardware
sources: [`hardware/actuator`](../../../hardware/actuator/README.md); firmware contract:
[`firmware/INTERFACE.md`](../../../hardware/actuator/firmware/INTERFACE.md).

**Status.** Design only: nothing has been printed, assembled or powered, and no PCB has been manufactured. The firmware
runs here against a simulated rig (eight STS3215 servos, the rail sensor, the E-stop contacts, the tools). What follows
is evidence about the protocol and firmware logic, not about the physical arm.

## What the device enforces itself

The arm does not trust the host. In firmware, before anything reaches the servo bus:

- every joint goal is checked against its range and against coupled limits (shoulder + elbow at most 175 deg, and two
  more), and every interpolated waypoint is checked again;
- a jammed or lagging joint freezes the arm at its measured pose and latches;
- the E-stop button cuts the servo rail in hardware; firmware latches a restart inhibit, and only an explicit `enable`
  with the contact released re-energises the arm. The arm has no brakes: it falls when the rail is cut;
- `stop` freezes motion and keeps holding torque, and is confirmed only when every servo reports it is not moving.

## The description

The gateway serves the arm from its sidecar, [`firmware/arm.sidecar.json`](../../../hardware/actuator/firmware/arm.sidecar.json);
`core/arm_digest.h` is generated from it, so the board and the gateway agree on every table:

```sh run
python sdk/c/tools/bhms_digest.py hardware/actuator/firmware/arm.sidecar.json --check
```

```text output
sha256:...
```

```python run
import json

arm = json.load(open("hardware/actuator/firmware/arm.sidecar.json"))
print(arm["deviceId"], arm["resources"], len(arm["properties"]), "properties")
for name, action in arm["actions"].items():
    lease = "lease" if action["requiresLease"] else "no lease"
    print(f"{name:15} {action['effect']:12} {lease:9} {action['completionEvidence']:9} {','.join(action['resources'])}")
print(arm["safety"]["stop"], arm["safety"]["stopEvidence"], arm["safety"]["stopMaxDurationMs"], "ms")
```

```text output
bhms-arm ['bhms-arm/joints', 'bhms-arm/power', 'bhms-arm/tool'] 46 properties
move_joints reversible lease measured bhms-arm/joints
home reversible lease measured bhms-arm/joints
hold none no lease reported
release_torque hazardous lease ... bhms-arm/joints
enable hazardous lease measured bhms-arm/power
tool_mount reversible lease ... bhms-arm/tool
grip hazardous lease ... bhms-arm/tool
calibrate irreversible lease ... bhms-arm/joints,bhms-arm/power
supported measured 3000 ms
```

The choices behind it:

- **Three resources**: `joints`, `power` and `tool`, so a lease on the joints lets an agent move without being able to
  power the arm or change tools.
- **`hazardous` where people or property can be hurt**: energising the rail (`enable`), dropping the arm
  (`release_torque`), and the tool actions that apply force (`grip`, `turn`, `press`). Each requires a lease, and a scope
  must name it literally.
- **`completionEvidence: measured`** with `verifiedBy` naming the joint position properties: the servos' encoders are an
  independent measurement of the pose.
- **46 measured properties** (positions, loads, currents, temperatures, rail voltage and current, E-stop contacts and
  state): an agent can check what happened instead of trusting the command.
- **Stop** is `supported` with `measured` evidence and a 3 s bound; `onDisconnect: unknown`, because a lost link does not
  stop the arm, and the description says so.

## Run the firmware without hardware

Build the firmware's host simulator (the real `core/` code and the C endpoint, against the simulated rig, with
AddressSanitizer and UndefinedBehaviorSanitizer):

```sh run requires=cmake timeout=600
cmake -S hardware/actuator/firmware -B build-fw -DCMAKE_BUILD_TYPE=Debug > /dev/null
cmake --build build-fw --target sim_arm > /dev/null
ls build-fw/sim_arm
```

Serve its serial line on a Unix socket, as if the controller were plugged in over USB
(`python -m bhms.testing.compact_endpoint`, the SDK's stand-in for a board on a serial port):

```sh run background wait=arm.sock requires=cmake
python -m bhms.testing.compact_endpoint build-fw/sim_arm arm.sock --workdir arm-work
```

## A policy: motion for the agent, power for the operator

The agent may move the joints, go home, hold and stop, and nothing else: energising the arm, releasing torque,
calibrating and the tools stay with the operator. The scopes name those actions one by one. Save as `arm-gateway.toml` (with real hardware, `port = "/dev/ttyACM0"`, as
in [`examples/bhms/compact-gateway.toml`](../../../examples/bhms/compact-gateway.toml)):

```toml file=arm-gateway.toml
[gateway]
id = "arm-gw"
state_dir = "arm-gw-state"
listen = ["unix:arm-gw.sock", "ws://127.0.0.1:8765"]
instructions = "One BHMS Arm. The operator enables it; lease arm/bhms-arm/joints before moving."

[[upstream]]
name = "arm"
type = "compact"
port = "unix:arm.sock"
sidecar = "hardware/actuator/firmware/arm.sidecar.json"

[principals.agent]                           # token arm-agent-token
tokens = ["sha256:00db02a2b8de33d2231d7313e10da377807ad3980902bbdb0c0b574645a2ceb1"]
scopes = ["read", "lease", "invoke:arm/bhms-arm/move_joints", "invoke:arm/bhms-arm/home", "invoke:arm/bhms-arm/hold",
          "stop:arm/*"]
bounds = { "arm/bhms-arm/move_joints" = { speed_pct = { maximum = 50 } } }
```

`check-policy` waits for the board's HELLO and lists what each scope grants:

```sh run requires=cmake timeout=120
bhms gateway check-policy arm-gateway.toml
```

```text output
1 device served
principal agent
invoke:arm/bhms-arm/move_joints: arm/bhms-arm/move_joints
stop:arm/*: arm/bhms-arm
0 warnings
```

A glob would have granted more than intended, though never a hazardous action (BHMS-AUTH-003):

```sh run requires=cmake timeout=120
sed 's#"invoke:arm/bhms-arm/move_joints"#"invoke:arm/*/*"#' arm-gateway.toml > glob-gateway.toml
bhms gateway check-policy glob-gateway.toml
```

```text output
invoke:arm/*/*: arm/bhms-arm/calibrate, arm/bhms-arm/hold, arm/bhms-arm/home, arm/bhms-arm/move_joints, arm/bhms-arm/tool_mount, arm/bhms-arm/tool_unmount
note: does not grant the hazardous arm/bhms-arm/enable, arm/bhms-arm/grip, arm/bhms-arm/press, arm/bhms-arm/release_torque, arm/bhms-arm/turn: a hazardous action needs a scope that names it literally (BHMS-AUTH-003)
```

```sh run background wait=tcp:127.0.0.1:8765 requires=cmake
bhms gateway arm-gateway.toml
```

## Operate it

The operator (the Unix socket owner, `admin`) energises the arm under a lease on joints and power, moves it, and is
refused by the firmware for a pose that breaks a coupled limit:

```python run requires=cmake timeout=120
import asyncio

from bhms.client import Client

ARM = "arm/bhms-arm"
POSE = {"base_yaw": 20, "shoulder_pitch": 40, "elbow_pitch": 80, "wrist_pitch": 30, "wrist_roll": 0, "speed_pct": 100}


async def main():
    async with await Client.connect("unix:arm-gw.sock") as client:
        lease = (await client.leases_acquire([f"{ARM}/joints", f"{ARM}/power"], ttl_ms=60_000)).lease
        enabled = (await client.actions_invoke(ARM, "enable", {}, lease_id=lease.lease_id, operation_key="enable-1",
                                               wait_ms=15_000)).operation
        print("enable:", enabled.state)
        moved = (await client.actions_invoke(ARM, "move_joints", POSE, lease_id=lease.lease_id, operation_key="move-1",
                                             wait_ms=30_000)).operation
        print("move:", moved.state, moved.result)
        yaw = (await client.properties_read(ARM, "base_yaw_position_deg", fresh=True)).observation
        print("base_yaw:", round(yaw.value), yaw.unit, yaw.evidence, yaw.quality)
        folded = dict(POSE, shoulder_pitch=90, elbow_pitch=120)  # 90 + 120 > 175: the forearm would hit the base
        refused = (await client.actions_invoke(ARM, "move_joints", folded, lease_id=lease.lease_id,
                                               operation_key="move-2", wait_ms=30_000)).operation
        print("folded:", refused.state, refused.effect, refused.error.bhms_code, refused.error.may_have_acted)
        await client.leases_release(lease.lease_id)


asyncio.run(main())
```

```text output
enable: completed
move: completed {'max_error_deg': ...}
base_yaw: 20 deg measured valid
folded: failed none OUT_OF_RANGE False
```

The firmware refused the folded pose before it reached the bus (`effect none`, `mayHaveActed false`); the error's
message carries the limit's detail code (16, forearm pitch, in `INTERFACE.md`).

The agent, over WebSocket with its token, moves within its narrowed speed bound (`bhms call`, like the agent tools,
takes the joint lease for the call), and cannot energise the arm:

```sh run requires=cmake
export BHMS_TOKEN=arm-agent-token
bhms call ws://127.0.0.1:8765 arm/bhms-arm home speed_pct=30 --key agent-home-1
```

```text output
arm/bhms-arm.home op-... completed: ...
```

```sh run requires=cmake exit=1
BHMS_TOKEN=arm-agent-token bhms call ws://127.0.0.1:8765 arm/bhms-arm enable --key agent-enable-1
```

```text output
Refused: ...
```

A stop from any principal with the `stop` scope freezes the arm. It returns at once (a stop never waits), so the CLI
and the agent tool report `initiated`; the confirmation, from the servos' measured moving flags, arrives as a `stop`
event moments later:

```sh run requires=cmake
BHMS_TOKEN=arm-agent-token bhms stop ws://127.0.0.1:8765 arm/bhms-arm
```

```text output
stop not confirmed on 1 of 1 devices (1 initiated): arm/bhms-arm initiated Next: check them with bhms_read or stop again (0 operations canceled)
```

```python run requires=cmake
import asyncio

from bhms.client import Client


async def main():
    async with await Client.connect("unix:arm-gw.sock") as client:
        await asyncio.sleep(1)
        events = (await client.events_read(device_id="arm/bhms-arm", types=["stop"])).events
        print([event.data["outcome"] for event in events][-2:])
        waited = (await client.stop("operator check", device_ids=["arm/bhms-arm"], wait_ms=3000)).stops[0]
        print(waited.outcome, waited.evidence)


asyncio.run(main())
```

```text output
['initiated', 'confirmed']
confirmed measured
```

A caller that can wait passes `wait_ms` (here 3 s, the arm's declared `stopMaxDurationMs`) and gets `confirmed` with
`measured` evidence in the answer. The agent tool `bhms_stop` has no wait: an agent checks the outcome with `bhms_read`
(the `arm_state` and speed properties) or stops again.

## Two gaps this run shows

- `move_joints` and `enable` complete with effect `unverified`, although the firmware measures the pose and the
  description declares `completionEvidence: measured`: the compact bridge does not yet turn the endpoint's measured
  RESULT into verifying observations. Until it does, check the pose properties yourself (as above) or with
  `bhms_read`. Recorded for the next revision of the binding.
- The firmware's refusal reaches the client as `OUT_OF_RANGE` with the limit as a number (`detail 16`), and with the
  generic hint that partial effects are possible, although the refusal proves nothing moved. Read `mayHaveActed` and
  `effect`, which are right.

## With the real arm

Not run by the docs test (it needs the hardware and the RP2040 toolchain):

```sh no-run
hardware/actuator/firmware/scripts/run_rp2040_on_worker.sh      # build bhms_arm.uf2 (pico-sdk 2.x in Docker)
# hold BOOTSEL, plug in USB, copy bhms_arm.uf2 to the RPI-RP2 drive
bhms gateway examples/bhms/compact-gateway.toml                  # port = "/dev/ttyACM1" for the arm
```

Before the first enable: calibrate once per assembly (`calibrate`, with the arm resting on its support at the rest
pose; `enable` is refused until then), follow the first power-up checklist in
[`docs/assembly.md`](../../../hardware/actuator/docs/assembly.md), test the E-stop with the rail on, and read the open
issues in [`docs/design.md`](../../../hardware/actuator/docs/design.md) (section 12).

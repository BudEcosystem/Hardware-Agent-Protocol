# BHMS Arm controller firmware (RP2040)

Makes the universal actuator a BHMS device: the arm's joints, coupled limits, torque caps, E-stop
restart inhibit and tool change are enforced **on the device**, and the host (gateway, agent,
SimLab) only ever sees the BHMS-Compact binary binding over USB CDC
([spec/bhms/11-compact-binding.md](../../../spec/bhms/11-compact-binding.md)). The wire contract
is [INTERFACE.md](INTERFACE.md); the endpoint is `sdk/c` (unchanged except one field, see below).

```
core/arm_params.[ch]   joint ranges, ratios, torque caps, coupled limits, tool IDs (== cad/params.py)
core/arm_limits.[ch]   joint / coupled / waypoint limit checks; limit codes double as ERROR.detail
core/sts.[ch]          STS3215 packet codec (checksums), half-duplex bus transactions with echo check
core/power.[ch]        E-stop latch, boot self-test, rail/contact fault rules, INA219 conversions
core/tool_id.[ch]      tool-ID windows and 5-sample debounce
core/epoch_flash.[ch]  two-sector, page-per-record, CRC'd boot-epoch store (power-fail safe)
core/arm.[ch]          the controller: enable sequence, trajectories, tool procedures, stop
core/cal_store.[ch]    joint calibration in flash (same CRC'd record log as the epoch)
core/arm_device.[ch]   the BHMS device table: 11 actions, 46 properties, stop, fencing
arm.sidecar.json       BHMS description; core/arm_digest.h is generated from it (tools/gen_sidecar.py)
hal/rp2040/            pico-sdk port: UART0 1 Mbps half-duplex, I2C INA219, ADC, E-stop IRQ, USB CDC, flash
sim/                   host simulation of the board (8 STS servos, rail, INA219, E-stop, tools) + `sim_arm`
tests/                 C unit tests (ASan/UBSan), table-sync tests, pty end-to-end test
```

## Behaviour in one page

* **Enable** (`enable` action, lease): VIN >= 9 V, E-stop contact released, boot self-test of the rail
  (once per boot), rail on, ping, program and **read back** every servo's angle window, torque cap
  (shoulder 780/1000), return delay; measure the pose and refuse (`FAILED`, fault 12) if it violates
  a joint or coupled limit with a 3 deg margin; set goal = present, torque on.
* **Measured pose is enforced too**: while moving, a jammed or lagging joint (measured pose outside a limit, or
  15 deg behind its waypoint) freezes the arm at the measured pose and latches (INTERFACE.md section 9.1).
* **move_joints**: all five angles (0.01 deg), speed 5..100 %. Refused before it reaches the bus when a
  joint is out of range or a coupled limit is violated (`OUT_OF_RANGE`, detail names the limit:
  0..4 joint, 0x10 forearm_pitch, 0x11 hairpin, 0x12 tool_pitch). The firmware interpolates in joint
  space (smoothstep, peak speed = the commanded fraction of servo no-load speed / ratio) and checks
  **every waypoint** again before writing it. A servo-side speed cap and the angle window are the
  next layers.
* **E-stop**: the button cuts the rail in hardware. The GPIO IRQ clears `SERVO_EN` and latches an
  edge; the supervisor latches the restart inhibit within the same tick. Releasing the button does not
  re-energise anything: motion is refused (`INHIBITED`, detail 1) until an explicit `enable` with the
  contact released. `estop_state` (0 released / 1 pressed / 2 fault), `estop_contact_open`,
  `servo_rail_mv` and `servo_rail_ma` are measured properties. Contact A welded / Q2 shorted (GPIO8
  high, rail > 2 V for > 20 ms) latches until power-cycle. The arm has no brakes: after an E-stop
  `pose_unknown` is true until the next enable.
* **STOP** (BHMS stop message): freezes motion and keeps holding; the stop is *initiated* at once and
  *confirmed* (measured) when every servo reports not-moving, or the rail is measured dead.
* **Tool change** (`tool_mount` / `tool_unmount`): ID stable 5 x 10 ms, `TOOL_EN` on, 50 ms, ping,
  program, torque on; unmount: torque off, `TOOL_EN` off, 60 ms discharge, then the client rolls the
  wrist. Refused while the E-stop is not released. Hot unplug clears `TOOL_EN` at once (`tool_lost`).

## Build and test (host)

```sh
cmake -S hardware/actuator/firmware -B build-fw -DCMAKE_BUILD_TYPE=Debug   # ASan+UBSan on by default
cmake --build build-fw && ctest --test-dir build-fw --output-on-failure
```

## Build (RP2040)

Needs `arm-none-eabi-gcc` and pico-sdk 2.x with `lib/tinyusb` (neither is installed on the
workstation; the lab worker builds in Docker):

```sh
hardware/actuator/firmware/scripts/run_rp2040_on_worker.sh      # ships sources, builds, prints size
# or locally:  export PICO_SDK_PATH=...; cmake -S hardware/actuator/firmware/hal/rp2040 -B build-rp2040 -G Ninja
```

Flash `bhms_arm.uf2` over BOOTSEL. The rail is never switched on at boot.

Built for RP2040 (arm-none-eabi-gcc 13.2, pico-sdk 2.1.1, -Os): 50 884 bytes flash, about 9 KB static RAM
(5 920 bss + ~3.1 KB data). The `.uf2` is produced by `tools/bin2uf2.py` (picotool needs git and network at
configure time; the container build uses `-DPICO_NO_PICOTOOL=1`).

## Not done / needs hardware

See the Task 13b report: the servo register addresses and the knob servo's multi-turn absolute mode
(position mode, both angle limits 0) are unverified against a physical STS3215 (INTERFACE.md section 9.3);
the FSR force scale is uncalibrated. Calibration (`calibrate` action) must be run once per assembly:
until then `enable` is refused. A controller reset or watchdog reset drops the servo rail and the arm
falls (INTERFACE.md section 9.5).

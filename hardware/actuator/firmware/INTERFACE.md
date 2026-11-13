# BHMS Arm controller — firmware interface (input to Task 13b)

This file is the contract between the controller hardware (Task 13a) and
the RP2040 firmware (Task 13b). The source of truth for the pin map is
`hardware/actuator/pcb/controller.py`. The source of truth for joint limits,
gear ratios, servo IDs and tool IDs is `hardware/actuator/cad/params.py`.
If this document and those files disagree, the files win.

## 1. RP2040 pin map

| GPIO | Net | Dir | Function | Notes |
|---|---|---|---|---|
| 0 | BUS_TX | out | UART0 TX → 74AHCT1G125 input A | 1 Mbps 8N1 |
| 1 | BUS_RX | in | UART0 RX ← 74LVC1G125 output Y | The RX buffer is always enabled, so the UART sees its own TX bytes (echo) |
| 2 | BUS_TXEN_N | out | Bus driver enable, **active low** | 10 k pull-up to 3V3: the driver is off during reset |
| 4 | I2C_SDA | i/o | I2C0 SDA (INA219 @ 0x40) | 4.7 k pull-up |
| 5 | I2C_SCL | out | I2C0 SCL | 4.7 k pull-up, run at 400 kHz |
| 6 | SERVO_EN | out | Servo-rail enable (gate of Q4) | 100 k pull-down: the rail is **off** during reset and boot |
| 7 | TOOL_EN | out | Tool-power enable (gate of Q5) | 100 k pull-down: tool power is off by default |
| 8 | ESTOP_SENSE_F | in | E-stop contact B (RC 1 k / 100 nF) | **low = released (closed)**, high = pressed, wire broken, or connector out |
| 11 | LED_R | out | Red LED cathode via 1 k | Active low |
| 12 | LED_G | out | Green LED cathode via 1 k | Active low |
| 13 | LED_B | out | Blue LED cathode via 680 Ω | Active low |
| 26 / ADC0 | TOOL_ID | analog | Tool identity divider (see §5) | 10 k pull-up to 3V3 on the connector side, 1 k series |
| 27 / ADC1 | TOOL_AUX1 | analog / gpio | Tool AUX1 | 330 Ω series, ESD clamp to 3V3 |
| 28 / ADC2 | TOOL_AUX2 | analog / gpio | Tool AUX2 | 330 Ω series, ESD clamp to 3V3 |
| 29 / ADC3 | VIN_SENSE | analog | Input voltage: VIN = V_adc × 11 | 100 k / 10 k divider |
| QSPI | — | — | W25Q128JVSIQ (16 MB) | Standard RP2040 boot flash |
| SWCLK/SWDIO | — | — | J7, JST-SH 3-pin: 1 SWCLK, 2 GND, 3 SWDIO | Raspberry Pi debug-connector pinout |
| RUN | — | — | 10 k pull-up, RESET button to GND | |
| USB | — | — | USB-C device, CC 5.1 k, USBLC6-2SC6 | BHMS-Compact over CDC-ACM |

GPIO3, GPIO9, GPIO10 and GPIO14–GPIO25 are not connected. Configure them
as inputs with pull-downs.

## 2. Power rails and default states

```
12 V in ─ F1 5 A ─ TVS ─ Q1 (reverse-polarity PFET) ─ VIN ─┬─ buck 5 V ─ OR ─ 5V_SYS ─ LDO 3V3 ─ RP2040
                                                           │            USB VBUS ─┘
                                                           └─ Q2 (high side) ─ shunt 10 mΩ ─ V_SERVO ─┬─ J4/J5 servo chains
                                                                                                      └─ Q3 ─ V_TOOL ─ J6 tool
```

* With USB connected and no 12 V, the MCU runs and the servo rail stays
  dead. The firmware must report this condition as "no actuator power"
  (VIN_SENSE < 9 V) rather than as a fault.
* Reset defaults: the servo rail is off, tool power is off, and the bus
  driver is tri-stated. Do not drive SERVO_EN high until the boot
  self-test in §4 passes.

## 3. Servo bus (Feetech STS protocol)

* Half duplex on one wire, idle high (10 k to 5 V), 1 Mbps, 8N1. The
  driver is a 74AHCT1G125 at 5 V (TTL inputs, so the 3.3 V GPIOs drive it
  correctly) with a 100 Ω series resistor. The receiver is a 74LVC1G125
  at 3.3 V; its input tolerates 5 V.
* Transmit sequence:
  1. Drive BUS_TXEN_N low.
  2. Write the frame.
  3. Wait for the UART **TX-complete** event (shift register empty), not
     for FIFO empty.
  4. Drive BUS_TXEN_N high within 5 µs.
  5. Discard the echoed bytes: the count equals the number of bytes sent.
     If the echo differs from what was sent, report a bus collision.
* Set the servo Return_Delay_Time (address 0x07) to 0 or 1 (2 µs units).
  This gives the turnaround at least 2 µs of margin.
* Frame format: `FF FF ID LEN INSTR P1..Pn CHK`, where
  `LEN = n + 2` and `CHK = ~(ID + LEN + INSTR + ΣP) & 0xFF`.
  Instructions: PING 0x01, READ 0x02, WRITE 0x03, REG_WRITE 0x04,
  ACTION 0x05, SYNC_READ 0x82, SYNC_WRITE 0x83. Broadcast ID is 0xFE.
* Control-table addresses used by the firmware. These come from the
  STS-series memory table used by the LeRobot Feetech driver. **Check them
  against the STS3215 manual before relying on them.**

  | Register | Addr | Size | Use |
  |---|---|---|---|
  | ID | 0x05 | 1 | Bus address (EEPROM) |
  | Baud_Rate | 0x06 | 1 | 0 = 1 Mbps |
  | Min_Angle_Limit / Max_Angle_Limit | 0x09 / 0x0B | 2 / 2 | Servo-side soft limits (see §3.1) |
  | Max_Torque_Limit | 0x10 | 2 | EEPROM torque cap (0..1000 = 0..100 %) |
  | P / D / I coefficient | 0x15 / 0x16 / 0x17 | 1 each | Position-loop gains |
  | Operating_Mode | 0x21 | 1 | 0 = position. The knob turner uses multi-turn |
  | Torque_Enable | 0x28 | 1 | |
  | Acceleration | 0x29 | 1 | |
  | Goal_Position | 0x2A | 2 | |
  | Goal_Speed | 0x2E | 2 | |
  | Torque_Limit | 0x30 | 2 | RAM torque cap |
  | Lock | 0x37 | 1 | EEPROM write lock |
  | Present_Position / Speed / Load | 0x38 / 0x3A / 0x3C | 2 each | |
  | Present_Voltage / Temperature | 0x3E / 0x3F | 1 each | 0.1 V / °C |
  | Moving | 0x42 | 1 | |
  | Present_Current | 0x45 | 2 | |

### 3.1 Servo IDs, ratios and limits

| ID | Joint | Chain / port | Ratio (servo:joint) | Joint range (deg) | Servo span (deg) |
|---|---|---|---|---|---|
| 1 | base_yaw | A / J4 | 1 | −150 … +150 | 300 |
| 2 | shoulder_pitch | A / J4 | 3 (17:51 spur, module 1.5) | −20 … +95 | 345 |
| 3 | elbow_pitch | A / J4 | 2 (17:34 spur) | −5 … +125 | 260 |
| 4 | wrist_pitch | B / J5 | 1 | −100 … +100 | 200 |
| 5 | wrist_roll | B / J5 | 1 | −150 … +150 | 300 |
| 6 | gripper | tool / J6 | rack, r = 12 mm | 0 … 30 mm per finger | ≈ 143 |
| 7 | knob turner | tool / J6 | 20:40 spur | multi-turn | multi-turn (±7 turns) |
| 8 | button presser | tool / J6 | cam, 4 mm throw | 0 … 8 mm stroke | 180 |

* Geared joints keep their servo span below 360°, so the servo's
  single-turn absolute encoder still gives an absolute joint angle after
  power-up. No homing is needed.
* `joint = sign × (raw − raw_zero) × 2π / 4096 / ratio`. Calibration
  stores `raw_zero` and `sign` per joint.
* Program Min/Max_Angle_Limit to the joint range × ratio, plus the
  calibration offset. The servo then rejects out-of-range goals itself:
  the second soft limit, behind the firmware's own limit check.
* Max_Torque_Limit (EEPROM and firmware): 100 % for IDs 1, 3, 4, 5; **78 %
  for ID 2** (shoulder, 2.29 N·m at the servo). This number is a design
  requirement, not a recommendation: below about 76 % the shoulder fails the
  2× margin for 250 g + gripper at full reach (1.113 N·m needed), and above
  78 % the PETG shoulder gear is over 0.5 × yield (docs/design.md §4). Write
  780 of 1000 to the register and have the firmware read it back at boot. For ID 6, at
  most 15 % (≈ 20 N per finger). For ID 7, 2.5 % (keeps the spiral
  flexure within ±25°). For ID 8, 20 %.
* The shoulder servo's travel is 345° of the 360° available. Calibrate so
  the 15° spare is split between the two joint limits (about 7° each), and
  never let the servo wrap through the 0/4095 boundary inside the joint
  range.
* Holding at full outstretched reach with the rated load (250 g object plus
  the 159 g gripper) needs 1.11 N·m at the shoulder servo. That is above the STS3215 continuous
  rating (about 1/3 of stall). Monitor Present_Temperature, and do not
  park the arm outstretched.

### 3.2 Speed limit and coupled joint limits

* **Speed limit.** Do not command a joint faster than the STS3215 no-load
  speed divided by the ratio: 4.71 rad/s at the servo (45 rpm, vendor
  figure recorded in `cad/params.py`, *estimate* until measured), so
  4.71 rad/s for yaw, wrist pitch and roll, 2.35 rad/s for the elbow and
  1.57 rad/s for the shoulder. The MJCF encodes the same limits as
  `max_speed_<joint>` and `sim/test_arm.py` checks them.
* **Coupled limits.** Every joint inside its own range is not enough:
  with the folded arm the forearm reaches the base, or the tool reaches the
  turret, base or upper arm. `cad/check_clearance.py` found such poses
  inside every single-joint limit (for example shoulder 30°, elbow 100°,
  wrist +100°: gripper fingers 98 mm³ and the presser tip 212 mm³ inside
  the turret). Angles are in degrees, zero is the "candle" pose, positive
  tilts toward +x. The firmware must reject any goal (and any interpolated
  waypoint) that violates one of:

  | Name | Sum | Limit | What it prevents |
  |---|---|---|---|
  | forearm_pitch | shoulder + elbow | ≤ 175 | forearm swinging into the base |
  | hairpin | elbow + wrist_pitch | ≤ 165 | tool or wrist folding back onto the upper arm |
  | tool_pitch | shoulder + elbow + wrist_pitch | ≤ 183 | tool reaching the turret/base (straight down is 180) |

  The lower side of each sum cannot be reached inside the single-joint
  limits, so no lower limit is needed (they are stored as −180). The
  numbers live in `cad/params.py` (`Arm.coupled_limits`); the MJCF exports
  them as `coupled_<name>_deg` / `coupled_<name>_joints`. Basis: 2000 seeded
  random poses inside all limits plus 150 poses ON each limit surface, per
  tool, and 1386 named/sweep checks show 0 collisions and at least 3 mm
  clearance at allowed poses between links that can approach each other,
  while poses outside collide (docs/design.md §10). The first collision
  on a surface was found at 195/185/190 (first draft of these limits), so
  they were backed off to the values above. The servos' own angle
  registers cannot express these sums, so this check is firmware only and
  has no second layer; apply it before the first torque-enable after
  every boot, and apply it with a few degrees of margin to the *measured*
  pose when the arm is moved by hand.

## 4. E-stop

Wiring (J2, JST-XH 4-pin), with an NC mushroom switch with two NC contacts:

```
J2.1 ESTOP_A ── contact A (NC) ── J2.2 ESTOP_B          (servo-rail gate loop)
J2.3 ESTOP_SENSE ── contact B (NC) ── J2.4 GND          (status to GPIO8)
```

* **Hardware path, no firmware involved:**
  1. Opening contact A, unplugging J2, or breaking the cable removes the
     pull-down from the gate of Q2.
  2. The 2.2 k resistor pulls the gate to the source, and the servo rail
     turns off within tens of µs.
  3. The tool rail sits downstream of Q2, so it turns off too.
* Q2 conducts only while **contact A is closed AND SERVO_EN is high**.
  Firmware can switch the rail off, but it cannot switch it on while the
  E-stop is pressed.
* **Restart inhibit is implemented in firmware**, not in hardware:
  * When GPIO8 goes high, clear SERVO_EN within 1 ms and latch an
    `estop` state.
  * Twisting the mushroom to release it must not re-energise the rail.
    The rail comes back only after an explicit enable command while
    GPIO8 is low.
  * A hardware reset latch is a rev-B item (see docs/design.md, Open
    issues).
* **Measured E-stop property.** Report all three signals, not a single
  boolean:
  1. Contact B state (GPIO8).
  2. Servo-rail voltage (INA219 bus voltage, 4 mV LSB).
  3. Servo-rail current (INA219).

  Consistency rules:
  * GPIO8 high and rail voltage > 2 V for more than 20 ms gives
    `estop_fault_contact_A_or_Q2`. Contact A is welded or Q2 has failed
    short. Stay latched and refuse to enable.
  * GPIO8 low, SERVO_EN high and rail voltage < 9 V gives
    `servo_rail_fault`. Possible causes: loop open (cable), fuse, or
    supply.
* Boot self-test, before the first enable. Run this with E-stop
  released:
  1. Enable for 50 ms and check that the rail rises above 10 V.
  2. Disable and check that it falls below 2 V within 50 ms.
* **The arm falls when the rail drops.** There is no brake on any joint,
  and the gear trains are not self-locking. Firmware must not use the
  E-stop as a normal stop: before cutting SERVO_EN deliberately (shutdown,
  fault), move to the rest pose (home: yaw 0°, shoulder 30°, elbow 90°, wrist 45°, roll 0°; forearm on the
  support) at reduced speed, then disable. Report `estop` as "arm may have
  moved: re-home before use" and never assume the pose after a rail cut.
* After the rail returns, every servo has rebooted. Before torque-enabling
  each servo, set its Goal_Position to its Present_Position.

## 5. Tool flange and tool ID

The tool connector J6 (JST-XH 6) uses the same order as the flange pogo
pins. Pin *i* sits at flange angle 60·*i*°.

| J6 pin | Pogo | Signal | Notes |
|---|---|---|---|
| 1 | 0 | V12_TOOL | Switched by Q3 (TOOL_EN), downstream of the E-stop switch |
| 2 | 1 | GND | |
| 3 | 2 | SERVO_BUS | The same bus as the arm. Tool servos use IDs 6–8 |
| 4 | 3 | AUX1 | ADC1. Knob turner: AS5600 analog OUT. Button presser: FSR divider |
| 5 | 4 | AUX2 | ADC2 or GPIO, reserved |
| 6 | 5 | TOOL_ID | ADC0. The tool has R_ID to GND; the controller has a 10 k pull-up |

ADC ratio = code / 4095 = R_ID / (10 k + R_ID). The ADC reference and the
pull-up are both 3V3, so the reading is ratiometric. Decode by window, and
require 5 consecutive matching samples taken 10 ms apart:

| Code | Tool | R_ID (1 %) | Ratio | Window |
|---|---|---|---|---|
| — | short / fault | 0 | 0.000 | < 0.045 |
| 1 | gripper | 1.0 k | 0.091 | 0.045 – 0.129 |
| 5 | reserved | 2.0 k | 0.167 | 0.129 – 0.207 |
| 2 | knob_turner | 3.3 k | 0.248 | 0.207 – 0.304 |
| 6 | reserved | 5.6 k | 0.359 | 0.304 – 0.430 |
| 3 | button_presser | 10 k | 0.500 | 0.430 – 0.571 |
| 7 | reserved | 18 k | 0.643 | 0.571 – 0.705 |
| 4 | slider_pusher | 33 k | 0.767 | 0.705 – 0.838 |
| 8 | reserved | 100 k | 0.909 | 0.838 – 0.955 |
| — | no tool (open) | ∞ | 1.000 | > 0.955 |

Tool power sequencing:

* The pogo pads are placed so that the pins touch them only in the locked
  bayonet position. During the 30° twist the pins ride on solder mask.
* Mount:
  1. Detect a valid ID, stable for 50 ms.
  2. Enable TOOL_EN.
  3. Wait 50 ms.
  4. PING the tool servo ID, if the tool has one.
* Unmount:
  1. Disable torque on the tool servo.
  2. Clear TOOL_EN.
  3. Check that V_TOOL has decayed below 2 V. There is no ADC on V_TOOL,
     so wait at least 50 ms. The tool LDO input capacitor discharges
     through the AS5600/LDO load.
  4. Only then command the unlocking roll.
* Hot unplug while powered (for example, a tool knocked off): the ID goes
  open-circuit. Clear TOOL_EN immediately and report `tool_lost`.

Bayonet motion, using the wrist roll:

* Lock: insert at relative angle +30°, then roll +30°. The stop pin and
  the ball detent fix the locked angle.
* Unlock: roll −30°, then retract along the tool axis.
* The tool rack (`cad/out/tool_rack.stl`) holds each tool's collar
  against rotation, so the roll joint alone performs the twist.

Tool contact PCB population (from `pcb/tool_contact.py`):

* Gripper: R_ID 1 k and the 3.3 V LDO.
* Knob turner: R_ID 3.3 k, the LDO and the AS5600. AS5600 OUT gives
  0–3.3 V for 0–360°, ratiometric to the tool's own 3.3 V LDO; expect
  about 1 % gain mismatch against the controller's 3V3.
* Button presser: R_ID 10 k, the LDO and a 10 k AUX1 divider. The FSR runs
  from 3V3_T to AUX1.
* Slider pusher: R_ID 33 k only. The tool is passive.

## 6. Current sensing (INA219, I2C 0x40)

* Shunt: 10 mΩ, 4-terminal (Kelvin).
* Configuration register: BRNG = 1 (32 V), PGA = /2 (±80 mV → ±8 A),
  12-bit, continuous shunt and bus. Value 0x299F.
* Calibration:
  * Current_LSB = 0.25 mA.
  * CAL = trunc(0.04096 / (0.00025 × 0.01)) = 16384 (0x4000).
  * Power_LSB = 20 × Current_LSB = 5 mW.
* Suggested limits:
  * Warn at 3.0 A for 1 s.
  * Above 4.5 A for 100 ms, clear SERVO_EN.
  * The 5 A fuse is the backstop.
* Typical per-servo current: idle 0.15 A (estimate). Holding at the worst
  pose with the rated load is about 2.8 A total (estimate from
  `cad/out/torque_budget.json`).

## 7. Status LED (suggested)

| State | LED |
|---|---|
| Booting, rail off | Blue |
| Ready (rail on) | Green |
| E-stop latched | Red, solid |
| Fault | Red, blinking 2 Hz |
| USB host connected, no 12 V | Blue, blinking |

## 8. What the firmware must expose over BHMS-Compact (Task 13b)

* One action per joint: absolute move with speed and acceleration. The
  limits in §3.1 are declared in the device description, and the firmware
  rejects out-of-limit goals before they reach the bus.
* Measured properties:
  * Joint position, speed, load and current, plus servo temperature.
  * VIN.
  * Servo-rail voltage and current.
  * E-stop contact state, plus the derived `estop` state: `released`,
    `pressed` or `fault`.
* A tool sub-device:
  * Identity from TOOL_ID, presence, and power state.
  * Per-tool actions: `grip(width, force)`, `turn(angle, torque_limit)`,
    `press(depth, force_limit)`. The slider pusher has no actuator
    actions.
  * Per-tool measured properties: finger opening, collet angle and
    flexure torque (knob turner), FSR force (button presser).
* Tool change as an explicit procedure with the sequencing in §5. It is
  refused while the `estop` state is not `released`.

## 9. Firmware behaviour that is part of the contract (Task 13b, fix round 1)

### 9.1 Limits are enforced on the measured pose too

The command checks (§3.2) only see what was asked for. A jammed or lagging joint can drive another
into a coupled limit although every commanded waypoint is legal, and an arm can be pushed. **On every
fresh telemetry sample, in every powered state with torque on** (holding, moving, tool operations),
all five joints (each sample at most 200 ms old) are checked:

* the measured pose against the joint and coupled limits with 4 deg of slack: fault 12 during a
  motion, fault 22 (`displaced`) while holding or in a tool operation;
* while moving, every joint against its commanded waypoint, bound 15 deg: fault 18 (`move_limit`
  names the joint).

On a violation the firmware writes goal = the freshly read position for every joint (up to three
attempts; if the freeze write cannot be confirmed the fault becomes 11 `bus_collision`), stops a tool
servo that was moving, ends the operation and **latches** ("recovery-only"). A latched arm keeps
holding and accepts exactly these ways out, none of which needs a power cycle:

* `move_joints` / `home` to a goal inside the limits: never refused because of earlier attempts, and
  bounded as described under "Fault episode" below. A completed recovery move clears the latch; a
  recovery that is cancelled (`hold`, STOP) or fails leaves the arm latched and holding.
* `release_torque` (lease, hazardous): the arm cannot be parked from a jam or a displacement, so torque
  goes off at once and **the arm drops: support it first**. The arm is then PARKED (rail on, torque
  off, `pose_unknown`). An `enable` after it re-energises only if the measured pose is inside the 3 deg
  enable margin; **if the arm still rests outside the margin that `enable` fails with fault 12 and the
  arm stays PARKED with torque off** (it is not re-energised outside the limits, and motion commands
  answer PRECONDITION, reason 6 `parked`). Move the arm inside by hand, torque being off, and `enable`
  again.
* `enable` while latched: if the measured pose is inside the 3 deg margin it re-energises normally
  (READY, the episode ends). If it is outside, the enable fails (fault 12, pose limit) and the arm stays
  in this same latched recovery-only state (rail on, torque on, the fault episode unchanged), which
  accepts the recovery move above. It never cuts the rail.
* `hold` is acknowledged (the arm is already frozen). Everything else is refused (INHIBITED).

**Fault episode: retries cannot ratchet the arm outward, whatever the goals.** The straight path to a
goal inside the (convex) limits never increases the excess *as commanded*, but with a jammed joint the
arm does not follow the command: shoulder stuck at 90 deg, goal (45, 125), and the elbow alone drives
`forearm_pitch` further out. A check of the goal or of its path therefore cannot bound this; the
firmware keeps a memory that no goal resets:

* An episode starts at the first latch and records the measured excess at that moment, `E0` (degrees
  beyond the worst joint or coupled limit; 0 when the latch was a following error inside the limits).
  It ends only when the measured pose is back inside **every** limit (excess 0) with the arm READY, or
  when an `enable` puts torque on inside the enable margin. A recovery move that completes inside its
  2 deg settle tolerance but still measures outside a limit clears the latch and not the episode; a
  new latch before the episode has ended keeps `E0` (it can only be lowered); a push while latched,
  `enable`, a cancelled or failed move do not change it.
* **Cap: 3 deg.** While the measured excess is at or below `E0 + 3`, a recovery goal runs as one
  straight move and the guard trips it as soon as the measured excess passes
  `min(best excess reached in this motion + 1 deg, max(E0 + 3, excess at the start + 0.5))`.
* **Above the cap no commanded motion can make it worse.** A recovery goal is then executed in
  stages: a stage commands only joints whose motion cannot enlarge the violation of any limit
  *whichever joints fail to move or stop on the way* (the test covers the whole box between the
  measured pose and the goal, not just the straight path); the other joints keep their present
  command. When the stage is reached as measured, the rest is planned again from the new measured
  pose (at most 4 stages, then the straight move to the goal). Shoulder stuck at 90, goal (45, 125):
  the stage is "shoulder to 45"; it fails on the jam (fault 18 or a settle timeout) with the elbow
  where it was. Once the jam is removed the very same goal, or `home`, completes: shoulder first,
  then the elbow. Reason 19 (`retry_no_progress`) is the refusal for "above the cap and no joint may
  move toward this goal"; with the present limits a goal inside the limits always has such a joint,
  so the code is defensive and not expected on the wire. Reason 18 (`recovery_worse`, the straight
  path itself increases the excess) is likewise unreachable while the limits are convex.
* **Worst case.** Everything a client can cause in one episode is bounded by
  `E0 + 3 (cap) + 0.5 (hysteresis) + overshoot of ONE trip`, the overshoot being what the joint travels
  until the guard's next sample of it (about 30 ms): at 100 % speed at most shoulder 2.7, elbow 4.0,
  wrist pitch 8.1 deg (90 / 135 / 269 deg/s x 0.03 s), so `E0 + 6.2 / 7.5 / 11.6` deg by arithmetic. In
  the simulator the trips that cross the cap happen early in a move, at low speed: the largest value
  measured over every retry pattern below is `E0 + 3.65` deg, and the tests assert `E0 + 3 + 1.5`.
  An external push is not a client action and is not bounded by this (the arm freezes where it is
  measured after each further 0.5 to 1 deg); the cap still applies to what the client does afterwards.
  Simulator runs (shoulder jammed at 90 deg unless noted; 40 attempts each; round-3 firmware in
  brackets): elbow goal alternating 124/125 at 100 %: 3.15 deg [38.8]; at 50 %: 3.24 [38.7];
  alternating 120/125 at 25 %: 3.02 [34.8]; goal drifting 0.6 deg per attempt: 3.15 [26.5]; shoulder
  pushed to 97 deg and blocked (`E0` = 12.0), `home` and `move(0, 80, 95)` alternating: 15.34, i.e.
  `E0 + 3.34` [17.3 after 12 attempts and rising].

**Overshoot of a single trip.** The guard sees a violation on the next telemetry sample of the joint
(each joint about every 25 ms) and trips when the excess is more than its threshold (4 deg slack when
unlatched; the episode rule above when latched). The arm therefore ends up resting past the threshold
by what the joint travels in one sample period: measured 0.1-1.6 deg in the simulator for the
shoulder/elbow jam at up to 100 % speed; the worst case by arithmetic is joint speed times about
30 ms: shoulder 2.7, elbow 4, wrist pitch 8 deg. The servo-side angle windows (§3.1) add
a second layer: a joint pushed past its window is pulled back toward the window edge by the servo
itself while the goal is frozen at the measured pose (seen in the simulator), so a displaced arm may
drift back inside the joint range on its own; that is intended and not an error. The 1 deg band, 4 deg
slack, 3 deg episode cap, 0.5 deg hysteresis, 15 deg following-error bound and the 200 ms sample age
are simulator-chosen values and are **to be verified on the hardware** with real servo latency and encoder noise. `move_error_deg` reports
the real worst error also for a failed move; a new motion starts from the measured pose when it
differs from the last command by more than 2 deg.

### 9.2 Servo status error bits, temperature

A joint servo reporting overload, over-temperature, voltage, current or sensor error bits while
torque is on freezes the arm the same way (fault 6; property `servo_error` = servo id << 8 | bits).
Property `temperature_warning` is true at 60 C; motion is refused (INHIBITED, reason 16) at 70 C.

### 9.3 Knob-turner mode (verify on hardware)

The knob servo runs as **multi-turn absolute position**: Operating_Mode 0 (position) with Min and Max
angle limit both 0; goal and present position are sign-magnitude counts (bit 15), 4096 per servo turn,
so the output range is +-1000 deg through the 2:1 spur (+-22 756 counts). The goal is the mount position (the
zero, whatever it was) plus the turn and must stay inside +-28 000 counts: +-7 servo turns are +-28 672 counts, and
the 15-bit magnitude would otherwise wrap; `turn` is refused (OUT_OF_RANGE) when zero + target exceeds it,
so with the knob mounted 8000 counts from zero only about +-900 deg remain on one side. The +-7 turn limit itself is
also to be verified on the servo. All writes
to it are absolute and therefore safe to repeat when an ACK is lost (the simulator can apply a write
and drop its reply; no duplicate motion). Mode 3 is **not** used: it is, as far as the reviewer and
the LeRobot Feetech driver convention indicate, a relative step mode in which a repeated or
"goal = present" write would command motion. Source: the STS-series memory table (Operating_Mode,
register 0x21; "position servo mode with both limits 0 = multi-turn") as used by the LeRobot Feetech
driver; **not checked against the Feetech STS3215 manual or on hardware: verify before first use**.

### 9.4 Calibration

Every limit is relative to the joint zero (`joint = sign x (raw - raw_zero) x 360 / 4096 / ratio`).
`raw_zero` and `sign` are stored in flash (two sectors below the boot counter, CRC'd records, newest
valid wins, so a power cut during a save leaves the previous copy). Until a calibration is stored the
property `calibrated` is false and `enable` is refused (PRECONDITION, reason 15). Procedure
(`calibrate` action, lease): put the arm at the rest pose on its support (yaw 0, shoulder 30, elbow 90,
wrist pitch 45, roll 0), rail off, E-stop released; the device powers the rail with torque off, reads
the five raw positions, defines them as the rest pose, refuses a zero that would put a joint range
across the encoder wrap (20 counts spare), switches the rail off and writes flash. Nothing moves.
Enable afterwards. Flash writes mask interrupts, so they only happen with the rail off (the boot
counter store at run time while the rail is on, i.e. a NEW_SESSION hello, is refused: the endpoint then
does not claim PERSISTENT_EPOCH).

### 9.5 Watchdog and controller reset

The hardware watchdog (250 ms) is fed only after a full endpoint poll plus controller tick. A reset
**drops the servo rail** (SERVO_EN pulls down in reset) and the unbraked arm falls; the rest pose is
the support the arm lands on only if it was resting there, otherwise expect the arm to drop wherever
it is. After a watchdog reset the boot defaults apply (rail off, torque off, explicit `enable`), the
property `watchdog_reset` is true and `fault_code` reads 19 until the next successful `enable`, which clears
both (and nothing else does); `pose_unknown` is true. Only a reset armed by the firmware's own watchdog
counts: a BOOTSEL/UF2 reboot is not reported as fault 19. Bus writes are time-bounded (3 ms) so nothing spins with interrupts off; a
flash sector erase takes tens of ms (worst case about 400 ms): the epoch/calibration store brackets every
erase with hooks that stretch the watchdog to 2500 ms and restore 250 ms afterwards (also if the erase
fails): `flash_safe_execute` may itself wait up to 1000 ms for the lockout and the erase itself takes up to
about 400 ms. Erases happen only with the rail off.

### 9.6 Fault and refusal codes added

| Fault | Meaning |
|---|---|
| 12 | a waypoint or the measured pose violated a limit |
| 18 | following error: a joint trails its commanded waypoint by more than 15 deg |
| 19 | watchdog reset |
| 20 | calibration failed or could not be stored |
| 21 | a tool motion stopped short of its goal (knob torque cap or stop) |
| 22 | measured pose outside a limit while holding or in a tool operation (displaced) |

Refusal reasons (ERROR.detail on INHIBITED/PRECONDITION): 15 not calibrated, 16 over-temperature,
17 not disabled (calibrate needs rail off), 18 recovery goal would worsen the limit excess along its path, 19 the same
recovery goal already made the pose worse and nothing has improved since.

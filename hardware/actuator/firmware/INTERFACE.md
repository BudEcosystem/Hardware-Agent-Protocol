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
| 2 | shoulder_pitch | A / J4 | 2 (17:34 spur) | −75 … +95 | 340 |
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
* Recommended Max_Torque_Limit (EEPROM): 100 % for IDs 1–5. For ID 6, at
  most 15 % (≈ 20 N per finger). For ID 7, 2.5 % (keeps the spiral
  flexure within ±25°). For ID 8, 20 %.
* Holding at full outstretched reach with the rated 250 g load needs
  1.26 N·m at the shoulder servo. That is above the STS3215 continuous
  rating (about 1/3 of stall). Monitor Present_Temperature, and do not
  park the arm outstretched.

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

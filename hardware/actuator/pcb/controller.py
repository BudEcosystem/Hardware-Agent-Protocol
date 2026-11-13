"""BHMS Arm controller board: circuit + placement.

Blocks (see docs/design.md "Controller"):
  power in   12 V screw terminal -> 5 A fuse -> bidirectional TVS ->
             P-MOSFET reverse-polarity protection -> 470 uF bulk -> VIN
  servo rail VIN -> high-side P-MOSFET (Q2) whose gate pull-down runs
             through the NC E-stop loop AND the firmware enable FET (Q4):
             opening the E-stop turns Q2 off with no firmware involvement
             -> Kelvin shunt (INA219 on I2C) -> V_SERVO -> 2 servo ports
  tool rail  V_SERVO -> P-MOSFET (Q3, firmware TOOL_EN) -> V_TOOL
  logic      12 V -> TPS54202 buck 5 V -> Schottky OR with USB VBUS ->
             5V_SYS -> AP2112K 3.3 V -> RP2040 + W25Q128 + 12 MHz crystal
  servo bus  RP2040 UART0 -> 74AHCT1G125 (5 V TTL, tri-state, 100 R)
             -> single-wire bus with 10 k pull-up; 74LVC1G125 (3.3 V,
             5 V-tolerant input) returns the bus to UART0 RX
  tool port  V_TOOL, GND, bus, AUX1/AUX2 (ADC1/ADC2, 330 R + ESD),
             TOOL_ID (ADC0 with 10 k pull-up; tool has R_ID to GND)
  misc       USB-C device (CC 5.1 k, USBLC6), SWD (JST-SH, Raspberry Pi
             debug pinout), BOOTSEL/RESET buttons, RGB status LED

Pin map (also in firmware/INTERFACE.md):
  GPIO0 BUS_TX  GPIO1 BUS_RX  GPIO2 BUS_TXEN_N  GPIO4 I2C0 SDA  GPIO5 I2C0 SCL
  GPIO6 SERVO_EN  GPIO7 TOOL_EN  GPIO8 ESTOP_SENSE (low = released/closed)
  GPIO11/12/13 LED R/G/B (active low)  GPIO26 TOOL_ID  GPIO27 AUX1
  GPIO28 AUX2  GPIO29 VIN_SENSE (1/11 divider)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cad"))

from circuit import Board, Part  # noqa: E402
from kicadlib import footprint_pads, load_footprint, load_symbol, symbol_pins  # noqa: E402
from params import DEFAULT  # noqa: E402

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
YAGEO = "Yageo"


def r(ref, value, mpn_code, a, b, pos, rot=0.0, group="", note=""):
    return Part(ref, "Device:R", R0603, value, f"RC0603FR-07{mpn_code}L", YAGEO, {"1": a, "2": b}, pos, rot,
                unit_price_usd=0.002, price_source="estimate (typical LCSC qty-100 price, not a quote)", group=group, note=note)


def c(ref, value, mpn, a, b, pos, rot=0.0, fp=C0603, group="", price=0.01, mfr="Samsung Electro-Mechanics"):
    return Part(ref, "Device:C", fp, value, mpn, mfr, {"1": a, "2": b}, pos, rot, unit_price_usd=price,
                price_source="estimate (typical LCSC qty-100 price, not a quote)", group=group)


C100N = "CL10B104KB8NNNC"  # 100 nF 50 V X7R 0603
C1U = "CL10A105KB8NNNC"  # 1 uF 50 V X5R 0603
C10U_25V = "CL21A106KAYNNNE"  # 10 uF 25 V X5R 0805
C15P = "CL10C150JB8NNNC"  # 15 pF 50 V C0G 0603


def rp2040_pin_numbers() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for pin in symbol_pins(load_symbol("MCU_RaspberryPi:RP2040")):
        out.setdefault(pin.name, []).append(pin.number)
    return out


QFN = "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm"
CAP_PITCH = 1.6  # 0603 courtyard width 1.46 mm + margin
CAP_OFFSET = 8.0  # 0603 decaps sit 8 mm from the QFN centre: leaves a 3 mm fan-out channel between the pin row and the caps


def place_decaps(u1_pos, pins: list[str]) -> list[tuple[tuple[float, float], float]]:
    """Place one 0603 per pin, radially outside the QFN next to its pin,
    pointing outward, spread along each side so courtyards never overlap."""
    pads = {p.number: p for p in footprint_pads(load_footprint(QFN))}
    sides: dict[str, list[tuple[float, int]]] = {}
    for i, pin in enumerate(pins):
        pd = pads[pin]
        side = ("R" if pd.x > 0 else "L") if abs(pd.x) > abs(pd.y) else ("B" if pd.y > 0 else "T")
        along = pd.y if side in "LR" else pd.x
        sides.setdefault(side, []).append((along, i))
    out: list[tuple[tuple[float, float], float]] = [((0.0, 0.0), 0.0)] * len(pins)
    for side, lst in sides.items():
        lst.sort()
        pos = []
        for along, _ in lst:
            pos.append(max(along, pos[-1] + CAP_PITCH) if pos else along)
        # Centre the group on the mean desired position.
        shift = sum(a for a, _ in lst) / len(lst) - sum(pos) / len(pos)
        for (along, i), q in zip(lst, pos):
            q += shift
            if side in "LR":
                sx = 1.0 if side == "R" else -1.0
                out[i] = ((u1_pos[0] + sx * CAP_OFFSET, u1_pos[1] + q), 0.0)
            else:
                sy = 1.0 if side == "B" else -1.0
                out[i] = ((u1_pos[0] + q, u1_pos[1] + sy * CAP_OFFSET), 90.0)
    return out


def build() -> Board:
    p = DEFAULT
    cfg = p.controller
    W, H = cfg.board_u, cfg.board_v
    b = Board("bhms_controller", "BHMS Arm controller (RP2040)", (W, H))
    b.power_nets = {"VIN_RAW": 1.5, "VIN_F": 1.5, "VIN": 1.5, "V_SW": 1.5, "V_SERVO": 1.5, "V_TOOL": 1.0}
    b.pwr_flag_nets = ["GND", "VIN_RAW", "VIN", "V_SERVO", "V_TOOL", "VBUS", "+5V", "5V_SYS"]
    P = b.parts.append

    # ---------------- power input ----------------
    g = "Power input"
    P(Part("J1", "Connector_Generic:Conn_01x02", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
           "12V IN", "1715721", "Phoenix Contact", {"1": "VIN_RAW", "2": "GND"}, (cfg.power_u - 2.54, 6.0), 0.0,
           unit_price_usd=0.80, group=g, note="12 V 5 A supply input; pin 1 +12 V"))
    P(Part("F1", "Device:Fuse", "Fuse:Fuse_Littelfuse-NANO2-451_453", "5A", "0451005.MRL", "Littelfuse",
           {"1": "VIN_RAW", "2": "VIN_F"}, (5.0, 16.0), 90.0, unit_price_usd=0.80, group=g))
    P(Part("D1", "Device:D_TVS", "Diode_SMD:D_SMB", "SMBJ15CA", "SMBJ15CA", "Littelfuse", {"1": "VIN_F", "2": "GND"},
           (11.0, 16.0), 90.0, unit_price_usd=0.20, group=g, note="bidirectional TVS, 15 V standoff"))
    P(Part("Q1", "Transistor_FET:Q_PMOS_GDS", "Package_TO_SOT_SMD:TO-252-2", "AOD4185", "AOD4185", "Alpha & Omega",
           {"G": "Q1_G", "D": "VIN_F", "S": "VIN"}, (9.0, 26.5), 0.0, unit_price_usd=0.40, group=g,
           note="reverse-polarity protection (body diode conducts first, then channel)"))
    P(r("R1", "100k", "100K", "Q1_G", "GND", (16.5, 21.0), 90.0, g))
    P(Part("D2", "Device:D_Zener", "Diode_SMD:D_SOD-123", "BZT52C12", "BZT52C12-7-F", "Diodes Inc",
           {"K": "VIN", "A": "Q1_G"}, (16.5, 25.5), 90.0, unit_price_usd=0.05, group=g, note="Vgs clamp"))
    P(Part("C1", "Device:C_Polarized", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", "470uF 25V", "EEU-FR1E471",
           "Panasonic", {"1": "VIN", "2": "GND"}, (3.5, 37.0), 0.0, unit_price_usd=0.60, group=g))
    P(c("C2", "10uF 25V", C10U_25V, "VIN", "GND", (14.8, 33.0), 0.0, C0805, g, 0.03))
    P(r("R2", "100k", "100K", "VIN", "VIN_SENSE", (14.8, 36.0), 0.0, g, "VIN sense divider top"))
    P(r("R3", "10k", "10K", "VIN_SENSE", "GND", (14.8, 38.5), 0.0, g, "VIN sense divider bottom"))
    P(c("C3", "100nF", C100N, "VIN_SENSE", "GND", (14.8, 41.0), 0.0, group=g, price=0.005))

    # ---------------- servo rail + E-stop ----------------
    g = "Servo rail, E-stop, current sense"
    P(Part("Q2", "Transistor_FET:Q_PMOS_GDS", "Package_TO_SOT_SMD:TO-252-2", "AOD4185", "AOD4185", "Alpha & Omega",
           {"G": "Q2_G", "S": "VIN", "D": "V_SW"}, (25.5, 26.5), 0.0, unit_price_usd=0.40, group=g,
           note="servo rail high-side switch; on only while the E-stop loop is closed AND SERVO_EN is high"))
    P(r("R16", "2.2k", "2K2", "VIN", "Q2_G", (21.0, 21.0), 90.0, g, "turns Q2 off when the loop opens"))
    P(Part("D3", "Device:D_Zener", "Diode_SMD:D_SOD-123", "BZT52C12", "BZT52C12-7-F", "Diodes Inc",
           {"K": "VIN", "A": "Q2_G"}, (32.0, 21.5), 0.0, unit_price_usd=0.05, group=g))
    P(r("R17", "220", "220R", "Q2_G", "ESTOP_A", (34.6, 9.6), 90.0, g, "loop current ~5 mA"))
    P(Part("J2", "Connector_Generic:Conn_01x04", "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical", "E-STOP",
           "B4B-XH-A(LF)(SN)", "JST", {"1": "ESTOP_A", "2": "ESTOP_B", "3": "ESTOP_SENSE", "4": "GND"},
           (cfg.estop_u - 3.75, 3.5), 0.0, unit_price_usd=0.15, group=g,
           note="1-2: NC contact A (power loop); 3-4: NC contact B (sense)"))
    P(Part("Q4", "Transistor_FET:2N7002", "Package_TO_SOT_SMD:SOT-23", "2N7002", "2N7002,215", "Nexperia",
           {"G": "SERVO_EN_G", "S": "GND", "D": "ESTOP_B"}, (42.0, 12.0), 0.0, unit_price_usd=0.05, group=g))
    P(r("R18", "100", "100R", "SERVO_EN", "SERVO_EN_G", (46.0, 12.0), 90.0, g))
    P(r("R19", "100k", "100K", "SERVO_EN_G", "GND", (42.0, 15.5), 0.0, g, "rail off while the MCU is in reset"))
    P(r("R20", "10k", "10K", "+3V3", "ESTOP_SENSE", (46.0, 6.0), 90.0, g))
    P(r("R21", "1k", "1K", "ESTOP_SENSE", "ESTOP_SENSE_F", (48.5, 6.0), 90.0, g))
    P(c("C22", "100nF", C100N, "ESTOP_SENSE_F", "GND", (51.0, 6.0), 90.0, group=g, price=0.005))
    P(Part("R22", "Device:R_Shunt", "Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm", "10m", "WSK2512R0100FEA",
           "Vishay Dale", {"1": "V_SW", "2": "SENSE_P", "3": "SENSE_N", "4": "V_SERVO"}, (25.5, 35.0), 0.0,
           unit_price_usd=1.20, group=g, note="4-terminal Kelvin shunt, 1 W"))
    P(Part("U9", "Sensor_Energy:INA219AxDCN", "Package_TO_SOT_SMD:SOT-23-8", "INA219AIDCNR", "INA219AIDCNR",
           "Texas Instruments",
           {"IN+": "SENSE_P", "IN-": "SENSE_N", "GND": "GND", "VS": "+3V3", "SCL": "I2C_SCL", "SDA": "I2C_SDA",
            "A0": "GND", "A1": "GND"}, (25.5, 40.5), 0.0, unit_price_usd=1.50, group=g, note="I2C address 0x40"))
    P(c("C23", "100nF", C100N, "+3V3", "GND", (29.5, 40.5), 90.0, group=g, price=0.005))
    P(r("R33", "4.7k", "4K7", "+3V3", "I2C_SDA", (21.0, 40.5), 90.0, g))
    P(r("R34", "4.7k", "4K7", "+3V3", "I2C_SCL", (18.5, 40.5), 90.0, g))
    P(c("C24", "10uF 25V", C10U_25V, "V_SERVO", "GND", (31.0, 33.0), 90.0, C0805, g, 0.03))
    P(Part("J4", "Connector_Generic:Conn_01x03", "Connector_Molex:Molex_SPOX_5267-03A_1x03_P2.50mm_Vertical", "SERVO A",
           "22035035", "Molex", {"1": "GND", "2": "V_SERVO", "3": "SERVO_BUS"}, (cfg.servo1_u - 2.5, 53.2), 0.0,
           unit_price_usd=0.30, group=g, note="chain A: yaw, shoulder, elbow (verify lead pinout)"))
    P(Part("J5", "Connector_Generic:Conn_01x03", "Connector_Molex:Molex_SPOX_5267-03A_1x03_P2.50mm_Vertical", "SERVO B",
           "22035035", "Molex", {"1": "GND", "2": "V_SERVO", "3": "SERVO_BUS"}, (cfg.servo2_u - 2.5, 53.2), 0.0,
           unit_price_usd=0.30, group=g, note="chain B: wrist pitch, wrist roll"))

    # ---------------- tool power + tool port ----------------
    g = "Tool port"
    P(Part("Q3", "Transistor_FET:Q_PMOS_GDS", "Package_TO_SOT_SMD:TO-252-2", "AOD4185", "AOD4185", "Alpha & Omega",
           {"G": "Q3_G", "S": "V_SERVO", "D": "V_TOOL"}, (43.5, 45.0), 0.0, unit_price_usd=0.40, group=g,
           note="tool power switch, downstream of the E-stop switch"))
    P(r("R23", "10k", "10K", "V_SERVO", "Q3_G", (35.5, 39.0), 90.0, g))
    P(Part("D4", "Device:D_Zener", "Diode_SMD:D_SOD-123", "BZT52C12", "BZT52C12-7-F", "Diodes Inc",
           {"K": "V_SERVO", "A": "Q3_G"}, (37.5, 34.5), 0.0, unit_price_usd=0.05, group=g))
    P(r("R24", "1k", "1K", "Q3_G", "TOOL_Q_D", (35.5, 42.8), 90.0, g))
    P(Part("Q5", "Transistor_FET:2N7002", "Package_TO_SOT_SMD:SOT-23", "2N7002", "2N7002,215", "Nexperia",
           {"G": "TOOL_EN_G", "S": "GND", "D": "TOOL_Q_D"}, (33.0, 46.0), 0.0, unit_price_usd=0.05, group=g))
    P(r("R25", "100", "100R", "TOOL_EN", "TOOL_EN_G", (41.5, 50.3), 0.0, g))
    P(r("R26", "100k", "100K", "TOOL_EN_G", "GND", (41.5, 52.6), 0.0, g))
    P(Part("J6", "Connector_Generic:Conn_01x06", "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical", "TOOL",
           "B6B-XH-A(LF)(SN)", "JST",
           {"1": "V_TOOL", "2": "GND", "3": "SERVO_BUS", "4": "AUX1_C", "5": "AUX2_C", "6": "TOOL_ID_C"},
           (cfg.tool_u - 6.25, 51.6), 0.0, unit_price_usd=0.20, group=g,
           note="to the flange pogo pins (same order as Flange.pin_names)"))
    P(r("R27", "1k", "1K", "TOOL_ID_C", "TOOL_ID", (60.0, 45.5), 0.0, g))
    P(r("R28", "10k", "10K", "+3V3", "TOOL_ID_C", (60.0, 43.0), 0.0, g, "tool-ID divider top (tool: R_ID to GND)"))
    P(r("R29", "330", "330R", "AUX1_C", "TOOL_AUX1", (55.0, 45.5), 0.0, g))
    P(r("R30", "330", "330R", "AUX2_C", "TOOL_AUX2", (55.0, 43.0), 0.0, g))
    P(Part("U8", "Power_Protection:PRTR5V0U2X", "Package_TO_SOT_SMD:SOT-143", "PRTR5V0U2X", "PRTR5V0U2X,215", "Nexperia",
           {"GND": "GND", "I/O1": "AUX1_C", "I/O2": "AUX2_C", "VCC": "+3V3"}, (50.5, 44.0), 0.0, unit_price_usd=0.15,
           group=g))
    P(Part("U7", "Power_Protection:PRTR5V0U2X", "Package_TO_SOT_SMD:SOT-143", "PRTR5V0U2X", "PRTR5V0U2X,215", "Nexperia",
           {"GND": "GND", "I/O1": "SERVO_BUS", "I/O2": "TOOL_ID_C", "VCC": "5V_SYS"}, (65.0, 44.5), 0.0,
           unit_price_usd=0.15, group=g))

    # ---------------- servo bus ----------------
    g = "Servo bus (half duplex)"
    P(Part("U5", "74xGxx:74AHCT1G125", "Package_TO_SOT_SMD:SOT-353_SC-70-5", "74AHCT1G125GW", "74AHCT1G125GW,125",
           "Nexperia", {"1": "BUS_TXEN_N", "2": "BUS_TX", "3": "GND", "4": "BUS_DRV", "5": "5V_SYS"}, (47.5, 37.5), 0.0,
           unit_price_usd=0.15, group=g, note="TX driver, TTL inputs, enabled by BUS_TXEN_N low"))
    P(r("R14", "100", "100R", "BUS_DRV", "SERVO_BUS", (47.5, 40.0), 0.0, g, "series termination"))
    P(r("R15", "10k", "10K", "5V_SYS", "SERVO_BUS", (51.0, 40.5), 90.0, g, "bus idle-high pull-up"))
    P(r("R35", "10k", "10K", "+3V3", "BUS_TXEN_N", (44.0, 37.5), 90.0, g, "driver disabled during reset"))
    P(c("C26", "100nF", C100N, "5V_SYS", "GND", (47.5, 34.5), 0.0, group=g, price=0.005))
    P(Part("U6", "74xGxx:74LVC1G125", "Package_TO_SOT_SMD:SOT-353_SC-70-5", "74LVC1G125GW", "74LVC1G125GW,125", "Nexperia",
           {"1": "GND", "2": "SERVO_BUS", "3": "GND", "4": "BUS_RX", "5": "+3V3"}, (53.0, 36.5), 0.0, unit_price_usd=0.10,
           group=g, note="RX buffer, 5 V tolerant input"))
    P(c("C27", "100nF", C100N, "+3V3", "GND", (53.0, 33.5), 0.0, group=g, price=0.005))

    # ---------------- 5 V buck + OR ----------------
    g = "5 V buck, USB OR, 3.3 V LDO"
    P(Part("U3", "Regulator_Switching:TPS54202DDC", "Package_TO_SOT_SMD:SOT-23-6", "TPS54202DDCR", "TPS54202DDCR",
           "Texas Instruments", {"GND": "GND", "SW": "BUCK_SW", "VIN": "VIN", "FB": "BUCK_FB", "EN": "BUCK_EN",
                                  "BOOT": "BUCK_BOOT"}, (24.0, 9.0), 0.0, unit_price_usd=0.50, group=g))
    P(c("C5", "100nF", C100N, "BUCK_BOOT", "BUCK_SW", (24.0, 5.0), 0.0, group=g, price=0.005))
    P(c("C6", "10uF 25V", C10U_25V, "VIN", "GND", (20.8, 9.5), 90.0, C0805, g, 0.03))
    P(c("C7", "100nF", C100N, "VIN", "GND", (20.8, 5.0), 90.0, group=g, price=0.005))
    P(r("R4", "100k", "100K", "VIN", "BUCK_EN", (27.5, 5.0), 90.0, g, "UVLO divider: on above ~6.6 V"))
    P(r("R5", "22k", "22K", "BUCK_EN", "GND", (29.5, 5.0), 90.0, g))
    P(Part("L1", "Device:L", "Inductor_SMD:L_Bourns_SRN6045TA", "10uH", "SRN6045TA-100M", "Bourns",
           {"1": "BUCK_SW", "2": "+5V"}, (29.7, 13.2), 0.0, unit_price_usd=0.35, group=g))
    P(r("R6", "100k", "100K", "+5V", "BUCK_FB", (24.0, 13.0), 0.0, g, "Vout = 0.596 (1 + 100k/13.7k) = 4.95 V"))
    P(r("R7", "13.7k", "13K7", "BUCK_FB", "GND", (24.0, 15.5), 0.0, g))
    P(c("C8", "22uF 10V", "GRM21BR61A226ME51L", "+5V", "GND", (35.5, 14.8), 90.0, C0805, g, 0.10, "Murata"))
    P(c("C9", "22uF 10V", "GRM21BR61A226ME51L", "+5V", "GND", (38.0, 14.8), 90.0, C0805, g, 0.10, "Murata"))
    P(Part("D5", "Device:D_Schottky", "Diode_SMD:D_SOD-123", "B5819W", "B5819W-TP", "MCC", {"A": "+5V", "K": "5V_SYS"},
           (36.0, 19.0), 0.0, unit_price_usd=0.05, group=g))
    P(Part("D6", "Device:D_Schottky", "Diode_SMD:D_SOD-123", "B5819W", "B5819W-TP", "MCC", {"A": "VBUS", "K": "5V_SYS"},
           (52.5, 13.0), 0.0, unit_price_usd=0.05, group=g))
    P(Part("U4", "Regulator_Linear:AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5", "AP2112K-3.3", "AP2112K-3.3TRG1",
           "Diodes Inc", {"VIN": "5V_SYS", "GND": "GND", "EN": "5V_SYS", "VOUT": "+3V3"}, (47.5, 27.5), 0.0,
           unit_price_usd=0.20, group=g))
    P(c("C10", "1uF", C1U, "5V_SYS", "GND", (44.0, 27.5), 90.0, group=g))
    P(c("C11", "10uF", C10U_25V, "+3V3", "GND", (51.0, 27.5), 90.0, C0805, g, 0.03))

    # ---------------- MCU ----------------
    g = "RP2040, flash, crystal"
    u1 = (62.0, 30.0)
    rp = rp2040_pin_numbers()
    mcu_nets = {
        "GPIO0": "BUS_TX", "GPIO1": "BUS_RX", "GPIO2": "BUS_TXEN_N", "GPIO3": "", "GPIO4": "I2C_SDA", "GPIO5": "I2C_SCL",
        "GPIO6": "SERVO_EN", "GPIO7": "TOOL_EN", "GPIO8": "ESTOP_SENSE_F", "GPIO9": "", "GPIO10": "",
        "GPIO11": "LED_R", "GPIO12": "LED_G", "GPIO13": "LED_B",
        **{f"GPIO{i}": "" for i in range(14, 26)},
        "GPIO26/ADC0": "TOOL_ID", "GPIO27/ADC1": "TOOL_AUX1", "GPIO28/ADC2": "TOOL_AUX2", "GPIO29/ADC3": "VIN_SENSE",
        "IOVDD": "+3V3", "USB_VDD": "+3V3", "ADC_AVDD": "+3V3", "VREG_VIN": "+3V3", "VREG_VOUT": "+1V1", "DVDD": "+1V1",
        "GND": "GND", "TESTEN": "GND", "XIN": "XIN", "XOUT": "XOUT", "RUN": "RUN", "SWCLK": "SWCLK", "SWDIO": "SWDIO",
        "USB_DP": "USB_DP", "USB_DM": "USB_DM", "QSPI_SCLK": "QSPI_SCLK", "QSPI_SD0": "QSPI_SD0", "QSPI_SD1": "QSPI_SD1",
        "QSPI_SD2": "QSPI_SD2", "QSPI_SD3": "QSPI_SD3", "~{QSPI_SS}": "QSPI_SS",
    }
    P(Part("U1", "MCU_RaspberryPi:RP2040", "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm", "RP2040", "RP2040",
           "Raspberry Pi", mcu_nets, u1, 0.0, unit_price_usd=1.00, group=g))
    # Decoupling: one 100 nF per IOVDD pin, at the pin; 1 uF on VREG_VIN and VREG_VOUT.
    decaps = [(n, "+3V3") for n in rp["IOVDD"]] + [(rp["USB_VDD"][0], "+3V3"), (rp["ADC_AVDD"][0], "+3V3")] + [
        (n, "+1V1") for n in rp["DVDD"]]
    decaps += [(rp["VREG_VIN"][0], "+3V3"), (rp["VREG_VOUT"][0], "+1V1")]
    places = place_decaps(u1, [pin for pin, _ in decaps])
    for i, ((pin, net), (pos, rot)) in enumerate(zip(decaps, places)):
        if i < len(decaps) - 2:
            P(c(f"C{40 + i}", "100nF", C100N, net, "GND", pos, rot, group=g, price=0.005))
        else:
            P(c(f"C{50 + i - (len(decaps) - 2)}", "1uF", C1U, net, "GND", pos, rot, group=g))
    P(Part("U2", "Memory_Flash:W25Q128JVS", "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm", "W25Q128JVSIQ", "W25Q128JVSIQ",
           "Winbond", {"~{CS}": "QSPI_SS", "DO/IO_{1}": "QSPI_SD1", "~{WP}/IO_{2}": "QSPI_SD2", "GND": "GND",
                       "DI/IO_{0}": "QSPI_SD0", "CLK": "QSPI_SCLK", "~{HOLD}/~{RESET}/IO_{3}": "QSPI_SD3", "VCC": "+3V3"},
           (73.0, 22.0), 90.0, unit_price_usd=1.20, group=g, note="16 MB QSPI flash"))
    P(c("C12", "100nF", C100N, "+3V3", "GND", (77.5, 16.5), 90.0, group=g, price=0.005))
    P(r("R10", "10k", "10K", "+3V3", "QSPI_SS", (69.0, 16.0), 90.0, g))
    P(r("R11", "1k", "1K", "QSPI_SS", "BOOTSEL", (69.0, 37.5), 0.0, g))
    P(Part("SW1", "Switch:SW_Push", "Button_Switch_SMD:SW_SPST_PTS810", "BOOTSEL", "PTS810 SJM 250 SMTR LFS", "C&K",
           {"1": "BOOTSEL", "2": "GND"}, (72.5, 41.5), 0.0, unit_price_usd=0.25, group=g))
    P(Part("SW2", "Switch:SW_Push", "Button_Switch_SMD:SW_SPST_PTS810", "RESET", "PTS810 SJM 250 SMTR LFS", "C&K",
           {"1": "RUN", "2": "GND"}, (72.5, 46.5), 0.0, unit_price_usd=0.25, group=g))
    P(r("R9", "10k", "10K", "+3V3", "RUN", (67.5, 46.5), 90.0, g))
    P(Part("Y1", "Device:Crystal_GND24", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", "12MHz", "ABM8-272-T3", "Abracon",
           {"1": "XIN", "3": "XTAL_O", "2": "GND", "4": "GND"}, (53.0, 21.5), 0.0, unit_price_usd=0.40, group=g))
    P(r("R8", "1k", "1K", "XOUT", "XTAL_O", (56.5, 23.4), 90.0, g, "RP2040 HW design guide"))
    P(c("C19", "15pF", C15P, "XIN", "GND", (49.2, 21.5), 90.0, group=g, price=0.005))
    P(c("C20", "15pF", C15P, "XTAL_O", "GND", (53.0, 25.0), 0.0, group=g, price=0.005))
    P(Part("J7", "Connector_Generic_MountingPin:Conn_01x03_MountingPin",
           "Connector_JST:JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal", "SWD", "SM03B-SRSS-TB(LF)(SN)", "JST",
           {"1": "SWCLK", "2": "GND", "3": "SWDIO", "MP": "GND"}, (76.2, 31.0), 90.0, unit_price_usd=0.40, group=g,
           note="Raspberry Pi debug connector pinout"))

    # ---------------- USB ----------------
    g = "USB-C device"
    P(Part("J3", "Connector:USB_C_Receptacle_USB2.0_16P", "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
           "USB-C", "USB4105-GF-A", "GCT",
           {"GND": "GND", "VBUS": "VBUS", "CC1": "USB_CC1", "CC2": "USB_CC2", "D+": "USB_DP_C", "D-": "USB_DM_C",
            "SBU1": "", "SBU2": "", "SHIELD": "GND"}, (cfg.usb_u, 3.1), 180.0, unit_price_usd=0.80, group=g))
    P(r("R31", "5.1k", "5K1", "USB_CC1", "GND", (56.0, 9.5), 90.0, g))
    P(r("R32", "5.1k", "5K1", "USB_CC2", "GND", (68.0, 9.5), 90.0, g))
    P(Part("U10", "Power_Protection:USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", "USBLC6-2SC6", "USBLC6-2SC6",
           "STMicroelectronics", {"I/O1": "USB_DP_C", "GND": "GND", "I/O2": "USB_DM_C", "VBUS": "VBUS"}, (62.0, 12.0),
           0.0, unit_price_usd=0.25, group=g))
    P(r("R12", "27", "27R", "USB_DP_C", "USB_DP", (60.0, 16.5), 90.0, g))
    P(r("R13", "27", "27R", "USB_DM_C", "USB_DM", (64.0, 16.5), 90.0, g))
    P(c("C25", "4.7uF", "CL10A475KO8NNNC", "VBUS", "GND", (56.0, 13.0), 90.0, group=g, price=0.02))

    # ---------------- LED ----------------
    g = "Status LED"
    led_u, led_v = 44.0, 20.0  # under the pod-lid light pipe (cad/parts/base.py)
    for k, (ref, col, mpn, rref, rval, rcode, net) in enumerate([
            ("D7", "red", "APTD1608LSURCK", "R36", "1k", "1K", "LED_R"),
            ("D8", "green", "APTD1608LZGCK", "R37", "1k", "1K", "LED_G"),
            ("D9", "blue", "APTD1608LVBC/D", "R38", "680", "680R", "LED_B")]):
        y = led_v - 1.5 + 1.5 * k
        P(Part(ref, "Device:LED", "LED_SMD:LED_0603_1608Metric", col, mpn, "Kingbright",
               {"A": "5V_SYS", "K": f"{net}_K"}, (led_u, y), 0.0, unit_price_usd=0.08, group=g,
               note="anode on 5V_SYS, sunk by the GPIO through R (off when the pin is high)"))
        P(r(rref, rval, rcode, f"{net}_K", net, (led_u - 3.5, y), 0.0, g))

    # ---------------- mechanical ----------------
    for k, (x, y) in enumerate([(3.5, 3.5), (W - 3.5, 3.5), (3.5, H - 3.5), (W - 3.5, H - 3.5)]):
        P(Part(f"H{k + 1}", "Mechanical:MountingHole", "MountingHole:MountingHole_3.2mm_M3", "M3", "", "", {}, (x, y),
               group="Mechanical"))
    return b

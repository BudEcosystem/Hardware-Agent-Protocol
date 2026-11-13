"""Tool contact PCB: one universal 28 mm round board bonded into every
tool plug (see cad/parts/tool_interface.py).

Bottom (B.Cu, faces the arm): six ENIG pads on r = 12 mm at the pogo pin
angles (pin i at 60*i deg, tool frame), no other copper features proud of
the surface.  Top (F.Cu, inside the plug bore, r < 10.5 mm): tool-ID
resistor, 30 V-rated 3.3 V LDO for tool electronics, AS5600 (knob turner
only), AUX1 divider resistor (button presser FSR), and wire pads.

Population per tool is listed in ``VARIANTS`` and in bom/bom.csv.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cad"))

from circuit import Board, Part  # noqa: E402
from params import DEFAULT  # noqa: E402
from sexpr import Q  # noqa: E402

CENTER = (15.0, 15.0)


def _fp_pad(name: str, layer: str, d: float, shape: str = "circle") -> list:
    side = "B" if layer.startswith("B") else "F"
    return ["footprint", Q(f"bhms:{name}"), ["layer", Q("F.Cu")],
            ["property", Q("Reference"), Q("REF**"), ["at", 0, -2.0, 0], ["layer", Q("F.Fab")], ["hide", "yes"],
             ["effects", ["font", ["size", 0.6, 0.6], ["thickness", 0.1]]]],
            ["property", Q("Value"), Q(name), ["at", 0, 2.0, 0], ["layer", Q("F.Fab")], ["hide", "yes"],
             ["effects", ["font", ["size", 0.6, 0.6], ["thickness", 0.1]]]],
            ["attr", "smd"],
            ["fp_circle", ["center", 0, 0], ["end", d / 2 + 0.25, 0], ["stroke", ["width", 0.05], ["type", "solid"]],
             ["fill", "none"], ["layer", Q(f"{side}.CrtYd")]],
            ["pad", Q("1"), "smd", shape, ["at", 0, 0], ["size", d, d], ["layers", Q(f"{side}.Cu"), Q(f"{side}.Mask")]]]


def _as5600_symbol() -> list:
    """AS5600 (ams OSRAM) SOIC-8: 1 VDD5V, 2 VDD3V3, 3 OUT, 4 GND, 5 PGO,
    6 SDA, 7 SCL, 8 DIR (datasheet pinout)."""
    eff = ["effects", ["font", ["size", 1.27, 1.27]]]
    pins = [("1", "VDD5V", "power_in", -10.16, 5.08, 0), ("2", "VDD3V3", "power_in", -10.16, 2.54, 0),
            ("8", "DIR", "input", -10.16, -2.54, 0), ("4", "GND", "power_in", 0.0, -10.16, 90),
            ("3", "OUT", "output", 10.16, 5.08, 180), ("5", "PGO", "input", 10.16, 2.54, 180),
            ("6", "SDA", "bidirectional", 10.16, -2.54, 180), ("7", "SCL", "input", 10.16, -5.08, 180)]
    unit = ["symbol", Q("AS5600_1_1")]
    for num, name, et, x, y, a in pins:
        unit.append(["pin", et, "line", ["at", x, y, a], ["length", 2.54], ["name", Q(name), eff], ["number", Q(num), eff]])
    return ["symbol", Q("bhms:AS5600"), ["pin_names", ["offset", 1.016]], ["exclude_from_sim", "no"], ["in_bom", "yes"],
            ["on_board", "yes"],
            ["property", Q("Reference"), Q("U"), ["at", 0, 8.89, 0], eff],
            ["property", Q("Value"), Q("AS5600"), ["at", 0, -12.7, 0], eff],
            ["property", Q("Footprint"), Q("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"), ["at", 0, 0, 0],
             ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]]],
            ["property", Q("Datasheet"), Q(""), ["at", 0, 0, 0], ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]]],
            ["symbol", Q("AS5600_0_1"), ["rectangle", ["start", -7.62, 7.62], ["end", 7.62, -7.62],
                                         ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]]],
            unit]


VARIANTS = {
    # ref -> {tool: value or None (DNP)}
    "R1": {"gripper": "1k", "knob_turner": "3.3k", "button_presser": "10k", "slider_pusher": "33k"},
    "U1": {"gripper": "TPS70933DBVR", "knob_turner": "TPS70933DBVR", "button_presser": "TPS70933DBVR", "slider_pusher": None},
    "C1": {"gripper": "1uF", "knob_turner": "1uF", "button_presser": "1uF", "slider_pusher": None},
    "C2": {"gripper": "1uF", "knob_turner": "1uF", "button_presser": "1uF", "slider_pusher": None},
    "U2": {"gripper": None, "knob_turner": "AS5600-ASOM", "button_presser": None, "slider_pusher": None},
    "C3": {"gripper": None, "knob_turner": "100nF", "button_presser": None, "slider_pusher": None},
    "R2": {"gripper": None, "knob_turner": None, "button_presser": "10k", "slider_pusher": None},
}


def tool_id_value(tool: str) -> str:
    return VARIANTS["R1"][tool]


def build() -> Board:
    p = DEFAULT
    f = p.flange
    cx, cy = CENTER
    rr = f.contact_pcb_d / 2
    # Keying flat (matches tool_interface.contact_pcb_flat): a chord at
    # distance d whose normal points at tool angle phi.
    d, phi = f.contact_pcb_flat_dist, math.radians(f.contact_pcb_flat_angle_deg)
    half = math.acos(d / rr)
    a1, a2 = phi - half, phi + half  # chord end angles (tool frame, CCW)
    amid = a2 + (2 * math.pi - 2 * half) / 2

    def bxy(a: float, r: float = rr) -> tuple[float, float]:
        return cx + r * math.cos(a), cy - r * math.sin(a)

    b = Board("bhms_tool_contact", "BHMS tool contact PCB (universal)", (30.0, 30.0))
    b.origin = (100.0, 100.0)
    b.outline = [("line", bxy(a1), bxy(a2)), ("arc", bxy(a2), bxy(amid), bxy(a1))]
    b.zone_nets = []  # too small for useful pours; GND is routed as tracks
    b.power_nets = {"V12_TOOL": 0.5}
    b.pwr_flag_nets = ["GND", "V12_TOOL"]
    P = b.parts.append

    def tool_xy(x: float, y: float) -> tuple[float, float]:
        """Tool frame (y up, viewed from the tool side) -> board coordinates."""
        return cx + x, cy - y

    nets = {"V12_TOOL": "V12_TOOL", "GND": "GND", "BUS": "SERVO_BUS", "AUX1": "AUX1", "AUX2": "AUX2", "TOOL_ID": "TOOL_ID"}
    for i, name in enumerate(f.pin_names):
        a = math.radians(360.0 * i / f.pogo_count)
        x, y = f.pogo_circle_r * math.cos(a), f.pogo_circle_r * math.sin(a)
        P(Part(f"TP{i + 1}", "Connector:TestPoint", "bhms:PogoPad_D2.4", name, "", "", {"1": nets[name]}, tool_xy(x, y),
               group="Contact pads (bottom)", custom_footprint=_fp_pad("PogoPad_D2.4", "B.Cu", 2.4),
               note=f"pogo pin {i} contact, ENIG"))
    g = "Tool electronics (top)"
    P(Part("R1", "Device:R", "Resistor_SMD:R_0603_1608Metric", "R_ID", "RC0603FR-07xxxL (per tool)", "Yageo",
           {"1": "TOOL_ID", "2": "GND"}, tool_xy(-6.5, -5.0), 0.0, unit_price_usd=0.002, group=g,
           note="tool identity, see params.Tools.tool_ids"))
    P(Part("U1", "Regulator_Linear:AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5", "TPS70933DBVR", "TPS70933DBVR",
           "Texas Instruments", {"VIN": "V12_TOOL", "GND": "GND", "EN": "V12_TOOL", "VOUT": "3V3_T"}, tool_xy(0.0, 6.6),
           0.0, unit_price_usd=0.35, group=g,
           note="30 V LDO; AP2112K symbol used for its identical SOT-23-5 pinout (IN, GND, EN, NC, OUT)"))
    P(Part("C1", "Device:C", "Capacitor_SMD:C_0603_1608Metric", "1uF 50V", "GRM188R61H105KAAL", "Murata",
           {"1": "V12_TOOL", "2": "GND"}, tool_xy(-4.6, 6.6), 90.0, unit_price_usd=0.03, group=g))
    P(Part("C2", "Device:C", "Capacitor_SMD:C_0603_1608Metric", "1uF", "GRM188R61H105KAAL", "Murata",
           {"1": "3V3_T", "2": "GND"}, tool_xy(4.6, 6.6), 90.0, unit_price_usd=0.03, group=g))
    P(Part("U2", "bhms:AS5600", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "AS5600-ASOM", "AS5600-ASOM", "ams OSRAM",
           {"1": "3V3_T", "2": "3V3_T", "3": "AUX1", "4": "GND", "5": "", "6": "", "7": "", "8": "GND"}, tool_xy(0.0, 0.0),
           90.0, unit_price_usd=2.00, group=g, custom_symbol=_as5600_symbol(),
           note="centred on the tool axis under the knob-shaft magnet; analog OUT -> AUX1"))
    P(Part("C3", "Device:C", "Capacitor_SMD:C_0603_1608Metric", "100nF", "CL10B104KB8NNNC", "Samsung Electro-Mechanics",
           {"1": "3V3_T", "2": "GND"}, tool_xy(4.8, -1.5), 90.0, unit_price_usd=0.005, group=g))
    P(Part("R2", "Device:R", "Resistor_SMD:R_0603_1608Metric", "10k", "RC0603FR-0710KL", "Yageo",
           {"1": "AUX1", "2": "GND"}, tool_xy(6.5, -5.0), 0.0, unit_price_usd=0.002, group=g,
           note="FSR divider (FSR from 3V3_T to AUX1)"))
    wire = [("W1", "V12_TOOL", (-7.6, 1.6)), ("W2", "GND", (-7.6, -1.6)), ("W3", "SERVO_BUS", (-2.6, -8.6)),
            ("W4", "3V3_T", (7.6, 1.6)), ("W5", "AUX1", (2.6, -8.6)), ("W6", "AUX2", (0.0, -7.6))]
    for ref, net, (x, y) in wire:
        P(Part(ref, "Connector_Generic:Conn_01x01", "bhms:WirePad_1.6", net, "", "", {"1": net}, tool_xy(x, y), group=g,
               custom_footprint=_fp_pad("WirePad_1.6", "F.Cu", 1.6, "circle"), note="solder pad for the tool harness"))
    for ref, var in VARIANTS.items():
        part = b.part(ref)
        part.note = (part.note + "; " if part.note else "") + "population: " + ", ".join(
            f"{t}={v or 'DNP'}" for t, v in var.items())
    return b

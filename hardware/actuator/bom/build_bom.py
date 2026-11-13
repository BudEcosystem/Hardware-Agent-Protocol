#!/usr/bin/env python3
"""Build bom/bom.csv for the BHMS Arm.

Sources:
  * purchased mechanical/electrical items: ``HARDWARE`` below
  * controller PCB parts: pcb/controller/netlist.json (generated with the board)
  * tool contact PCB parts and per-tool population: pcb/tool_contact/netlist.json
    and pcb/tool_contact.VARIANTS
  * printed parts (filament mass from the CAD mass model): cad/out/parts.json

Prices are ESTIMATES (no live distributor quote was possible offline):
typical 2026 single-unit or small-batch distributor pricing in USD; every
row says so in ``price_source``.  Quantities are for ONE arm with all four
tools.  Section totals and a grand total are appended as rows.

    python bom/build_bom.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "pcb"))
sys.path.insert(0, str(ROOT / "cad"))

EST = "estimate (typical 2026 distributor price, not a quote)"

# (section, item, manufacturer, mpn, qty, unit_usd, notes)
HARDWARE = [
    # ---- arm: actuators and bearings ----
    ("Arm", "Serial bus servo 12 V, 30 kg.cm, 4096-count magnetic encoder", "Feetech", "STS3215 (12 V, C018 1:345)", 5, 18.00,
     "IDs 1-5; variant code to confirm with supplier at order time"),
    ("Arm", "Deep-groove ball bearing 8x22x7", "generic (e.g. SKF)", "608-2RS", 4, 0.50, "shoulder and elbow shafts"),
    ("Arm", "Deep-groove ball bearing 4x13x5", "generic (e.g. SKF)", "624-2RS", 3, 0.60, "2 pinion supports, wrist idler"),
    ("Arm", "Deep-groove ball bearing 30x42x7", "generic (e.g. SKF)", "6806-2RS", 1, 3.00, "yaw turntable"),
    ("Arm", "Hex bolt M8x70, partial thread, 8.8, zinc", "generic", "ISO 4014 M8x70", 2, 0.40, "shoulder/elbow shafts"),
    ("Arm", "Nyloc nut M8", "generic", "ISO 10511 M8", 2, 0.08, ""),
    ("Arm", "Washer M8 (16 mm OD)", "generic", "ISO 7089 M8", 4, 0.03, "bear on the 608 inner races only"),
    ("Arm", "Socket head cap screw M4x12", "generic", "ISO 4762 M4x12", 6, 0.06, "2 pinion supports, 4 shell-to-plate"),
    ("Arm", "Socket head cap screw M4x16 + nyloc nut", "generic", "ISO 4762 M4x16 / ISO 10511 M4", 1, 0.12, "wrist idler"),
    ("Arm", "Washer M4 (9 mm OD)", "generic", "ISO 7089 M4", 4, 0.02, "inner-race spacers"),
    ("Arm", "Heat-set insert M4 x 6", "generic (e.g. Ruthex)", "M4x8.1 RX-M4x8.1", 6, 0.10, "pinion stubs, shell bosses"),
    ("Arm", "Heat-set insert M3 x 5.7", "generic (e.g. Ruthex)", "RX-M3x5.7", 32, 0.06, "servo lids (5), pod lid, PCB"),
    ("Arm", "Socket head cap screw M3x8", "generic", "ISO 4762 M3x8", 32, 0.04, ""),
    ("Arm", "Pan head screw M2x8 (servo horn)", "generic", "ISO 7045 M2x8", 20, 0.03, "turret, pinions, wrist, flange"),
    ("Arm", "Ball spring plunger M5, 3 mm ball, stainless", "generic", "select at order (M5 x 12 class)", 1, 1.50,
     "bayonet detent; MPN not fixed"),
    ("Arm", "Heat-set insert M5", "generic", "RX-M5x9.5", 1, 0.15, "detent plunger"),
    ("Arm", "Dowel pin 3 x 6 mm, hardened", "generic", "ISO 8734 3x6", 1, 0.10, "bayonet stop pin"),
    ("Arm", "Spring-loaded contact (pogo pin), through-hole, 2.0 mm barrel, ~8 mm", "Mill-Max (0906 class)",
     "select at order (Mill-Max 0906 series)", 6, 1.20, "flange contacts; exact MPN not fixed"),
    ("Arm", "Cable 6-core 26 AWG, PUR, flexible", "generic (e.g. Igus chainflex)", "select at order", 1.5, 3.00,
     "metres; tool harness through the arm"),
    ("Arm", "Servo extension lead 3-pin 5264, 400 mm", "Feetech", "accessory", 2, 1.50, "chain A/B up the service loop"),
    ("Arm", "Cable tie 2.5 x 100 mm", "generic", "", 10, 0.02, ""),
    # ---- base and safety ----
    ("Base & safety", "Hex bolt M8x60 + hex nut (clamp screw)", "generic", "ISO 4017 M8x60 / ISO 4032 M8", 1, 0.45, ""),
    ("Base & safety", "Adhesive rubber foot 10 mm", "3M", "SJ5302", 6, 0.15, ""),
    ("Base & safety", "Emergency stop push button, 40 mm mushroom, turn release, 1 NC", "Schneider Electric", "XB4BS8445", 1,
     25.00, "contact block A -> E-STOP pins 1-2 (power loop)"),
    ("Base & safety", "Add-on contact block 1 NC", "Schneider Electric", "ZBE102", 1, 6.00, "contact B -> pins 3-4 (sense)"),
    ("Base & safety", "Single-position control station enclosure", "Schneider Electric", "XALD01", 1, 12.00, ""),
    ("Base & safety", "JST XH 4-pin housing + crimp contacts", "JST", "XHP-4 / SXH-001T-P0.6", 1, 0.20, "E-stop cable"),
    ("Base & safety", "Power supply 12 V 6 A, enclosed, screw terminals", "Mean Well", "LRS-75-12", 1, 20.00,
     "IEC inlet cord not included"),
    ("Base & safety", "Cable 2-core 18 AWG + ferrules", "generic", "", 1.0, 1.50, "metres; PSU to J1"),
    # ---- tools ----
    ("Gripper", "Serial bus servo 12 V (STS3215)", "Feetech", "STS3215 (12 V, C018 1:345)", 1, 18.00, "bus ID 6"),
    ("Gripper", "Heat-set insert M3 + M3x8 screw", "generic", "RX-M3x5.7 / ISO 4762 M3x8", 6, 0.10, "lid + finger screws"),
    ("Gripper", "Pan head screw M2x8 (horn)", "generic", "ISO 7045 M2x8", 4, 0.03, ""),
    ("Knob turner", "Serial bus servo 12 V (STS3215)", "Feetech", "STS3215 (12 V, C018 1:345)", 1, 18.00, "bus ID 7"),
    ("Knob turner", "Deep-groove ball bearing 8x22x7", "generic", "608-2RS", 2, 0.50, ""),
    ("Knob turner", "Linear shaft 8 mm h6, cut to length", "Misumi", "PSFJ8-100", 1, 4.00, "cut to the length in cad/out/assembly.json"),
    ("Knob turner", "Diametric magnet 6 x 2.5 mm N35", "generic (AS5600 kit magnet)", "select at order", 1, 0.50, ""),
    ("Knob turner", "Set screw M3x6 + M3 nut", "generic", "ISO 4027 M3x6 / ISO 4032 M3", 2, 0.06, ""),
    ("Knob turner", "Heat-set insert M3 + M3x8 screw", "generic", "RX-M3x5.7 / ISO 4762 M3x8", 7, 0.10, "lid + collet"),
    ("Knob turner", "Pan head screw M2x8 (horn)", "generic", "ISO 7045 M2x8", 4, 0.03, ""),
    ("Button presser", "Serial bus servo 12 V (STS3215)", "Feetech", "STS3215 (12 V, C018 1:345)", 1, 18.00, "bus ID 8"),
    ("Button presser", "Force-sensing resistor, 7.6 mm round", "Interlink Electronics", "FSR 400 (order code to confirm)", 1,
     7.00, "tip sensor, read on AUX1"),
    ("Button presser", "Compression spring OD 12, wire 0.8, free length 18 mm", "generic", "select at order", 1, 0.30, ""),
    ("Button presser", "Heat-set insert M3 + M3x8 screw", "generic", "RX-M3x5.7 / ISO 4762 M3x8", 4, 0.10, "servo lid"),
    ("Button presser", "Pan head screw M2x8 (horn)", "generic", "ISO 7045 M2x8", 4, 0.03, ""),
]

FILAMENT_USD_PER_KG = {"PLA": 20.0, "PETG": 22.0, "TPU": 32.0}
TOOL_SECTION = {"gripper": "Gripper", "knob_turner": "Knob turner", "button_presser": "Button presser",
                "slider_pusher": "Slider pusher"}
PRINTED_SECTION = {
    "gripper_": "Gripper", "knob_": "Knob turner", "presser_": "Button presser", "pusher_": "Slider pusher",
    "tool_rack": "Fixtures", "tolerance_coupon": "Fixtures", "clamp_": "Base & safety", "base_": "Base & safety",
    "pod_lid": "Base & safety",
}


def printed_rows(parts: dict) -> list[dict]:
    rows = []
    for name, info in sorted(parts.items()):
        if not info.get("printed", True):
            continue
        section = next((s for k, s in PRINTED_SECTION.items() if name.startswith(k)), "Arm")
        grams = info["mass_model_g"] * info["qty"] * 1.10  # +10 % supports/purge (estimate)
        usd_kg = FILAMENT_USD_PER_KG[info["material"]]
        rows.append({"section": section, "item": f"Printed part {name} ({info['material']})", "manufacturer": "self-printed",
                     "mpn": f"cad/out/{name}.stl", "qty": info["qty"], "unit_usd": round(grams / info["qty"] * usd_kg / 1000, 3),
                     "price_source": "filament estimate: CAD mass model x 1.1, " + f"{usd_kg:.0f} USD/kg",
                     "notes": f"{info['mass_model_g']:.1f} g each, ~{info['print_time_h_est']:.1f} h each (estimate); "
                              f"orientation: {info['orientation']}"})
    return rows


def pcb_rows(netlist: dict, section: str, board_label: str, qty_boards: int = 1) -> list[dict]:
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for p in netlist["parts"]:
        if not p["mpn"] or p["dnp"]:
            continue
        key = (p["mpn"], p["manufacturer"], p["value"], p["footprint"].split(":")[-1])
        g = groups.setdefault(key, {"refs": [], "price": p["unit_price_usd"], "src": p["price_source"]})
        g["refs"].append(p["ref"])
    rows = []
    for (mpn, mfr, value, fp), g in groups.items():
        rows.append({"section": section, "item": f"{board_label}: {value} ({fp})", "manufacturer": mfr, "mpn": mpn,
                     "qty": len(g["refs"]) * qty_boards, "unit_usd": g["price"],
                     "price_source": EST if g["src"] == "estimate" else g["src"],
                     "notes": " ".join(sorted(g["refs"], key=lambda r: (r.rstrip("0123456789"), int(r.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") or 0))))})
    return rows


def tool_pcb_rows(netlist: dict) -> list[dict]:
    from tool_contact import VARIANTS

    parts = {p["ref"]: p for p in netlist["parts"]}
    rows = []
    for tool, section in TOOL_SECTION.items():
        rows.append({"section": section, "item": "Tool contact PCB, 28 mm round, 2-layer 1.6 mm ENIG", "manufacturer": "JLCPCB",
                     "mpn": "pcb/tool_contact/fab (Gerbers)", "qty": 1, "unit_usd": 1.00,
                     "price_source": EST + " (5-board panel price / 5)", "notes": "ENIG required for the pogo pads"})
        for ref, p in parts.items():
            if not p["mpn"]:
                continue
            if ref in VARIANTS:
                val = VARIANTS[ref][tool]
                if val is None:
                    continue
                mpn = p["mpn"]
                if ref == "R1":
                    code = {"1k": "1K", "3.3k": "3K3", "10k": "10K", "33k": "33K"}[val]
                    mpn = f"RC0603FR-07{code}L"
                rows.append({"section": section, "item": f"Tool PCB {ref}: {val}", "manufacturer": p["manufacturer"], "mpn": mpn,
                             "qty": 1, "unit_usd": p["unit_price_usd"], "price_source": EST, "notes": p["note"]})
    return rows


def main() -> int:
    parts = json.loads((ROOT / "cad" / "out" / "parts.json").read_text())
    ctrl = json.loads((ROOT / "pcb" / "controller" / "netlist.json").read_text())
    tool = json.loads((ROOT / "pcb" / "tool_contact" / "netlist.json").read_text())
    rows = []
    for section, item, mfr, mpn, qty, unit, notes in HARDWARE:
        rows.append({"section": section, "item": item, "manufacturer": mfr, "mpn": mpn, "qty": qty, "unit_usd": unit,
                     "price_source": EST, "notes": notes})
    rows.append({"section": "Controller", "item": "Controller PCB 80 x 56 mm, 2-layer 1.6 mm, HASL lead-free", "manufacturer": "JLCPCB",
                 "mpn": "pcb/controller/fab (Gerbers)", "qty": 1, "unit_usd": 2.00, "price_source": EST + " (5-board order / 5)",
                 "notes": "JLCPCB standard 2-layer rules"})
    rows += pcb_rows(ctrl, "Controller", "Controller")
    rows += tool_pcb_rows(tool)
    rows += printed_rows(parts)
    for r in rows:
        r["ext_usd"] = round(float(r["qty"]) * float(r["unit_usd"]), 2)
    order = ["Arm", "Base & safety", "Controller", "Gripper", "Knob turner", "Button presser", "Slider pusher", "Fixtures"]
    rows.sort(key=lambda r: order.index(r["section"]))
    totals = OrderedDict((s, 0.0) for s in order)
    for r in rows:
        totals[r["section"]] += r["ext_usd"]
    fields = ["section", "item", "manufacturer", "mpn", "qty", "unit_usd", "ext_usd", "price_source", "notes"]
    with (HERE / "bom.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fields})
        for s, t in totals.items():
            w.writerow({"section": s, "item": f"TOTAL {s}", "ext_usd": round(t, 2), "price_source": "sum of estimates"})
        arm_total = totals["Arm"] + totals["Base & safety"] + totals["Controller"]
        w.writerow({"section": "TOTAL", "item": "TOTAL arm (arm + base & safety + controller, no tools)",
                    "ext_usd": round(arm_total, 2), "price_source": "sum of estimates"})
        w.writerow({"section": "TOTAL", "item": "TOTAL arm with all four tools and fixtures",
                    "ext_usd": round(sum(totals.values()), 2), "price_source": "sum of estimates"})
    for s, t in totals.items():
        print(f"{s:16s} {t:8.2f} USD")
    print(f"{'arm only':16s} {totals['Arm'] + totals['Base & safety'] + totals['Controller']:8.2f} USD")
    print(f"{'everything':16s} {sum(totals.values()):8.2f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())

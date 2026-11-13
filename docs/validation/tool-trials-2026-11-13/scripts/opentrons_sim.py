import json
out = {}
try:
    import opentrons
    from opentrons import simulate
    p = simulate.get_protocol_api("2.19")
    tips = p.load_labware("opentrons_96_tiprack_300ul", 1); plate = p.load_labware("corning_96_wellplate_360ul_flat", 2)
    pip = p.load_instrument("p300_single_gen2", "right", tip_racks=[tips])
    pip.transfer(50, plate["A1"], plate["B1"])
    out = {"ok": True, "version": opentrons.__version__, "commands": len(p.commands()), "first": p.commands()[:2]}
except Exception as e:
    out = {"ok": False, "error": f"{type(e).__name__}: {e}"[:400]}
print(json.dumps(out))

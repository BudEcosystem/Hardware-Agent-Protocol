#!/usr/bin/env python3
"""Regenerate the TypeScript budget conversion table from the shared Python UCUM registry."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sdk/python/src"))
from bhms.protocol.units import UNITS  # noqa: E402

registry = {key: [unit.dimension, float(unit.factor), float(unit.offset)] for key, unit in UNITS.items()}
(ROOT / "sdk/typescript/src/generated/budgetUnits.ts").write_text(
    "// Generated from sdk/python/src/bhms/protocol/units.py; shared BHMS UCUM subset.\n"
    "export const BUDGET_UNITS: Record<string, readonly [string, number, number]> = "
    + json.dumps(registry, indent=2) + ";\n"
)

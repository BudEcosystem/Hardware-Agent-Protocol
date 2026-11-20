#!/usr/bin/env python3
"""Read retained text as data; never import/execute a candidate or compiler.

Reproduce bounded measurements, exact text-repeat joins and coverage hashes.
This script writes only measurements.json and coverage.json in this new packet.
"""
import collections
import hashlib
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PINS = json.loads((HERE / "source-pins.json").read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


raw = {}
for name, pin in PINS["inputs"].items():
    data = (ROOT / pin["path"]).read_bytes()
    assert len(data) == pin["bytes"] and sha(data) == pin["sha256"], name
    raw[name] = data.splitlines(keepends=True)

UNITS = {
    "hms_standing_poll": (15752, 20078, 7410),
    "hms_standing_handle": (20082, 23854, 5692),
    "hms_endpoint_handle": (23955, 27143, 4880),
}
instruction = re.compile(r"^\t([a-z][a-z0-9]*)\s*(.*?)\s*$")


def insns(first, last):
    result = []
    for no in range(first, last + 1):
        match = instruction.fullmatch(raw["ltrans.s"][no - 1].decode().rstrip("\n"))
        if match:
            op, operands = match.groups()
            result.append((no, op, operands, 4 if op in {"call", "jmp", "lds", "sts"} else 2))
    return result


units = {}
old = json.loads((HERE / "body-observations.json").read_text())["units"]
for name, (first, last, mapped) in UNITS.items():
    rows = insns(first, last)
    counts = collections.Counter(row[1] for row in rows)
    calls = collections.Counter(row[2] for row in rows if row[1] == "call")
    width = sum(row[3] for row in rows)
    table_bytes = 32 if name == "hms_standing_handle" else 0
    # The standing switch has sixteen .word directives, separately counted.
    words = [line.decode().strip() for line in raw["ltrans.s"][first-1:last]
             if line.decode().lstrip().startswith(".word ")]
    assert len(words) * 2 == table_bytes
    assert width + table_bytes == mapped
    assert width == old[name]["instruction_bytes"]
    assert len(rows) == old[name]["instructions"]
    assert dict(calls) == old[name]["calls"]
    repeated = []
    for repeat in old[name]["literal_repeated_instruction_runs"]:
        left, right = insns(*repeat["a"]), insns(*repeat["b"])
        assert [(r[1], r[2]) for r in left] == [(r[1], r[2]) for r in right]
        assert len(left) == repeat["instructions"]
        assert sum(r[3] for r in left) == repeat["nominal_instruction_bytes_each"]
        repeated.append({key: repeat[key] for key in (
            "a", "b", "instructions", "nominal_instruction_bytes_each")})
    units[name] = {
        "raw_lines": [first, last], "instructions": len(rows),
        "instruction_width_sum": width, "switch_table_bytes": table_bytes,
        "map_section_bytes": mapped, "opcode_histogram": dict(sorted(counts.items())),
        "static_direct_call_sites": dict(sorted(calls.items())),
        "literal_repeats_verified": repeated,
        "y_offset_adjust_instructions": sum(
            bool(re.search(r"r(?:28|29),\d+-\d+$", r[2])) for r in rows),
        "machine_byte_identity_established": False,
    }

map_text = b"".join(raw["runtime.map"]).decode()
sections = {}
for name in (".text", ".data", ".bss", ".noinit"):
    matches = re.findall(r"^" + re.escape(name) + r"\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)", map_text, re.M)
    assert len(matches) == 1, (name, matches)
    address, count = matches[0]
    sections[name] = {"address": int(address, 16), "bytes": int(count, 16)}
assert sections[".text"]["bytes"] == 41784
assert sections[".data"]["bytes"] == 26
assert sections[".bss"]["bytes"] == 1477
assert sections[".noinit"]["bytes"] == 0
for name, (_, _, count) in UNITS.items():
    match = re.search(r"^ \.text\." + re.escape(name) + r"\s+0x[0-9a-f]+\s+0x([0-9a-f]+)", map_text, re.M)
    assert match and int(match.group(1), 16) == count

retention = json.loads(b"".join(raw["retention.json"]))
root_names = [item["name"] for item in retention["function_roots"]] + retention["other_required_symbols"]
assert len(root_names) == len(set(root_names)) == 30
assert len(retention["storage_roots"]) == 9
assert len({item["name"] for item in retention["storage_roots"]}) == 9


def allocated_symbol(name, section_name, aggregate):
    # A root must have exactly one allocated input section and symbol line,
    # and the symbol must start that section inside the aggregate region.
    symbols = re.findall(r"^\s+0x([0-9a-f]+)\s+" + re.escape(name) + r"$", map_text, re.M)
    entries = re.findall(r"^ " + re.escape(section_name) +
                         r"\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)", map_text, re.M)
    assert len(symbols) == len(entries) == 1, (name, symbols, entries)
    address, size = (int(value, 16) for value in entries[0])
    assert address == int(symbols[0], 16) and size > 0, name
    region = sections[aggregate]
    assert region["address"] <= address < address + size <= region["address"] + region["bytes"], name
    return {"name": name, "section": section_name, "address": address, "bytes": size}


function_allocations = []
for name in root_names:
    section_name = ".text.startup.main" if name == "main" else ".text." + name
    function_allocations.append(allocated_symbol(name, section_name, ".text"))
storage_allocations = []
for item in retention["storage_roots"]:
    allocation = allocated_symbol(item["name"], ".bss." + item["name"], ".bss")
    assert allocation["bytes"] == item["bytes"], item
    storage_allocations.append(allocation)
for allocations in (function_allocations, storage_allocations):
    ordered = sorted(allocations, key=lambda item: item["address"])
    assert all(left["address"] + left["bytes"] <= right["address"]
               for left, right in zip(ordered, ordered[1:]))
assert sum(item["bytes"] for item in storage_allocations) == sections[".bss"]["bytes"] == 1477

wide = {"__cmpdi2", "__cmpdi2_s8", "__adddi3", "__subdi3"}
flash = sections[".text"]["bytes"] + sections[".data"]["bytes"]
dump("measurements.json", {
    "schema": "hms-standing-size-measurements/1",
    "scope": "Failed-link map and assembly text only; no ELF, projected savings, candidate or compiler execution",
    "source_pins_sha256": sha((HERE / "source-pins.json").read_bytes()),
    "units": units, "sections": sections, "flash": flash,
    "physical_limit": 32768, "application_limit": 32256,
    "physical_excess": flash - 32768, "application_excess": flash - 32256,
    "selected_body_bytes": sum(unit[2] for unit in UNITS.values()),
    "function_roots_plus_main_present": len(root_names),
    "charged_storage_roots_exact": len(retention["storage_roots"]),
    "function_root_allocations": function_allocations,
    "charged_storage_allocations": storage_allocations,
    "wide_arithmetic_direct_call_sites": sum(
        count for unit in units.values() for name, count in unit["static_direct_call_sites"].items() if name in wide),
    "decoder64_direct_call_sites": sum(
        count for unit in units.values() for name, count in unit["static_direct_call_sites"].items() if name in {"r64", "get64"}),
    "encoder64_direct_call_sites": sum(
        count for unit in units.values() for name, count in unit["static_direct_call_sites"].items() if name in {"w64", "put64"}),
})

# These are precise human-read ranges, not a claim of semantic review of each
# instruction in the three mechanically enumerated full units.
READS = {
    "standing.c": [(1, 749)], "endpoint.c": [(1, 630)],
    "standing.h": [(1, len(raw["standing.h"]))],
    "endpoint.h": [(1, len(raw["endpoint.h"]))],
    "retention.json": [(1, len(raw["retention.json"]))],
    "parent-result.md": [(1, len(raw["parent-result.md"]))],
    "runtime.map": [(430, 790)], "wpa.inline": [(6435, 6638)],
    "ltrans.s": [(151,334), (413,452), (8061,8112), (8785,8823),
                  (18140,18375), (18920,19210), (20082,20215),
                  (21905,22017), (22770,22850), (23955,24250),
                  (26635,26715), (26815,26890)],
}
coverage = []
for name, ranges in READS.items():
    for first, last in ranges:
        data = b"".join(raw[name][first-1:last])
        assert last <= len(raw[name]) and first <= last
        coverage.append({"input": name, "first": first, "last": last,
                         "bytes": len(data), "sha256": sha(data),
                         "kind": "human-read complete stated range"})
for name, (first, last, _) in UNITS.items():
    data = b"".join(raw["ltrans.s"][first-1:last])
    coverage.append({"input": "ltrans.s", "first": first, "last": last,
                     "bytes": len(data), "sha256": sha(data), "unit": name,
                     "kind": "complete mechanical instruction enumeration; partial semantic reading as separately listed"})
dump("coverage.json", {"schema": "hms-standing-size-read-coverage/1", "ranges": coverage})
print(json.dumps({"status": "PASS", "units": len(units), "flash": flash,
                  "physical_excess": flash - 32768,
                  "scope": "stdlib text-data analysis only"}, sort_keys=True))

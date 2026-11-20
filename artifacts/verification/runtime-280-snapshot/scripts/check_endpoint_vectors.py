#!/usr/bin/env python3
"""Independent design-fixture checks; no endpoint executor or acquired code."""
import binascii
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "protocol/endpoint/vectors.json"
SPEC = ROOT / "spec/11-endpoint-wire.md"
data = json.loads(VECTORS.read_text())
sha = lambda b: hashlib.sha256(b).hexdigest()
u = lambda b: int.from_bytes(b, "big")
rev8 = lambda v: int(f"{v:08b}"[::-1], 2)
rev16 = lambda v: int(f"{v:016b}"[::-1], 2)
for path, expected in data["sourceHashes"].items():
    assert sha((ROOT / path).read_bytes()) == expected, path

assert data["layout"]["maxDecodedFrameBytes"] == 20 + 192 + 2
assert data["layout"]["maxEncodedFrameBytes"] == 2 * 214 + 2
assert sum([219, 70, 214, 10, 67, 193, 69, 32, 96, 64, 256, 512]) == 1802
assert 2048 - 1802 == 246
assert struct.calcsize(">BBIHI32sHBBBBHQQQIQ") == 88
assert struct.calcsize(">IHI32sBBBBBBHIQQQB") == 79
assert 7 + 79 == 86

decoded = {}
response_count = 0
for item in data["wireVectors"]:
    name = item["name"]
    assert name not in decoded
    wire = bytes.fromhex(item["encoded_frame_hex"])
    assert len(wire) == item["encoded_frame_length"] <= 430
    assert wire[0] == wire[-1] == 0x7e
    interior = iter(wire[1:-1])
    raw = bytearray()
    for byte in interior:
        assert byte != 0x7e
        if byte == 0x7d:
            byte = next(interior) ^ 0x20
            assert byte in (0x7d, 0x7e)
        raw.append(byte)
    # Independent stdlib CCITT implementation, with explicit bit reflection;
    # do not import or call the fixture generator or serial codec.
    crc = rev16(binascii.crc_hqx(bytes(rev8(v) for v in raw), 0xffff))
    assert crc == 0xf0b8, name
    assert raw[:3] == b"HM\x01" and raw[4] == 0
    assert (raw[3], raw[5], u(raw[6:14]), u(raw[14:18])) == (
        item["frame"]["kind"], item["frame"]["channel"],
        item["frame"]["session"], item["frame"]["sequence"])
    payload = bytes(raw[20:-2])
    assert u(raw[18:20]) == len(payload) == item["payload_length"]
    assert len(raw) == 20 + len(payload) + 2 <= 214
    assert payload == bytes.fromhex(item["payload_hex"])
    assert payload[0] == 1
    decoded[name] = payload
    if item["frame"]["kind"] == 2:
        response_count += 1
        opcode, status = payload[1], payload[6]
        if status:
            assert len(payload) == 7
        elif opcode == 0x81:
            assert len(payload) == 186
            assert u(payload[87:91]) == 1
            assert u(payload[91:93]) == 0
            assert payload[93:125] == bytes(32)
            assert payload[125] == 0 and u(payload[126:128]) == 57
            assert list(payload[128:133]) == [8, 72, 32, 1, 1]
            assert u(payload[133:141]) == 1000
            assert payload[141:] == bytes(45)
        elif opcode in (0x90, 0x91, 0x92):
            assert len(payload) == 69
            assert payload[45] <= 4 and u(payload[46:48]) < 128
        elif opcode in (0xa0, 0xa1, 0xa2):
            assert len(payload) == 86 + payload[85] <= 118
            assert u(payload[57:61]) > 0
            assert payload[54] in (0, 1)
            assert payload[53] & ~5 == 0
            times = [u(payload[a:a + 8]) for a in (61, 69, 77)]
            known = [v for v in times if v != 2**64 - 1]
            assert known == sorted(known)
            if name == "invalid_simulation_verified_receipt":
                assert payload[51:53] == bytes([5, 1])
            else:
                assert not (payload[51] in (1, 5) and payload[52] == 1)
        else:
            assert opcode == 0xa3 and len(payload) == 7

op = decoded["op_scaled_pair"]
fields = struct.unpack_from(">BBIHI32sHBBBBHQQQIQ", op)
assert fields[:5] == (1, 0x20, 2, 7, 1)
assert fields[6:] == (0x1234, 5, 8, 0, 0, 0, 1100, 1200, 1500, 200, 1600)
assert struct.unpack_from(">IIii", op, 88) == (5, 9, 1000, -25)
assert len(op) == 88 + 4 * op[46].bit_count() + op[47]
maximum = decoded["op_maximum_192_bytes"]
assert len(maximum) == 88 + 4 * maximum[46].bit_count() + maximum[47] == 192
assert maximum[46:48] == bytes([255, 72])
assert maximum[-72:] == bytes(range(72))
for name in ("completed_still_holds_resources", "completed_quiescent_receipt"):
    assert int.from_bytes(decoded[name][86:], "big", signed=True) == 975

for key, expected in (("syntheticInstalledManifest", "installedManifest"),
                      ("syntheticHostContext", "hostContext")):
    encoded = json.dumps(data[key], sort_keys=True, separators=(",", ":")).encode()
    assert sha(encoded) == data["fixtureDigests"][expected]
manifest_digest = bytes.fromhex(data["fixtureDigests"]["installedManifest"])
context_digest = bytes.fromhex(data["fixtureDigests"]["hostContext"])
assert decoded["bind_request"] == struct.pack(">BBIH", 1, 0x10, 1, 7) + manifest_digest + context_digest
assert decoded["arm_request"] == struct.pack(">BBIH", 1, 0x11, 2, 7) + context_digest + struct.pack(">Q", 2000)
assert decoded["revoke_request"] == struct.pack(">BBIHH", 1, 0x12, 2, 7, 6)
for name, opcode in (("query_request", 0x21), ("cancel_request", 0x22),
                     ("retire_request", 0x23), ("query_after_retirement", 0x21)):
    assert decoded[name] == struct.pack(">BBIHI", 1, opcode, 2, 7, 1) + op[12:44]

for key, digest_key, payload in (
        ("firstRequest", "firstIntentDigest", op),
        ("maximumRequest", "maximumIntentDigest", maximum)):
    # These fixtures contain only ASCII object keys/strings and bounded integer
    # numbers; sorted compact JSON agrees with their canonical intent form.
    canonical = json.dumps(data["hostMapping"][key]["intent"], sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False).encode()
    digest = sha(b"HMS-INTENT-JCS-SHA256-v0.1\x00" + canonical)
    assert "sha256:" + digest == data["hostMapping"][digest_key]
    assert payload[12:44].hex() == digest

for case in data["negativeAdmissionCases"]:
    assert case["vector"] in decoded
    assert case["mutationAssertions"] == {
        "newEffectCount": 0,
        "partialResourceAcquisition": False,
        "admissionAdvancesCallOrFenceFloors": False,
    }
for case in data["stateScenarios"]:
    for step in case["steps"]:
        if "inputVector" in step:
            assert step["inputVector"] in decoded

print(json.dumps({
    "passed": True,
    "spec_sha256": sha(SPEC.read_bytes()),
    "vectors_sha256": sha(VECTORS.read_bytes()),
    "host_contract_source_sha256": sha((ROOT / "hms/contracts.py").read_bytes()),
    "checker_sha256": sha(Path(__file__).read_bytes()),
    "wire_vectors_independently_unescaped_and_fcs_checked": len(decoded),
    "responses_layout_checked": response_count,
    "host_intent_digest_mappings_checked": 2,
    "synthetic_manifest_and_context_digests_checked": 2,
    "negative_case_references_and_nonmutation_assertions_checked": len(data["negativeAdmissionCases"]),
    "state_scenario_references_checked": len(data["stateScenarios"]),
    "memory_arithmetic_only": {"planned": 1802, "unallocated": 246},
    "scope": "Independent framing/FCS, exact layout arithmetic, response offsets, selected semantic invariants and synthetic intent mapping. Negative/state outcomes remain design assertions; no endpoint decoder, execution, measured target memory, NVM, stop or hardware test.",
}, indent=2))

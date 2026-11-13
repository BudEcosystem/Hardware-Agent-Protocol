"""Read-only verification of captured native frames and source stability."""
from pathlib import Path
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORKTREE = Path('/home/bud/Desktop/bud/hms-harness-a1626788')
sys.path.insert(0, str(HERE / 'runtime-fixture'))
from hms.endpoint_wire import Execution, Opcode, Operation, Receipt, Request, decode_response
from protocol.serial.frame import Decoder


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame(raw):
    decoder = Decoder()
    events = [event for byte in bytes.fromhex(raw) if (event := decoder.feed(byte)) is not None]
    assert len(events) == 1 and events[0][0] == 'frame'
    return events[0][1]


records = [json.loads(line) for line in (HERE / 'compact-capture.jsonl').read_text().splitlines()]
assert len(records) == 4
assert records[0]['scenario'] == 'ptc-three-native-c'
dispatch = [event for event in records[0]['dispatch'] if event['data']['name'] == 'hardware_invoke']
assert len(dispatch) == 6
for index in range(3):
    assert dispatch[2*index]['data']['arguments'] == dispatch[2*index+1]['data']['arguments']
verified = []
for index, evidence in enumerate(records[0]['evidence'] + [row['evidence'] for row in records[1:]]):
    operation_frame = frame(evidence['opWireHex'])
    operation = Operation.parse(operation_frame.payload)
    requests = [frame(raw) for raw in evidence['frames']['requests']]
    assert sum(request.payload == operation_frame.payload for request in requests) == 1
    assert evidence['totalOpFrames'] == sum(request.payload[1] == Opcode.OP for request in requests)
    response = frame(evidence['nativeReceipt']['wireHex'])
    reference_sequence = int.from_bytes(response.payload[2:6], 'big')
    request = next(request for request in requests if request.sequence == reference_sequence)
    receipt = decode_response(response, Request(request), operation=operation, simulator_only=True)
    assert isinstance(receipt, Receipt) and receipt.execution == Execution.COMPLETED
    assert receipt.verification == 0 and receipt.evidence_kind == 5 and receipt.held_resources == 0
    assert int.from_bytes(receipt.result[8:], 'big') == [25, 42, 1][index % 3]
    assert receipt.result.hex() == evidence['nativeReceipt']['resultHex']
    assert int.from_bytes(receipt.result[:8], 'big') == evidence['nativeReceipt']['sampleTick']
    assert evidence['requestDigest'] == 'sha256:' + operation.reference.intent_digest.hex()
    if index >= 3:
        record = records[index-2]
        crash = record['crash']
        assert evidence['queriedAfterRestart'] and evidence['opWireHex'] == crash['opWireHex']
        assert any(request.payload == operation.reference.payload(Opcode.QUERY)
                   for request in requests[crash['requestCount']:])
        assert record['admitted']['result']['operationId'] == record['replayed']['result']['operationId'] == record['again']['result']['operationId']
        assert record['status']['result']['result'] == record['again']['result']['result']
    verified.append(dict(operationId=evidence['operationId'], value=evidence['nativeReceipt']['value'],
                         sampleTick=evidence['nativeReceipt']['sampleTick'], operationOpFrames=1,
                         queriedAfterRestart=evidence['queriedAfterRestart']))

fixture = json.loads((HERE / 'fixture-inputs.json').read_text())['sha256']
for name, expected in fixture.items():
    assert digest(HERE / 'runtime-fixture' / name) == expected, name
hms = json.loads((HERE / 'prior-harness-verification.json').read_text())['hms_inputs_sha256']
for name, expected in hms.items():
    assert digest(ROOT / name) == digest(HERE / 'runtime-fixture' / name) == expected, name
overlay = json.loads((HERE / 'patch-inputs.json').read_text())
for name, expected in overlay['all_overlay_inputs_sha256'].items():
    assert digest(WORKTREE / name) == expected, name
for name, expected in overlay['harness_package_sources_sha256'].items():
    assert digest(HERE / 'packages' / Path(name).relative_to('packages/experimental')) == expected, name
assert digest(HERE / 'harness.patch') == overlay['patch_sha256']
result = dict(passed=True, decoded_native_receipts=verified, fixture_files=len(fixture), live_hms_inputs=len(hms),
              package_files=len(overlay['harness_package_sources_sha256']), overlay_files=len(overlay['all_overlay_inputs_sha256']),
              scope='Read-only captured-frame checks and exact post-run source/fixture/export hashes. No new action or hardware execution. One forwarded OP per operation; fan/focus values are not independent effect counters.',
              source_sha256=digest(Path(__file__)), capture_sha256=digest(HERE / 'compact-capture.jsonl'))
(HERE / 'verification/capture-and-source-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))

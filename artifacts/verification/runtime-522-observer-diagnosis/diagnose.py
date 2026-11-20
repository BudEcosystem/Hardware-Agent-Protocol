"""Read immutable failed-attempt evidence; never execute a test or runtime."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

LANE = Path(__file__).resolve().parent
ROOT = LANE.parents[2]
ATTEMPT = ROOT / 'artifacts/verification/runtime-attempts/20261106T212220.223800Z-c4b3400474ac'
PINS = {}


def retain(path, expected=None):
    data = path.read_bytes()
    pin = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    if expected is not None:
        assert pin['sha256'] == expected['sha256'], path
        if 'bytes' in expected:
            assert pin['bytes'] == expected['bytes'], path
    PINS[str(path.relative_to(ROOT))] = pin
    return pin


def read_json(path):
    retain(path)
    return json.loads(path.read_bytes())


receipt = read_json(ATTEMPT / 'receipt.json')
assert receipt['status'] == 'failed' and receipt['tests'] == 522
assert receipt['failures'] == 0 and receipt['errors'] == 2 and receipt['skipped'] == 0
assert receipt['inputs_stable'] and receipt['stable_input_proof'] and receipt['compiler_identity_stable']
assert not receipt['runner_errors'] and not receipt['input_capture_errors']
assert receipt['input_changes'] == {'added': [], 'removed': [], 'changed': []}
snapshots = []
for label in ('files_before', 'files_after'):
    entries = receipt[label]
    assert len(entries) == 112 and len({item['path'] for item in entries}) == 112
    for item in entries:
        retain(ROOT / item['snapshot_path'], item)
    snapshots.append({item['path']: item['sha256'] for item in entries})
assert snapshots[0] == snapshots[1] == {item['path']: item['sha256'] for item in receipt['files']}
for item in receipt['outputs']:
    retain(ROOT / item['path'], item)
    if 'original_path' in item:
        retain(ROOT / item['original_path'], item)
assert len(receipt['outputs']) == 25
identity_before = read_json(ATTEMPT / 'outputs/pat-compiler-identity-before.json')
assert identity_before == read_json(ATTEMPT / 'outputs/pat-compiler-identity-after.json')

pointer_path = ROOT / 'artifacts/verification/local-runtime-current.json'
pointer_bytes = pointer_path.read_bytes()
pointer = json.loads(pointer_bytes)
pointer_copied = pointer.get('attempt_id') == receipt['attempt_id']
if pointer_copied:
    assert pointer['status'] == 'failed' and pointer['current_pass'] is False
    retain(ROOT / pointer['receipt']['path'], pointer['receipt'])
    retain(ROOT / pointer['last_success']['path'], pointer['last_success'])
    with (LANE / 'current-pointer-at-diagnosis.json').open('xb') as output:
        output.write(pointer_bytes)

# These are pure codecs from the immutable attempt tree. They do not open a
# runtime, native process, transport or device.
sys.path.insert(0, str(ATTEMPT / 'inputs-before'))
from protocol.serial.frame import Decoder
from hms.endpoint_wire import Request, Refusal, decode_response


def decode(wire):
    decoder, frames = Decoder(), []
    for byte in wire:
        event = decoder.feed(byte)
        if event and event[0] == 'frame':
            frames.append(event[1])
    assert len(frames) == 1
    return frames[0]


def packet_facts(rows):
    requests, tx, responses, refusals = {}, Counter(), Counter(), []
    for direction, adapter, wire in rows:
        frame = decode(wire)
        if direction == 'tx':
            tx[(adapter, int(frame.payload[1]))] += 1
            requests[(adapter, frame.sequence)] = Request(frame)
        else:
            key = (adapter, int.from_bytes(frame.payload[2:6], 'big'))
            response = decode_response(frame, requests.pop(key), simulator_only=True)
            responses[(adapter, type(response).__name__)] += 1
            if isinstance(response, Refusal):
                refusals.append(repr(response))
    return {'transmits': [{'adapter': adapter, 'opcode': opcode, 'count': count}
                         for (adapter, opcode), count in sorted(tx.items())],
            'responses': [{'adapter': adapter, 'kind': kind, 'count': count}
                          for (adapter, kind), count in sorted(responses.items())],
            'refusals': refusals,
            'unmatchedTransmit': [{'adapter': adapter, 'sequence': sequence,
                                   'opcode': int(request.opcode)}
                                  for (adapter, sequence), request in requests.items()]}


def database(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)


names = [
    'test_multi_cli-MultiCliTests-test_named_streams_mixed_scenarios_and_offline_reop-9200acf66b0c4a92a325f45616042003',
    'procedure-transport-371f954ab6dd48088ce5eb4e2846082b']
cases = {}
for name in names:
    original = ROOT / 'artifacts/verification/transport-failures' / name
    manifest = read_json(original / 'manifest.json')
    for item in manifest['files']:
        retain(original / item['path'], item)
        retain(ATTEMPT / 'outputs/transport-failures' / name / item['path'], item)
    capture, report = read_json(original / 'capture.json'), read_json(original / 'report.json')
    with database(original / 'databases/authority.db') as db:
        tables = ['operations', 'events', 'claims', 'replay_keys', 'ep_commands',
                  'pr_procedures', 'pr_steps', 'pr_keys', 'pr_events', 'resource_floors']
        counts = {table: db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in tables}
        assert all(value == 0 for value in counts.values())
        packets = packet_facts(db.execute('SELECT direction,adapter,wire FROM ep_packets ORDER BY id'))
        states = [{'adapter': adapter, **{key: json.loads(document)[key]
                   for key in ('fault', 'call', 'tx', 'rx', 'lastTick')}}
                  for adapter, document in db.execute('SELECT adapter,document FROM ep_state')]
        last_clock = int(db.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0])
    plants = []
    for plant in (original / 'databases').glob('simulated-plant-*.db'):
        with database(plant) as db:
            devices = [{'instance': instance, 'value': json.loads(value), 'effectCount': effects}
                       for instance, value, effects in db.execute('SELECT * FROM devices')]
            plants.append({'path': str(plant.relative_to(ROOT)), 'devices': devices,
                           'receipts': db.execute('SELECT count(*) FROM receipts').fetchone()[0],
                           'fences': db.execute('SELECT count(*) FROM fences').fetchone()[0]})
        assert all(item['effectCount'] == 0 for item in devices)
    cases[name] = {'manifest': str((original / 'manifest.json').relative_to(ROOT)),
                   'manifestSha256': PINS[str((original / 'manifest.json').relative_to(ROOT))]['sha256'],
                   'manifestFileCount': len(manifest['files']), 'capturedAtUtc': capture['capturedAtUtc'],
                   'error': capture['reason'], 'counts': counts, 'packetHistory': packets,
                   'endpointStates': states, 'lastClockUnixMs': last_clock, 'plants': plants,
                   'recordedRefusals': report['refusals'], 'processOutput': report['processOutput'],
                   'requestHistory': report['requestHistory']}
    assert not report['refusals'] and not packets['refusals']
    if name.startswith('procedure-transport'):
        relay = read_json(original / 'relay.json')
        assert relay['error'] is None and not relay['pendingReplies']
        # Relay capture happens separately from the database backup. Match its
        # own request/response pairs without requiring identical snapshot time.
        rows = []
        for tx, rx in zip(relay['requests'], relay['responses']):
            rows += [('tx', 'test-route:procedure-transport-native', bytes.fromhex(tx)),
                     ('rx', 'test-route:procedure-transport-native', bytes.fromhex(rx))]
        assert len(relay['requests']) == len(relay['responses']) == 9
        cases[name]['relay'] = packet_facts(rows)
        cases[name]['stage'] = 'Second child native inspection (mcp-child:1): observer failed before prepare was sent, after first local-fan prepare returned admitted:false. MCP projection not yet entered.'
        cases[name]['mcpMessages'] = len(report['mcpMessages'])
        cases[name]['validatedToolReplies'] = report['validatedToolReplies']
    else:
        cases[name]['stage'] = 'First local-fan scenario: observer failed before first prepare was sent; requestHistory entry was appended before observer.'

trace = read_json(ATTEMPT / 'outputs/procedure-transport-trace.json')
other_cases = {}
for name, case in trace['cases'].items():
    if not case['passed']:
        continue
    other_cases[name] = {'passed': True, 'completedChildren': [
        {'operationId': child['operationId'], 'executionState': child['executionState']}
        for child in case.get('children', [])], 'recordedRefusals': case['refusals']}
    for key in ('nativeEvidence', 'sqlitePlantEvidence', 'syntheticDispatchCounter', 'syntheticEffectCounter'):
        if key in case:
            other_cases[name][key] = case[key]
    if 'independentCompleted' in case:
        child = case['independentCompleted']
        other_cases[name]['independentCompleted'] = {
            'operationId': child['operationId'], 'executionState': child['executionState']}

analysis = {'schema': 'hms-runtime-observer-diagnosis/1', 'attemptId': receipt['attempt_id'],
            'receiptSha256': PINS[str((ATTEMPT / 'receipt.json').relative_to(ROOT))]['sha256'],
            'summary': {'status': 'failed', 'tests': 522, 'passedTests': 520, 'failures': 0,
                        'errors': 2, 'seconds': 549.474, 'skipped': 0},
            'retentionValidation': {'beforeSnapshots': 112, 'afterSnapshots': 112, 'outputs': 25,
                'sourceHashSetsEqual': True, 'allRecordedHashesVerified': True,
                'compilerIdentityBytesEqual': True, 'compilerIdentityStableReceiptFlag': True,
                'sourceStableReceiptFlags': True, 'currentPointerCopied': pointer_copied},
            'cases': cases, 'otherProcedureCases': other_cases,
            'conclusion': 'Both errors originate in external test-observer SQLite count reads before their intended prepare calls. Neither failed case reached invoke or procedure submission. This run is failed, not a passing runtime qualification.',
            'limits': ['The capture does not record exact writer/lock ownership or commit timing; no claim of scheduler starvation or a specific production persistence defect follows.',
                       'Separate database backups and relay capture are not simultaneous; unmatched packets in one snapshot do not prove a transport timeout.',
                       'Other completed CLI/modern-MCP/paused-route cases use separate state directories and must not be attributed to the failed legacy-MCP case.',
                       'Native relay OP counts establish original-byte handoffs, not independent physical effects; SQLite and test-control counters establish only synthetic fixture effects.',
                       'No source edits, test reruns, native execution, physical I/O or live-source comparison were performed by this diagnosis.']}
for name, data in [('diagnosis.json', analysis), ('evidence-pins.json', PINS)]:
    with (LANE / name).open('x') as output:
        json.dump(data, output, indent=2, sort_keys=True)
        output.write('\n')
for name, expected in PINS.items():
    data = (ROOT / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected['sha256'] and len(data) == expected['bytes'], name
print(json.dumps({'verifiedEvidenceFiles': len(PINS), 'summary': analysis['summary'],
                  'retentionValidation': analysis['retentionValidation']}, indent=2))

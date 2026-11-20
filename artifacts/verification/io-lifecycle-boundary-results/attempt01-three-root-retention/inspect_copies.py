"""Read only acquired logical SQLite copies; no original DB or project imports."""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import sqlite3

BASE = Path(__file__).resolve().parent
EVIDENCE = BASE / 'attempt/evidence'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    if isinstance(value, bytes):
        return {'blobHex': value.hex()}
    if isinstance(value, (list, tuple)):
        return [encoded(item) for item in value]
    return value


def bounded_rows(db, sql):
    values = db.execute(sql).fetchmany(129)
    assert len(values) <= 128, sql
    return values


def inspect(path):
    path = path.resolve()
    assert path.is_relative_to(EVIDENCE.resolve()) and not path.is_symlink()
    before = sha(path)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        tables = {row[0] for row in bounded_rows(db, "SELECT name FROM sqlite_master WHERE type='table'")}
        wanted = ('operations', 'replay_keys', 'claims', 'resource_floors', 'lc_dispatch',
                  'lc_receipts', 'lc_publications', 'io_dispatch_links', 'io_authority_receipts',
                  'io_lc_receipts', 'io_receipts', 'io_receipt_versions', 'io_owners')
        value = {'counts': {table: db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                            for table in wanted if table in tables}, 'rowDigests': {}}
        if 'operations' in tables:
            value['operations'] = [dict(id=r[0], state=r[1], mayHaveActed=r[2]) for r in
                                   bounded_rows(db, 'SELECT id,state,may_have_acted FROM operations ORDER BY id')]
            value['claims'] = [dict(resource=r[0], operation=r[1]) for r in
                               bounded_rows(db, 'SELECT resource,operation_id FROM claims ORDER BY resource')]
            value['catalogRevision'] = db.execute('SELECT current_revision FROM rc_catalog').fetchone()[0]
            value['publications'] = [json.loads(r[0]) for r in
                                     bounded_rows(db, 'SELECT document FROM lc_publications ORDER BY operation')]
        if 'io_lc_snapshots' in tables:
            value['snapshots'] = [list(r) for r in
                                  bounded_rows(db, 'SELECT revision,operation FROM io_lc_snapshots ORDER BY revision')]
            value['lifecycleReceipts'] = []
            for row in bounded_rows(db, 'SELECT document FROM io_lc_receipts ORDER BY operation'):
                document = json.loads(row[0]); dispatch = document['dispatch']
                value['lifecycleReceipts'].append(dict(operationId=document['operationId'],
                    generationApplied=document['generationApplied'], target=dispatch['target'],
                    claims=dispatch['scope']['claims'], affected=sorted(dispatch['affected']),
                    affectedConsumers=dispatch['scope']['affectedConsumers']))
            value['effects'] = [list(r) for r in bounded_rows(db, 'SELECT * FROM io_effects ORDER BY instance')]
        orders = {'reg_bindings': 'instance', 'reg_binding_history': 'instance,generation',
                  'io_authority_receipts': 'operation,sequence', 'io_receipts': 'operation',
                  'io_receipt_versions': 'operation,sequence', 'io_effects': 'instance'}
        for table, order in orders.items():
            if table in tables:
                rows = bounded_rows(db, 'SELECT * FROM ' + table + ' ORDER BY ' + order)
                wire = json.dumps(encoded(rows), separators=(',', ':'), ensure_ascii=True).encode()
                value['rowDigests'][table] = dict(rows=len(rows), sha256=hashlib.sha256(wire).hexdigest())
    assert before == sha(path), path
    value['fileSha256'] = before
    return value


snapshots = {}
for capture in sorted(EVIDENCE.rglob('capture.json')):
    record = json.loads(capture.read_bytes())
    case, phase = capture.parent.parent.name, capture.parent.name
    files = {row['path']: inspect(capture.parent / row['path']) for row in record['files']}
    snapshots[case + '/' + phase] = dict(authority=files['authority.db'],
        board=next(value for name, value in files.items() if name != 'authority.db'))

driver = 'test_direct_driver_generation_owns_siblings_and_replays_one_publication/'
admitted = snapshots[driver + '00-driver-admitted-before-effect']
committed = snapshots[driver + '01-driver-provider-committed-before-settlement']
final = snapshots[driver + '02-final']
claims = ['atom:chan0', 'atom:driverA', 'atom:pin5', 'atom:pin6', 'atom:timer0']
assert [r['resource'] for r in admitted['authority']['claims']] == claims
assert admitted['authority']['operations'][0]['state'] == 'accepted'
assert admitted['board']['counts']['io_lc_receipts'] == 0
assert [r['resource'] for r in committed['authority']['claims']] == claims
assert committed['authority']['catalogRevision'] == 1
assert committed['authority']['operations'][0]['state'] == 'dispatching'
assert committed['board']['lifecycleReceipts'][0]['generationApplied'] is True
assert final['authority']['operations'][0]['state'] == 'completed'
assert final['authority']['claims'] == [] and final['authority']['catalogRevision'] == 2
publication = final['authority']['publications'][0]['publication']
assert publication['target'] == 'driverA' and publication['generation'] == 'generation:2'
assert sorted(publication['bindings']) == ['sim:gpio5', 'sim:gpio5:other-route', 'sim:pwm5']
assert final['board']['counts']['io_lc_receipts'] == 1 and len(final['board']['snapshots']) == 2
assert all(sum(row[1:]) == 0 for row in final['board']['effects'])

idle = 'test_service_without_ordinary_dependents_keeps_ordinary_history/'
before = snapshots[idle + '01-ordinary-receipt-before-empty-service-advance']
committed = snapshots[idle + '02-empty-service-provider-committed-before-settlement']
final = snapshots[idle + '03-final']
assert before['authority']['counts']['io_authority_receipts'] > 0
assert before['board']['counts']['io_receipt_versions'] > 0
for part in ('authority', 'board'):
    assert before[part]['rowDigests'] == committed[part]['rowDigests'] == final[part]['rowDigests']
assert [r['resource'] for r in committed['authority']['claims']] == ['atom:svcIdle']
assert committed['board']['lifecycleReceipts'][0]['affected'] == []
assert committed['board']['lifecycleReceipts'][0]['affectedConsumers'] == []
assert final['authority']['claims'] == [] and final['authority']['catalogRevision'] == 2
publication = final['authority']['publications'][0]['publication']
assert publication['target'] == 'svcIdle' and publication['bindings'] == {}
assert all(r['state'] == 'completed' for r in final['authority']['operations'])
assert final['board']['counts']['io_lc_receipts'] == final['authority']['counts']['lc_publications'] == 1

ceiling = 'test_literal_safe_integer_revision_refuses_before_admission/'
for name, value in snapshots.items():
    if name.startswith(ceiling):
        assert all(count == 0 for count in value['authority']['counts'].values())
        assert all(count == 0 for count in value['board']['counts'].values())
        assert value['authority']['catalogRevision'] == 1 and value['board']['snapshots'] == [[1, '']]
        assert all(sum(row[1:]) == 0 for row in value['board']['effects'])

output = dict(profile='hms.copied-boundary-db-inspection/1', snapshots=snapshots,
              inspectedCopies=18, hashesUnchanged=True, originalDatabaseConnections=0,
              scope='Selected stored facts supplement the pinned passing tests; no project import or rerun, physical effect, true revision-history exhaustion or independent reviewer execution.')
(BASE / 'copied-db-inspection.json').write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps(dict(snapshots=len(snapshots), databases=18, hashesUnchanged=True)))

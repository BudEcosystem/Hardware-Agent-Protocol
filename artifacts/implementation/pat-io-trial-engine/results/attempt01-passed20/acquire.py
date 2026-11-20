"""One-shot retention and read-only evidence comparison; no project imports.

This verifies capture integrity, not qualification or independent effect semantics.
Run from the HMS root. Never deletes or changes the original attempt/scratch.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-trial-engine'
SOURCE = BASE / 'harness01/attempts/attempt01-trial20'
OUT = BASE / 'results/attempt01-passed20'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path, row):
    assert path.is_file() and not path.is_symlink(), str(path)
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], str(path)


def inventory(path):
    rows = []
    for entry in sorted(path.rglob('*')):
        assert not entry.is_symlink(), str(entry)
        if entry.is_dir():
            continue
        assert stat.S_ISREG(entry.stat().st_mode), str(entry)
        rows.append({'path': entry.relative_to(path).as_posix(),
                     'bytes': entry.stat().st_size, 'sha256': sha(entry)})
    return rows


def identity(path):
    value = path.lstat()
    assert stat.S_ISDIR(value.st_mode)
    return dict(path=str(path), device=value.st_dev, inode=value.st_ino,
                uid=value.st_uid, gid=value.st_gid, mode=stat.S_IMODE(value.st_mode))


def write(name, value):
    with (OUT / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


result = read(SOURCE / 'result.json')
assert result['currentPass'] is True and result['errors'] == []
assert result['childState'] == 'exited' and result['exitCode'] == 0
assert not Path('/proc/' + str(result['pid'])).exists()
assert result['counts'] == dict(testsRun=20, failures=0, errors=0, skips=0,
                                expectedFailures=0, unexpectedSuccesses=0)

seals = []
for relative, expected in [
    ('implementation01', '01094d2df482576fb2f42f75ceb5dfa11c1a0705f6dd4ce8a3f1d8132842642f'),
    ('harness01', '6d546d40822fd35e31a166740a8a92efd37f9283c365749ad878a84503fe1adf'),
]:
    index = BASE / relative / 'index.json'
    assert sha(index) == expected
    rows = read(index)['files']
    for row in rows:
        verify(ROOT / row['path'], row)
    seals.append({'path': str(index.relative_to(ROOT)), 'sha256': expected, 'filesVerified': len(rows)})

for prefix, directory, count in [('inputs', SOURCE / 'project', 159),
                                  ('frozen', ROOT, 162), ('harness', SOURCE / 'harness', 6)]:
    rows = read(SOURCE / (prefix + '-before.json'))
    assert rows == read(SOURCE / (prefix + '-after.json')) and len(rows) == count
    for row in rows:
        verify(directory / row['path'], row)
external = read(SOURCE / 'external-before.json')
assert external == read(SOURCE / 'external-after.json') and len(external['files']) == 159
for row in external['files']:
    verify(Path(row['resolvedPath']), row)
origins = read(SOURCE / 'imports.json')
assert origins['violations'] == origins['prohibitedAttempts'] == []
assert origins['summary']['recordCount'] == len(origins['records']) == 691
for row in origins['records']:
    if 'sha256' in row:
        assert sha(Path(row['origin'])) == row['sha256'], row['origin']
for name in ['compiler', 'driver']:
    assert read(SOURCE / (name + '-before.json')) == read(SOURCE / (name + '-after.json'))
selection = read(SOURCE / 'harness/targets.json')['targets']
actual = read(SOURCE / 'actual-tests.json')
assert actual['loaded'] == actual['executed'] == selection
log = (SOURCE / 'output.log').read_text()
assert log.endswith('Ran 20 tests in 114.915s\n\nOK\n')
assert [line.split('(')[1].split(')')[0] for line in log.splitlines() if line.endswith(' ... ok')] == selection

raw_before = read(SOURCE / 'raw-scratch-before.json')
raw = Path(result['scratchPath'])
assert identity(raw) == raw_before['identity'] and identity(raw.parent) == raw_before['parent']
scratch_rows = read(SOURCE / 'scratch-index.json')
assert inventory(raw) == inventory(SOURCE / 'scratch') == scratch_rows
assert sum(row['bytes'] for row in scratch_rows) == 17183506
before = inventory(SOURCE)
shutil.copytree(SOURCE, OUT / 'attempt')
assert inventory(OUT / 'attempt') == before == inventory(SOURCE)

TABLES = {
    'board': set('io_meta io_resources io_owners io_fences io_receipts io_receipt_versions io_effects'.split()),
    'authority': set(('meta series namespaces operations replay_keys resource_floors claims events '
                      'io_dispatch_links io_authority_receipts pr_meta pr_procedures pr_steps pr_keys pr_events '
                      'rt_catalog rt_adapters rt_io_installation rc_catalog rc_generations rc_tokens rc_proofs').split()),
}


def decode(cell):
    assert set(cell) == {'type', 'value'}
    kind, value = cell['type'], cell['value']
    if kind == 'blob-utf8':
        assert type(value) is str
        return value.encode('utf-8')
    assert (kind == 'null' and value is None or kind == 'integer' and type(value) is int or
            kind == 'text' and type(value) is str)
    return value


observations = []
checkpoint_count = table_reference_count = 0
copied = OUT / 'attempt/scratch'
for workspace in sorted(copied.iterdir()):
    manifest = workspace / 'engine-0.json'
    if not manifest.exists():
        assert workspace.name == 'test_nonempty_output_directory_is_not_opened_as_runtime_state'
        continue
    manifest = read(manifest)
    assert manifest['closed'] is True and manifest['cleanupErrors'] == []
    refs, report = manifest['records'], manifest['report']
    assert report['qualificationPassed'] is False and report['independentOutcomeChecked'] is False
    assert [r['path'] for r in refs] == ['%06d.json' % i for i in range(len(refs))]
    trial = workspace / 'trial-0'
    docs = {}
    for ref in refs:
        verify(trial / 'records' / ref['path'], ref)
        assert ref['bytes'] <= 65536
        docs[ref['path']] = read(trial / 'records' / ref['path'])
    assert len(refs) <= 4096 and sum(r['bytes'] for r in refs) <= 16 * 1024 * 1024
    clock, pending, last_phase, checkpoints = 1000000, None, 0, []
    for number, ref in enumerate(refs):
        doc = docs[ref['path']]
        assert doc['profile'] == 'hms.pat.io-trial-record/0.1'
        kind, value = doc['kind'], doc['value']
        if kind == 'clock_advanced':
            assert value['from'] == clock and type(value['to']) is int and value['to'] > clock
            clock = value['to']
        elif kind == 'call_started':
            assert pending is None and value['clock'] == clock and value['phase'] == last_phase + 1
            pending = (value['phase'], value['label']); last_phase = value['phase']
        elif kind in {'call_returned', 'call_failed'}:
            assert pending == (value['phase'], value['label']) and value['clock'] == clock
            pending = None
        elif kind == 'runtime_opened':
            assert value['wallMs'] == clock
        elif kind == 'checkpoint':
            assert value['wallMs'] == value['monotonicMs'] == clock
            assert len(value['tables']) == 29
            expected = {(s, t) for s, tables in TABLES.items() for t in tables}
            assert {(t['store'], t['table']) for t in value['tables']} == expected
            for table in value['tables']:
                count, columns = 0, None
                assert len(table['pages']) == max(1, (table['rowCount'] + 7) // 8)
                for page_ref in table['pages']:
                    idx = int(page_ref['path'][:6])
                    assert idx < number and refs[idx] == page_ref
                    page = docs[page_ref['path']]
                    assert page['kind'] == 'table_page'
                    page = page['value']
                    assert page['store'] == table['store'] and page['table'] == table['table']
                    assert page['first'] == count and page['totalRows'] == table['rowCount']
                    assert len(page['rows']) == min(8, table['rowCount'] - count)
                    assert all(len(row) == len(page['columns']) for row in page['rows'])
                    for row in page['rows']:
                        for cell in row:
                            decode(cell)
                    if columns is not None:
                        assert columns == page['columns']
                    columns = page['columns']; count += len(page['rows'])
                assert count == table['rowCount']
                table_reference_count += 1
            checkpoints.append(value); checkpoint_count += 1
    assert pending is None and clock == report['clock']
    final = checkpoints[-1]
    assert final['label'] == 'test_final'
    dbs = list((trial / 'state').glob('*.db'))
    assert len(dbs) == 2
    stores = {'authority': trial / 'state/authority.db',
              'board': next(p for p in dbs if p.name.startswith('synthetic-io-board-'))}
    values = {}
    for store, database in stores.items():
        connection = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
            for table in [t for t in final['tables'] if t['store'] == store]:
                pages = [docs[r['path']]['value'] for r in table['pages']]
                columns = pages[0]['columns']
                assert all(re.fullmatch('[a-z_]+', name) for name in [table['table']] + columns)
                actual_columns = [r[1] for r in connection.execute('PRAGMA table_info(' + table['table'] + ')')]
                assert actual_columns == columns
                fields = ','.join('"' + c + '"' for c in columns)
                actual_rows = connection.execute('SELECT ' + fields + ' FROM "' + table['table'] + '" ORDER BY ' + fields).fetchall()
                captured = [tuple(decode(c) for c in row) for page in pages for row in page['rows']]
                assert actual_rows == captured, (workspace.name, store, table['table'])
                values[table['table']] = actual_rows
        finally:
            connection.close()
    observations.append({'method': workspace.name, 'records': len(refs), 'checkpoints': len(checkpoints),
        'tablesComparedToClosedDatabases': 29, 'clock': clock,
        'parentState': report['procedure']['executionState'] if report['procedure'] else None,
        'unresolvedOperations': report['unresolvedOperations'], 'heldClaims': len(values['claims']),
        'boardOwners': len(values['io_owners']), 'currentReceipts': len(values['io_receipts']),
        'receiptVersions': len(values['io_receipt_versions']), 'effectRows': values['io_effects']})

assert len(observations) == 19 and sum(r['records'] for r in observations) == 2619
lost = next(o for o in observations if o['method'] == 'test_missing_current_receipt_remains_unresolved')
assert len(lost['unresolvedOperations']) == lost['heldClaims'] == lost['boardOwners'] == 1
assert lost['currentReceipts'] == 0 and lost['receiptVersions'] == 1
assert inventory(OUT / 'attempt') == before == inventory(SOURCE)
assert inventory(raw) == scratch_rows and identity(raw) == raw_before['identity']
write('observations.json', {'scope': 'Capture consistency only; no independent qualification decision.',
    'checkpoints': checkpoint_count, 'tableReferencesChecked': table_reference_count,
    'closedDatabasesReadOnly': 38, 'finalTablesCompared': 19 * 29, 'states': observations})
write('proof.json', {'scope': 'Actual original-host trial20 tests with retained raw I/O phases.',
    'counts': result['counts'], 'testSeconds': 114.915, 'elapsedSeconds': result['elapsedSeconds'],
    'projectInputsVerified': 159, 'frozenInputsVerified': 162, 'activeHarnessInputsVerified': 6,
    'externalFilesVerified': 159, 'preparationSeals': seals,
    'originSummary': origins['summary'], 'actualOriginFileHashesRechecked': True,
    'bytecodeReadsRefused': len(origins['deniedBytecodeReads']),
    'compilerAndDriverStable': True, 'methodOrderAndLogVerified': True,
    'rawScratch': raw_before['identity'], 'rawScratchOriginalRetained': True,
    'rawAndCopiedScratchFilesVerified': len(scratch_rows), 'rawScratchBytes': 17183506,
    'attemptFilesAcquired': len(before), 'recordsVerified': 2619, 'engineStates': 19,
    'readOnlyDatabases': 38, 'finalCheckpointTablesCompared': 551,
    'independentReview': False, 'independentOutcomeChecked': False, 'qualificationPassed': False,
    'limitations': ['Selected configuration tables only; not complete live configuration attestation.',
        'Read-only comparison validates serialization, not independent effect semantics.',
        'Fault matrix orchestration, independent reducer, aggregate quota and public qualification remain unfinished.',
        'Original host simulation only; no physical device or live inference executed.',
        'No live HMS changes or extension of the historical full748 regression.']})
print(json.dumps({'attemptFiles': len(before), 'scratchFiles': len(scratch_rows),
                  'records': 2619, 'checkpoints': checkpoint_count,
                  'tableReferences': table_reference_count, 'finalTables': 551}))

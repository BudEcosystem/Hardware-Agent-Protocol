"""Independent read-only reconstruction and exact retained-scope audit."""
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PINS = {
    'implementation01': 'd53ac39d4b0051d9d8cbe4e2a332bc5c0778584be2d87cf47314ce4fcb92e9d5',
    'implementation02': 'aaec11af3df57d6ed02d8390efae851e9f74261ce573089841feebe0f7cfef37',
    'harness01': 'c47f295da703b7e3ed2cd31ef330b24ffe4acff0e0c46c0cb1dedae0b1e20124',
    'harness02': 'c52336f0ef06395007a7f568492abed3680e10e05a5223c81d44f99cbe569b5b',
    'harness03': '85b87454013a41189edd60bbf3e2c84b4b81a1b0b8b81fdbd7e13f7a0393c5aa',
}
FAILED_METHOD = 'test_evidence_vault.VaultTests.test_page_capacity_rolls_back_and_control_still_completes'

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    assert path.stat().st_size <= 16 * 1024 * 1024
    return hashlib.sha256(path.read_bytes()).hexdigest()

def digest(body):
    return 'sha256:' + hashlib.sha256(body).hexdigest()

def canonical(value):
    def check(item):
        if type(item) is dict:
            assert all(type(key) is str and key.isascii() for key in item)
            for child in item.values(): check(child)
        elif type(item) is list:
            for child in item: check(child)
        else:
            assert type(item) in (str, int, bool, type(None))
            assert type(item) is not int or abs(item) <= 2**53 - 1
            assert type(item) is not str or item.isascii()
    check(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def hashed(domain, value):
    return digest(domain + b'\0' + canonical(value))

for folder, pin in PINS.items():
    index = BASE / folder / 'index.json'
    assert sha(index) == pin
    for row in read(index)['files']:
        path = ROOT / row['path'] if folder.startswith('implementation') else index.parent / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
project1 = BASE / 'implementation01/project'
project2 = BASE / 'implementation02/project'
differences = [path.relative_to(project1).as_posix() for path in project1.rglob('*')
               if path.is_file() and sha(path) != sha(project2 / path.relative_to(project1))]
assert differences == ['tests/test_evidence_vault.py']
def methods(project):
    tree = ast.parse((project / 'tests/test_evidence_vault.py').read_bytes())
    return {cls.name + '.' + method.name: ast.dump(method, include_attributes=False)
        for cls in tree.body if isinstance(cls, ast.ClassDef) for method in cls.body
        if isinstance(method, ast.FunctionDef)}
old_methods, new_methods = methods(project1), methods(project2)
assert old_methods.keys() == new_methods.keys()
assert [key for key in old_methods if old_methods[key] != new_methods[key]] == ['VaultTests.test_page_capacity_rolls_back_and_control_still_completes']
scopes = []
passing = set()
for folder in ('harness01', 'harness02', 'harness03'):
    attempt = BASE / folder / 'attempts/attempt01'
    result = read(attempt / 'result.json')
    assert result['childState'] == 'exited' and result['inputAndExternalVerificationPassed']
    assert result['timeoutSeconds'] == 180 and result['maxSingleFileBytes'] == 16777216
    assert result['maxTotalScratchBytes'] == 268435456 and result['scratchRetained']
    assert not result['totalDiskQuotaEnforced']
    config = read(attempt / 'child-config.json')
    for row in config['expectedInputs']:
        path = attempt / 'project' / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    for row in config['expectedExternalInputs']:
        assert sha(Path(row['resolvedPath'])) == row['sha256']
    assert sha(attempt / 'original-authority.db') == 'f106c3312d0c05b69be52b5fae65edd19892b9c019bd62d6691ec3555cc93099'
    inventory = read(attempt / 'scratch-index.json')
    for row in inventory['files']:
        path = attempt / 'scratch' / row['path']
        if row['kind'] == 'retained-negative-symlink':
            assert path.is_symlink() and os.readlink(path) == row['target']
            assert hashlib.sha256(row['target'].encode()).hexdigest() == row['sha256']
        else:
            assert not path.is_symlink() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    returned = read(attempt / 'actual-tests.json')
    origins = read(attempt / 'imports.json')
    assert origins['summary']['allOriginsMatched']
    assert len(read(attempt / 'sqlite-connections.json')) <= 64
    if folder == 'harness01':
        assert result['status'] == 'failed' and result['exitCode'] == 1
        assert returned['executed'] == [] and inventory['files'] == []
        assert read(attempt / 'sqlite-connections.json') == []
        rows = []
    else:
        assert returned['loaded'] == returned['executed'] == config['targets'] and returned['exactSelection']
        rows = re.findall(r'^test_\w+ \(([^)]+)\) \.\.\. (ok|FAIL|ERROR)$', (attempt / 'output.log').read_text(), re.M)
        assert len(rows) == len(config['targets']) and [name for name, state in rows] == config['targets']
        passing.update(name for name, state in rows if state == 'ok')
        expected_failures = [FAILED_METHOD] if folder == 'harness02' else []
        assert [name for name, state in rows if state != 'ok'] == expected_failures
        assert result['status'] == ('failed' if expected_failures else 'passed')
        assert read(attempt / 'child-errors.json') == []
        assert read(attempt / 'compiler-before.json') == read(attempt / 'compiler-after.json')
        assert read(attempt / 'driver-before.json') == read(attempt / 'driver-after.json')
    scopes.append(dict(harness=folder, status=result['status'], counts=result['counts'],
                       completedMethodReceipts=rows, scratchBytes=result['scratchBytes']))
assert passing == set(read(BASE / 'harness02/targets.json')) and len(passing) == 22

actual_root = BASE / 'harness02/attempts/attempt01'
corrected_root = BASE / 'harness03/attempts/attempt01'
actual_vault = actual_root / 'scratch/test_complete_retained_original_evidence_bytes/bulk/evidence.db'
fixture = actual_root / 'original-authority.db'
failed_control = actual_root / 'scratch/test_page_capacity_rolls_back_and_control_still_completes/authority.db'
corrected_control = corrected_root / 'scratch/test_page_capacity_rolls_back_and_control_still_completes/authority.db'
corrected_vault = corrected_control.parent / 'bulk/evidence.db'
paths = [fixture, actual_vault, failed_control, corrected_control, corrected_vault]
allowed = {path.as_uri() + '?mode=ro&immutable=1' for path in paths}
connections = []
def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system', 'os.fork', 'os.exec', 'os.posix_spawn'):
        raise RuntimeError('External execution/network veto')
    if event == 'sqlite3.connect':
        assert args[0] in allowed and args[0] not in connections
        connections.append(args[0])
sys.addaudithook(audit)
held = []
locks = []
try:
    for path in paths:
        assert not path.is_symlink() and not any(os.path.lexists(str(path) + suffix) for suffix in ('-journal', '-wal', '-shm'))
        if path == fixture:
            continue
        lock = Path(str(path) + '.owner')
        fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        held.append(fd)
        info = os.fstat(fd)
        assert stat.S_ISREG(info.st_mode) and info.st_size == 0 and info.st_uid == os.getuid() and info.st_nlink == 1
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(dict(path=str(lock.relative_to(BASE)), device=str(info.st_dev), inode=str(info.st_ino)))
    before = {str(path): sha(path) for path in paths}
    data = {}
    for path in (fixture, actual_vault):
        db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            old = path == fixture
            prefix = 'ioec' if old else 'ev'
            refs = db.execute('SELECT path,digest FROM ' + prefix + '_documents WHERE sequence=1 LIMIT 4012').fetchall()
            assert len(refs) == 4011 and len(dict(refs)) == 4011
            checks = db.execute('SELECT typeof(digest),length(CAST(digest AS BLOB)),typeof(body),length(body) FROM '
                                + prefix + '_bodies LIMIT 2799').fetchall()
            assert len(checks) == 2798 and all(a == 'text' and b == 71 and c == 'blob' and 0 <= d <= 16777216 for a,b,c,d in checks)
            assert sum(row[3] for row in checks) == 13638563
            bodies = dict(db.execute('SELECT digest,body FROM ' + prefix + '_bodies LIMIT 2799'))
            assert len(bodies) == 2798 and all(digest(body) == key for key, body in bodies.items())
            assert {key for name, key in refs} == set(bodies)
            data['original' if old else 'vault'] = dict(refs=dict(refs), bodies=bodies)
            if old:
                receipt_wire = db.execute('SELECT receipt FROM ioec_runs WHERE sequence=1').fetchone()[0]
                receipt = json.loads(receipt_wire)
            else:
                meta_wire = db.execute('SELECT record FROM ev_meta WHERE singleton=1').fetchone()[0]
                meta = json.loads(meta_wire)
                assert canonical(meta) == meta_wire and meta['authorityId'] == '1' * 32
                records = db.execute('SELECT sequence,intent,binding,record FROM ev_manifests LIMIT 2').fetchall()
                assert len(records) == 1
                sequence, intent, binding, wire = records[0]
                manifest = json.loads(wire)
                assert canonical(manifest) == wire and sequence == manifest['sequence'] == 1
                assert manifest['intentDigest'] == intent and manifest['bindingDigest'] == binding
                assert manifest['scope'] == 'immutable-bytes-only' and manifest['previousManifestDigest'] is None
                assert manifest['storeId'] == meta['storeId'] and manifest['authorityId'] == meta['authorityId']
                assert db.execute('PRAGMA page_size').fetchone()[0] == meta['pageSize'] == 1024
                assert db.execute('PRAGMA page_count').fetchone()[0] * 1024 == actual_vault.stat().st_size <= meta['maxPages'] * 1024 == 15728640
        finally:
            db.close()
    assert data['original'] == data['vault']
    assert intent == digest(receipt_wire) and binding == digest(canonical(receipt['anchor']))
    chain = hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0')
    expanded = 0
    for name, key in sorted(data['vault']['refs'].items()):
        size = len(data['vault']['bodies'][key]); expanded += size
        chain.update(canonical(dict(path=name, bytes=size, sha256=key)) + b'\n')
    closure = dict(documents=4011, bytes=expanded, digest='sha256:' + chain.hexdigest())
    assert closure == manifest['closure'] == receipt['closure'] and expanded == 15355663
    sources = []
    for name in ('__init__.py', 'contracts.py', 'connection.py', 'store.py'):
        path = project1 / 'evidence_vault' / name
        assert sha(path) == sha(project2 / 'evidence_vault' / name)
        sources.append(dict(path='evidence_vault/' + name, bytes=path.stat().st_size, sha256=sha(path)))
    computed_identity = hashed(b'HMS-PAT-EVIDENCE-VAULT-IMPLEMENTATION-v0.1', dict(
        legacyIdentity='sha256:107d9e5eee100fdf1c102cb1a0e7bb865259eb2eab91d6db068643c11e600709', sources=sources))
    assert meta['implementationDigest'] == computed_identity
    controls = []
    for path, expected_claims in ((failed_control, 1), (corrected_control, 0)):
        db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            operations = db.execute('SELECT id,state,may_have_acted FROM operations LIMIT 2').fetchall()
            assert len(operations) == 1 and operations[0][1:] == ('completed', 1)
            claims = db.execute('SELECT count(*) FROM claims').fetchone()[0]
            assert claims == expected_claims and db.execute('SELECT count(*) FROM replay_keys').fetchone()[0] == 1
            events = db.execute('SELECT sequence,kind,payload FROM events ORDER BY sequence LIMIT 6').fetchall()
            assert [row[1] for row in events] == ['accepted', 'dispatch_claimed', 'execution_evidence'] + ([] if expected_claims else ['resources_released'])
            completion = json.loads(events[2][2])
            assert completion['evidence']['kind'] == 'simulation' and completion['evidence']['assertions'] == ['completed']
            if not expected_claims:
                released = json.loads(events[3][2])
                assert released['evidence']['kind'] == 'simulation' and released['evidence']['assertions'] == ['resources_quiescent']
            controls.append(dict(path=str(path.relative_to(BASE)), state='completed', claims=claims, events=[row[1] for row in events]))
        finally:
            db.close()
    db = sqlite3.connect(corrected_vault.as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        assert db.execute('SELECT count(*) FROM ev_manifests').fetchone()[0] == 1
        assert db.execute('SELECT body FROM ev_bodies').fetchall() == [(b'original',)]
        assert corrected_vault.stat().st_size <= 32768
    finally:
        db.close()
    assert {str(path): sha(path) for path in paths} == before
    result = dict(scope='Immutable byte-vault component only; no authority publication or PAT qualification',
        distinctMethodsWithPassingReceipts=22, originalFullScopePassed=False, correctedMethodScopePassed=True,
        startupFailuresRetained=1, fullScopeTestFailuresRetained=1, productionIdenticalAcrossSelections=True,
        scopes=scopes, sourcePins=PINS, originalProjectFilesUnchanged=275,
        originalAndStoredReferences=4011, uniqueBodies=2798, uniqueBodyBytes=13638563,
        expandedBytes=expanded, allOriginalAndStoredBytesMatched=True,
        actualVaultBytes=actual_vault.stat().st_size, maximumVaultBytes=15728640,
        headroomBytes=15728640-actual_vault.stat().st_size, vaultImplementationDigest=computed_identity,
        manifestDigest=hashed(b'HMS-PAT-EVIDENCE-VAULT-MANIFEST-v0.1', manifest),
        vaultAuthorityIsExplicitTestFixture=True, originalAuthorityAssociationQualified=False,
        readOnlyAuditDatabases=len(paths), unchangedDatabaseHashes=before, ownerLocksHeld=locks,
        controlHistories=controls, failedClaimRemainsHeld=True, correctedControlQuiescenceVerified=True,
        sourceAndInputBytesUnchanged=True, noNewWorkerExecution=True, noPhysicalEffects=True,
        aggregateQuotaEnforced=False, physicalCapacityReserved=False, authorityPublicationImplemented=False,
        publicMountingImplemented=False, goalStatus='active')
    with (BASE / 'RESULTS.json').open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key:value for key,value in result.items() if key not in ('scopes', 'sourcePins', 'unchangedDatabaseHashes', 'ownerLocksHeld', 'controlHistories')}))
finally:
    for fd in reversed(held):
        os.close(fd)

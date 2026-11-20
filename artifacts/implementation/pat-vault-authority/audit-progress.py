"""Audit achieved scopes and explicit remaining work; no project imports or writes to state."""
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PINS = {'implementation01': 'cc5d2f6b337645f2483b94e46e9559ead5f6c905bd8b92231c67138dd5f1c6ce',
        'implementation02': '5d605fa018c9b7673260707cb5cffe630b99a70072e29c16879dd64de4bb975e'}
VAULT_ID = 'sha256:a7b12404007cfabb919c5eee9c3db3d3b33c39d6322c7d37e82e1020100910b5'

def read(path): return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.stat().st_size <= 16 * 1024 * 1024
    return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
def digest(domain, value): return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()
def document(body):
    assert type(body) is bytes and len(body) <= 16384
    value = json.loads(body); assert canonical(value) == body
    return value
def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')

project_hashes = {}; consumers = {}
for name, expected in PINS.copy().items():
    folder = BASE / name; assert sha(folder / 'index.json') == expected
    project_hashes[name] = {}
    for row in read(folder / 'index.json')['files']:
        path = ROOT / row['path']; assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
        if path.is_relative_to(folder / 'project'):
            project_hashes[name][path.relative_to(folder / 'project').as_posix()] = row['sha256']
    assert len(project_hashes[name]) == 284
    inherited = read(folder / 'baseline-inputs.json')['files']; assert len(inherited) == 280
    assert all(project_hashes[name][row['path']] == row['sha256'] for row in inherited)
    rows = []
    for filename in ('__init__.py', 'contracts.py', 'store.py'):
        path = folder / 'project/evidence_authority' / filename
        rows.append(dict(path='evidence_authority/' + filename, bytes=path.stat().st_size, sha256=sha(path)))
    consumers[name] = digest(b'HMS-PAT-VAULT-IMPORT-IMPLEMENTATION-v0.1', dict(vaultIdentity=VAULT_ID, sources=rows))
assert {name for name in project_hashes['implementation01'] if
        project_hashes['implementation01'][name] != project_hashes['implementation02'][name]} == {
            'evidence_authority/store.py', 'tests/test_vault_authority.py'}
methods = {}
for name in ('implementation01', 'implementation02'):
    tree = ast.parse((BASE / name / 'project/tests/test_vault_authority.py').read_bytes())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    methods[name] = {node.name: ast.dump(node) for node in cls.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')}
assert len(methods['implementation01']) == 19 and len(methods['implementation02']) == 20
assert all(methods['implementation02'][name] == body for name, body in methods['implementation01'].items())
attempts = {}; unexecuted = []
for folder in sorted(BASE.glob('harness[0-9][0-9]')):
    PINS[folder.name] = sha(folder / 'index.json')
    for row in read(folder / 'index.json')['files']:
        path = folder / row['path']; assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    attempt = folder / 'attempts/attempt01'
    if not attempt.exists(): unexecuted.append(folder.name); continue
    result = read(attempt / 'result.json'); assert result['childState'] == 'exited' and result['scratchRetained']
    source = 'implementation02' if folder.name in ('harness18', 'harness19') else 'implementation01'
    assert result['sourceIndexSha256'] == PINS[source] and result['harnessIndexSha256'] == PINS[folder.name]
    assert result['inputAndExternalVerificationPassed'] and result['timeoutSeconds'] == 180
    assert result['maxSingleFileBytes'] == 16 * 1024 * 1024 and result['maxTotalScratchBytes'] == 256 * 1024 * 1024
    config = read(attempt / 'child-config.json'); assert len(config['expectedInputs']) == 284
    for row in config['expectedInputs']:
        path = attempt / 'project' / row['path']; assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    for row in config['expectedExternalInputs']:
        path = Path(row['resolvedPath']); assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    inventory = read(attempt / 'scratch-index.json'); raw = Path(inventory.get('rawPath', attempt / 'scratch'))
    for row in inventory['files']:
        assert row['kind'] == 'file'
        for path in (raw / row['path'], attempt / 'scratch' / row['path']):
            assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    assert sum(row['bytes'] for row in inventory['files']) == inventory['bytes'] == result['scratchBytes']
    if result['counts'] is not None:
        actual = read(attempt / 'actual-tests.json'); targets = read(folder / 'targets.json')
        assert actual['loaded'] == actual['executed'] == targets and actual['exactSelection']
        origins = read(attempt / 'imports.json')
        assert origins['summary']['allOriginsMatched'] and not origins['violations'] and not origins['prohibitedAttempts']
        assert read(attempt / 'child-errors.json') == []
        assert len(read(attempt / 'sqlite-connections.json')) <= 64
    if result['status'] == 'passed':
        assert result['exitCode'] == 0 and result['counts']['testsRun'] == len(read(folder / 'targets.json'))
        assert all(value == 0 for key, value in result['counts'].items() if key != 'testsRun')
        assert read(attempt / 'compiler-before.json') == read(attempt / 'compiler-after.json')
        assert read(attempt / 'driver-before.json') == read(attempt / 'driver-after.json')
    attempts[folder.name] = dict(path=attempt, raw=raw, result=result, source=source)
failed = [name for name, value in attempts.items() if value['result']['status'] == 'failed']
assert failed == ['harness01', 'harness03', 'harness05', 'harness07', 'harness13']
assert unexecuted == ['harness02', 'harness04', 'harness06', 'harness14', 'harness15', 'harness16', 'harness17']
assert attempts['harness05']['result']['exitCode'] == -9 and attempts['harness05']['result']['counts'] is None
assert attempts['harness07']['result']['counts']['errors'] == 1
assert attempts['harness13']['result']['counts']['failures'] == 1
assert 'test_original_attempt_change_after_seal_prevents_publication) ... ok' in (attempts['harness13']['path'] / 'output.log').read_text()
previous_passes = [target for n in range(8, 13) for target in read(BASE / ('harness%02d' % n) / 'targets.json')]
previous_passes.append('test_vault_authority.VaultAuthorityTests.test_original_attempt_change_after_seal_prevents_publication')
assert len(previous_passes) == len(set(previous_passes)) == 11
current_passes = [target for n in (18, 19) for target in read(BASE / ('harness%02d' % n) / 'targets.json')]
assert len(current_passes) == len(set(current_passes)) == 3
assert all(attempts['harness%02d' % n]['result']['status'] == 'passed' for n in (18, 19))
pending = ['test_vault_authority.VaultAuthorityTests.' + name for name in methods['implementation02']
           if 'test_vault_authority.VaultAuthorityTests.' + name not in current_passes]
assert len(pending) == 17

# Independent database audit: a complete original-source publication, the retained
# specific-error failure, and all corrected-source controls. No partial SIGKILL
# database is opened or recovered by this audit.
cases = [('harness08', 'test_publication_and_cold_replay_preserve_original_receipt', (1, 1, 1)),
    ('harness13', 'test_configuration_change_after_seal_prevents_publication', (1, 0, 1)),
    ('harness18', 'test_configuration_change_after_seal_prevents_publication', (1, 0, 1)),
    ('harness18', 'test_revocation_after_seal_preserves_authority_refusal', (1, 0, 1)),
    ('harness19', 'test_expired_snapshot_before_commit_rolls_back_publication', (1, 0, 1))]
audited = []; hashes = {}; lock_count = 0
for scope, method, counts in cases:
    info = attempts[scope]; root = info['raw'] / method; owners = []; dbs = []
    paths = [root / 'runtime/authority.db', root / 'vault/evidence.db', root / 'supervisor/attempts.db']
    before = {str(path): sha(path) for path in paths}
    try:
        for path in sorted(root.rglob('*.owner')):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); owners.append(fd); lock_count += 1
        assert len(owners) == 4
        for path in paths:
            assert not any(os.path.lexists(str(path) + suffix) for suffix in ('-journal', '-wal', '-shm'))
            db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, isolation_level=None)
            db.execute('PRAGMA query_only=ON'); dbs.append(db)
        authority, vault, supervisor = dbs
        meta = document(authority.execute('SELECT record FROM evi_meta').fetchone()[0])
        assert meta['authorityId'] == authority.execute("SELECT value FROM meta WHERE key='authority'").fetchone()[0]
        assert meta['consumerIdentity'] == consumers[info['source']] and meta['vault']['authorityId'] == meta['authorityId']
        assert meta['vault']['implementationDigest'] == VAULT_ID and meta['intentCharge'] == 33792
        assert authority.execute("SELECT value FROM reg_meta WHERE key='vault_evidence_import'").fetchone()[0] == 'hms.pat.vault-import/0.1|' + digest(b'HMS-PAT-VAULT-IMPORT-MOUNT-v0.1', meta)
        assert document(vault.execute('SELECT record FROM ev_meta').fetchone()[0]) == meta['vault']
        intents = authority.execute('SELECT intent,record FROM evi_intents').fetchall()
        pubs = authority.execute('SELECT intent,record FROM evi_publications').fetchall()
        manifests = vault.execute('SELECT intent,binding,record FROM ev_manifests').fetchall()
        assert tuple(map(len, (intents, pubs, manifests))) == counts
        assert supervisor.execute('SELECT count(*) FROM qs_attempts').fetchone()[0] == 1
        assert authority.execute('SELECT count(*) FROM operations').fetchone()[0] == 0
        assert authority.execute('SELECT count(*) FROM claims').fetchone()[0] == 0
        key, body = intents[0]; intent = document(body)
        assert key == digest(b'HMS-PAT-VAULT-IMPORT-INTENT-v0.1', intent)
        assert intent['consumerIdentity'] == consumers[info['source']] and intent['previousIntentDigest'] is None
        anchor = intent['anchor']; assert anchor['authorityId'] == meta['authorityId']
        assert intent['bindingDigest'] == digest(b'HMS-PAT-VAULT-ORIGINAL-BINDING-v0.1', anchor)
        reservation = document(authority.execute('SELECT receipt FROM iosr_runs').fetchone()[0])
        handoff = document(authority.execute('SELECT receipt FROM iose_handoffs').fetchone()[0])
        assert anchor['attemptId'] == handoff['attemptId']
        assert anchor['requestDigest'] == reservation['requestDigest'] == handoff['requestDigest']
        assert anchor['configurationReceiptDigest'] == reservation['configurationReceiptDigest']
        manifest_key, binding, body = manifests[0]; manifest = document(body)
        assert manifest_key == key and binding == intent['bindingDigest'] and manifest['scope'] == 'immutable-bytes-only'
        assert manifest['storeId'] == intent['storeId'] == meta['vault']['storeId']
        objects = dict(vault.execute('SELECT digest,body FROM ev_bodies'))
        assert all(key == 'sha256:' + hashlib.sha256(body).hexdigest() for key, body in objects.items())
        refs = vault.execute('SELECT path,digest FROM ev_documents ORDER BY path').fetchall()
        chain = hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0'); size = 0
        for path, key in refs:
            body = objects[key]; size += len(body)
            chain.update(canonical(dict(path=path, bytes=len(body), sha256=key)) + b'\n')
        assert manifest['closure'] == dict(documents=len(refs), bytes=size, digest='sha256:' + chain.hexdigest())
        evaluation = document(objects[dict(refs)['evaluation.json']])
        assert evaluation['anchor'] == anchor and evaluation['consumerIdentity'] == consumers[info['source']]
        assert all(evaluation[field] is False for field in ('physicalObjectiveVerified', 'wallDeadlineAttested', 'aggregateDiskQuotaEnforced', 'catalogActivated'))
        if pubs:
            pub_key, body = pubs[0]; publication = document(body)
            assert pub_key == intents[0][0] == publication['intentDigest']
            assert publication['manifestDigest'] == digest(b'HMS-PAT-EVIDENCE-VAULT-MANIFEST-v0.1', manifest)
            assert publication['closure'] == manifest['closure'] and publication['evaluationDigest'] == dict(refs)['evaluation.json']
        assert len(canonical(meta)) + 1024 + len(intents) * 33792 <= meta['maxControlBytes']
        audited.append(dict(scope=scope, method=method, source=info['source'], intents=counts[0],
            publications=counts[1], manifests=counts[2], authorityId=meta['authorityId'], storeId=meta['vault']['storeId'],
            references=len(refs), objects=len(objects), exactBytesVerified=True, physicalOrActualMatrixQualification=False))
    finally:
        for db in reversed(dbs): db.close()
        for fd in reversed(owners): os.close(fd)
    after = {str(path): sha(path) for path in paths}; assert before == after; hashes.update(after)

output = dict(status='progress-verified-incomplete', sourcePins=PINS, consumers=consumers,
    inheritedFilesUnchanged=280, originalSourcePassingMethods=previous_passes,
    currentSourcePassingMethods=current_passes, currentSourceRemainingMethods=pending,
    originalAggregatePassed=False, currentFullSelectionPassed=False, failedScopesRetained=failed,
    preparedUnexecutedScopes=unexecuted, readonlyDatabaseCount=len(hashes), ownerLocks=lock_count,
    unchangedDatabaseHashes=hashes, databaseAudits=audited,
    originalFailedConfigurationFixtureStillUnpublished=True,
    actualOriginalRunProfileVerified=False, catalogIntegrated=False, physicalCapacityReserved=False,
    publicMounted=False, noWorkerExecuted=True, physicalEffects=False, goalStatus='active')
write(BASE / 'PROGRESS-RESULTS.json', output)
write(BASE / 'pending-methods.json', dict(source='implementation02', methods=pending,
    instruction='Verify the complete remaining current-source selection in fresh bounded scopes; do not run superseded source01 harness14-17'))
print(json.dumps(dict(status=output['status'], previousSourcePasses=11, currentSourcePasses=3,
    currentSourcePending=17, readonlyDatabases=len(hashes), ownerLocks=lock_count, goalStatus='active')))

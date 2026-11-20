"""Independent read-only audit of selected controls; imports no project modules."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE / 'implementation01'
SOURCE_PIN = 'cc5d2f6b337645f2483b94e46e9559ead5f6c905bd8b92231c67138dd5f1c6ce'
VAULT_IDENTITY = 'sha256:a7b12404007cfabb919c5eee9c3db3d3b33c39d6322c7d37e82e1020100910b5'
MAX_FILE = 16 * 1024 * 1024

def read(path): return json.loads(path.read_bytes())

def raw_sha(body): return hashlib.sha256(body).hexdigest()

def sha(path):
    assert not path.is_symlink() and path.stat().st_size <= MAX_FILE
    return raw_sha(path.read_bytes())

def canonical(value):
    # Audited metadata contains ASCII property names, integral numbers, booleans,
    # null and UTF-8 strings; no floating-point JCS formatting is needed here.
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()

def digest(domain, value): return 'sha256:' + raw_sha(domain + b'\0' + canonical(value))

def document(body):
    assert type(body) is bytes and len(body) <= 16384
    value = json.loads(body); assert canonical(value) == body
    return value

assert sha(SOURCE / 'index.json') == SOURCE_PIN
source_files = read(SOURCE / 'index.json')['files']
for row in source_files:
    path = ROOT / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
inherited = read(SOURCE / 'baseline-inputs.json')['files']; assert len(inherited) == 280
for row in inherited:
    path = SOURCE / 'project' / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
new_sources = []
for name in ('__init__.py', 'contracts.py', 'store.py'):
    path = SOURCE / 'project/evidence_authority' / name
    new_sources.append(dict(path='evidence_authority/' + name, bytes=path.stat().st_size, sha256=sha(path)))
consumer_identity = digest(b'HMS-PAT-VAULT-IMPORT-IMPLEMENTATION-v0.1',
    dict(vaultIdentity=VAULT_IDENTITY, sources=new_sources))
source_pins = {'implementation01': SOURCE_PIN}
for folder in sorted(BASE.glob('harness[0-9][0-9]')):
    source_pins[folder.name] = sha(folder / 'index.json')
    for row in read(folder / 'index.json')['files']:
        path = folder / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']

attempts = {}
for folder in sorted(BASE.glob('harness[0-9][0-9]')):
    attempt = folder / 'attempts/attempt01'
    if not attempt.exists(): continue
    result = read(attempt / 'result.json'); assert result['childState'] == 'exited'
    assert result['sourceIndexSha256'] == SOURCE_PIN and result['harnessIndexSha256'] == source_pins[folder.name]
    assert result['inputAndExternalVerificationPassed'] and result['scratchRetained']
    assert result['timeoutSeconds'] == 180 and result['maxSingleFileBytes'] == MAX_FILE
    assert result['maxTotalScratchBytes'] == 256 * 1024 * 1024
    config = read(attempt / 'child-config.json')
    assert len(config['expectedInputs']) == 284
    for row in config['expectedInputs']:
        path = attempt / 'project' / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    for row in config['expectedExternalInputs']:
        path = Path(row['resolvedPath'])
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    inventory = read(attempt / 'scratch-index.json')
    raw = Path(inventory.get('rawPath', attempt / 'scratch'))
    for row in inventory['files']:
        assert row['kind'] == 'file'
        for path in (raw / row['path'], attempt / 'scratch' / row['path']):
            assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    assert sum(row['bytes'] for row in inventory['files']) == inventory['bytes'] == result['scratchBytes']
    attempts[folder.name] = dict(result=result, config=config, raw=raw, attempt=attempt)
for name in ('harness01', 'harness03', 'harness05', 'harness07'):
    assert attempts[name]['result']['status'] == 'failed'
assert attempts['harness05']['result']['exitCode'] == -9
assert attempts['harness05']['result']['counts'] is None and attempts['harness05']['result']['origins'] is None
assert attempts['harness07']['result']['counts']['errors'] == 1
assert 'PAT_EVIDENCE_VAULT_SNAPSHOT_UNAVAILABLE' in (attempts['harness07']['attempt'] / 'output.log').read_text()
assert all(name not in attempts for name in ('harness02', 'harness04', 'harness06'))
selection = read(BASE / 'control-selections.json')
completed = []
for scope in selection['scopes']:
    info = attempts[scope['harness']]; result = info['result']; count = len(scope['targets'])
    assert result['status'] == 'passed' and result['exitCode'] == 0
    assert result['counts']['testsRun'] == count
    assert all(value == 0 for key, value in result['counts'].items() if key != 'testsRun')
    actual = read(info['attempt'] / 'actual-tests.json')
    assert actual['exactSelection'] and actual['loaded'] == actual['executed'] == scope['targets']
    origins = read(info['attempt'] / 'imports.json')
    assert origins['summary']['allOriginsMatched'] and not origins['violations'] and not origins['prohibitedAttempts']
    assert read(info['attempt'] / 'child-errors.json') == []
    assert len(read(info['attempt'] / 'sqlite-connections.json')) <= 64
    assert read(info['attempt'] / 'compiler-before.json') == read(info['attempt'] / 'compiler-after.json')
    assert read(info['attempt'] / 'driver-before.json') == read(info['attempt'] / 'driver-after.json')
    completed.extend((target, info) for target in scope['targets'])
assert [target for target, _ in completed] == selection['originalMethods'] and len(completed) == 19

expected = {
    'test_mount_requires_real_authority_and_admin_and_exact_vault': (0, 0, 0, 0),
    'test_publication_and_cold_replay_preserve_original_receipt': (1, 1, 1, 1),
    'test_transport_success_does_not_publish_without_semantic_success': (1, 0, 0, 1),
    'test_before_intent_commit_rolls_back_without_evidence': (0, 0, 0, 1),
    'test_after_intent_commit_resumes_same_intent': (1, 1, 1, 1),
    'test_after_seal_resumes_without_original_archive_or_new_worker': (1, 1, 1, 1),
    'test_before_publication_commit_keeps_unpublished_manifest': (1, 0, 1, 1),
    'test_lost_publication_reply_reconciles_exact_receipt': (1, 1, 1, 1),
    'test_expired_snapshot_before_commit_rolls_back_publication': (1, 0, 1, 1),
    'test_revocation_after_inspection_keeps_intent_unpublished': (1, 0, 0, 1),
    'test_configuration_change_after_seal_prevents_publication': (1, 0, 1, 1),
    'test_original_attempt_change_after_seal_prevents_publication': (1, 0, 1, 1),
    'test_corrupt_published_body_is_refused_without_repair': (1, 1, 1, 1),
    'test_unavailable_vault_does_not_become_novelty_or_replacement': (1, 1, 1, 1),
    'test_intent_capacity_refuses_second_run_before_archive_read': (1, 1, 1, 2),
    'test_supervisor_source_and_archive_reads_stay_outside_control_transaction': (1, 1, 1, 1),
    'test_temporary_shadow_refuses': (1, 1, 1, 1),
    'test_no_paths_callbacks_or_transaction_reentry': (0, 0, 0, 1),
    'test_bulk_full_keeps_original_intent_and_no_publication': (1, 0, 0, 1),
}
audited = []; hashes = {}; owner_count = 0
for target, info in completed:
    name = target.split('.')[-1]; root = info['raw'] / name
    owners = []
    dbs = []
    paths = [root / 'runtime/authority.db', root / 'vault/evidence.db', root / 'supervisor/attempts.db']
    before = {str(path): sha(path) for path in paths}
    try:
        for path in sorted(root.rglob('*.owner')):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); owners.append(fd); owner_count += 1
        assert len(owners) >= 4
        for path in paths:
            assert not any(os.path.lexists(str(path) + suffix) for suffix in ('-journal', '-wal', '-shm'))
            db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, isolation_level=None)
            db.execute('PRAGMA query_only=ON'); dbs.append(db)
        authority, vault, supervisor = dbs
        meta = document(authority.execute('SELECT record FROM evi_meta').fetchone()[0])
        assert meta['authorityId'] == authority.execute("SELECT value FROM meta WHERE key='authority'").fetchone()[0]
        assert meta['consumerIdentity'] == consumer_identity and meta['vault']['authorityId'] == meta['authorityId']
        assert meta['vault']['implementationDigest'] == VAULT_IDENTITY and meta['intentCharge'] == 33792
        assert authority.execute("SELECT value FROM reg_meta WHERE key='vault_evidence_import'").fetchone()[0] == 'hms.pat.vault-import/0.1|' + digest(b'HMS-PAT-VAULT-IMPORT-MOUNT-v0.1', meta)
        assert document(vault.execute('SELECT record FROM ev_meta').fetchone()[0]) == meta['vault']
        intents = authority.execute('SELECT sequence,evaluator,run,intent,record FROM evi_intents ORDER BY sequence').fetchall()
        pubs = authority.execute('SELECT sequence,intent,record FROM evi_publications ORDER BY sequence').fetchall()
        manifests = vault.execute('SELECT sequence,intent,binding,record FROM ev_manifests ORDER BY sequence').fetchall()
        attempts_count = supervisor.execute('SELECT count(*) FROM qs_attempts').fetchone()[0]
        assert (len(intents), len(pubs), len(manifests), attempts_count) == expected[name]
        assert authority.execute('SELECT count(*) FROM operations').fetchone()[0] == 0
        assert authority.execute('SELECT count(*) FROM claims').fetchone()[0] == 0
        known_intents = {}; prior = None
        for sequence, evaluator, run, key, body in intents:
            value = document(body)
            assert sequence == value['sequence'] and key == digest(b'HMS-PAT-VAULT-IMPORT-INTENT-v0.1', value)
            assert value['previousIntentDigest'] == prior and value['storeId'] == meta['vault']['storeId']
            assert value['consumerIdentity'] == consumer_identity
            anchor = value['anchor']; assert (evaluator, run) == (anchor['evaluatorId'], anchor['runId'])
            assert anchor['authorityId'] == meta['authorityId'] and value['bindingDigest'] == digest(b'HMS-PAT-VAULT-ORIGINAL-BINDING-v0.1', anchor)
            reservation = document(authority.execute('SELECT receipt FROM iosr_runs WHERE evaluator=? AND run=?', (evaluator, run)).fetchone()[0])
            handoff = document(authority.execute('SELECT receipt FROM iose_handoffs WHERE evaluator=? AND run=?', (evaluator, run)).fetchone()[0])
            assert anchor['attemptId'] == handoff['attemptId'] and anchor['requestDigest'] == reservation['requestDigest'] == handoff['requestDigest']
            assert anchor['configurationReceiptDigest'] == reservation['configurationReceiptDigest']
            known_intents[key] = value; prior = key
        objects = dict(vault.execute('SELECT digest,body FROM ev_bodies'))
        invalid = [key for key, body in objects.items() if key != 'sha256:' + raw_sha(body)]
        assert len(invalid) == (1 if name == 'test_corrupt_published_body_is_refused_without_repair' else 0)
        known_manifests = {}; prior = None
        for sequence, intent_key, binding, body in manifests:
            value = document(body)
            assert intent_key in known_intents and binding == known_intents[intent_key]['bindingDigest']
            assert value['sequence'] == sequence and value['intentDigest'] == intent_key and value['bindingDigest'] == binding
            assert value['previousManifestDigest'] == prior and value['scope'] == 'immutable-bytes-only'
            refs = vault.execute('SELECT path,digest FROM ev_documents WHERE sequence=? ORDER BY path', (sequence,)).fetchall()
            if not invalid:
                chain = hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0'); total = 0
                for path, key in refs:
                    raw = objects[key]; total += len(raw)
                    chain.update(canonical(dict(path=path, bytes=len(raw), sha256=key)) + b'\n')
                assert value['closure'] == dict(documents=len(refs), bytes=total, digest='sha256:' + chain.hexdigest())
            prior = digest(b'HMS-PAT-EVIDENCE-VAULT-MANIFEST-v0.1', value)
            known_manifests[intent_key] = (value, prior, dict(refs))
        prior = None
        for sequence, key, body in pubs:
            value = document(body); manifest, manifest_digest, refs = known_manifests[key]
            assert value['sequence'] == sequence and value['intentDigest'] == key
            assert value['previousPublicationDigest'] == prior and value['manifestDigest'] == manifest_digest
            assert value['closure'] == manifest['closure'] and value['evaluationDigest'] == refs['evaluation.json']
            evaluation = document(objects[refs['evaluation.json']])
            assert evaluation['anchor'] == known_intents[key]['anchor'] and evaluation['consumerIdentity'] == consumer_identity
            assert all(evaluation[field] is False for field in ('physicalObjectiveVerified', 'wallDeadlineAttested', 'aggregateDiskQuotaEnforced', 'catalogActivated'))
            prior = digest(b'HMS-PAT-VAULT-PUBLICATION-v0.1', value)
        assert len(canonical(meta)) + 1024 + len(intents) * 33792 <= meta['maxControlBytes']
        assert vault.execute('PRAGMA page_count').fetchone()[0] <= meta['vault']['maxPages']
        audited.append(dict(method=target, intents=len(intents), publications=len(pubs), manifests=len(manifests),
            originalAttempts=attempts_count, intentionallyInvalidBodies=len(invalid), authorityId=meta['authorityId'],
            storeId=meta['vault']['storeId'], authorityBytes=paths[0].stat().st_size, vaultBytes=paths[1].stat().st_size))
    finally:
        for db in reversed(dbs): db.close()
        for fd in reversed(owners): os.close(fd)
    after = {str(path): sha(path) for path in paths}; assert before == after; hashes.update(after)

output = dict(scope='Authority publication controls only; substituted semantic oracle, no actual worker or physical qualification',
    status='passed', sourcePins=source_pins, inheritedFilesUnchanged=280, projectFiles=284,
    distinctMethodsWithPassingReceipts=19, disjointPassingScopes=10, originalAggregatePassed=False,
    failedScopesRetained=['harness01', 'harness03', 'harness05', 'harness07'],
    preparedUnexecutedScopes=['harness02', 'harness04', 'harness06'], consumerIdentity=consumer_identity,
    readonlyDatabaseCount=len(hashes), ownerLocks=owner_count, databaseHashes=hashes, controls=audited,
    actualOriginalDataProfileVerified=False, catalogIntegrationImplemented=False,
    physicalCapacityReserved=False, publicProfileMounted=False, goalStatus='active')
with (BASE / 'RESULTS.json').open('x') as stream:
    json.dump(output, stream, indent=2); stream.write('\n')
print(json.dumps({key: output[key] for key in ('status', 'distinctMethodsWithPassingReceipts',
    'disjointPassingScopes', 'originalAggregatePassed', 'readonlyDatabaseCount', 'ownerLocks', 'consumerIdentity', 'goalStatus')}))

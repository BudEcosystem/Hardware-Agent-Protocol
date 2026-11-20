"""Independent receipt and retained-copy audit; no project imports or state repair."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PRIOR = ROOT / 'artifacts/implementation/pat-vault-authority'
SOURCE_PIN = '38925326d56fca55353eb5e505e2c740426d2d508257fce81984aa085db54eca'
PRIOR_PIN = '5d605fa018c9b7673260707cb5cffe630b99a70072e29c16879dd64de4bb975e'
CONSUMER = 'sha256:0e7ff6440fdb93e941ff4b5b0f2f275558f67f1e63a3c719c66756f81b7971d5'
VAULT = 'sha256:a7b12404007cfabb919c5eee9c3db3d3b33c39d6322c7d37e82e1020100910b5'

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
def verify_index(folder, prefix, pin):
    assert sha(folder / 'index.json') == pin
    for row in read(folder / 'index.json')['files']:
        path = prefix / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']

selection = read(BASE / 'selection.json')
assert sha(PRIOR / 'index.json') == selection['priorStageIndexSha256']
assert selection['priorSourceIndexSha256'] == PRIOR_PIN
verify_index(BASE / 'implementation01', ROOT, SOURCE_PIN)
verify_index(PRIOR / 'implementation02', ROOT, PRIOR_PIN)
project = BASE / 'implementation01/project'
previous = PRIOR / 'implementation02/project'
old_files = {p.relative_to(previous).as_posix(): sha(p) for p in previous.rglob('*') if p.is_file()}
new_files = {p.relative_to(project).as_posix(): sha(p) for p in project.rglob('*') if p.is_file()}
assert len(old_files) == 284 and len(new_files) == 285
assert set(new_files) - set(old_files) == {'tests/test_vault_authority_edges.py'}
assert all(new_files[name] == value for name, value in old_files.items())
rows = []
for filename in ('__init__.py', 'contracts.py', 'store.py'):
    path = project / 'evidence_authority' / filename
    rows.append(dict(path='evidence_authority/' + filename, bytes=path.stat().st_size, sha256=sha(path)))
assert digest(b'HMS-PAT-VAULT-IMPORT-IMPLEMENTATION-v0.1', dict(vaultIdentity=VAULT, sources=rows)) == CONSUMER

interrupted = read(BASE / 'interruption-observation.json')
assert interrupted['status'] == 'interrupted-unverified' and interrupted['originalScope'] == 'harness03'
partial = BASE / 'harness03/attempts/attempt01'
assert not (partial / 'result.json').exists()
retained_partial = {p.relative_to(partial).as_posix() for p in partial.rglob('*') if p.is_file()}
assert retained_partial == {row['path'] for row in interrupted['retainedFiles']}
for row in interrupted['retainedFiles']:
    path = partial / row['path']; assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
for name in ('run_attempt.py', 'attempt_child.py', 'targets.json'):
    assert sha(BASE / 'harness03' / name) == sha(BASE / 'harness12' / name)

interrupted07 = read(BASE / 'interruption07/observation.json')
assert interrupted07['status'] == 'interrupted-unverified' and interrupted07['toolExecutionExitCode'] == 143
partial07 = BASE / 'harness07/attempts/attempt01'
assert not (partial07 / 'result.json').exists()
assert {p.relative_to(partial07).as_posix() for p in partial07.rglob('*') if p.is_file()} == {r['path'] for r in interrupted07['retainedAttemptFiles']}
for row in interrupted07['retainedAttemptFiles']:
    path = partial07 / row['path']; assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
for row in interrupted07['rawFiles']:
    paths = [BASE / 'interruption07/scratch' / row['path']]
    if Path(interrupted07['rawPath']).exists(): paths.append(Path(interrupted07['rawPath']) / row['path'])
    for path in paths: assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
for name in ('run_attempt.py', 'attempt_child.py', 'targets.json'):
    assert sha(BASE / 'harness07' / name) == sha(BASE / 'harness13' / name)
continuations = {'harness03':'harness12', 'harness07':'harness13'}
scopes = [continuations.get(row['harness'],row['harness']) for row in selection['scopes']]
assert len(scopes) == len(set(scopes)) == 11
receipts = []; targets_seen = []; attempts = {}
for base, names, source_pin, expected_inputs in ((BASE, scopes, SOURCE_PIN, 285),
                                               (PRIOR, ['harness18','harness19'], PRIOR_PIN, 284)):
    for name in names:
        folder = base / name; attempt = folder / 'attempts/attempt01'
        harness_pin = sha(folder / 'index.json'); verify_index(folder, folder, harness_pin)
        result = read(attempt / 'result.json'); targets = read(folder / 'targets.json')
        assert result['status'] == 'passed' and result['errors'] == []
        assert result['childState'] == 'exited' and result['exitCode'] == 0
        assert result['sourceIndexSha256'] == source_pin and result['harnessIndexSha256'] == harness_pin
        assert result['inputAndExternalVerificationPassed'] and result['sourceInputs'] == expected_inputs
        assert result['timeoutSeconds'] == 180 and result['elapsedSeconds'] <= 180
        assert result['maxSingleFileBytes'] == 16777216 and result['maxTotalScratchBytes'] == 268435456
        assert result['noWorkerLaunched'] and result['noPhysicalEffects'] and not result['totalDiskQuotaEnforced']
        assert result['counts']['testsRun'] == len(targets)
        assert all(value == 0 for key,value in result['counts'].items() if key != 'testsRun')
        assert read(attempt / 'test-return.json') == result['counts']
        actual = read(attempt / 'actual-tests.json')
        assert actual['loaded'] == actual['executed'] == targets and actual['exactSelection']
        origins = read(attempt / 'imports.json')
        assert origins['summary']['allOriginsMatched'] and not origins['violations'] and not origins['prohibitedAttempts']
        assert read(attempt / 'child-errors.json') == [] and len(read(attempt / 'sqlite-connections.json')) <= 64
        for component in ('compiler','driver'):
            assert read(attempt / (component + '-before.json')) == read(attempt / (component + '-after.json'))
        config = read(attempt / 'child-config.json'); assert len(config['expectedInputs']) == expected_inputs
        for row in config['expectedInputs']:
            path = attempt / 'project' / row['path']
            assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
        for row in config['expectedExternalInputs']:
            path = Path(row['resolvedPath'])
            assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
        inventory = read(attempt / 'scratch-index.json'); raw = Path(inventory['rawPath'])
        copied = attempt / 'scratch'; assert copied.is_dir()
        assert {p.relative_to(copied).as_posix() for p in copied.rglob('*') if p.is_file()} == {r['path'] for r in inventory['files']}
        if raw.exists():
            assert {p.relative_to(raw).as_posix() for p in raw.rglob('*') if p.is_file()} == {r['path'] for r in inventory['files']}
        for row in inventory['files']:
            assert row['kind'] == 'file'
            paths = [copied / row['path']]
            if raw.exists(): paths.append(raw / row['path'])
            for path in paths:
                assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
        assert sum(row['bytes'] for row in inventory['files']) == inventory['bytes'] == result['scratchBytes']
        assert len(inventory['files']) == result['scratchEntries'] <= 8192
        key = ('current/' if base == BASE else 'prior/') + name
        attempts[key] = copied
        receipts.append(dict(scope=key, path=attempt.relative_to(ROOT).as_posix(),
            harnessIndexSha256=harness_pin, resultSha256=sha(attempt / 'result.json'), targets=targets,
            elapsedSeconds=result['elapsedSeconds'], retainedCopyVerified=True,
            historicalRawPath=str(raw), rawAvailableAtAudit=raw.exists(), rawVerifiedIfPresent=True))
        targets_seen.extend(targets)
assert len(targets_seen) == len(set(targets_seen)) == 25
assert set(targets_seen) == set(selection['targets'] + selection['priorPassingMethods'])

# Fresh read-only examination of retained copies. Original raw inode/lease
# identities are not reconstructed or claimed by opening these copies.
cases = [
 ('current/harness01','test_publication_and_cold_replay_preserve_original_receipt',(1,1,1)),
 ('current/harness02','test_transport_success_does_not_publish_without_semantic_success',(1,0,0)),
 ('current/harness12','test_after_seal_resumes_without_original_archive_or_new_worker',(1,1,1)),
 ('current/harness04','test_before_publication_commit_keeps_unpublished_manifest',(1,0,1)),
 ('current/harness04','test_lost_publication_reply_reconciles_exact_receipt',(1,1,1)),
 ('current/harness09','test_bulk_full_keeps_original_intent_and_no_publication',(1,0,0)),
 ('current/harness09','test_current_consumer_identity_change_refuses_replay',(1,1,1)),
 ('current/harness11','test_lost_installation_reply_reopens_original_association',(0,0,0)),
 ('current/harness11','test_published_history_survives_configuration_drift_without_replanning',(1,1,1)),
 ('prior/harness18','test_configuration_change_after_seal_prevents_publication',(1,0,1)),
 ('prior/harness18','test_revocation_after_seal_preserves_authority_refusal',(1,0,1)),
 ('prior/harness19','test_expired_snapshot_before_commit_rolls_back_publication',(1,0,1)),
]
audits = []; hashes = {}; lock_count = 0
for scope, method, counts in cases:
    root = attempts[scope] / method; locks = []; dbs = []
    paths = [root / 'runtime/authority.db', root / 'vault/evidence.db', root / 'supervisor/attempts.db']
    before = {str(path): sha(path) for path in paths}
    try:
        for path in sorted(root.rglob('*.owner')):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); locks.append(fd); lock_count += 1
        assert len(locks) == 4
        for path in paths:
            assert not any(os.path.lexists(str(path) + suffix) for suffix in ('-journal','-wal','-shm'))
            db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, isolation_level=None)
            db.execute('PRAGMA query_only=ON'); dbs.append(db)
        authority, vault, supervisor = dbs
        meta = document(authority.execute('SELECT record FROM evi_meta').fetchone()[0])
        assert meta['authorityId'] == authority.execute("SELECT value FROM meta WHERE key='authority'").fetchone()[0]
        assert meta['consumerIdentity'] == CONSUMER and meta['vault']['authorityId'] == meta['authorityId']
        assert meta['vault']['implementationDigest'] == VAULT and meta['intentCharge'] == 33792
        assert authority.execute("SELECT value FROM reg_meta WHERE key='vault_evidence_import'").fetchone()[0] == 'hms.pat.vault-import/0.1|' + digest(b'HMS-PAT-VAULT-IMPORT-MOUNT-v0.1', meta)
        assert document(vault.execute('SELECT record FROM ev_meta').fetchone()[0]) == meta['vault']
        intents = authority.execute('SELECT intent,record FROM evi_intents').fetchall()
        pubs = authority.execute('SELECT intent,record FROM evi_publications').fetchall()
        manifests = vault.execute('SELECT intent,binding,record FROM ev_manifests').fetchall()
        assert tuple(map(len,(intents,pubs,manifests))) == counts
        assert supervisor.execute('SELECT count(*) FROM qs_attempts').fetchone()[0] == (0 if counts == (0,0,0) else 1)
        assert authority.execute('SELECT count(*) FROM operations').fetchone()[0] == 0
        assert authority.execute('SELECT count(*) FROM claims').fetchone()[0] == 0
        decoded = {}
        for key, body in intents:
            intent = document(body); decoded[key] = intent
            assert key == digest(b'HMS-PAT-VAULT-IMPORT-INTENT-v0.1', intent)
            assert intent['consumerIdentity'] == CONSUMER and intent['previousIntentDigest'] is None
            anchor = intent['anchor']; assert anchor['authorityId'] == meta['authorityId']
            assert intent['bindingDigest'] == digest(b'HMS-PAT-VAULT-ORIGINAL-BINDING-v0.1', anchor)
            reservation = document(authority.execute('SELECT receipt FROM iosr_runs').fetchone()[0])
            handoff = document(authority.execute('SELECT receipt FROM iose_handoffs').fetchone()[0])
            assert anchor['attemptId'] == handoff['attemptId']
            assert anchor['requestDigest'] == reservation['requestDigest'] == handoff['requestDigest']
            assert anchor['configurationReceiptDigest'] == reservation['configurationReceiptDigest']
        objects = dict(vault.execute('SELECT digest,body FROM ev_bodies'))
        assert all(key == 'sha256:' + hashlib.sha256(body).hexdigest() for key,body in objects.items())
        refs = vault.execute('SELECT path,digest FROM ev_documents ORDER BY path').fetchall()
        chain = hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0'); size = 0
        for path, key in refs:
            body = objects[key]; size += len(body)
            chain.update(canonical(dict(path=path, bytes=len(body), sha256=key)) + b'\n')
        for key, binding, body in manifests:
            manifest = document(body); intent = decoded[key]
            assert binding == intent['bindingDigest'] and manifest['scope'] == 'immutable-bytes-only'
            assert manifest['storeId'] == intent['storeId'] == meta['vault']['storeId']
            assert manifest['closure'] == dict(documents=len(refs), bytes=size, digest='sha256:' + chain.hexdigest())
            evaluation = document(objects[dict(refs)['evaluation.json']])
            assert evaluation['anchor'] == intent['anchor'] and evaluation['consumerIdentity'] == CONSUMER
            assert all(evaluation[field] is False for field in ('physicalObjectiveVerified','wallDeadlineAttested','aggregateDiskQuotaEnforced','catalogActivated'))
            for pub_key, pub_body in pubs:
                pub = document(pub_body); assert pub_key == key == pub['intentDigest']
                assert pub['manifestDigest'] == digest(b'HMS-PAT-EVIDENCE-VAULT-MANIFEST-v0.1', manifest)
                assert pub['closure'] == manifest['closure'] and pub['evaluationDigest'] == dict(refs)['evaluation.json']
        if not manifests: assert not refs and not objects
        assert len(canonical(meta)) + 1024 + len(intents) * 33792 <= meta['maxControlBytes']
        audits.append(dict(scope=scope, method=method, counts=counts, references=len(refs), bodies=len(objects),
            exactBytesVerified=True, retainedCopyOnly=True, originalLeaseIdentityRecreated=False))
    finally:
        for db in reversed(dbs): db.close()
        for fd in reversed(locks): os.close(fd)
    after = {str(path): sha(path) for path in paths}; assert before == after; hashes.update(after)

negative_cases = [
 ('current/harness06','test_corrupt_published_body_is_refused_without_repair','corrupt-body'),
 ('current/harness10','test_malformed_authority_record_refuses_before_body_fetch_without_repair','malformed-record'),
 ('current/harness10','test_installation_failure_before_commit_retains_uninstalled_vault','uninstalled'),
]
for scope, method, kind in negative_cases:
    root = attempts[scope] / method; locks = []; dbs = []
    paths = [root / 'runtime/authority.db', root / 'vault/evidence.db', root / 'supervisor/attempts.db']
    before = {str(path): sha(path) for path in paths}
    try:
        for path in sorted(root.rglob('*.owner')):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); locks.append(fd); lock_count += 1
        assert len(locks) == 4
        for path in paths:
            assert not any(os.path.lexists(str(path) + suffix) for suffix in ('-journal','-wal','-shm'))
            db = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, isolation_level=None)
            db.execute('PRAGMA query_only=ON'); dbs.append(db)
        authority, vault, supervisor = dbs
        if kind == 'uninstalled':
            assert authority.execute("SELECT count(*) FROM sqlite_master WHERE name GLOB 'evi_*' OR tbl_name GLOB 'evi_*'").fetchone()[0] == 0
            assert authority.execute("SELECT count(*) FROM reg_meta WHERE key='vault_evidence_import'").fetchone()[0] == 0
            assert vault.execute('SELECT count(*) FROM ev_manifests').fetchone()[0] == 0
            assert supervisor.execute('SELECT count(*) FROM qs_attempts').fetchone()[0] == 0
        else:
            assert tuple(authority.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in ('evi_intents','evi_publications')) == (1,1)
            assert vault.execute('SELECT count(*) FROM ev_manifests').fetchone()[0] == 1
            assert supervisor.execute('SELECT count(*) FROM qs_attempts').fetchone()[0] == 1
            objects = dict(vault.execute('SELECT digest,body FROM ev_bodies'))
            bad = {key for key,body in objects.items() if key != 'sha256:' + hashlib.sha256(body).hexdigest()}
            if kind == 'corrupt-body':
                summary_key = vault.execute("SELECT digest FROM ev_documents WHERE path='inspection/summary.json'").fetchone()[0]
                assert bad == {summary_key} and objects[summary_key] == b'{}'
            else:
                assert not bad
                assert tuple(authority.execute('SELECT typeof(record),record FROM evi_intents').fetchone()) == ('text','retained invalid text type')
                observed = read(root / 'malformed-authority.json')
                assert observed['bodyFetchExecuted'] is False and observed['reconstructed'] is False
        assert authority.execute('SELECT count(*) FROM operations').fetchone()[0] == 0
        assert authority.execute('SELECT count(*) FROM claims').fetchone()[0] == 0
        audits.append(dict(scope=scope,method=method,negativeState=kind,retainedCopyOnly=True,
            stateUnrepaired=True,originalLeaseIdentityRecreated=False))
    finally:
        for db in reversed(dbs): db.close()
        for fd in reversed(locks): os.close(fd)
    after = {str(path): sha(path) for path in paths}; assert before == after; hashes.update(after)

output = dict(status='controls-verified-incomplete-system', sourceIndexSha256=SOURCE_PIN,
    priorSourceIndexSha256=PRIOR_PIN, consumerIdentity=CONSUMER, inheritedFilesUnchanged=284,
    productionChanged=False, passingMethods=targets_seen, distinctPassingMethods=25,
    currentScopeMethods=22, priorCurrentProductionMethods=3, remainingSelectedMethods=[],
    originalAggregatePassed=False, singleAggregateSelectionRun=False,
    interruptedScopes=['harness03','harness07'], interruptedScopesRetainedUnverified=True,
    continuations=continuations, scopes=receipts, readonlyDatabaseCount=len(hashes),
    ownerLocks=lock_count, unchangedDatabaseHashes=hashes, databaseAudits=audits,
    rawStateReconstructed=False, actualOriginalRunProfileVerified=False, catalogIntegrated=False,
    physicalCapacityReserved=False, publicMounted=False, noWorkerExecuted=True,
    physicalEffects=False, goalStatus='active')
write(BASE / 'RESULTS.json', output)
print(json.dumps({key:output[key] for key in ('status','distinctPassingMethods','readonlyDatabaseCount','ownerLocks','goalStatus')}))

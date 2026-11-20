"""Read retained identity/refusal fixtures without importing candidate code."""
import ast
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

B = Path.cwd()/'artifacts/implementation/pat-io-execution-handoff'
F = B/'results'/sys.argv[1]
A, R = F/'attempt', F/'attempt/scratch'
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
def assignment(path, name):
    tree = ast.parse(path.read_bytes())
    return ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)))
proof = read(F/'proof.json')
assert proof['status'] == 'passed' and proof['counts']['testsRun'] == 13
project = A/'project/supervisor'
meta_sql = assignment(project/'authority_ledger.py', 'META_SQL')
attempt_sql = assignment(project/'attempt_ledger.py', 'ATTEMPT_SQL')
index_sql = assignment(project/'attempt_ledger.py', 'INDEX_SQL')
expected = {('qs_meta','table','qs_meta',meta_sql), ('qs_attempts','table','qs_attempts',attempt_sql),
            ('qs_singleflight','index','qs_attempts',index_sql),
            ('sqlite_autoindex_qs_attempts_1','index','qs_attempts',None),
            ('sqlite_autoindex_qs_attempts_2','index','qs_attempts',None)}
rows = []; identities = set(); attempts = 0
for path in sorted(R.glob('*/*/attempts.db')):
    method, label = path.parent.parent.name, path.parent.name
    original = Path(proof['rawScratch']['path'])/path.relative_to(R)
    assert sha(original) == sha(path)
    owner = os.open(original.parent/'supervisor.owner', os.O_RDONLY|os.O_NOFOLLOW)
    try: fcntl.flock(owner, fcntl.LOCK_EX|fcntl.LOCK_NB)
    finally: os.close(owner)
    assert not any(path.with_name(path.name+suffix).exists() for suffix in ('-wal','-shm','-journal'))
    before = sha(path); db = sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True)
    kind = 'version2'; identity = None
    try:
        schema = set(db.execute('SELECT name,type,tbl_name,sql FROM sqlite_master'))
        if label == 'legacy':
            kind = 'legacy-version1'; assert db.execute('SELECT version FROM qs_meta').fetchall() == [(1,)]
            assert schema == expected - {('qs_meta','table','qs_meta',meta_sql)} | {
                ('qs_meta','table','qs_meta','CREATE TABLE qs_meta(version INTEGER NOT NULL CHECK(version=1))')}
        elif method == 'test_partial_metadata_never_reinitializes':
            kind = 'retained-missing-metadata'; assert schema == expected - {('qs_meta','table','qs_meta',meta_sql)}
        else:
            if method == 'test_added_trigger_is_not_trusted_on_lookup':
                kind = 'retained-extra-trigger'; assert expected < schema and len(schema) == len(expected)+1
                assert next(row for row in schema if row not in expected)[0:3] == ('unexpected','trigger','qs_attempts')
            else: assert schema == expected
            version, identity = db.execute('SELECT version,authority FROM qs_meta').fetchone()
            assert type(version) is int and version == 2
            if method == 'test_multibyte_identity_is_bounded_before_fetch':
                kind = 'retained-multibyte-identity'; assert identity == '😀'*43
            else:
                assert type(identity) is str and re.fullmatch(r'supervisor:[0-9a-f]{32}', identity)
                if method == 'test_changed_open_metadata_is_checked_even_for_absent_run': kind = 'retained-changed-identity'
                else: assert identity not in identities; identities.add(identity)
            if method == 'test_temporary_metadata_shadow_refuses': kind = 'transient-shadow-final-durable-state'
        records = db.execute('SELECT id,deployment,evaluator,run,request,digest,record,return_bytes,active FROM qs_attempts').fetchall()
        assert len(records) <= 1
        for identifier, deployment, evaluator, run, request, digest, record, returned, active in records:
            q, r = json.loads(request), json.loads(record)
            assert canonical(q) == request and canonical(r) == record
            assert digest == 'sha256:'+hashlib.sha256(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1\0'+request).hexdigest()
            assert r['attemptId'] == identifier and r['requestDigest'] == digest
            assert (deployment,evaluator,run) == tuple(q['context'][name] for name in ('deployment','evaluatorId','runId'))
            assert returned is r['archive'] is r['lease'] is r['pid'] is None and active == 1
            assert r['history'] in (['admitted'], ['admitted','interrupted']) and r['state'] == r['history'][-1]
            assert r['reason'] == ('OWNER_LOST' if r['state'] == 'interrupted' else None)
            assert not (path.parent/identifier).exists(); attempts += 1
    finally: db.close()
    assert sha(path) == before
    receipt = path.parent.parent/'refusal.json'
    if receipt.exists():
        refusal = read(receipt); assert refusal['before'] == refusal['after'] == before and refusal['reset'] is False
    rows.append(dict(path=path.relative_to(R).as_posix(), sha256=before, kind=kind, authorityId=identity,
                     attempts=len(records), originalOwnerFree=True, databaseUnchanged=True))
assert len(rows) == 14 and attempts == 3
report = dict(scope='Source-free retained supervisor identity/schema/admission/refusal observations; no producer execution.',
    tests=13, databases=rows, admittedOrInterruptedAttempts=attempts, allOriginalOwnersFree=True,
    allDatabasesUnchanged=True, noAttemptDirectories=True, actualWorkerExecuted=False,
    qualificationPassed=False, independentReview=False)
with (F/'supervisor-authority-audit.json').open('x') as stream: stream.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(databases=len(rows), attempts=attempts, allDatabasesUnchanged=True, actualWorkerExecuted=False)))

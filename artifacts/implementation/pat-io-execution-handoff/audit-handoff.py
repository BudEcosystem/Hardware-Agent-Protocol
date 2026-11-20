"""Independent read-only reservation/mount/request/attempt association joins."""
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
F = B/'results'/sys.argv[1]; A = F/'attempt'; R = A/'scratch'
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
def digest(domain, value): return 'sha256:'+hashlib.sha256(domain+b'\0'+canonical(value)).hexdigest()
def document(body):
    assert type(body) is bytes and 0 < len(body) <= 65536
    value = json.loads(body); assert canonical(value) == body
    return value
def open_db(path):
    assert not any(path.with_name(path.name+s).exists() for s in ('-wal','-shm','-journal'))
    original = Path(proof['rawScratch']['path'])/path.relative_to(R)
    assert sha(original) == sha(path)
    owner = original.with_name(original.name+'.owner') if path.name == 'authority.db' else original.parent/'supervisor.owner'
    fd = os.open(owner, os.O_RDONLY|os.O_NOFOLLOW)
    try: fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
    finally: os.close(fd)
    return sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True)

proof = read(F/'proof.json')
kind = read(B/proof['harness']/'review.json')['selectionKind']
assert kind in ('handoff','process')
if kind == 'handoff': assert proof['status'] == 'passed'
tree = ast.parse((A/'project/supervisor/io_service_execution.py').read_bytes())
ddl = ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_DDL' for t in n.targets)))
expected_schema = {(n,'table',n,sql) for n,sql in ddl.items()} | {('sqlite_autoindex_iose_handoffs_1','index','iose_handoffs',None)}
corrupt = {'test_noncanonical_handoff_is_retained_and_not_repaired':'noncanonical',
    'test_oversize_handoff_refuses_before_document_parse':'oversize', 'test_non_object_handoff_refuses':'array',
    'test_added_execution_trigger_refuses':'extra-trigger', 'test_missing_mount_tables_with_anchor_never_reinitialize':'missing-tables'}
reports = []; valid_handoffs = 0; supervisor_attempts = 0
for database in sorted(R.glob('*/runtime/authority.db')):
    work = database.parent.parent; method = work.name; before = sha(database)
    supervisor_path = work/'supervisor/attempts.db'; supervisor_pin = sha(supervisor_path)
    db, control = open_db(database), open_db(supervisor_path)
    retained_corruption = corrupt.get(method)
    try:
        meta, reg = dict(db.execute('SELECT key,value FROM meta')), dict(db.execute('SELECT key,value FROM reg_meta'))
        assert all(db.execute('SELECT count(*) FROM '+table).fetchone() == (0,) for table in ('operations','claims','events','replay_keys'))
        version, identity = control.execute('SELECT version,authority FROM qs_meta').fetchone()
        assert version == 2 and re.fullmatch(r'supervisor:[0-9a-f]{32}', identity)
        actual = control.execute('SELECT id,request,record,return_bytes FROM qs_attempts').fetchall()
        assert len(actual) <= 1; supervisor_attempts += len(actual)
        for identifier, request_raw, record_raw, returned in actual:
            request, record = document(request_raw), document(record_raw)
            assert record['attemptId'] == identifier
            assert record['requestDigest'] == digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1', request)
            if kind == 'handoff':
                assert record['lease'] is record['pid'] is returned is None
                assert 'launching' not in record['history'] and not (supervisor_path.parent/identifier).exists()
        schema = set(db.execute("SELECT name,type,tbl_name,sql FROM sqlite_master WHERE name GLOB 'iose_*' OR tbl_name GLOB 'iose_*'"))
        if method == 'test_path_or_claimed_identity_cannot_replace_actual_supervisor_object':
            assert not schema and 'io_service_execution' not in reg and not actual
            reports.append(dict(method=method, mounted=False, handoffs=0, supervisorAttempts=0, databaseSha256=before, supervisorSha256=supervisor_pin))
            continue
        if retained_corruption == 'missing-tables':
            assert not schema and 'io_service_execution' in reg and len(actual) == 1
            reports.append(dict(method=method, retainedCorruption=retained_corruption, handoffs=None, supervisorAttempts=1, databaseSha256=before, supervisorSha256=supervisor_pin))
            continue
        if retained_corruption == 'extra-trigger':
            assert expected_schema < schema and len(schema) == len(expected_schema)+1
        else: assert schema == expected_schema
        mount = document(db.execute('SELECT record FROM iose_meta WHERE singleton=1').fetchone()[0])
        assert mount['profile'] == 'hms.pat.io-service-execution/0.1'
        assert mount['authorityId'] == meta['authority'] and mount['deployment'] == reg['deployment']
        assert mount['supervisorAuthorityId'] == identity
        assert reg['io_service_execution'] == mount['profile']+'|'+digest(b'HMS-PAT-IO-SERVICE-EXECUTION-v0.1', mount)
        rows = db.execute('SELECT sequence,evaluator,run,receipt FROM iose_handoffs ORDER BY sequence').fetchall()
        assert [row[0] for row in rows] == list(range(1,len(rows)+1)) and len(rows) <= mount['maxHandoffs'] <= 32
        previous = None; prior_time = mount['createdAtUnixMs']; joins = []
        for sequence, evaluator, run, wire in rows:
            if retained_corruption in ('noncanonical','oversize','array'):
                assert (wire.endswith(b' ') if retained_corruption == 'noncanonical' else wire == b' '*4097 if retained_corruption == 'oversize' else wire == b'[]')
                continue
            handoff = document(wire)
            request_raw, reservation_raw = db.execute('SELECT request,receipt FROM iosr_runs WHERE evaluator=? AND run=?',(evaluator,run)).fetchone()
            request, reservation = document(request_raw), document(reservation_raw)
            request_digest = digest(b'HMS-PAT-IO-SUPERVISOR-REQUEST-v0.1', request)
            reservation_digest = digest(b'HMS-PAT-IO-SERVICE-RUN-RESERVATION-v0.1', reservation)
            timestamp = handoff['committedAtUnixMs']; assert type(timestamp) is int and prior_time <= timestamp <= 2**53-1
            assert handoff == dict(profile='hms.pat.io-service-handoff/0.1', authorityId=meta['authority'], deployment=reg['deployment'],
                supervisorAuthorityId=identity, evaluatorId=evaluator, runId=run, reservationDigest=reservation_digest,
                requestDigest=request_digest, attemptId=handoff['attemptId'], sequence=sequence, principal=handoff['principal'],
                committedAtUnixMs=timestamp, previousHandoffDigest=previous)
            assert re.fullmatch(r'[0-9a-f]{32}', handoff['attemptId']) and handoff['principal'] == 'owner'
            previous = digest(b'HMS-PAT-IO-SERVICE-HANDOFF-v0.1', handoff); prior_time = timestamp
            if method == 'test_missing_attempt_after_association_is_not_new_admission':
                assert not actual; disposition = 'retained-association-missing-attempt'
            else:
                assert len(actual) == 1 and actual[0][1] == request_raw
                if method == 'test_changed_attempt_id_under_same_request_is_refused':
                    assert actual[0][0] != handoff['attemptId']; disposition = 'retained-attempt-id-mismatch'
                else:
                    assert actual[0][0] == handoff['attemptId']; disposition = 'exact-original-attempt'
            joins.append(dict(attemptId=handoff['attemptId'], requestDigest=request_digest,
                reservationDigest=reservation_digest, associationDigest=previous, disposition=disposition))
            valid_handoffs += 1
        if method == 'test_preexisting_changed_request_cannot_be_associated':
            assert not rows and len(actual) == 1
            reserved = document(db.execute('SELECT request FROM iosr_runs').fetchone()[0])
            reserved['limits']['maxStreamBytes'] -= 1
            assert document(actual[0][1]) == reserved
        reports.append(dict(method=method, mounted=True, authorityId=meta['authority'], supervisorAuthorityId=identity,
            handoffs=len(rows), supervisorAttempts=len(actual), associations=joins, retainedCorruption=retained_corruption,
            databaseSha256=before, supervisorSha256=supervisor_pin))
    finally:
        db.close(); control.close()
        assert sha(database) == before and sha(supervisor_path) == supervisor_pin
assert len(reports) == proof['counts']['testsRun']
report = dict(scope='Source-free Journal mount/reservation/request/original-attempt joins; no worker-outcome or promotion conclusion.',
    methods=len(reports), authorities=reports, validatedHandoffs=valid_handoffs, supervisorAttempts=supervisor_attempts,
    originalOwnerLeasesFree=True, allDatabasesUnchanged=True, sourceAuthorityEffectsZero=True,
    noProducerLaunchInControlScopes=kind=='handoff', qualificationPassed=False)
with (F/'handoff-audit.json').open('x') as stream: stream.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(methods=len(reports), validatedHandoffs=valid_handoffs, supervisorAttempts=supervisor_attempts,
    allDatabasesUnchanged=True, sourceAuthorityEffectsZero=True)))

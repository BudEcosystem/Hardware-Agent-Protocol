"""Freeze a reviewed read-only audit adapted to the observed terminal outcome."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
old=ROOT/'artifacts/implementation/pat-io-proof-batch/audit-actual.py'
original=old.read_text();updated=original
changes={
    "STAGE=BASE/'implementation01';HARNESS=BASE/'harness02';ATTEMPT=HARNESS/'attempts/attempt01-actual'":
    "STAGE=ROOT/'artifacts/implementation/pat-io-proof-batch/implementation01';HARNESS=BASE/'harness02';ATTEMPT=HARNESS/'attempts/attempt01-accounting'",
    "HPIN='094098cab10de007e509f99895997915f6956634cb045f0d241ae333a01b08dc'":
    "HPIN='8c3800eec1af47f41027bd61efedeafe567d74944659db88870858c41c31e30a'",
    'assert len(locks)==37':'assert len(locks)==49',
    'assert len(cases)==20 and len(manifests)==19':'assert len(cases)==26 and len(manifests)==25',
    "assert matrix['cases'][19]['definition']['scenario']=='late_parent_reporting'":
    "assert matrix['cases'][25]['definition']['scenario']=='permission_after_completion'",
    'pureControls=63,productionCandidateChanged=True':'pureControls=15,productionCandidateChanged=False',
    "caseDirectories=20,caseManifests=19,incompleteScenario='late_parent_reporting'":
    "caseDirectories=26,caseManifests=25,incompleteScenario='permission_after_completion'",
    '    for db in reversed(dbs):db.close()':
    (BASE/'accounting-audit.inc').read_text()+'    for db in reversed(dbs):db.close()',
    "summary=dict(stageStatus='verified-progress-actual-scope-failed'":
    "summary=dict(stageStatus='verified-resource-observation-original-scope-failed',resourceObservation=observation",
}
for before,after in changes.items():
    if before=='    for db in reversed(dbs):db.close()':
        assert updated.count(before)==2
        updated=updated.replace(before,after,1)
    else:
        assert updated.count(before)==1,before
        updated=updated.replace(before,after)
ast.parse(updated)
(BASE/'references').mkdir(exist_ok=True)
for name,body in (('references/original-audit-actual.py',original),('audit.py',updated),
        ('audit.py.patch',''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),fromfile='proof-batch/audit-actual.py',tofile='accounting/audit.py')))):
    with (BASE/name).open('x') as stream:stream.write(body)
review=dict(reviewer='primary-agent',independentReview=False,originalAuditSha256=hashlib.sha256(old.read_bytes()).hexdigest(),
    auditSha256=hashlib.sha256(updated.encode()).hexdigest(),newAccountingLogicSha256=hashlib.sha256((BASE/'accounting-audit.inc').read_bytes()).hexdigest(),
    sourceDatabasesReadonly=4,caseDatabasesOpened=0,expectedOwnerWriterLocks=49,
    originalFailedScopePreserved=True,sourceCodeExecuted=False)
with (BASE/'audit-review.json').open('x') as stream:json.dump(review,stream,indent=2);stream.write('\n')
print(json.dumps(review))

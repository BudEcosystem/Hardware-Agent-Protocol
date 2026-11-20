"""Report exact scopes, incomplete selections and retained failures without merging claims."""
import json
from pathlib import Path
B=Path('artifacts/implementation/pat-io-execution-handoff'); R=B/'results'
PINS={'implementation01':'f53286e08e528fd764893afc6f6765128c388a349ef536c2f22b17bc521f6035',
      'implementation02':'52590e9723805e43f76ad50c94d306d4d6a45c031e00b5fff2b6572c38ee4b90'}
def read(p): return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x') as f:f.write(json.dumps(v,indent=2)+'\n')
selected=set(); new_controls=set(); by_harness={}
for n in range(1,31):
    name='harness%02d'%n; targets=read(B/name/'targets.json')['targets']
    assert not selected.intersection(targets); selected.update(targets); by_harness[name]=targets
    if n in range(18,25) or n>=26:new_controls.update(targets)
assert len(selected)==349 and len(new_controls)==50
entries=[]; seen_harnesses=set(); passed=set(); failed=set(); incomplete=set(); complete=set()
for folder in sorted(R.iterdir()):
    if not (folder/'proof.json').exists():continue
    proof=read(folder/'proof.json'); result=read(folder/'attempt/result.json'); harness=proof['harness']
    assert harness not in seen_harnesses; seen_harnesses.add(harness)
    targets=by_harness[harness]; review=read(B/harness/'review.json'); kind=review.get('selectionKind','inherited')
    assert proof['sourceIndexSha256']==review['sourceIndexSha256'] in PINS.values()
    assert result['status']==proof['status'] and result['childState']=='exited'
    storage=read(folder/'storage-audit.json'); assert storage['databaseBytesUnchanged']
    item=dict(destination=folder.name,harness=harness,attempt=proof['attempt'],status=proof['status'],
        selectedMethods=len(targets),targets=targets,counts=proof['counts'],testSeconds=proof.get('testSeconds'),
        elapsedSeconds=proof['elapsedSeconds'],sourceIndexSha256=proof['sourceIndexSha256'],
        rawScratch=proof['rawScratch'],rawScratchFiles=proof['rawScratchFiles'],rawScratchBytes=proof['rawScratchBytes'],
        attemptFilesAcquired=proof['attemptFilesAcquired'],databases=len(storage['databases']),
        actualOrigins=proof.get('actualOrigins'),parentSqliteConnections=proof.get('sqliteConnections'))
    if proof['status']=='timed_out':
        assert proof['counts'] is None and proof['fullChildReceiptAvailable'] is False
        incomplete.update(targets); item['completedLogChecks']=proof['completedOkLines']
        assert set(proof['completedLogTargets'])<=set(targets)
    else:
        actual=read(folder/'attempt/actual-tests.json')
        assert actual['loaded']==actual['executed']==targets and actual['exactSelection']
        assert result['errors']==result['childErrors']==[] and proof['counts']['testsRun']==len(targets)
        complete.update(targets)
        if proof['status']=='passed':passed.update(targets)
        else:
            assert proof['status']=='failed'; failed.update(targets)
    item['audits']=sorted(p.name for p in folder.glob('*-audit.json'))
    if kind=='authority':assert 'supervisor-authority-audit.json' in item['audits']
    if kind in ('handoff','process'):assert 'handoff-audit.json' in item['audits']
    if kind=='history':
        history=read(folder/'history-audit.json');assert history['allDatabasesUnchanged'] and history['originalValidHandoffs']==2
        item['historyCorruption']=history['retainedCorruption'];item['historicalReplayVerified']=history['historicalReplayVerified']
    process_scope=kind=='process' or (kind=='inherited' and len(targets)==1)
    if process_scope:
        audit='process-audit.json' if proof['status']=='passed' else 'failure-audit.json'
        value=read(folder/audit);assert value['ledgerUnchanged'] and not value['qualificationPassed']
        item['processAudit']=audit
        for key in ('attemptId','history','archive','states','effects','claims','owners','codeImageFiles','runtimeFiles',
                    'groupStatus','completedCases','preCrashReason','workerFailureCode','inspectedStates','uninspectedStates',
                    'effectsComplete','observedEffects','observedClaims','observedOwners'):
            if key in value:item[key]=value[key]
    entries.append(item)
assert seen_harnesses==set(by_harness) and len(entries)==30
assert passed.isdisjoint(failed) and complete==passed|failed and complete.isdisjoint(incomplete)
assert selected==complete|incomplete and new_controls<=passed
analysis=dict(scope='Durable supervisor authority and Journal-to-original-attempt handoff; five test-only multi-run extensions preserve all prior production bytes.',
    goalStatus='active',sourceIndices=PINS,selectedDistinctMethods=len(selected),completedReceiptMethods=len(complete),
    distinctPassingMethods=len(passed),distinctFailingMethods=len(failed),incompleteSelectionMethods=len(incomplete),
    failedMethods=sorted(failed),incompleteSelectionTargets=sorted(incomplete),
    completedLogChecksWithoutFullReceipt=sum(x.get('completedLogChecks',0) for x in entries),
    attemptedScopes=len(entries),retainedFailedAttempts=sum(x['status']=='failed' for x in entries),
    retainedTimeoutAttempts=sum(x['status']=='timed_out' for x in entries),newPassingControlMethods=len(new_controls),
    actualHandoffWorkerPassed=False,actualHandoffPostDriftReplayReached=False,
    regressionComplete=False,publicServiceMounted=False,physicalValidation=False,qualificationPassed=False,
    aggregateFilesystemQuotaEnforced=False,deploymentDeadlineGuarantee=False,
    retainedAcquisitionToolFailures=['acquisition-timeout-failure01.json'],attempts=entries)
analysis['retainedAuditToolFailures']=sorted(p.name for p in B.glob('*-audit-*.log') if 'Traceback (most recent call last):' in p.read_text())
assert next(x for x in entries if x['harness']=='harness25')['status']=='failed'
write(B/'RESULTS.json',analysis)
for item in entries:
    folder=R/item['destination']; status=item['status']
    description=(str(item['selectedMethods'])+' selected methods; no complete test receipt. '+str(item['completedLogChecks'])+' completed checks appear in the partial log. This is not a passing selection.'
        if status=='timed_out' else str(item['counts']['testsRun'])+' completed methods, '+str(item['counts']['failures'])+' failures and '+str(item['counts']['errors'])+' errors.')
    links='; '.join('['+name.removesuffix('.json')+']('+name+')' for name in item['audits'])
    if 'archive' in item:
        description+=' Recorded supervisor reason: '+str(item['archive']['supervisorReason'])+'.'
        if item.get('preCrashReason'):description+=' Pre-crash reason: '+item['preCrashReason']+'.'
        if item.get('workerFailureCode'):description+=' Worker failure: '+item['workerFailureCode']+'.'
    with (folder/'README.md').open('x') as f:f.write('# '+item['attempt']+'\n\n'+status+': '+description+'\n\n[Acquisition](proof.json), [original output](attempt/output.log). '+links+'.\n\nOriginal raw state and complete copies are retained. Incomplete execution and later unreached assertions are not claimed. No physical or public-service qualification is established.\n')
table='| Attempt | Selected methods | Result | Test seconds |\n|---|---:|---|---:|\n'+'\n'.join(
    '| ['+x['attempt']+']('+x['destination']+'/README.md) | '+str(x['selectedMethods'])+' | '+x['status']+' | '+('unavailable' if x['testSeconds'] is None else str(x['testSeconds']))+' |' for x in entries)
failure_table='| Failed worker attempt | Recorded reason | Retained states | Uninspected states |\n|---|---|---:|---:|\n'+'\n'.join(
    '| ['+x['attempt']+']('+x['destination']+'/README.md) | '+str(x.get('preCrashReason') or x.get('workerFailureCode') or x['archive']['supervisorReason'])+' | '+str(x['states'])+' | '+str(x.get('uninspectedStates',0))+' |'
    for x in entries if x['status']=='failed' and 'archive' in x)
with (R/'README.md').open('x') as f:f.write('''# Durable execution-handoff results

All **50 new control methods pass**: 13 supervisor-authority checks, 32 handoff checks and five additional multi-run history checks. Across all 349 selected methods, **'''+str(len(passed))+' have complete passing receipts, '+str(len(failed))+' have complete failing receipts, and '+str(len(incomplete))+''' belong to incomplete selections**. Every one of the 30 frozen scopes was invoked once. Partial log checks are reported separately and are not promoted to passing-scope evidence.

The explicit version-2 supervisor ledger has a durable authority identity. The Journal mount pins that actual store and commits an association from reservation and request digests to the original attempt before launch. Only the invocation that creates and associates the attempt can launch it. Replays and recovery preserve the original attempt; missing/replaced stores, mismatched rows, revoked authority and retained corruption do not authorize a replacement. Legacy ledger behavior is preserved by the reviewed metadata hooks and AST comparison. This is an isolated library candidate.

The real new handoff worker persists its association before launch but reaches its original 60-second deadline without a complete return. Its full 30-case inspection and later configuration/session replay are unreached. Eleven states remain; ten can be inspected, showing seven activations, four completions and three cancellations with no observed claims or owners. One incomplete state prevents aggregate effect/claim/owner totals from being known. Its bytes remain untouched. The control-scope replay checks do not substitute for this missing end-to-end result.

The 206-method compatibility batch reaches its original 180-second harness deadline. Its log has 194 completed checks, but lacks the complete child, origin and final compiler/driver receipts. All 614 raw scratch files match their retained copies and inventory. Read-only checks preserve eleven intentionally corrupt records, three diagnostic lease fixtures and three malformed returns. The initial acquisition helper compared path-component ordering with serialized string ordering and failed; its original source and [failure record](../acquisition-timeout-failure01.json) are retained. Correcting only inventory ordering allowed acquisition; no test or retained state was changed.

The spawn-loss worker returns a canonical failed group after 26 cases with `PAT_IO_AUTHORITY_UNEXPECTED_FAILURE`. Its final recorded public call receives the expected `ACCESS_DENIED`; the wrapper does not retain the inner error responsible for the later generic failure. The [trace and source review](../AUTHORITY-FAILURE.md) identify a possible masking path but do not establish its cause in this run. It is not relabeled as a deadline or permission bypass.

The legacy configured-worker variant stops for `SUPERVISOR_RETENTION_UNKNOWN`, before its deadline. All three retained states are inspectable, with two activations, one completion, no cancellation and one remaining claim/board owner. Its scanner does not preserve the underlying exception detail. Terminal file counts cannot establish the transient cause, and process exit does not settle that retained modeled effect.

The inherited canonical-document auditor initially used its preceding stage's fixed result-folder name. Its failed log and original reader are retained; the corrected reader accepts the current result argument and verifies the existing 19-test result without rerunning it. The archive-loss state's first reader also encountered a missing runtime table during interrupted construction. A corrected read-only preflight records that state as uninspected, without creating tables or inferring zero effects. The original failed reader/log remain retained. Any additional retained audit-tool failures appear in the exact summary.

The five multi-run controls use a separate test-only source copy. All 252 preceding project files remain byte-identical; one test module adds coverage for two distinct attempts, reopen replay, forged receipt links, borrowed attempt IDs, regressed timestamps and reordered committed rows. Each control substitutes both launch boundaries. Independent read-only audits join two reservations and 74 input documents to the actual attempts and verify the exact retained mutation or replay.

No original worker, harness, effect, storage or timing bounds were widened. Failed logical runs were not relaunched. Source copy 1 has 252 project/255 frozen files; copy 2 has 253/256. Created worker images use the unchanged production closure of 262 files, including ten supervisor sources and 157 runtime dependencies. Current authorization and admission eligibility remain separate from historical replay. There is no cross-database atomicity or protection against coordinated rollback of both stores.

'''+failure_table+'''

'''+table+'''

See the [exact summary](../RESULTS.json), [design](../DESIGN.md) and [next work](../NEXT.md). Serialized I/O evidence import, configuration-aware promotion, public tooling, protected capacity and aggregate storage enforcement, prompt learning, persistent Arduino applications and actual device/driver/hub providers remain unfinished. The full HMS goal remains active.
''')
with (B/'README.md').open('x') as f:f.write('# Durable supervisor authority and run handoff\n\n[Design](DESIGN.md), [review](REVIEW.md), [exact results](results/README.md), [next integration work](NEXT.md).\n\nAll 50 new controls pass. The actual handoff worker remains incomplete at its original deadline, and the 206-method compatibility batch times out. This isolated candidate is not a public-service or physical-control qualification. The full HMS goal remains active.\n\n[Original source](implementation01/index.json), [test-only history extension](implementation02/index.json), [machine-readable results](RESULTS.json).\n')
print(json.dumps({k:v for k,v in analysis.items() if k not in ('attempts','failedMethods','incompleteSelectionTargets')}))

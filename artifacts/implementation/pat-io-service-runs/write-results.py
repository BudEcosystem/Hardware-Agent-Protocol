"""Reconcile all exact scopes without converting retained failures into passes."""
import json
from pathlib import Path

ROOT = Path.cwd()
B = ROOT/'artifacts/implementation/pat-io-service-runs'
R = B/'results'
PIN = '8086023d524443fb617b654ad7573f1ef25a7388e12f991d28457457a720ba8d'

def read(path):
    return json.loads(path.read_bytes())

def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2)+'\n')

selected = set()
for number in range(1, 17):
    selected.update(read(B/('harness%02d'%number)/'targets.json')['targets'])
assert len(selected) == 279
entries = []
tested, passed, failed = set(), set(), set()
captured = []
for folder in sorted(R.iterdir()):
    if not (folder/'proof.json').exists():
        continue
    proof = read(folder/'proof.json')
    result = read(folder/'attempt/result.json')
    targets = read(folder/'attempt/actual-tests.json')['executed']
    assert proof['status'] == result['status'] and result['childState'] == 'exited'
    assert result['errors'] == result['childErrors'] == []
    assert proof['sourceIndexSha256'] == PIN
    assert (proof['sourceFilesVerified'], proof['frozenFilesVerified'], proof['externalPinsVerified']) == (246, 249, 159)
    tested.update(targets)
    if proof['status'] == 'passed':
        assert not passed.intersection(targets)
        passed.update(targets)
    else:
        assert len(targets) == 1
        failed.update(targets)
        failure = read(folder/'failure-audit.json')
        assert (failure.get('preCrashReason', failure['archive']['supervisorReason']) == 'SUPERVISOR_DEADLINE'
                or failure.get('workerFailureCode') == 'PAT_IO_GROUP_WALL_LIMIT')
        assert not failure['qualificationPassed'] and failure['ledgerUnchanged']
    storage = read(folder/'storage-audit.json')
    assert storage['databaseBytesUnchanged']
    item = {k: proof[k] for k in ('attempt', 'harness', 'status', 'counts', 'testSeconds',
            'elapsedSeconds', 'sourceIndexSha256', 'rawScratch', 'rawScratchFiles', 'rawScratchBytes')}
    item.update(destination=folder.name, attemptFiles=proof['attemptFilesAcquired'],
                actualOrigins=proof['actualOrigins']['recordCount'],
                parentSqliteConnections=proof['sqliteConnections'], databases=len(storage['databases']))
    for name in ('process-audit.json', 'failure-audit.json'):
        if (folder/name).exists():
            process = read(folder/name)
            item.update(processAudit=name, states=process['states'], effects=process['effects'],
                        claims=process['claims'], owners=process['owners'],
                        transportComplete=process['archive']['transportComplete'],
                        unresolvedEffects=process['archive']['unresolvedEffects'])
            if name == 'process-audit.json':
                item.update(groupStatus=process['groupStatus'], completedCases=process['completedCases'])
                if process['groupStatus'] == 'captured':
                    captured.append(folder.name)
            else:
                item.update(groupStatus=process.get('groupStatus', 'incomplete'), completedCases=process.get('completedCases'),
                            supervisorReason=process['archive']['supervisorReason'],
                            preCrashReason=process.get('preCrashReason'), workerFailureCode=process.get('workerFailureCode'))
    entries.append(item)
assert len(entries) == 17 and tested == selected
assert len(passed) >= 267 and not passed.intersection(failed)
reserved = 'test_io_service_runs.IoReservedProcessTests.test_reserved_owned_group_replays_after_config_and_session_change'
assert reserved in failed and reserved not in passed
new_controls = set(read(B/'harness14/targets.json')['targets']) | set(read(B/'harness15/targets.json')['targets'])
assert len(new_controls) == 29 and new_controls <= passed
inherited_controls = set(read(B/'harness01/targets.json')['targets']) | set(read(B/'harness12/targets.json')['targets'])
assert len(inherited_controls) == 238 and inherited_controls <= passed
for folder in ('attempt03-failed-reserved-owned', 'attempt04-failed-diagnostic-reserved'):
    run = read(R/folder/'run-audit.json')
    assert run['validatedRuns'] == 1 and run['validatedDocuments'] == 37
    assert run['completedWorker'] is False and run['postWorkerReplayReached'] is False
analysis = dict(scope='Durable original I/O run reservations; controls and distinct inherited process regression, with unresolved reserved-worker deadline failure.',
    goalStatus='active', sourceIndexSha256=PIN, selectedDistinctMethods=len(selected),
    distinctTestedMethods=len(tested), distinctPassingMethods=len(passed), distinctFailingMethods=len(failed),
    failingMethods=sorted(failed), unexecutedMethods=sorted(selected-tested),
    totalMethodExecutions=sum(x['counts']['testsRun'] for x in entries),
    retainedFailedAttempts=sum(x['status'] == 'failed' for x in entries),
    newReservationControlMethods=29, reservationControlsVerified=True,
    reservedWorkerEndToEndVerified=False, postWorkerConfigurationSessionReplayVerified=False,
    publicServiceMounted=False, completedInheritedGroups=captured, attempts=entries,
    qualificationPassed=False, physicalValidation=False, aggregateFilesystemQuotaEnforced=False)
write(B/'RESULTS.json', analysis)

for item in entries:
    folder = R/item['destination']
    links = []
    for name, label in [('authority-audit.json', 'Authority history'), ('run-audit.json', 'Reservation/input joins'),
                        ('process-audit.json', 'Process/image/outcome audit'), ('failure-audit.json', 'Failure audit'),
                        ('control-audit.json', 'Retained corruption audit'), ('authority-service-audit.json', 'Authority-to-worker joins'),
                        ('diagnostic-summary.json', 'Passive diagnostic'), ('state-audit.json', 'Retained states')]:
        if (folder/name).exists():
            links.append('['+label+']('+name+')')
    with (folder/'README.md').open('x') as stream:
        stream.write('# '+item['attempt']+'\n\n'+item['status']+': '+str(item['counts']['testsRun'])+' methods, '+
            str(item['counts']['failures'])+' failures, '+str(item['counts']['errors'])+' errors. '+
            '[Exact acquisition](proof.json), [retained output](attempt/output.log), [storage audit](storage-audit.json). '+
            '; '.join(links)+'.\n\nOriginal raw state and complete copies remain retained. '+
            ('A worker time-limit failure is retained in its archive, pre-crash receipt or failed group return; no complete-group or later replay claim follows. ' if item['status']=='failed' else '')+
            'No public or physical qualification is claimed.\n')
table = '| Attempt | Methods | Result | Test seconds |\n|---|---:|---|---:|\n'+'\n'.join(
    '| ['+x['attempt']+']('+x['destination']+'/README.md) | '+str(x['counts']['testsRun'])+' | '+x['status']+' | '+str(x['testSeconds'])+' |' for x in entries)
with (R/'README.md').open('x') as stream:
    stream.write('''# Durable logical I/O run results

**'''+str(len(passed))+' of 279 distinct methods pass; '+str(len(failed))+''' distinct methods fail.** All 267 control methods pass, including 29 new reservation controls. All selected methods were executed; 17 retained attempts include the extra passive diagnostic. The reserved-worker method failed in both its ordinary and diagnostic attempts at the original 60-second worker deadline. The later configuration/session-change replay portion was not reached. There is no end-to-end reserved-worker acceptance claim.

The store shares the existing Journal authority and atomically retains each logical run's candidate/configuration intent, request, receipt and complete original bundle. Exact replay precedes fresh planning, source, session and capacity checks, while current administrative authorization and retained-state validation remain mandatory. Changed intent under the same key conflicts. Controls cover concurrency, lost replies, rollback, lowered capacity, source/configuration/session drift, detached results and deliberately corrupt history. A reservation is an input commitment, not an execution receipt.

Independent read-only audits join the two failed workers to their original authority records and all 37 retained documents each. The first failure retains 12 synthetic states, seven activations, four completions, three cancellations and one claim; the diagnostic retains 16 states, ten activations, five completions, five cancellations and no claims. Neither has a complete return. Source authorities have zero device effects. No state was reset, repaired or relaunched.

The passive observer recorded 34.68 worker CPU seconds across a 59.118-second sampled interval. System CPU pressure was present, but this does not establish causality or a deployment capacity guarantee. It changed neither scheduling nor deadlines. The separate inherited regression methods exercise the expanded worker image and original recovery expectations; their successes cannot repair either reserved-worker failure.

The inherited owner-loss-after-settlement method also fails. Its original crash receipt records `SUPERVISOR_DEADLINE` before the planned owner exit; reopening archives `OWNER_LOST` with no worker return or known exit code. Eight retained states contain five activations, two completions, three cancellations and one claim. The complete-group and later replay assertions were not reached. The initial generic failure auditor rejected this different archive shape; its log is retained, and a separate read-only audit joins the pre-crash deadline to the recovered archive without changing the source or state.

The owner-loss-after-spawn method returns a canonical failed group with `PAT_IO_GROUP_WALL_LIMIT` at the unchanged 60,000 ms limit. It records 26 completed-case entries of the required 30, 23 retained states, fifteen activations, seven completions, eight cancellations and one claim. Its complete retained output closure is verified, but neither full semantic inspection nor the later replay assertions was reached. The separate failed-return auditor and the generic auditor's initial assertion-failure log are both retained. None of these partial results is promoted.

Every attempt verifies 246 project files, 249 frozen inputs, six active harness files and 159 external pins. Where created, code images contain 259 files, including eight supervisor sources and 157 runtime dependencies. All original limits remain. The source differs from its baseline only by the new run module/test and the supervisor source-list addition; inherited tests are unchanged. Primary-agent review only.

'''+table+'''

See the [exact summary](../RESULTS.json), [design](../DESIGN.md) and [next work](../NEXT.md). Public mounting, protected compute/storage capacity, durable supervisor-authority handoff, serialized evidence import and configuration-aware promotion remain unfinished. So do prompt learning, persistent Arduino applications and real device/driver/hub providers. The full HMS goal remains active.
''')
with (B/'README.md').open('x') as stream:
    stream.write('# Durable logical I/O run reservations\n\n[Design](DESIGN.md), [results](results/README.md), [frozen source](implementation01/README.md), [exact summary](RESULTS.json), [next work](NEXT.md).\n\n'+
        str(len(passed))+' of 279 distinct methods pass. All 267 controls pass; the new reserved-worker method reaches its original deadline in two retained attempts, and two inherited owner-loss methods fail after supervisor or worker time limits. Their later replay assertions are unreached. The implementation remains isolated and the full HMS goal remains active.\n')
print(json.dumps({k:analysis[k] for k in ('distinctTestedMethods', 'distinctPassingMethods', 'distinctFailingMethods', 'retainedFailedAttempts')}))

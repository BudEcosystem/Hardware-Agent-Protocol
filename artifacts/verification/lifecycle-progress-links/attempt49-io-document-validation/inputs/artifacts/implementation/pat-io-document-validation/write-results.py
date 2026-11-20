"""Reconcile this candidate's exact selection, including every retained failure."""
import json
from pathlib import Path

ROOT = Path.cwd()
B = ROOT/'artifacts/implementation/pat-io-document-validation'
R = B/'results'
PIN = '31118f7405fcce5f4828bf4d256faea21e61b6d5bae470632376d9c8c484c4c0'

def read(path):
    return json.loads(path.read_bytes())

def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2)+'\n')

selected, tested, passed, failed = set(), set(), set(), set()
for number in range(1, 18):
    targets = read(B/('harness%02d'%number)/'targets.json')['targets']
    assert not selected.intersection(targets)
    selected.update(targets)
assert len(selected) == 298
entries, captured = [], []
for folder in sorted(R.iterdir()):
    if not (folder/'proof.json').exists():
        continue
    proof, result = read(folder/'proof.json'), read(folder/'attempt/result.json')
    actual = read(folder/'attempt/actual-tests.json')
    targets = actual['executed']
    assert actual['loaded'] == targets and actual['exactSelection']
    assert proof['status'] == result['status'] and result['childState'] == 'exited'
    assert result['errors'] == result['childErrors'] == []
    assert proof['sourceIndexSha256'] == PIN
    assert (proof['sourceFilesVerified'], proof['frozenFilesVerified'], proof['externalPinsVerified']) == (248, 251, 159)
    assert not tested.intersection(targets)
    tested.update(targets)
    if proof['status'] == 'passed':
        passed.update(targets)
    else:
        assert len(targets) == 1
        failed.update(targets)
        failure = read(folder/'failure-audit.json')
        assert (failure.get('preCrashReason', failure['archive']['supervisorReason']) in {'SUPERVISOR_DEADLINE', 'SUPERVISOR_RETENTION_UNKNOWN'}
                or failure.get('workerFailureCode') == 'PAT_IO_GROUP_WALL_LIMIT')
        assert not failure['qualificationPassed'] and failure['ledgerUnchanged']
    storage = read(folder/'storage-audit.json')
    assert storage['databaseBytesUnchanged']
    item = {k:proof[k] for k in ('attempt', 'harness', 'status', 'counts', 'testSeconds',
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
            for key in ('inspectedStates', 'uninspectedStates', 'effectsComplete', 'observedEffects', 'observedClaims', 'observedOwners'):
                if key in process:
                    item[key] = process[key]
            if name == 'process-audit.json':
                item.update(groupStatus=process['groupStatus'], completedCases=process['completedCases'])
                if process['groupStatus'] == 'captured':
                    captured.append(folder.name)
            else:
                item.update(groupStatus=process.get('groupStatus', 'incomplete'), completedCases=process.get('completedCases'),
                            supervisorReason=process['archive']['supervisorReason'],
                            preCrashReason=process.get('preCrashReason'), workerFailureCode=process.get('workerFailureCode'))
    entries.append(item)
assert len(entries) == 17 and tested == selected and len(passed)+len(failed) == 298
controls = set()
for number in (1, 12, 14, 15, 17):
    controls.update(read(B/('harness%02d'%number)/'targets.json')['targets'])
assert len(controls) == 286 and controls <= passed
reserved = 'test_io_service_runs.IoReservedProcessTests.test_reserved_owned_group_replays_after_config_and_session_change'
assert reserved in passed and reserved not in failed
run = read(R/'attempt03-passed-reserved-owned/run-audit.json')
assert run['validatedRuns'] == 1 and run['validatedDocuments'] == 37
assert run['allDatabasesUnchanged'] and run['sourceAuthorityEffectsZero']
checks = list((R/'attempt03-passed-reserved-owned/attempt/scratch').glob('*/run-replay-checks.json'))
assert len(checks) == 1
replay = read(checks[0])
assert replay['replayWithoutPlanning'] and replay['sameSupervisorAttempt'] and replay['sourceEffectsUnchanged']
analysis = dict(scope='Bounded exact-byte canonical-document validation reuse with original current-storage reads and unchanged execution limits.',
    goalStatus='active', sourceIndexSha256=PIN, selectedDistinctMethods=298,
    distinctTestedMethods=len(tested), distinctPassingMethods=len(passed), distinctFailingMethods=len(failed),
    failingMethods=sorted(failed), unexecutedMethods=sorted(selected-tested),
    totalMethodExecutions=sum(x['counts']['testsRun'] for x in entries),
    retainedFailedAttempts=sum(x['status'] == 'failed' for x in entries),
    retainedAuditToolFailures=['attempt11-pwm-audit-failed-process.log'],
    canonicalControlMethods=19, allControlMethods=286, canonicalControlsVerified=True, reservationControlsVerified=True,
    reservedWorkerEndToEndVerified=True, postWorkerConfigurationSessionReplayVerified=True,
    deploymentDeadlineGuarantee=False, publicServiceMounted=False, completedGroups=captured, attempts=entries,
    qualificationPassed=False, physicalValidation=False, aggregateFilesystemQuotaEnforced=False)
write(B/'RESULTS.json', analysis)

for item in entries:
    folder = R/item['destination']
    links = []
    for name, label in [('authority-audit.json', 'Authority history'), ('run-audit.json', 'Reservation/input joins'),
                        ('process-audit.json', 'Process/image/outcome audit'), ('failure-audit.json', 'Failure audit'),
                        ('control-audit.json', 'Retained corruption audit'), ('authority-service-audit.json', 'Authority-to-worker joins'),
                        ('canonical-control-audit.json', 'Canonical-document controls'), ('service-audit.json', 'Configured-service joins'),
                        ('state-audit.json', 'Retained states')]:
        if (folder/name).exists():
            links.append('['+label+']('+name+')')
    with (folder/'README.md').open('x') as stream:
        stream.write('# '+item['attempt']+'\n\n'+item['status']+': '+str(item['counts']['testsRun'])+' methods, '+
            str(item['counts']['failures'])+' failures, '+str(item['counts']['errors'])+' errors. '+
            '[Exact acquisition](proof.json), [retained output](attempt/output.log), [storage audit](storage-audit.json). '+
            '; '.join(links)+'.\n\nOriginal raw state and complete copies remain retained. '+
            ('The original stop reason and incomplete evidence are retained. Complete-group or later replay assertions after the failed check are not claimed. ' if item['status']=='failed' else '')+
            'No public or physical qualification is claimed.\n')
table = '| Attempt | Methods | Result | Test seconds |\n|---|---:|---|---:|\n'+'\n'.join(
    '| ['+x['attempt']+']('+x['destination']+'/README.md) | '+str(x['counts']['testsRun'])+' | '+x['status']+' | '+str(x['testSeconds'])+' |' for x in entries)
def shown(value):
    return 'unknown' if value is None else str(value)

failure_table = '| Failed attempt | States | Activations/completions/cancellations | Claims/owners | Completed case entries |\n|---|---:|---|---|---|\n'+'\n'.join(
    '| ['+x['attempt']+']('+x['destination']+'/README.md) | '+str(x['states'])+' | '+
    '/'.join(shown(x['effects'][k]) for k in ('activations','completed','canceled'))+' | '+
    shown(x['claims'])+'/'+shown(x['owners'])+' | '+shown(x['completedCases'])+' |' for x in entries if x['status']=='failed')
with (R/'README.md').open('x') as stream:
    stream.write('''# Exact-byte document validation results

**'''+str(len(passed))+' of 298 distinct methods pass; '+str(len(failed))+''' methods fail.** All 286 control methods pass, including the 19 new canonical-document controls. Each selected method runs once in seventeen retained scopes. All original deadlines, effect/storage budgets, durable writes and complete 30-case group requirements remain unchanged.

The per-engine memo retains only successful validation of complete immutable byte strings, bounded to 64 entries and 128 KiB of key bytes. Original SQL schema/count/type/size checks and current row reads still execute on every snapshot. Changed documents must validate again. Selected parser/encoder dependency changes disable reuse; these compatibility guards are not complete Python-process attestation. No authority, session, permission, source-image verification or physical outcome is cached. Only one inherited production file changes; inherited tests remain byte-identical.

The reserved-worker method now completes all 30 cases, independent inspection and replay after configuration/session changes. A read-only audit joins its one reservation and all 37 documents to the original supervisor request/attempt; replay performs no new planning or second launch. The complete group retains 26 synthetic states, 21 activations, 11 completions, ten cancellations and no claims/owners. This fresh result neither repairs the preceding stage's failures nor proves a deadline guarantee on arbitrary hubs.

The owner-loss-after-settlement case still reaches the supervisor deadline before its planned owner exit. Recovery archives `OWNER_LOST` without a complete return or known exit code. The owner-loss-after-spawn case returns a canonical failed group with `PAT_IO_GROUP_WALL_LIMIT`, retaining 29 completed-case entries of 30. Authority-configured, legacy-configured and PWM cases also reach `SUPERVISOR_DEADLINE` with no return. Their partial states and original leases are retained and inspected read-only; no reset, repair or new logical-key retry occurs. Failed or incomplete groups are not promoted. All failures appear in the exact table and linked audits below.

The PWM failure retains one incomplete state with a transaction journal. Its bytes remain untouched and its logical state is not opened for recovery. Aggregate effects/claims/owners remain unknown. The fifteen inspectable states show ten activations, five completions, five cancellations and zero observed claims/owners; these observations cannot establish totals for the unknown state. The initial generic failure auditor raised a `TypeError` when it encountered the unknown fields. Its [log](../attempt11-pwm-audit-failed-process.log) and the subsequent [partial-state audit](attempt11-failed-pwm/failure-audit.json) are both retained; no test, source, limit or state was changed to obtain that audit.

The archive-commit owner-loss method stops for `SUPERVISOR_RETENTION_UNKNOWN`, a different condition from a deadline. Its pre-exit crash receipt exactly matches the retained archived record, with one worker and no complete return. The original collector maps any retention-scan exception to this reason without recording the exception details; the specific cause cannot be inferred from the terminal inventory. This case also retains fifteen inspectable states with ten activations, five completions and five cancellations, plus one uninspected transaction-bearing state. Overall effect/claim/owner totals remain unknown. Neither the scanner nor its limits was changed in this stage.

'''+failure_table+'''

The [duplication analysis](../analysis/retained-document-duplication.json) finds 7,768 hypothetical exact-input reuses among 9,000 validations in a preceding retained group. The focused 1,000-repeat observation performs one full validation instead of 1,000, with observed process CPU time about 0.083 s versus 1.013 s. This isolated work observation has no timing acceptance threshold and cannot establish the cause of process deadlines or deployed performance. The [host observation](../analysis/host-capacity-observation.json) describes the observer's visible affinity/cgroup ancestry; it reserves no worker capacity.

Each attempt verifies 248 project files, 251 frozen inputs, six harness files and 159 external pins. Created worker images contain 260 files, including eight supervisor sources and 157 runtime dependencies. Original raw state and exact acquired copies are retained. Primary-agent review only; no physical endpoint, MCU/emulator, live inference/service, acquired controller code or adjacent Harness checkout is used.

'''+table+'''

See the [exact summary](../RESULTS.json), [design](../DESIGN.md) and [next work](../NEXT.md). Durable supervisor-store identity and admission handoff, public service mounting, protected capacity, evidence import/promotion, prompt learning, persistent Arduino applications and real device/driver/hub providers remain unfinished. The full HMS goal remains active.
''')
with (B/'README.md').open('x') as stream:
    stream.write('# Bounded reuse of canonical-document validation\n\n[Design](DESIGN.md), [results](results/README.md), [frozen source](implementation01/README.md), [exact summary](RESULTS.json), [next work](NEXT.md).\n\n'+
        str(len(passed))+' of 298 methods pass, including all 286 controls. The reserved-worker group and configuration/session replay pass; '+str(len(failed))+' process methods retain deadline or retention-scan failures. This isolated candidate provides no deployment deadline guarantee. The full HMS goal remains active.\n')
print(json.dumps({k:analysis[k] for k in ('distinctTestedMethods', 'distinctPassingMethods', 'distinctFailingMethods', 'retainedFailedAttempts')}))

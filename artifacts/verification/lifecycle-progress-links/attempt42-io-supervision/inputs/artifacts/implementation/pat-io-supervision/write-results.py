"""Reconcile complete attempts, owned-run audits and retained failures."""
import json
from pathlib import Path

ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision';R=B/'results'
def read(p):return json.loads(p.read_bytes())
names=['attempt01-failed160','attempt02-passed160','attempt03-failed-setup','attempt04-passed160','attempt06-acquired-gpio']
entries=[];passed=set()
for name in names:
    folder=R/name;p=read(folder/'proof.json');result=read(folder/'attempt/result.json')
    assert p['status']==result['status'] and result['childState']=='exited' and result['errors']==result['childErrors']==[]
    assert p['sourceFilesVerified']==237 and p['frozenFilesVerified']==240 and p['externalPinsVerified']==159
    assert p['actualOrigins']['allOriginsMatched']
    if p['status']=='passed':passed.update(read(folder/'attempt/actual-tests.json')['executed'])
    entries.append(dict(destination=name,attempt=p['attempt'],status=p['status'],counts=p['counts'],testSeconds=p['testSeconds'],elapsedSeconds=p['elapsedSeconds'],
        sourceIndexSha256=p['sourceIndexSha256'],harnessIndexSha256=p['harnessIndexSha256'],rawScratch=p['rawScratch'],
        rawScratchFiles=p['rawScratchFiles'],rawScratchBytes=p['rawScratchBytes'],attemptFiles=p['attemptFilesAcquired'],
        actualOrigins=p['actualOrigins']['recordCount'],parentSqliteConnections=p['sqliteConnections']))
    (folder/'README.md').write_text(f'''# {p['status'].title()} {p['counts']['testsRun']}-method attempt

[Proof](proof.json), [complete log](attempt/output.log), [terminal result](attempt/result.json).
{p['counts']['testsRun']}methods; {p['counts']['failures']}failures; {p['counts']['errors']}errors;
{p['testSeconds']:.3f}test seconds and {p['elapsedSeconds']:.3f}s harness elapsed, within180s.
All237project/240frozen inputs,6active harness inputs and159external pins remain unchanged;
{p['actualOrigins']['recordCount']}actual origins match. Parent ledger opens: {p['sqliteConnections']}.
Raw scratch retains {p['rawScratchFiles']}files/{p['rawScratchBytes']}bytes, with a complete verified copy.

See [validation correction](../../CORRECTION.md), [private fixture correction](../../SETUP-CORRECTION.md)
and [acquisition correction](../../ACQUISITION-CORRECTION.md) for the preserved failures.
No physical device, MCU, inference or live service runs in this scope. A passing
supervisor transport result does not qualify a PAT or enforce aggregate storage.
''')
assert len(passed)==161
owned=read(R/'attempt06-acquired-gpio/owned-audit.json');storage=read(R/'attempt06-acquired-gpio/storage-audit.json')
assert owned['cases']==30 and owned['states']==26 and owned['claims']==owned['owners']==0
assert owned['codeImageExactClosure'] and owned['archive']['transportComplete'] and not owned['qualificationPassed']
assert len(storage['databases'])==53 and storage['databaseBytesUnchanged']
current=entries[-1];summary=owned['independentSummary'];charges=owned['groupAccounting']['charged']
with (R/'attempt06-acquired-gpio/README.md').open('a') as f:f.write('''
The [owned-run audit](owned-audit.json) independently matches the durable ledger,
pre-launch input and launch envelope, original lease identity, worker result and
complete output digest. The256-file private code image exactly matches its
source/resource/seven-package inventory, including157dependency files.
[State audit](state-audit.json) finds26states,21activations,11completions,10cancellations,
zero claims and owners. [Storage audit](storage-audit.json) checks53unchanged
databases:52compact case databases and the separate4096-byte-page supervisor ledger.
The test independently inspects all30cases, confirms replay before/after reopen,
and rejects changed same-key input. Supervisor archive semantic qualification
and quota flags remain false; unresolved effects are not inferred from transport.
''')
(R/'attempt05-passed-gpio/README.md').write_text('# Acquisition stopped on ordering\n\n[Failure record](failure.json), [correction](../../ACQUISITION-CORRECTION.md).\nThe completed test was not rerun. All4,269raw/copy/index entries match; the fresh acquisition is [here](../attempt06-acquired-gpio/README.md).\n')
analysis=dict(scope='161distinct methods:160pure and one real owned GPIO group with independent semantics. No public/physical qualification.',
    distinctPassingMethods=161,currentPureMethods=160,currentProcessMethods=1,attempts=entries,completedGroupCases=30,
    supervisorTransportComplete=True,independentGroupInspection=True,supervisedPwmExecuted=False,source03ProductionMatchesSource02=True,
    outputClosure=owned['outputClosure'],codeImageFiles=owned['codeImageFiles'],codeImageBytes=owned['codeImageBytes'],
    groupAccounting=charges,endpointEffects=owned['endpointEffects'],claims=0,owners=0,databases=53,databaseBytes=storage['totalBytes'],
    acquisitionFailurePreserved=True,originalsAndCopiesRetained=True,configurationAttested=False,actualAggregateStorageEnforced=False,
    publicQualificationMounted=False,qualificationPassed=False,physicalMeasurementChecked=False)
(B/'RESULTS.json').write_text(json.dumps(analysis,indent=2)+'\n')
table='\n'.join(f"| [{e['destination']}]({e['destination']}/README.md) |{e['counts']['testsRun']-e['counts']['errors']-e['counts']['failures']}pass /{e['counts']['errors']}errors |{e['testSeconds']:.3f}|{e['rawScratchFiles']} /{e['rawScratchBytes']}|" for e in entries)
(R/'README.md').write_text(f'''# Owned finite I/O supervision:161 distinct checks pass

The [current source03](../implementation03/README.md) passes160pure checks and one
actual owned GPIO integration method. The latter captures all30cases for the
representative constant single-step candidate and independently inspects their
complete histories. It verifies private inputs before launch, exclusive owner
admission, actual attempt/run association, exact replay before and after reopening,
and changed-same-key refusal. The source02/03production is identical.

| Attempt | Result | Test seconds | Raw files / bytes |
|---|---|---:|---:|
{table}

The full test takes {current['testSeconds']:.3f}s including setup, image creation,
capture, archival, replay and independent inspection. The original60s supervisor/
group deadlines and180s test-parent deadline remain; this is not a timing benchmark
or wall-clock attestation. The archive verifies {owned['outputClosure']['fileCount']}output files,
{owned['outputClosure']['bytes']}bytes. The256-file private image is3,918,651bytes with
the complete selected157-file dependency inventory. Raw acquisition retains
4,269files/19,309,515bytes under this separate supervisor integration's256MiB
acquisition scope; the pure harness remains16MiB, attempt reservation64MiB and
group-derived bound20MiB. None is an actual filesystem quota.

Read-only audits verify53unchanged databases and26case states with21activations,
11completions,10cancellations, zero claims and owners. The group accounts for
{charges['actualChildOperations']}operations, {charges['reservedChildOperations']}reserved admissions,
{charges['schedulerTicks']}ticks and {charges['records']}worker records. Failed challenge
completion objectives remain failed even when their expected fault response passes.
The initial validation error, unsafe fixture ancestor and acquisition-order mismatch
are retained with corrections. The completed worker was not rerun for acquisition.

This is isolated synthetic supervision, not public or physical qualification.
Trusted fixed service configuration, hard aggregate storage, supervised PWM,
I/O-specific owner-loss/interruption/limit failures and serialized public import
remain. The broader prompt-to-PAT learning, persistent Arduino applications,
real device/driver/intelligence-hub providers and microscope objective stays active.
''')
(B/'README.md').write_text('# Finite I/O supervision\n\n[Design](DESIGN.md), [results](results/README.md), [current source](implementation03/README.md).\n[Validation correction](CORRECTION.md), [fixture correction](SETUP-CORRECTION.md), [acquisition correction](ACQUISITION-CORRECTION.md).\n')
print(json.dumps(dict(distinctPassingMethods=161,groupAccounting=charges,output=owned['outputClosure'],databaseBytes=storage['totalBytes'])))

"""Reconcile instrumented diagnostic runs without erasing nominal failures."""
import json
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision-profile';R=B/'results'
def read(p):return json.loads(p.read_bytes())
entries=[]
for name in ('attempt01-profiled-pwm','attempt02-profiled-worker-failed'):
 F=R/name;p=read(F/'proof.json');r=read(F/'attempt/result.json');assert r['childState']=='exited'and r['errors']==r['childErrors']==[]
 entries.append(dict(destination=name,harness=p['harness'],attempt=p['attempt'],status=p['status'],counts=p['counts'],testSeconds=p['testSeconds'],elapsedSeconds=p['elapsedSeconds'],rawScratch=p['rawScratch'],rawScratchFiles=p['rawScratchFiles'],rawScratchBytes=p['rawScratchBytes'],attemptFiles=p['attemptFilesAcquired'],actualOrigins=p['actualOrigins']['recordCount'],bytecodeReadsRefused=p['bytecodeReadsRefused'],parentSqliteConnections=p['sqliteConnections'],sourceIndexSha256=p['sourceIndexSha256'],harnessIndexSha256=p['harnessIndexSha256']))
 audits=sorted(F.glob('*audit.json'))
 (F/'README.md').write_text(f"# {p['status'].title()} instrumented diagnostic\n\n[Proof](proof.json), [complete log](attempt/output.log), [terminal result](attempt/result.json).\n\nOne original PWM method; {p['counts']['failures']} failures; {p['testSeconds']:.3f} test seconds. All 239 project/242 frozen inputs, six active harness files and159 external pins remain stable. Raw originals and copies retain {p['rawScratchFiles']}files/{p['rawScratchBytes']}bytes.\n\n"+' '.join(f'[{q.stem}]({q.name})'for q in audits)+"\n\nSee [stage results](../README.md). Instrumentation changes timing and is not a production optimization or qualification claim.\n")
parent=read(R/'attempt01-profiled-pwm/attempt/profile.json');owned=read(R/'attempt01-profiled-pwm/process-audit.json')
assert owned['completedCases']==30 and owned['states']==26 and owned['claims']==owned['owners']==0
F=R/'attempt02-profiled-worker-failed';worker_file=next((F/'attempt/scratch').glob('*/supervisor/*/worker-profile.json'));worker=read(worker_file);partial=read(F/'worker-profile-audit.json')
assert worker['reason']=='SIGTERM'and partial['retainedCaseManifests']==10 and partial['completeStatePairs']==6
parent_metrics={k:parent[k]for k in ('wallSeconds','parentCpuSeconds','childUserSeconds','childSystemSeconds','totalFunctions')}
worker_metrics={k:worker[k]for k in ('reason','wallMicroseconds','cpuMicroseconds','totalFunctions')}
analysis=dict(scope='Two separate bounded diagnostic profiles of the original PWM method; no production performance fix.',attempts=entries,parentProfile=parent_metrics,workerProfile=worker_metrics,parentCaseCount=30,parentIndependentInspection=True,parentProductionUnchanged=True,workerChangedFiles=['supervisor/worker_entry.py'],workerCaseDirectories=partial['retainedCaseDirectories'],workerCaseManifests=partial['retainedCaseManifests'],workerCompleteStatePairs=6,originalNominalFailuresResolved=False,preciseFailureCauseEstablished=False,originalsAndCopiesRetained=True,publicQualificationMounted=False,actualAggregateStorageEnforced=False,qualificationPassed=False,goalStatus='active')
(B/'RESULTS.json').write_text(json.dumps(analysis,indent=2)+'\n')
worker_link=worker_file.relative_to(F).as_posix()
(R/'README.md').write_text(f'''# Supervised I/O profiling evidence

The parent-instrumented original PWM test passes: all30cases complete, independent
inspection succeeds, and exact replay before/after reopen and same-key conflict
checks pass. Source and request semantics are unchanged. It takes157.708test seconds
(163.036s including harness collection), within the original180s outer bound.
The supervisor/group still use60s. Parent timing includes61.963s in collection,
which includes archival after producer settlement, and64.801s in independent
history inspection. These cumulative values overlap with their callees.

| Diagnostic | Test result | Raw files / bytes | Parent SQL opens |
|---|---|---:|---:|
| [Parent profile](attempt01-profiled-pwm/README.md) | 1 pass |4269 /19551533|2|
| [Worker profile](attempt02-profiled-worker-failed/README.md) | 1 failure, original deadline |1198 /8004907|1|

The [parent profile](attempt01-profiled-pwm/attempt/profile.json) records1767tree
scans (24.396 cumulative profiled seconds), about2.89million DirEntry.stat calls,
and86089canonical encodings (61.842 cumulative profiled seconds across the whole
test). Parent CPU is121.061s; reaped child CPU is35.150s. The profile is not a
controlled benchmark or proof of the cause of earlier deadline failures.
Read-only audits verify the exact256-file image,3936output files/14,821,081bytes,
26states/53databases,21activations,11completions,10cancellations and zero observed
claims/owners. The original uninstrumented PWM failure remains authoritative
negative evidence for its own attempt; this pass does not repair or replace it.

The separate [worker profile](attempt02-profiled-worker-failed/{worker_link})
changes only the worker entry to profile run_io_group. The parent is uninstrumented.
A bounded receipt is attempted on SIGTERM, then the worker raises SIGTERM to itself
with default disposition; the original parent stop/kill grace remains. The actual
archive recordsexit-15, SUPERVISOR_DEADLINE, no group return, false transport/semantic
qualification and unknown unresolved effects. The11,841-byte profile is associated
with the exact private image, source identity, retained input and physical attempt.
All238other source files and the original test remain unchanged.

That worker profile records53.451s wall/42.847s CPU over907functions before
interruption. It observes12739canonical encodings (26.975 cumulative seconds),
71installation normalizations (6.054s),10runtime openings (21.028s), and452binding
proof calculations (7.574s). These are overlapping instrumented times, not sums.
It retains11case directories,10manifests, six complete state pairs and an incomplete
authority-only state for case10. Observed complete pairs have4activations,
2completions and2cancellations; no aggregate effect-resolution claim follows.
All14databases retain their original bytes. No old mutation is retried or repaired.

Both runs keep the original selected239project/242frozen inputs,6active harness
files and159external pins stable. Their837/831 actual origin inventories are
recorded precisely in the proofs; system libraries are not a complete attested
runtime closure. The original60s/180s deadlines,32-case,20MiBderived-output,
64MiBattempt,256MiBroot and collection limits remain. No physical device, MCU,
inference, acquired controller or live service executes.

[Next decision](../NEXT.md): investigate bounded reuse of pure installation
normalization with exact original-type/byte checks, current source revalidation,
dependency invalidation and detached results. No authority state or validation
boundary may be skipped. The memo is not implemented here; scanning is not slowed
and the general JCS encoder is not changed. The original PWM/archive-commit
nominal failures remain unresolved, and the full end-to-end goal remains active.
''')
(B/'README.md').write_text('# Supervised I/O profiles\n\n[Design](DESIGN.md), [results](results/README.md), [next decision](NEXT.md). No production performance fix or physical qualification.\n')
block='''\nThe [supervised I/O profiles]({prefix}artifacts/implementation/pat-io-supervision-profile/results/README.md)
separate parent collection/reduction cost from worker execution. The instrumented
parent test completes and independently checks all30PWMcases; the separate worker
profile reaches the original deadline with10manifests and an incomplete next state.
Repeated canonical serialization, runtime reconstruction and installation validation
are measured optimization targets. The original uninstrumented PWM and archive-commit
failures remain preserved and unresolved. No production optimization, quota change,
validation bypass or physical qualification is claimed. The next candidate is bounded
reuse of pure installation normalization, with current source checks and strict
input/dependency invalidation, before uninstrumented regression testing.\n'''
for name,prefix in [('docs/prompt-to-pat.md','../'),('docs/io-driver-hub-control.md','../')]:
 p=ROOT/name;text=p.read_text();assert 'The [supervised I/O profiles]'not in text;p.write_text(text+'\n'+block.format(prefix=prefix))
p=ROOT/'PROGRESS.md';text=p.read_text();anchor='The separate [qualification supervisor rebase]';assert text.count(anchor)==1;p.write_text(text.replace(anchor,block.format(prefix='')+'\n'+anchor))
p=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';text=p.read_text();anchor='Profile and address these failures before treating those paths as complete.';assert text.count(anchor)==1;p.write_text(text.replace(anchor,'The [separate parent/worker profiles](../pat-io-supervision-profile/results/README.md) now measure repeated serialization, setup and tree-scan work; the [next design](../pat-io-supervision-profile/NEXT.md) investigates bounded pure installation reuse. No production fix exists yet. Address the nominal failures before treating those paths as complete.'))
print(json.dumps(analysis))

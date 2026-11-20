"""Reconcile actual failed full groups, successful cutoffs and measured costs."""
from pathlib import Path
import json
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-group-worker';R=B/'results'
names=['attempt01-passed11','attempt02-failed-gpio-acquired','attempt03-passed12',
       'attempt04-failed-gpio-deadline','attempt05-passed-cutoff','attempt06-profiled-cutoff']
proofs=[json.loads((R/n/'proof.json').read_bytes())for n in names]
assert [p['status']for p in proofs]==['passed','failed','passed','failed','passed','passed']
assert [p['counts']['testsRun']for p in proofs]==[11,1,12,1,1,1]
table='\n'.join('| ['+p['attempt']+']('+n+'/proof.json) | '+p['status']+' | '+str(p['counts']['testsRun'])+' | '+str(p['testSeconds'])+' | '+str(p['rawScratchBytes'])+' |'for n,p in zip(names,proofs))
(R/'README.md').write_text('''# Shared current-group capture: bounded failures retained

The coordinator now attempts one exact current-candidate matrix, with evidence,
configuration, manifests, admissions, scheduler ticks and deadline checks sharing
one ledger. **The complete group has not passed.** The current corrected source
has 13 distinct passing methods: 12 pure/preflight methods and one actual
record-cutoff method. Profiling repeats that cutoff method; it is not an additional
distinct passing case. The full GPIO method fails at the original group deadline.
PWM remains unexecuted pending correction of the shared performance cost.

| Attempt | Result | Methods | Test seconds | Raw scratch bytes |
|---|---|---:|---:|---:|
'''+table+'''

The [first full-group failure](attempt02-failed-gpio-acquired/proof.json) completed
the candidate and extra-parameter refusal, then found a real coordinator error:
the planner represents nonapplicability with no error code, while compilation
returns `PAT_NOT_APPLICABLE`. [Source02](../implementation02/README.md) maps that
exact distinction, retains actual compiler codes separately from static outcomes,
and adds a pure check of all four negative cases. The planner, compiler, runtime,
fault schedules and budget rules remain unchanged. The [diagnosis](../DIAGNOSIS.json)
and exact [two-file correction](../negative-result-correction.patch) are retained.

The corrected full GPIO attempt completes **12 of 30 cases** before the original
60-second group boundary refuses further capture. Its active case is
`latest_start_before`, index 12. The [deadline diagnosis](../DEADLINE-DIAGNOSIS.json)
retains 1,160 charged records, 3,108,990 charged producer bytes, eight completed-case
operations and 29 charged scheduler ticks. Actual scratch is 6,879,179 bytes,
including the unfinished case's state. The ledger's after-close state accounting
does not include that unfinished case; it is not a hard filesystem quota.
The final bounded failure receipt survives. No remaining case is run and no
qualified result is returned. The 62.808-second test includes setup outside the
group and terminal work; checked group boundaries are not hard preemption.

The actual reduced-record test stops at **250 charged records**, retaining 258
scratch files including two private runtime states. Later cases do not start and
the populated group directory cannot be reused. The reserved terminal document
is included in the record ceiling and charged conservatively at 65,536 bytes.
Read-only [deadline-state inspection](attempt04-failed-gpio-deadline/state-audit.json)
finds six activations, three completed cycles, three cancellations and no retained
claims/board owners across nine created states; the unfinished case has no child
or effect. The [cutoff-state inspection](attempt05-passed-cutoff/state-audit.json)
finds the completed candidate and a canceled unactivated child. These endpoint
observations do not replace complete-history validation or prove the remaining
matrix cases.

The [diagnostic profile](attempt06-profiled-cutoff/attempt/profile.json) covers the
same cutoff test after imports. Its 26.981 seconds include profiler overhead;
the ordinary test took 11.919 seconds. Repeated topology parsing accounts for
285 calls and 13.672 cumulative seconds in this sampled path. JSON Schema and
canonical serialization also appear prominently; cumulative timings overlap.
The [analysis](../PROFILE-ANALYSIS.json) directs the next change toward bounded
reuse of exactly validated topology/schema bytes and current matrix setup, while
preserving strict input types, detached outputs, validation and identity checks.
No optimization has yet been implemented or verified.

Every executed attempt preserves 217 project files, 220 frozen entries, six active
harness inputs and 159 selected external pins. Ordinary attempts have 722 matched
origin records and 221 refused bytecode reads; the profiler has 727/223. No
prohibited attempt occurs. Complete attempt copies and original raw scratch roots
are retained. Source/compiler/driver identities are stable within every attempt;
source02's worker/driver identity changes from source01 and is never presented as
the old deployment. Read-only state inspection verifies database hashes unchanged.

The first acquisition of the single-test failure encountered a plural-only log
regex. Its [failed acquisition record](attempt02-failed-gpio/acquisition-error.json)
remains. The one-line [acquirer correction](../acquire02.patch) accepts `test` or
`tests` for the exact observed count and acquires into a fresh destination.
No test or producer is restarted for acquisition. Prepared source01 PWM/cutoff
and source02 PWM harnesses remain unexecuted.

All original group and harness ceilings remain. Live HMS, physical devices,
drivers, hub providers and the adjacent Harness are untouched. Primary-agent
review was used because existing helpers remain usage-limited. Complete group
execution, independent outcome composition, current configuration/run association,
actual aggregate filesystem quotas, persistent service and public qualification
remain unfinished. See [design](../DESIGN.md) and
[qualification work](../../pat-io-outcome-history/NEXT-QUALIFICATION.md).
''')
p=B/'DESIGN.md';s=p.read_text();s+='''
The [actual results](results/README.md) retain a coordinator mapping failure,
its correction, twelve passing pure/preflight methods, a passing real cutoff,
and a full GPIO attempt that reaches12of30 cases before the unchanged60-second
deadline. The repeated cutoff profile identifies validation reuse as the next
performance investigation. No full GPIO/PWM group has passed.
''';s=s.replace('reaches12of30','reaches 12 of 30').replace('unchanged60-second','unchanged 60-second');p.write_text(s)
p=ROOT/'PROGRESS.md';s=p.read_text();marker='The separate [qualification supervisor rebase]';assert s.count(marker)==1
addition='''The [current I/O group coordinator](artifacts/implementation/pat-io-group-worker/results/README.md)
now attempts the exact combined matrix with one shared capture ledger. All 25
fixed challenges and candidate cases are connected. Ordered single-engine
tickets enforce program identity, before-write evidence charging, per-case child
reservations, combined scheduler ticks and the original group clock. A terminal
receipt is reserved before effects. Closed state sizes enter derived accounting;
SQLite/WAL growth still lacks a hard filesystem quota.

The current source has **13 distinct passing methods**: 12 pure/preflight checks
and one actual 250-record cutoff. The complete GPIO group **does not pass**:
it completes 12 of 30 cases, then refuses at the original 60-second boundary.
Its 6,879,179 raw bytes, incomplete case and bounded failure receipt remain. A
read-only audit finds six activations, three completed cycles, three cancellations
and zero retained claims/owners across nine created states; the active thirteenth
case has no child/effect. This does not establish remaining matrix coverage.
PWM is deferred until the shared performance cost is corrected.

The earlier full-group failure exposed a real nonapplicability/error-code mapping
bug after two completed cases. Source02 fixes only that mapping and its tests;
the original failure and all state remain. A plural-only single-test acquisition
regex also failed before copying; its one-line correction and fresh acquisition
are retained. No producer rerun was needed for acquisition. All six executed
attempts keep 217 project inputs, 220 frozen entries, six harness files and159
external pins stable, with matched actual origins and unchanged within-attempt
compiler/driver identities. Original deadlines and storage ceilings are preserved.

Profiling the same passing cutoff test identifies 285 topology parses and13.672
cumulative seconds inside a26.981-second instrumented test; cumulative timings
overlap and profiling adds overhead. The next change should remove redundant
validation of exact immutable inputs without changing accepted documents or
authority checks. No such optimization is yet verified. Complete group outcomes,
attestation, aggregate filesystem enforcement, public qualification, learning,
persistent Arduino controllers and physical device/driver/hub controls remain
unfinished. Live HMS and the adjacent Harness stay unchanged.

'''.replace('and159','and 159').replace('and13.672','and 13.672').replace('a26.981','a 26.981')
s=s.replace(marker,addition+marker);p.write_text(s)
p=ROOT/'docs/prompt-to-pat.md';s=p.read_text();marker='An operator says, for example,';assert s.count(marker)==1
s=s.replace(marker,'''The [current-group capture coordinator](../artifacts/implementation/pat-io-group-worker/results/README.md)
connects the exact candidate/fixed matrix under one ledger. Twelve pure checks
and an actual record-cutoff check pass. The complete GPIO attempt reaches 12 of
30 cases before its original deadline, so it remains incomplete and cannot
qualify a PAT. Profiling identifies repeated topology/schema validation for the
next performance correction. No limit was widened or failed evidence discarded.

'''+marker);p.write_text(s)
p=ROOT/'docs/io-driver-hub-control.md';s=p.read_text();s+='''
The [current I/O group coordinator](../artifacts/implementation/pat-io-group-worker/results/README.md)
now applies shared capture accounting across the exact matrix. Its actual
record-limit cutoff passes and preserves state. The full GPIO group stops after
12 of 30 cases at the original deadline, so group qualification is still
unfinished. Profiling points to repeated topology/schema validation. Serialized
evidence charging does not provide a hard SQLite/WAL quota or physical timing.
''';p.write_text(s)
p=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';s=p.read_text()
old='| Group budgets and retained evidence | Current trial has 4,096 combined records, 16 MiB, 64 KiB documents, 2,048 ticks and 60-second wall limit | Enforce these at group scope with 32-case/512-operation preflight and 20 MiB derived-closure accounting. Per-trial limits alone do not establish aggregate admission |'
new='| Group budgets and retained evidence | The [current coordinator](../pat-io-group-worker/results/README.md) applies shared serialized-evidence, ticket, tick and deadline accounting with a pre-reserved failure receipt; the real250-record cutoff passes | Full GPIO reaches only12of30 cases before the original60-second deadline. Optimize measured redundant validation without widening limits, then finish exact group execution and outcome checks. Closed-state size accounting is not a hard SQLite/WAL quota; enforce actual aggregate storage before public qualification |'.replace('real250','real 250').replace('only12of30','only 12 of 30').replace('original60','original 60')
assert old in s;s=s.replace(old,new)
s=s.replace('The next implementation binds them to exact current-candidate\ngroup execution, uses the new selected compiler identity within complete trusted\nsetup attestation, and enforces aggregate budgets',
    'The current coordinator now attempts exact current-candidate group capture but\nstops at12of30 cases on its original deadline. The next implementation corrects\nthe measured repeated-validation cost, completes every case, joins the independent\noutcomes and trusted current setup, and finishes actual aggregate enforcement'.replace('at12of30','at 12 of 30'))
p.write_text(s)
p=ROOT/'scripts/check_project_links.py';s=p.read_text();marker="        ROOT/'artifacts/implementation/pat-compiler-identity/DESIGN.md',";assert s.count(marker)==1
names=['DESIGN.md','implementation01/README.md','implementation02/README.md','results/README.md']
names += ['harness%02d/%s'%(i,n)for i in range(1,10)for n in ('README.md','SCOPE.md')]
s=s.replace(marker,'\n'.join("        ROOT/'artifacts/implementation/pat-io-group-worker/"+n+"',"for n in names)+'\n'+marker);p.write_text(s)
print(json.dumps(dict(attempts=6,fullGroupPassed=False,currentDistinctPassingMethods=13,documentsReconciled=True)))

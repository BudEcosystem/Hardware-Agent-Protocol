"""Reconcile exact schema reuse, retained deadline failure and measured costs."""
import json
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-schema-memo';R=B/'results'
names=['attempt01-passed44','attempt02-passed-cutoff','attempt03-failed-gpio-deadline','attempt04-profiled-cutoff']
proofs=[json.loads((R/n/'proof.json').read_bytes())for n in names]
assert[p['status']for p in proofs]==['passed','passed','failed','passed']
assert[p['counts']['testsRun']for p in proofs]==[44,1,1,1]
table='\n'.join('| ['+p['attempt']+']('+n+'/proof.json) | '+p['status']+' | '+str(p['counts']['testsRun'])+' | '+str(p['testSeconds'])+' | '+str(p['rawScratchBytes'])+' |'for n,p in zip(names,proofs))
(R/'README.md').write_text('''# Bounded schema reuse:45 distinct checks pass, full group still incomplete

The [single-file production change](../schema-reuse.patch) reuses successful
JSON Schema checks for exact bounded bytes and the same private validator.
Every call still parses a detached tree, rejects invalid scalar types and runs
all graph, generation, electrical footprint and lifecycle semantics. Eight LRU
entries bound retained document bytes to512KiB plus object overhead. Private
validator replacement invalidates reuse; in-place mutation of those import-time
validators is outside the supported configuration contract. See the
[design](../DESIGN.md) and [source review](../implementation01/source-review.json).

**45 distinct methods pass:**21 existing topology checks,11 new schema reuse
regressions,12 existing group boundary/preflight checks and the actual record
cutoff. The profiler repeats that cutoff and adds no distinct method.
**The complete GPIO group still fails.** PWM remains prepared but unexecuted
pending correction of shared time and storage costs.

| Attempt | Result | Methods | Test seconds | Raw scratch bytes |
|---|---|---:|---:|---:|
'''+table+'''

The full GPIO group completes **25 of30 cases**, versus12 in the
[preceding source](../../pat-io-group-worker/results/README.md), before the
unchanged60-second deadline. This is a comparison of retained attempts, not a
controlled benchmark. The active26th case is `permission_after_completion`;
its runtime state has not been created. All21 earlier runtime states remain.
The [deadline diagnosis](../DEADLINE-DIAGNOSIS.json) records2,891 charged records,
7,438,380 charged producer bytes,8,941,568 observed state bytes,20 completed-case
child operations and78 charged scheduler ticks. The reserved terminal receipt
survives; all qualification/attestation/full-coverage flags remain false.
The [read-only state audit](attempt03-failed-gpio-deadline/state-audit.json)
observes14 activations,6 completed cycles,8 cancellations and zero claims/owners.
Those endpoint observations do not validate complete histories or unrun cases.

The actual cutoff still stops at250 charged records, retains258 raw files and
two private states, prevents later cases and rejects reuse of the populated
directory. Its6.338-second uninstrumented test compares with11.919 seconds in
the prior source; timings are diagnostic, with no performance guarantee.
Both cutoff [state audits](attempt02-passed-cutoff/state-audit.json) preserve the
completed nominal candidate and an unactivated canceled child.

The new [profile](attempt04-profiled-cutoff/attempt/profile.json) takes14.417
instrumented test seconds versus26.981 previously. Both perform285 topology
parses and494 topology/generation snapshots. Topology cumulative time changes
from13.672 to2.014 seconds, snapshot time from13.953 to2.088 seconds, and
JSON Schema iter_errors calls from30,239 to1,731. Cumulative times overlap and
profiling overhead is material. The [comparison](../PROFILE-ANALYSIS.json)
identifies remaining canonical serialization and repeated complete matrix
reconstruction; it does not justify bypassing runtime authority or semantics.

Retained raw GPIO evidence occupies16,324,409 bytes, near the unchanged16MiB
harness ceiling. The read-only [storage analysis](../STORAGE-ANALYSIS.json)
finds8,941,568 allocated SQLite bytes,1,720,199 payload bytes and7,123,390 unused
bytes within pages. The next storage investigation is a fixed smaller-page
profile for freshly created stores, with recovery/durability validation. No
database was rewritten, vacuumed, compressed or deleted. Complete group storage
cannot be predicted as compliant from this partial attempt; no ceiling is raised.

All four attempts keep218 project inputs,221 frozen entries,6 harness inputs and
159 external pins stable. All actual origin hashes match:724 records for the
pure selection,722 for ordinary group attempts and727 for the profiler;
222/221/223 bytecode reads respectively are refused. No prohibited attempt
occurs. Complete attempt copies and original scratch roots remain, and database
hashes stay unchanged during read-only inspection. Source/compiler/driver
identity is stable within each attempt; prior source evidence is not relabeled
as the new deployment. Primary-agent review was used; helpers remain usage-limited.

Live HMS, the adjacent Harness and physical devices remain unchanged. Independent
current-group outcomes, trusted configuration/run association, actual aggregate
storage enforcement, persistent supervision and public qualification remain
unfinished. Persistent Arduino applications, learning/reuse and physical
device/driver/intelligence-hub control remain part of the full goal. See
[qualification work](../../pat-io-outcome-history/NEXT-QUALIFICATION.md).
''')
# Space quantitative prose without changing identifiers, paths or evidence.
p=R/'README.md';s=p.read_text()
for old,new in [('reuse:45','reuse: 45'),('to512','to 512'),('pass:**21','pass:** 21'),(',11',', 11'),(',12',', 12'),('of30','of 30'),('versus12','versus 12'),('unchanged60','unchanged 60'),('active26th','active 26th'),('All21','All 21'),('records2,891','records 2,891'),(',8,941',', 8,941'),(',20',', 20'),('and78','and 78'),('observes14','observes 14'),(',6 completed',', 6 completed'),(',8 cancellations',', 8 cancellations'),('at250','at 250'),('retains258','retains 258'),('Its6.338','Its 6.338'),('with11.919','with 11.919'),('takes14.417','takes 14.417'),('versus26.981','versus 26.981'),('perform285','perform 285'),('and494','and 494'),('from13.672','from 13.672'),('to2.014','to 2.014'),('from13.953','from 13.953'),('to2.088','to 2.088'),('from30,239','from 30,239'),('to1,731','to 1,731'),('occupies16,324','occupies 16,324'),('unchanged16MiB','unchanged 16 MiB'),('finds8,941','finds 8,941'),(',1,720',', 1,720'),('and7,123','and 7,123'),('keep218','keep 218'),(',221',', 221'),(',6 harness',', 6 harness'),('and\n159','and\n159'),('match:724','match: 724'),('selection,722','selection, 722'),('and727','and 727')]:s=s.replace(old,new)
p.write_text(s.replace('512KiB','512 KiB').replace('and7, 123,390','and 7,123,390'))
p=ROOT/'PROGRESS.md';s=p.read_text();start=s.index('The [current I/O group coordinator]');end=s.index('The separate [qualification supervisor rebase]',start)
s=s[:start]+'''The [shared group coordinator](artifacts/implementation/pat-io-group-worker/results/README.md)
connects all25 fixed challenges and candidate cases under one ledger, with exact
case tickets, before-write evidence charging, reserved failure output and the
original deadline. Its first corrected source completes12 of30 GPIO cases before
that deadline; the mapping bug, acquisition correction and original failed
attempts remain preserved in that stage.

The subsequent [bounded schema reuse stage](artifacts/implementation/pat-io-schema-memo/results/README.md)
changes one production file and passes **45 distinct methods**:21 existing
topology checks,11 new reuse regressions,12 group boundary/preflight checks and
one actual250-record cutoff. Exact successful schema bytes may be reused within
an eight-entry cache; strict token parsing, detached outputs and every graph,
generation, electrical footprint and authority check remain.216 other inherited
project files are unchanged. Private import-time validators are not a mutable
configuration surface or deployment attestation.

The new full GPIO attempt completes **25 of30 cases**, then still fails at the
original60-second boundary. Its active26th case has no created runtime. All21
earlier states and16,324,409 raw bytes remain; that is close to the unchanged
16MiB harness retention ceiling. The reserved failure receipt survives. A
read-only audit finds14 activations,6 completed cycles,8 cancellations and no
claims/owners. This is an endpoint observation, not complete-history validation.
PWM remains prepared but unexecuted pending the shared time/storage correction.

The same cutoff test takes6.338 uninstrumented seconds versus11.919 previously;
instrumented runs take14.417 versus26.981 seconds. This is not a controlled
benchmark. The [new profile](artifacts/implementation/pat-io-schema-memo/PROFILE-ANALYSIS.json)
still performs285 topology parses but reduces their cumulative time from13.672
to2.014 seconds. Cumulative times overlap and include profiler overhead.
Repeated full matrix construction and canonical serialization remain significant.
The [storage audit](artifacts/implementation/pat-io-schema-memo/STORAGE-ANALYSIS.json)
finds8,941,568 allocated SQLite bytes,1,720,199 payload bytes and7,123,390 unused
page bytes. Next investigate exact trusted validated-matrix reuse and a fixed
smaller-page profile for newly created stores; preserve standalone validation,
runtime authority, recovery/durability and every original bound. No retained
database has been rewritten, vacuumed, compressed or deleted.

All four new attempts retain stable218 project inputs,221 frozen entries,6 active
harness inputs and159 external pins, matched actual origins and unchanged
within-attempt compiler/driver identities. All original scratch roots and complete
copies remain. Review is by the primary agent; no independent-agent review was
available. Live HMS and the adjacent Harness are unchanged. Full group capture,
independent outcomes, trusted setup/run association, hard aggregate storage,
public qualification, learning, persistent Arduino controllers and physical
device/driver/intelligence-hub controls remain unfinished.

'''+s[end:]
replacements={'all25':'all 25','completes12 of30':'completes 12 of 30','methods**:21':'methods**: 21','checks,11':'checks, 11','regressions,12':'regressions, 12','actual250':'actual 250','remain.216':'remain. 216','of30':'of 30','original60':'original 60','active26th':'active 26th','All21':'All 21','and16,324':'and 16,324','16MiB harness':'16 MiB harness','finds14':'finds 14',',6 completed':', 6 completed',',8 cancellations':', 8 cancellations','takes6.338':'takes 6.338','versus11.919':'versus 11.919','take14.417':'take 14.417','versus26.981':'versus 26.981','performs285':'performs 285','from13.672':'from 13.672','to2.014':'to 2.014','finds8,941':'finds 8,941',',1,720':', 1,720','and7,123':'and 7,123','stable218':'stable 218',',221':', 221',',6 active':', 6 active','and159':'and 159'}
for old,new in replacements.items():s=s.replace(old,new)
p.write_text(s)
p=ROOT/'docs/prompt-to-pat.md';s=p.read_text();start=s.index('The [current-group capture coordinator]');end=s.index('An operator says, for example,',start)
s=s[:start]+'''The [shared group coordinator](../artifacts/implementation/pat-io-group-worker/results/README.md)
connects exact candidate/fixed cases under one ledger. The subsequent
[bounded schema reuse](../artifacts/implementation/pat-io-schema-memo/results/README.md)
passes45 distinct checks and preserves parsing and all semantic validation.
GPIO now reaches25 of30 cases before its unchanged deadline, so it still cannot
qualify a PAT. Retained state is also near the original storage ceiling. Measured
matrix-validation and SQLite page costs guide the next correction. No limit was
widened or failed evidence discarded; learning/promotion remains unfinished.

'''+s[end:];s=s.replace('passes45','passes 45').replace('reaches25 of30','reaches 25 of 30');p.write_text(s)
p=ROOT/'docs/io-driver-hub-control.md';s=p.read_text();start=s.index('The [current I/O group coordinator]')
s=s[:start]+'''The [shared I/O group coordinator](../artifacts/implementation/pat-io-group-worker/results/README.md)
applies one capture budget to the exact matrix. The subsequent
[bounded schema reuse](../artifacts/implementation/pat-io-schema-memo/results/README.md)
passes45 distinct checks, including the actual record cutoff, while preserving
every topology/generation/authority semantic check. Full GPIO reaches25 of30
cases before its unchanged deadline; retained evidence is near the original
storage ceiling. Complete capture and independent outcomes remain unfinished.
Serialized charging and closed-state inspection do not provide a hard SQLite/WAL
quota or establish physical timing, drivers or intelligence-hub lifecycle control.
''';s=s.replace('passes45','passes 45').replace('reaches25 of30','reaches 25 of 30');p.write_text(s)
p=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';s=p.read_text()
old='Full GPIO reaches only 12 of 30 cases before the original 60-second deadline. Optimize measured redundant validation without widening limits, then finish exact group execution and outcome checks.'
new='The [schema-reuse correction](../pat-io-schema-memo/results/README.md) passes45 distinct checks and reaches25 of30 GPIO cases before the unchanged60-second deadline, with16,324,409 retained bytes near the16MiB harness ceiling. Correct measured matrix-validation and new-store SQLite page costs without widening limits, then finish exact capture/outcomes.'
assert old in s;s=s.replace(old,new)
old='stops at 12 of 30 cases on its original deadline. The next implementation corrects\nthe measured repeated-validation cost, completes every case, joins the independent'
new='now reaches25 of30 cases after bounded schema reuse, but still stops on its\noriginal deadline near the retained-storage ceiling. The next implementation\naddresses measured repeated matrix validation and newly created store size,\ncompletes every case, joins the independent'
assert old in s;s=s.replace(old,new)
s=s.replace('capture but\nnow','capture and\nnow')
for old,new in [('passes45','passes 45'),('reaches25 of30','reaches 25 of 30'),('unchanged60','unchanged 60'),('with16,324','with 16,324'),('the16MiB','the 16 MiB')]:s=s.replace(old,new)
p.write_text(s)
p=ROOT/'scripts/check_project_links.py';s=p.read_text();marker="        ROOT/'artifacts/implementation/pat-io-group-worker/DESIGN.md',";assert s.count(marker)==1
names=['DESIGN.md','implementation01/README.md','results/README.md']+['harness%02d/%s'%(i,n)for i in range(1,6)for n in ('README.md','SCOPE.md')]
s=s.replace(marker,'\n'.join("        ROOT/'artifacts/implementation/pat-io-schema-memo/"+n+"',"for n in names)+'\n'+marker);p.write_text(s)
print(json.dumps(dict(executedAttempts=4,distinctPassingMethods=45,fullGroupPassed=False,allOriginalBoundsUnchanged=True)))

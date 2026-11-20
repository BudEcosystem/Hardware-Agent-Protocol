"""Reconcile successful full GPIO capture and retained incomplete PWM evidence."""
import json
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-group-efficiency';R=B/'results'
names=['attempt01-passed87','attempt02-passed-storage6','attempt03-passed-cutoff',
       'attempt04-passed-gpio','attempt05-failed-pwm','attempt06-profiled-pwm-failure']
proofs=[json.loads((R/n/'proof.json').read_bytes())for n in names]
assert[p['status']for p in proofs]==['passed','passed','passed','passed','failed','failed']
assert[p['counts']['testsRun']for p in proofs]==[87,6,1,1,1,1]
table='\n'.join('| ['+p['attempt']+']('+n+'/proof.json) | '+p['status']+' | '+str(p['counts']['testsRun'])+' | '+str(p['testSeconds'])+' | '+str(p['rawScratchBytes'])+' |'for n,p in zip(names,proofs))
(R/'README.md').write_text('''# Full GPIO capture passes; PWM remains incomplete

The [candidate](../implementation01/README.md) explicitly associates each group
case with the already validated five input documents and uses a fixed compact
layout for fresh synthetic stores. **95 distinct methods pass:**87 pure checks,
six actual storage checks, the record cutoff and full GPIO group. **PWM fails**
at the original deadline after28 of30 cases. A separate diagnostic profile
repeats that failed method; it is not another distinct test or a passing result.

| Attempt | Result | Methods | Test seconds | Raw scratch bytes |
|---|---|---:|---:|---:|
'''+table+'''

The full GPIO test verifies all30 exact case IDs and all25 fixed challenges,
rehashes every manifest and both evidence streams, independently sums accounting,
and checks52 retained SQLite headers. It observes28 actual child operations,
44 reserved admissions and99 scheduler ticks. Charged evidence is3,832 records
and10,149,988 producer bytes;4,510,720 closed state bytes bring derived accounting
to14,660,708 bytes, including the conservative65,536-byte terminal reservation.
Actual retained scratch is14,606,609 bytes across3,936 files. All original
deadlines and byte/record/case/tick ceilings remain. The58.305-second test leaves
little observed timing margin and is not a performance guarantee.

The [GPIO state audit](attempt04-passed-gpio/state-audit.json) observes21
activations,11 completed cycles,10 cancellations and zero claims/owners across26
runtime states. The final resource challenge has four completed actors and no
retained owner. The [storage audit](attempt04-passed-gpio/storage-audit.json)
finds52 intact1024-byte-page databases, with2,176,346 payload bytes and2,195,539
unused page bytes. Endpoint observations and exact capture accounting do not
replace independent complete-history outcome checking. Every group qualification,
attestation, physical-measurement and hard-quota flag remains false.

PWM completes28 cases before the original60-second group deadline. The active
`binding_pending` case has created state but no child/effect; the final shared
resource case is unrun. Its13,125,092 raw bytes and bounded failure receipt remain.
The [state audit](attempt05-failed-pwm/state-audit.json) observes16 activations,
seven completions, nine cancellations and no claims/owners across25 states.
No case is skipped and no failing result is converted to success. See the exact
[group accounting and diagnoses](../GROUP-ANALYSIS.json).

The actual cutoff still stops at250 charged records and preserves258 raw files,
including two runtime states. The unchanged logical history now occupies977,425
bytes. The six layout tests verify actual page sizes, DELETE/EXTRA settings,
foreign-key enforcement, integrity, rollback and owner exclusion. They exercise
pending recovery and same-key replay after reopen, reject mismatched expected
layouts without rewriting database bytes, and show the default opener preserves
an existing compact layout. These are settings/rollback/reopen checks, not
physical power-loss durability or filesystem-quota attestation.

The87 pure methods include the preceding44 checks,30 combined-matrix checks,
twelve new validated-input checks and one invalid-storage-profile check. Exact
comparison preserves numeric types, bounded detached documents, all five runner
families and standalone full validation. Current source changes11 inherited
production modules and one existing test file, adds one production and two test
modules, and leaves206 inherited files byte-identical. See the
[review](../implementation01/source-review.json) and [delta](../implementation.patch).

The [PWM profile](attempt06-profiled-pwm-failure/attempt/profile.json) reaches16
cases under the same deadline and fails as expected by the ordinary test's
unchanged assertions. Profiling adds overhead. It records39,452 canonical
encodings taking31.440 cumulative instrumented seconds;184 configuration captures
take20.095 cumulative seconds. Timings overlap. Source review confirms6,157
configured writer calls serialize a record again in the base writer, even on
reuse. The [analysis](../PROFILE-ANALYSIS.json) directs the next change toward
removing redundant encoding and bounded reuse of exact unchanged table pages,
while retaining current SQL inspection, type/size checks, locks, fsync, every
evidence record/reference and all source/authority checks. No further optimization
is implemented or verified in this stage.

All six attempts retain stable221 project inputs,224 frozen entries, six harness
inputs and159 external pins. All selected actual import hashes match. Pure,
storage, ordinary group and profile runs respectively record730/726/724/729
origins and refuse225/223/222/224 bytecode reads; no prohibited attempt occurs.
Source/compiler/driver identities are stable within each attempt. All complete
attempt copies and original raw scratch roots remain. Read-only audits verify
unchanged database bytes. Primary-agent review was used; helpers remain
usage-limited. Live HMS and the adjacent Harness remain unchanged.

Full PWM capture, independent current-group outcomes, trusted configuration/run
association, enforced aggregate storage, durable supervision and public
qualification remain unfinished. Persistent Arduino applications, synthesis and
learning, physical I/O/driver providers and intelligence-hub lifecycle/compute
control remain part of the complete goal. See [design](../DESIGN.md) and
[remaining qualification work](../../pat-io-outcome-history/NEXT-QUALIFICATION.md).
''')
# Insert spaces only at known prose word/number boundaries, never inside numbers.
def prose(s):
 import re
 s=re.sub(r'(?<=[A-Za-z:])(?=\d)', ' ', s)
 return re.sub(r'(?<=[A-Za-z])[,;](?=\d)',lambda m:m[0]+' ',s)
# Apply only prose lines so paths, identifiers, table links and inline code stay exact.
p=R/'README.md';lines=p.read_text().splitlines(True)
for i,line in enumerate(lines):
 if not any(x in line for x in ('[','`','|','http')):lines[i]=prose(line)
p.write_text(''.join(lines))
p=ROOT/'PROGRESS.md';s=p.read_text();start=s.index('The [shared group coordinator]');end=s.index('The separate [qualification supervisor rebase]',start)
s=s[:start]+'''The [shared group coordinator](artifacts/implementation/pat-io-group-worker/results/README.md)
connects all25 fixed challenges and candidate cases under one accounting ledger.
The preceding [schema reuse stage](artifacts/implementation/pat-io-schema-memo/results/README.md)
reached25 of30 GPIO cases before its original deadline; those failures remain.

The new [group efficiency stage](artifacts/implementation/pat-io-group-efficiency/results/README.md)
passes **95 distinct methods**:87 pure checks, six actual storage tests, the
record cutoff and the first complete GPIO group. A trusted validated-input bundle
compares all five bounded detached documents before each fixed case, preserving
exact numeric types and standalone full validation. Runtime authority and source
checks remain. Fresh synthetic stores opt into1024-byte pages; reopening never
converts a database. All three worker runtime-open paths select the same profile.
SQL schemas, DELETE/EXTRA durability settings and recovery remain unchanged.

Full GPIO now captures **all30 cases**, including all25 fixed challenges, under
the original limits. Its58.305-second test checks28 actual operations,44 reserved
admissions,99 ticks,3,832 charged records,10,149,988 producer bytes and14,660,708
derived bytes. The complete14,606,609-byte raw tree and52 databases remain. A
read-only audit finds21 activations,11 completed cycles,10 cancellations and no
claims/owners across26 states. The new layout retains4,510,720 SQLite bytes,
with2,176,346 payload and2,195,539 unused page bytes. The pass has little timing
margin; it is not a hard-real-time or general performance guarantee.

**PWM still fails after28 of30 cases** at the original60-second boundary.
Its active `binding_pending` case has state but no child/effect, and the final
shared-resource case is unrun. All13,125,092 raw bytes remain. Endpoint inspection
finds16 activations, seven completions, nine cancellations and no claims/owners
across25 created states. A separate diagnostic profile repeats the unchanged
failing method and completes16 cases because of instrumentation overhead.
It records39,452 canonical encodings and6,157 configured writer calls that repeat
encoding in the base writer. The [profile analysis](artifacts/implementation/pat-io-group-efficiency/PROFILE-ANALYSIS.json)
directs the next change toward redundant writer encoding and bounded exact
unchanged-page reuse while preserving inspections, locks, fsync, records and
every guard and ceiling. No further encoding optimization is yet verified.

The actual250-record cutoff still passes and retains977,425 bytes. Six storage
tests check headers/settings/integrity, rollback, owner exclusion, pending
recovery, replay and mismatched-layout refusal without database rewrite. These
checks do not prove physical power-loss durability or a hard aggregate quota.
All six attempts retain stable221 project inputs,224 frozen entries, six active
harness inputs and159 external pins, matched origins and unchanged within-attempt
compiler/driver identities. All originals and complete copies remain; prior
failure evidence is untouched. Review is by the primary agent; helpers remain
usage-limited. Live HMS and the adjacent Harness are unchanged.

Complete GPIO capture is not independent qualification. Full PWM capture,
composed current-group outcomes, trusted setup/run association, enforced aggregate
storage, supervision, public qualification, agent learning, persistent Arduino
applications and physical device/driver/intelligence-hub providers remain
unfinished. The complete end-to-end goal stays active.

'''+s[end:]
prefix=s[:start];block=s[start:s.index('The separate [qualification supervisor rebase]',start)];suffix=s[s.index('The separate [qualification supervisor rebase]',start):]
lines=block.splitlines(True)
for i,line in enumerate(lines):
 if not any(x in line for x in ('[','`','|','http')):lines[i]=prose(line)
p.write_text(prefix+''.join(lines)+suffix)
p=ROOT/'docs/prompt-to-pat.md';s=p.read_text();start=s.index('The [shared group coordinator]');end=s.index('An operator says, for example,',start)
s=s[:start]+'''The [current group efficiency stage](../artifacts/implementation/pat-io-group-efficiency/results/README.md)
passes95 distinct checks and completes all30 GPIO cases under the original
limits. Exact validated-input reuse and compact fresh stores preserve authority,
type, recovery and replay checks. PWM remains incomplete at28 of30 cases before
the deadline. Its failed state and diagnostic profile are retained. The next
correction targets repeated evidence encoding, followed by independent current
outcomes, trusted setup and actual aggregate enforcement. Capture alone cannot
qualify or promote a learned PAT.

'''+s[end:]
for a,c in [('passes95','passes 95'),('all30','all 30'),('at28 of30','at 28 of 30')]:s=s.replace(a,c)
p.write_text(s)
p=ROOT/'docs/io-driver-hub-control.md';s=p.read_text();start=s.index('The [shared I/O group coordinator]')
s=s[:start]+'''The [current group efficiency stage](../artifacts/implementation/pat-io-group-efficiency/results/README.md)
passes95 distinct checks and completes all30 GPIO cases, including the shared
pin/PWM/alias challenge, within the original capture limits. Exact plan reuse and
compact fresh SQLite stores retain runtime authority, durability settings and
recovery behavior. Full PWM still reaches only28 of30 cases before its deadline;
the failed attempt remains. Independent outcomes, actual aggregate quotas and
physical driver/intelligence-hub lifecycle qualification are still required.
'''
for a,c in [('passes95','passes 95'),('all30','all 30'),('only28 of30','only 28 of 30')]:s=s.replace(a,c)
p.write_text(s)
p=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';s=p.read_text()
start=s.index('| Group budgets and retained evidence |');end=s.index('\n| Persistent service',start)
s=s[:start]+'''| Group budgets and retained evidence | The [group efficiency stage](../pat-io-group-efficiency/results/README.md) passes95 distinct checks, including the actual250-record cutoff and complete30-case GPIO capture at58.305 test seconds with14,606,609 retained bytes | PWM still fails after28 of30 cases at the original deadline. Correct measured redundant evidence encoding without changing cases, fsync, guards or bounds; then complete independent outcomes. Compact fresh-store layout and closed-state accounting do not impose a hard aggregate filesystem quota; actual enforcement remains required |'''+s[end:]
start=s.index('components. The coordinator attempts exact current-candidate group capture');end=s.index('\nFinite I/O qualification',start)
s=s[:start]+'''components. The group now completes all30 GPIO cases under the original bounds,
but PWM remains incomplete after28 cases at the unchanged deadline. The next
implementation removes measured redundant evidence encoding while preserving
current inspections, exact records/references and durability. It must then finish
all required current-candidate capture, join independent outcomes with trusted
current setup, and enforce actual aggregate storage before public qualification
or promotion. Captured cases and endpoint state observations do not substitute
for those independent semantic and deployment checks.
'''+s[end:]
for a,c in [('passes95','passes 95'),('actual250','actual 250'),('complete30','complete 30'),('at58.305','at 58.305'),('with14,606','with 14,606'),('after28 of30','after 28 of 30'),('all30','all 30'),('after28','after 28')]:s=s.replace(a,c)
p.write_text(s)
p=ROOT/'scripts/check_project_links.py';s=p.read_text();marker="        ROOT/'artifacts/implementation/pat-io-schema-memo/DESIGN.md',";assert s.count(marker)==1
names=['DESIGN.md','implementation01/README.md','results/README.md']+['harness%02d/%s'%(i,n)for i in range(1,7)for n in ('README.md','SCOPE.md')]
s=s.replace(marker,'\n'.join("        ROOT/'artifacts/implementation/pat-io-group-efficiency/"+n+"',"for n in names)+'\n'+marker);p.write_text(s)
print(json.dumps(dict(attempts=6,distinctPassingMethods=95,gpioCapturedCases=30,pwmCapturedCases=28,qualified=False)))

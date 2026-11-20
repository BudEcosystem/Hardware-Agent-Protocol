"""Reconcile only after all six exact corrected selections pass and are acquired."""
import json
from pathlib import Path
ROOT=Path.cwd();BASE=ROOT/'artifacts/implementation/pat-io-clock-history'
def read(p):return json.loads(p.read_bytes())
folders=['attempt03-passed33','attempt04-passed73','attempt07-passed48','attempt09-passed14','attempt10-passed13','attempt06-passed20']
proofs=[read(BASE/'results'/f/'proof.json')for f in folders]
for proof,count in zip(proofs,[33,73,48,14,13,20]):
 assert proof['status']=='passed' and proof['counts']==dict(testsRun=count,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
 assert proof['sourceIndexSha256']=='f98de6d5d3c76335cb74032da5641750a21d6de37af8004f2738f0797aba5ff9'
 assert proof['sqliteConnections']==proof['rawScratchFiles']==proof['rawScratchBytes']==0
methods=[]
for p in proofs:methods+=read(BASE/p['harness']/'targets.json')['targets']
assert len(methods)==len(set(methods))==201
for f,p in zip(folders,proofs):
 count=p['counts']['testsRun'];text='# Passing pure history selection\n\n'
 text+=f"[All {count} exact methods](attempt/output.log) passed in {p['testSeconds']:.3f} test seconds\nand {p['elapsedSeconds']:.3f} elapsed seconds. The [acquisition proof](proof.json)\nretains the complete {p['attemptFilesAcquired']:,}-file attempt and original empty raw root.\n"
 text+=f"All {p['actualOrigins']['recordCount']} actual origins matched; {p['bytecodeReadsRefused']} bytecode reads were refused.\nAll 8,022 project files, 8,025 frozen inputs, six harness inputs and 159 external\npins remained stable, including compiler/driver receipts. The tested checker made\nno SQLite connection, network call, subprocess launch or device action.\nThese checks do not qualify a PAT.\n\n"
 text+='See the [combined result](../README.md) for scope and retained earlier failures.\n'
 with (BASE/'results'/f/'README.md').open('x')as out:out.write(text)
lines=['# Independent clock-history results','',
 'The corrected [source03](../implementation03/README.md) passes **201 distinct methods**',
 'across six bounded pure-inspection runs. All 33 new checks pass, including the six',
 'original GPIO/PWM captures and rehashed adversarial histories. The remaining 168',
 'unchanged tests cover board, operation, configuration, observation and authorization',
 'history. No device action or runtime database connection is replayed.','',
 '| Selection | Tests | Test seconds | Elapsed seconds | Result |','|---|---:|---:|---:|---|']
for label,f,p in zip(['Clock semantics','Board and operation','Configuration','Observation A','Observation B','Authorization'],folders,proofs):
 lines.append(f"| {label} | {p['counts']['testsRun']} | {p['testSeconds']:.3f} | {p['elapsedSeconds']:.3f} | [Pass]({f}/README.md) |")
lines += ['',
 'The first two 33-test runs are retained: [receipt-key shadow](attempt01-failed33/README.md)',
 'and [missing atomic release in the model](attempt02-failed33/README.md). Each had',
 'two errors and one failed assertion. Corrections use fresh source snapshots; all',
 'tests, fixtures, producer, runtime, provider and compiler bytes remain unchanged.','',
 'The [combined 75-test timeout](attempt05-timeout75/README.md) and later',
 '[observation 27-test timeout](attempt08-timeout27/README.md) are also retained.',
 'Their incomplete child evidence cannot count as passes. The identical 75 methods',
 'finally run in 48+14+13 selections with the original deadline and every other',
 'bound unchanged.','',
 'The composed checker independently derives exact clock/call controls, whole-domain',
 'static timing, PAT correspondence, configuration/authorization, board effects,',
 'operation events/claims, parent state and observation sampling. It verifies:',
 '',
 '- Original dispatch at 1,000,000, guard at 1,000,099 and due equality at the reserved',
 '  run limit: no activation or board fence; atomic authority claim release.',
 '- Wall/monotonic faults: all 29 execution and 15 configuration tables remain',
 '  unchanged. Cached samples retain their original timestamps. Restoring the',
 '  monotonic source under the same owner does not clear the failure latch.',
 '- New-owner reopen: retain request, replay keys, floors and claims; stop the',
 '  original-owner receipt; reconcile before releasing claims; refuse resume;',
 '  cancel the parent without admitting its suffix.',
 '',
 'Across the six original cases: four activations, zero completed cycles and four',
 'cancellations. All six completion contracts fail as intended, all six expected',
 'fault responses pass, and all are settled/quiescent. They cover 116 paired',
 'checkpoints, 664 execution records and 270 configuration records. A failed clock',
 'refresh leaves output pending until explicit recovery; this proves no autonomous',
 'or physical stopping deadline.','',
 'Private timing/cause handoffs are derived from exact context and must be consumed.',
 'Old public profiles/default folds preserve their refusals. Receipt attacks retain',
 'coherent digests and event references; table attacks retain valid serialization',
 'and configuration joins. Pure inspection rejects file/SQL/live-clock use.','',
 'Original 180-second/16 MiB scratch/8,192-file and other acquisition limits remain.',
 'All ten attempt directories and original empty raw roots are retained, including',
 'failures. Primary-agent review only: helpers remain usage-limited. Live HMS and',
 'the adjacent Harness were not changed.','',
 'Full matrix execution, current source/configuration attestation, aggregate quotas,',
 'public qualification, persistent prompt applications, PAT learning, physical',
 'drivers and intelligence-hub lifecycle/compute management remain incomplete.',
 'The [remaining qualification audit](../../pat-io-outcome-history/NEXT-QUALIFICATION.md)',
 'continues to apply. These histories do not qualify a PAT.','']
with (BASE/'results/README.md').open('x')as f:f.write('\n'.join(lines))
def change(path,before,after):
 p=ROOT/path;s=p.read_text();assert s.count(before)==1,(path,before);p.write_text(s.replace(before,after))
change('PROGRESS.md',
 'In-phase guard delay, clock faults/new epochs, binding/full-read withdrawal,\nauxiliary actors and complete candidate matrix execution remain open. Current\n',
 'At this forward-time stage, guard delay and clock faults were still open; the\nlater stages below add those cases. Binding/full-read withdrawal, auxiliary\nactors and complete candidate matrix execution remain open. Current\n')
change('PROGRESS.md',
 'and a pure-reader veto check pass. Full semantic clock-history composition is\nstill missing: board, authority, parent and sampling folds must derive these\nhistories before expected outcome or qualification can be checked. The\n',
 'and a pure-reader veto check pass. This capture-stage reader does not compose\nboard, authority, parent and sampling semantics. The later clock-history stage\nbelow supplies that composition for these six exact cases. The original\n')
change('PROGRESS.md','semantic composition, binding/full-read withdrawal, auxiliary actors, aggregate\nbudgets, public qualification, prompt learning, persistent Arduino controllers\nand physical driver/intelligence-hub management are still required.',
 'binding/full-read withdrawal, auxiliary actors, aggregate budgets, public\nqualification, prompt learning, persistent Arduino controllers and physical\ndriver/intelligence-hub management are still required.')
section='''The [independent clock-history composition](artifacts/implementation/pat-io-clock-history/results/README.md)
now passes **201 distinct methods across six bounded runs**: 33 new checks and 168
unchanged board, operation, configuration, observation and authorization regressions.
The six retained GPIO/PWM captures receive independently checked expected fault
responses. Whole-domain timing, PAT correspondence, installed configuration,
trusted authorization, board effects, authority/parent events and sample history
all compose before the result asserts complete history or expected response.

The delayed-start fold preserves dispatch at 1,000,000 and guard at 1,000,099, derives
run-limit equality, no-start evidence, zero effects/fences and atomic claim release.
The fault fold derives unchanged execution/configuration state and cached samples,
including the sticky invalid mapping after its source is restored. New-owner
reopen retains the old identities and claims, stops the old receipt, reconciles,
refuses resume and cancels without a suffix. All six completion contracts fail as
intended; all are settled and quiescent. Four activations, zero completed cycles
and four cancellations remain the exact original totals. No autonomous or physical
stopping deadline follows: output remained pending during the failed refresh.

Two earlier 33-test attempts each had two errors and one failed assertion. Fresh
source snapshots fix a receipt-key shadow and the missing atomic claim-release
transition in the new model. All tests/fixtures and runtime/provider/compiler
bytes remain unchanged. Both complete semantic failures, the subsequent 75- and
27-test timeouts, and all passing attempts are retained. The same 75 tests finally
pass in 48+14+13 selections without changing their source, assertions or deadline.
The six corrected selections preserve the original 180-second and 16 MiB scratch
limits, forbid every SQLite connection, and keep all 8,022 project inputs,
8,025 frozen entries and 159 external pins stable. Primary-agent review only;
helpers remain usage-limited. Live HMS and the adjacent Harness remain untouched.

This completes semantic checking for the three exact clock challenges, not the
current candidate's full matrix. Binding/full-read changes, auxiliary actors,
current source/configuration attestation, measured aggregate limits, public
qualification, persistent prompt apps, learning, physical drivers and hub
lifecycle/compute management remain open. Qualification, matrix coverage,
aggregate-storage and physical-measurement success flags remain false.

'''
change('PROGRESS.md','The separate [qualification supervisor rebase]',section+'The separate [qualification supervisor rebase]')
change('docs/prompt-to-pat.md',
 'reader checks structure and the exact control schedule. Independent semantic\nclock-history/outcome composition remains unfinished; these captures cannot yet\nqualify a PAT or complete prompt learning and persistent application deployment.',
 'capture reader checks structure and the exact control schedule. The subsequent\n[independent semantic composition](../artifacts/implementation/pat-io-clock-history/results/README.md)\npasses 201 distinct checks across six bounded runs. It derives the six expected\nfault responses from configuration, ownership, effects, events and observations,\nincluding atomic no-start claim release and recovery without later steps. These\nresults still cannot qualify a PAT: full candidate matrix execution, current\nattestation, aggregate enforcement, prompt learning and persistent deployment\nremain unfinished.')
change('docs/io-driver-hub-control.md',
 'autonomous stopping deadline. The new reader checks structure/control schedules;\nfull semantic clock-outcome checks, actual drivers and hub lifecycle/compute\nmanagement remain unfinished.',
 'autonomous stopping deadline. The later\n[independent clock-history composition](../artifacts/implementation/pat-io-clock-history/results/README.md)\npasses 201 distinct tests and verifies all six exact expected fault responses.\nIt checks effects, authority/parent history, retained ownership and cached\nobservations without executing I/O. Complete candidate matrix qualification,\nactual drivers and hub lifecycle/compute management remain unfinished.')
p=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md';s=p.read_text()
s=s.replace('new clock captures add in-phase guard delay | Compose the in-phase timeline into independent semantic folds, then all schedules into current candidate group execution with measured aggregate bounds',
 'the [clock semantic checker](../pat-io-clock-history/results/README.md) preserves dispatch/guard event times independently | Integrate all schedules into current candidate group execution with measured aggregate bounds')
s=s.replace('Complete the [semantic clock-history handoff](../pat-io-clock-challenges/results/attempts01-02/SEMANTIC-HANDOFF.md): phase-local event times, invalid-clock refresh, sticky mapping, retained pending output and exact recovery before group outcome reduction. The new clock reader currently checks structure/control only',
 'The [composed semantic checker](../pat-io-clock-history/results/README.md) now verifies all six exact clock/guard responses, including cached samples, atomic no-start release and retained recovery. Integrate those checks with current candidate group execution; these historical fixtures do not establish full coverage')
p.write_text(s)
p=ROOT/'scripts/check_project_links.py';s=p.read_text();needle="        ROOT/'artifacts/implementation/pat-qualification-supervisor/README.md',"
assert s.count(needle)==1
paths=['DESIGN.md']+[f'implementation{i:02}/README.md'for i in range(1,4)]+[f'harness{i:02}/{f}'for i in range(1,17)for f in ['README.md','SCOPE.md']]+['results/README.md']+[f'results/{f}/README.md'for f in ['attempt01-failed33','attempt02-failed33','attempt05-timeout75','attempt08-timeout27']+folders]
s=s.replace(needle,''.join("        ROOT/'artifacts/implementation/pat-io-clock-history/"+name+"',\n"for name in paths)+needle);p.write_text(s)
print(json.dumps(dict(distinctTests=len(methods),newMarkdownPaths=len(paths),proofs=[dict(tests=p['counts']['testsRun'],testSeconds=p['testSeconds'],elapsedSeconds=p['elapsedSeconds'])for p in proofs])))

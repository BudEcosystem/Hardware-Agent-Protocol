"""Record bounded encoding checks, deadline failures and the current profile."""
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-page-encoding'; R = B / 'results'
assert not (R / 'index.json').exists()
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, v):
    with p.open('x') as f: f.write(json.dumps(v, indent=2) + '\n')

names = ('attempt01-passed117', 'attempt02-passed-cutoff', 'attempt03-failed-gpio-history', 'attempt04-profiled-gpio-failure')
attempts, groups, passed = [], [], set()
for name in names:
    folder = R / name; p = read(folder / 'proof.json')
    if p['status'] == 'passed': passed.update(read(folder / 'attempt/actual-tests.json')['executed'])
    attempts.append(dict(attempt=name, status=p['status'], counts=p['counts'], testSeconds=p['testSeconds'],
        elapsedSeconds=p['elapsedSeconds'], rawScratchBytes=p['rawScratchBytes'], rawScratchFiles=p['rawScratchFiles']))
    if (folder / 'state-audit.json').exists():
        group = read(folder / 'state-audit.json')['groups'][0]; storage = read(folder / 'storage-audit.json')
        effects = {k: sum((s['effects'][i] or 0) for s in group['states']) for i, k in enumerate(('activations', 'completed', 'canceled'))}
        effects.update(claims=sum(s['claims'] for s in group['states']), owners=sum(s['owners'] for s in group['states']))
        groups.append(dict(attempt=name, captureStatus=group['groupStatus'], error=group['groupError'],
            completedCases=group['completedCases'], states=len(group['states']), sqliteBytes=storage['totalBytes'],
            endpointEffects=effects, activeState=next((s for s in group['states'] if s['caseId'] == group['activeCaseId']), None)))
    text = '# Retained page-encoding attempt\n\n'
    text += f"{p['counts']['testsRun']} method(s), {p['counts']['failures']} failure(s), {p['counts']['errors']} error(s); {p['testSeconds']:.3f} test seconds / {p['elapsedSeconds']:.3f} harness seconds.\n\n"
    text += f"All 227 project files, 230 frozen inputs, six active harness files and 159 external pins remain stable. Matched origins, unchanged compiler/driver identities, complete original scratch and copies are retained: {p['rawScratchFiles']:,} files / {p['rawScratchBytes']:,} bytes; {p['sqliteConnections']} SQL connections.\n\n"
    text += '[Acquisition proof](proof.json), [result](attempt/result.json), [complete log](attempt/output.log).\n\n'
    if (folder / 'state-audit.json').exists(): text += '[Closed state audit](state-audit.json), [storage audit](storage-audit.json); no database bytes changed.\n\n'
    if (folder / 'attempt/profile.json').exists(): text += '[Instrumented profile](attempt/profile.json); overhead is included, and cumulative times overlap.\n\n'
    text += 'See the [stage result](../README.md). No complete current-group inspection, physical result or qualification claim.\n'
    (folder / 'README.md').write_text(text)
assert len(passed) == 118
profile = read(R / names[-1] / 'attempt/profile.json')
selected = [row for row in profile['top100'] if any(x in row['label'] for x in (
    '/hms/contracts.py:', '/hms/synthetic_io_runtime.py:', '/hms/synthetic_io_installation.py:',
    '/hms/synthetic_io_catalog.py:', '/hms/resource_topology.py:', '/hms/pat_io_configuration_capture.py:',
    '/hms/pat_io_trials.py:', '/hms/pat_contracts.py:', '/hms/pat_io_page_encoding.py:',
    'sqlite3.Connection', 'posix.fsync'))]
write(B / 'PROFILE-ANALYSIS.json', dict(scope='Current instrumented full GPIO target; incomplete capture remains failed. Cumulative times overlap and cannot be summed.',
    attempt=names[-1], wallSeconds=profile['wallSeconds'], cpuSeconds=profile['cpuSeconds'], completedCases=11,
    selectedRows=selected, topSelf=profile['top100Self'][:15], conclusions=[
        'Uninstrumented full GPIO stops after23/30 cases; instrumented target stops after11/30 at the same60s capture deadline. Neither reaches independent inspection. No improvement or regression magnitude is established by these uncontrolled individual runs.',
        'Instrumented whole method uses68.21665259299334 wall seconds and55.802854883 process CPU seconds, including pre-run setup and profiler overhead. The difference alone does not identify a scheduling, host-load or filesystem cause.',
        'Canonical encoding remains16,976calls/31.450 cumulative seconds; exact current runtime setup, installation normalization, topology parsing and cell validation account for substantial overlapping work.',
        'Next source should examine bounded exact reuse of validated pure snapshots and redundant installation encoding, with input-type preservation, detachment, source/validator association and every current SQL/authority read retained. No mutable authority or generation decisions may be inherited from a cache.',
        'Page encoding capacity and source invariants pass focused checks, but full current acceptance remains incomplete. Do not widen deadlines or drop challenges to replace the missing result.']))
write(B / 'GROUP-ANALYSIS.json', dict(scope='118 distinct passing checks; incomplete fresh GPIO captures and diagnostic profile retained.',
    sourceIndexSha256=sha(B / 'implementation01/index.json'), distinctPassingMethods=118, attempts=attempts, captures=groups,
    currentPwmExecuted=False, independentlyInspectedCurrentGroups=0, qualificationPassed=False, independentAgentReview=False))
text = '''# Exact page encoding passes; current capture still misses its deadline

**118 distinct methods pass:** all 107 prior pure checks plus ten new encoding
checks, followed by the actual record-cutoff test. The cutoff retains exactly
977,425 raw bytes, matching the previous encoding stage. Exact page bytes/digests,
typed keys, caller mutation, profile/metadata changes, eviction, both streams,
budget precedence and failed-write retention pass. Closed fake-query fixtures
also verify that warm pages still reread SQL shape/count/size/type/rows and
revalidate blob documents. The actual group runs use private SQLite states.

| Attempt | Status | Test seconds | Raw bytes |
|---|---|---:|---:|
'''
for row in attempts: text += f"| [{row['attempt']}]({row['attempt']}/README.md) | {row['status']} | {row['testSeconds']:.3f} | {row['rawScratchBytes']:,} |\n"
text += '''
The uninstrumented GPIO attempt stops after 23 of 30 cases at the original 60s
capture deadline. Its active permission-before-dispatch case has a rejected child,
failed parent and no receipt/effect/claim/owner. The instrumented run stops after
11 cases; its active not-before-boundary case retains an accepted child, running
parent and one claim, with no receipt or activation. That unresolved state remains
unchanged. Neither attempt reaches independent inspection. PWM harness04 remains
unexecuted after the GPIO gate fails.

The profile reports 16,976 canonical calls with 31.450 cumulative seconds, and
substantial overlapping runtime setup, installation/topology and cell-validation
work. Whole-method process CPU/wall totals are 55.803/68.217 seconds, including
pre-run setup and instrumentation. These are not benchmarks; cumulative times
cannot be added, and no exact cause of run-to-run variation is established.

The source contains all 225 inherited current-worker inputs, with two new files
and two modified writer modules. Historical fixture data and its dedicated test
are explicitly excluded from this worker closure; original inputs remain pinned
and untouched. The memo holds at most 128 exact pages / 1MiB of encoded bytes.
Every SQL capture/validation method, reservation and durable storage body remains
unchanged. All four attempts preserve 227 project/230 frozen inputs, six active
harness files, 159 external pins, actual origins and within-run identities.

[Design](../DESIGN.md), [source review](../implementation01/source-review.json),
[unchanged method proof](../source-invariant-review.json), [group analysis](../GROUP-ANALYSIS.json),
[profile analysis](../PROFILE-ANALYSIS.json).
Primary-agent review only; helpers remain usage-limited. Live HMS, adjacent
Harness, physical devices/MCUs, inference and external controllers are untouched.
Fresh complete capture/inspection, trusted process/run association, hard aggregate
storage, public qualification, persistent applications, learning and real
device/driver/intelligence-hub providers remain required.
'''
(R / 'README.md').write_text(text)
print(json.dumps(dict(distinctPassingMethods=len(passed), captures=groups)))

"""Record complete current synthetic groups with independent outcome checks."""
import collections
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-snapshot-reuse'; R = B / 'results'
assert not (R / 'index.json').exists()
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, v):
    with p.open('x') as f: f.write(json.dumps(v, indent=2) + '\n')
names = ('attempt01-failed129', 'attempt02-passed129', 'attempt03-passed-cutoff', 'attempt04-passed-gpio-history', 'attempt05-passed-pwm-history')
attempts, passed, groups = [], set(), []
for name in names:
    folder = R / name; p = read(folder / 'proof.json')
    if p['status'] == 'passed': passed.update(read(folder / 'attempt/actual-tests.json')['executed'])
    attempts.append(dict(attempt=name, status=p['status'], counts=p['counts'], testSeconds=p['testSeconds'], elapsedSeconds=p['elapsedSeconds'],
        rawScratchFiles=p['rawScratchFiles'], rawScratchBytes=p['rawScratchBytes'], sourceIndexSha256=p['sourceIndexSha256']))
    text = '# Retained snapshot-reuse attempt\n\n'
    text += f"{p['counts']['testsRun']} method(s), {p['counts']['failures']} failure(s), {p['counts']['errors']} error(s); {p['testSeconds']:.3f} test seconds / {p['elapsedSeconds']:.3f} harness seconds.\n\n"
    text += f"All 228 project/231 frozen inputs, six active harness files and 159 external pins remain stable. Matched origins, unchanged within-attempt compiler/driver identities and complete original raw output plus copies are retained: {p['rawScratchFiles']:,} files / {p['rawScratchBytes']:,} bytes; {p['sqliteConnections']} SQL connections.\n\n"
    text += '[Acquisition proof](proof.json), [result](attempt/result.json), [complete log](attempt/output.log).\n\n'
    if (folder / 'state-audit.json').exists(): text += '[Closed state audit](state-audit.json), [storage audit](storage-audit.json); all database bytes unchanged.\n\n'
    text += 'The [stage result](../README.md) distinguishes acquisition, complete independent semantics and remaining qualification/attestation gates. Original failures are never relabeled.\n'
    (folder / 'README.md').write_text(text)
assert len(passed) == 132
for name, method in ((names[-2], 'test_complete_gpio_history'), (names[-1], 'test_complete_pwm_history')):
    folder = R / name; scratch = folder / 'attempt/scratch' / method
    summary = read(scratch / 'inspection/summary.json'); checks = read(scratch / 'inspection/checks.json')
    group = read(scratch / 'group/result.json'); matrix = read(scratch / 'requested/matrix.json'); candidate = read(scratch / 'requested/candidate.json')
    assert group['status'] == 'captured' and group['error'] is None and len(group['cases']) == len(summary['cases']) == len(matrix['cases']) == 30
    assert len(candidate['steps']) == 1 and candidate['parameters'] == {}
    assert checks['checkerCalls'] == dict(inspect_timing_challenge=8, inspect_clock_challenge=3, inspect_lifecycle_challenge=10, inspect_authority_challenge=3, inspect_resource_challenge=1)
    assert checks['earlyArchiveRefusals'] == 3 and checks['independentReaderPure'] and checks['requestedSetupPreserved'] and checks['fullOriginalGroupAssertions']
    for key in ('requiredMatrixCoverageChecked', 'independentOutcomeChecked', 'archiveAccountingChecked', 'trustedSetupMatched', 'implementationIdentityMatched'):
        assert summary[key] is True
    for key in ('configurationAttested', 'implementationIdentityAttested', 'runAssociationAttested', 'wallDeadlineAttested', 'actualAggregateStorageEnforced', 'qualificationPassed', 'physicalMeasurementChecked'):
        assert summary[key] is False
    profiles, outcomes = collections.Counter(), collections.Counter()
    for i, row in enumerate(summary['cases']):
        p = scratch / 'inspection' / ('case-%02d.json' % i); value = read(p)
        assert sha(p) == row['inspectionSha256'] and p.stat().st_size == row['inspectionBytes'] <= 65536
        assert row['caseId'] == group['cases'][i]['caseId'] == matrix['cases'][i]['caseId'] and row['expectedResponseVerified'] is True
        profiles[value['profile']] += 1
        if 'staticOutcome' in value: outcomes[value['staticOutcome']] += 1
        else:
            outcome = value.get('trial', value)['outcome']; outcomes[outcome.get('contractStatus', outcome.get('completionContract'))] += 1
    audit = read(folder / 'state-audit.json')['groups'][0]; storage = read(folder / 'storage-audit.json')
    assert audit['completedCases'] == 30 and audit['activeCaseId'] is None and len(audit['states']) == 26
    effects = {key: sum((s['effects'][i] or 0) for s in audit['states']) for i, key in enumerate(('activations', 'completed', 'canceled'))}
    effects.update(claims=sum(s['claims'] for s in audit['states']), owners=sum(s['owners'] for s in audit['states']))
    assert effects == dict(activations=21, completed=11, canceled=10, claims=0, owners=0)
    assert len(storage['databases']) == 52 and storage['totalBytes'] == summary['accounting']['observedStateBytes']
    assert all(x['pageSize'] == 1024 and x['integrity'] == ['ok'] for x in storage['databases'])
    groups.append(dict(attempt=name, candidateSteps=1, candidateParameters={}, fixedChallenges=25,
        summary=summary, checks=checks, profiles=dict(profiles), outcomes=dict(outcomes), states=26, databases=52,
        endpointEffects=effects, inspectionFiles=32, totalInspectionBytes=sum(p.stat().st_size for p in (scratch / 'inspection').iterdir())))
write(B / 'GROUP-ANALYSIS.json', dict(scope='132 distinct passing checks, including complete current one-step constant GPIO/PWM capture and independent group outcomes.',
    sourceIndexSha256=sha(B / 'implementation02/index.json'), distinctPassingMethods=len(passed), attempts=attempts,
    currentGroupsIndependentlyInspected=2, groups=groups, qualificationPassed=False, independentAgentReview=False))
text = '''# Complete current GPIO and PWM histories independently checked

**132 distinct methods pass:** 129 pure checks, the actual record-cutoff test,
and both complete current GPIO/PWM history pipelines. Each full pipeline checks
one constant, single-step candidate, its negative cases and all 25 fixed
challenges (30 total cases). This is two representative finite synthetic
candidates, not arbitrary applications or physical qualification.

| Attempt | Status | Test seconds | Raw bytes |
|---|---|---:|---:|
'''
for row in attempts: text += f"| [{row['attempt']}]({row['attempt']}/README.md) | {row['status']} | {row['testSeconds']:.3f} | {row['rawScratchBytes']:,} |\n"
text += '''
The first pure run retains 128 passes and one new test expectation failure.
Source02 changes only that assertion to require containment, dependency and alias
graph checks. Production matches source01. The corrected 129-method run passes,
including the subsequent repeated-cycle refusals. Original failures, scratch
and complete copies remain immutable.

The full test durations include setup, capture, independent inspection and three
early forged-archive refusals. The original 60s capture checks and 180s harness
deadline remain; these observations are not benchmarks or independent wall-time
attestation. No required case, effect, record, file or byte ceiling is widened.

| Verified group | GPIO | PWM |
|---|---:|---:|
| Cases / fixed challenges | 30 / 25 | 30 / 25 |
| Actual operations / reserved admissions | 28 / 44 | 28 / 44 |
| Ticks / charged worker records | 99 / 3,832 | 99 / 3,832 |
| Producer bytes | 10,149,988 | 10,289,708 |
| Retained state bytes | 4,510,720 | 4,585,472 |
| Derived bytes | 14,660,708 | 14,875,180 |
| Case-inspection bytes (30 documents) | 216,187 | 217,881 |
| Complete inspection output (32 files) | 227,991 | 229,685 |

Each full run retains 26 states / 52 databases. Closed read-only audits find
21 activations, 11 completions, 10 cancellations and no claims or owners; integrity
checks and hashes pass. These endpoint audits supplement the separate complete
history checks. The actual record-cutoff test retains the same 977,425 raw bytes
as before and stops the group at its original lowered record budget.

Independent readers run with file/SQL/clock access forbidden and dispatch exactly
8 timing, 3 clock, 10 lifecycle, 3 authority and 1 shared-resource checks. Separate
pre-run setup is preserved. Every case response, nominal completion, negative
outcome, archive file and operation/tick/record/byte association is checked.
The reader's matrix, outcome, accounting, trusted-setup and identity-match flags
are true. The acquisition proof itself makes no semantic claim.

Configuration/implementation/run/wall attestation, hard aggregate storage,
physical measurement and qualification flags remain false. The next required
work is trusted process/run association, actual aggregate enforcement and
supervised public qualification. Persistent applications, prompt learning and
real device/driver/intelligence-hub providers remain required by the full goal.

[Design](../DESIGN.md), [test correction](../CORRECTION.md),
[source01 review](../implementation01/source-review.json), [source02 review](../implementation02/source-review.json),
[unchanged semantic methods](../source-invariant-review.json), [analysis](../GROUP-ANALYSIS.json),
[GPIO inspection](attempt04-passed-gpio-history/attempt/scratch/test_complete_gpio_history/inspection/summary.json),
[PWM inspection](attempt05-passed-pwm-history/attempt/scratch/test_complete_pwm_history/inspection/summary.json).

All attempts preserve 228 project/231 frozen inputs, six active harness inputs,
159 external pins, actual origins and within-run identities. Review is by the
primary agent; helpers remain usage-limited. Live HMS, adjacent Harness,
physical devices/MCUs, inference and external controllers remain untouched.
'''
(R / 'README.md').write_text(text)
print(json.dumps(dict(distinctPassingMethods=len(passed), currentGroupsIndependentlyInspected=2,
    groups=[dict(attempt=g['attempt'], accounting=g['summary']['accounting'], outcomes=g['outcomes']) for g in groups])))

"""Summarize verified terminated attempts without modifying retained evidence."""
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd()
B = ROOT / 'artifacts/implementation/pat-io-encoding'
R = B / 'results'
NAMES = ('attempt01-passed96', 'attempt02-passed-cutoff', 'attempt03-passed-gpio', 'attempt04-passed-pwm')
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, value):
    with p.open('x') as f: f.write(json.dumps(value, indent=2) + '\n')

proofs = [read(R / name / 'proof.json') for name in NAMES]
passed = set()
for name, proof in zip(NAMES, proofs):
    assert proof['status'] == 'passed'
    passed.update(read(R / name / 'attempt/actual-tests.json')['executed'])
    assert proof['sourceFilesVerified'] == 222 and proof['frozenFilesVerified'] == 225
    text = ('# Retained encoding validation attempt\n\n'
        f"{proof['counts']['testsRun']} tests passed in {proof['testSeconds']:.3f} test seconds; "
        f"{proof['elapsedSeconds']:.3f} harness seconds. The complete raw tree retains "
        f"{proof['rawScratchFiles']:,} files / {proof['rawScratchBytes']:,} bytes.\n\n"
        '[Acquisition proof](proof.json), [result](attempt/result.json), '
        '[test log](attempt/output.log), [exact selection](attempt/actual-tests.json).\n\n'
        'The 222 project inputs, 225 frozen entries, six active harness inputs and '
        '159 selected external files remained stable. Executed origins matched. '
        'Compiler and driver identities remained unchanged within the attempt. '
        'Original raw output and complete acquisition are retained.\n\n')
    if name != NAMES[0]:
        text += '[Closed state audit](state-audit.json) and [storage audit](storage-audit.json) '
        text += 'read only terminated retained database copies and checked unchanged hashes.\n\n'
    text += 'This is synthetic capture evidence, not independent qualification, physical measurement or a hard aggregate filesystem quota.\n'
    (R / name / 'README.md').write_text(text)
assert len(passed) == 99
groups = []
for name, proof in zip(NAMES[2:], proofs[2:]):
    folder = R / name
    paths = list((folder / 'attempt/scratch').rglob('group/result.json'))
    assert len(paths) == 1
    group = read(paths[0]); audit = read(folder / 'state-audit.json')['groups'][0]
    storage = read(folder / 'storage-audit.json')
    assert group['status'] == 'captured' and len(group['cases']) == 30
    assert len(audit['states']) == 26 and len(storage['databases']) == 52
    assert all(s['claims'] == s['owners'] == 0 for s in audit['states'])
    assert all(db['pageSize'] == 1024 for db in storage['databases'])
    effects = dict(zip(('activations', 'completed', 'canceled'),
        [sum((state['effects'][i] or 0) for state in audit['states']) for i in range(3)]))
    effects.update(claims=0, owners=0)
    groups.append(dict(attempt=name, testSeconds=proof['testSeconds'], elapsedSeconds=proof['elapsedSeconds'],
        groupStatus=group['status'], completedCases=len(group['cases']), accounting=group['accounting'],
        rawScratchFiles=proof['rawScratchFiles'], rawScratchBytes=proof['rawScratchBytes'],
        createdStates=26, endpointEffects=effects, sqliteBytes=storage['totalBytes'],
        sqlitePayloadBytes=storage['payloadBytes'], sqliteUnusedBytes=storage['unusedBytes']))
write(B / 'GROUP-ANALYSIS.json', dict(scope='Both complete synthetic groups under unchanged limits; no independent full-history qualification claim.',
    sourceIndexSha256=sha(B / 'implementation01/index.json'), distinctPassingMethods=99, groups=groups,
    originalFailedPwmRetained=True, tablePageMemoAdded=False, limitsRelaxed=False,
    independentOutcomeChecked=False, configurationAttested=False, actualAggregateStorageEnforced=False, qualificationPassed=False))
text = '# Complete GPIO and PWM capture with one encoding per envelope\n\n'
text += '**99 distinct methods pass:** 96 selected checks, the actual 250-record cutoff, and both unchanged full groups.\n\n'
text += '| Attempt | Test seconds | Retained raw bytes | Result |\n|---|---:|---:|---|\n'
for name, proof in zip(NAMES, proofs):
    text += f"| [{name}]({name}/README.md) | {proof['testSeconds']:.3f} | {proof['rawScratchBytes']:,} | Pass |\n"
text += '\nBoth groups execute all 30 cases, including all 25 fixed challenges, under the original 60s group deadline. '
text += 'Each retains 26 states and 52 compact databases. The endpoint audits find no retained claims or owners. '
text += 'Exact operation, tick, record, producer/derived-byte and source checks remain in the original full methods.\n\n'
text += 'The three production changes remove duplicate evidence and topology encodings. Nine focused methods verify exact bytes, '
text += 'reference reuse, both evidence streams, budget precedence and retained exclusive-create/fsync failures. '
text += 'All original validations, schemas, guards, SQL queries, locks, durability and ceilings remain. No page cache was added.\n\n'
text += 'The [previous PWM deadline failures](../../pat-io-group-efficiency/results/README.md) remain retained. '
text += 'Harness01 in this stage was never executed: pre-execution review found its inherited 87-item literal in a 96-target guard. '
text += 'Corrected [harness05](../harness05/review.json) pins all 96 targets; the original preparation remains. '
text += 'Review was by the primary agent; existing helpers were unavailable under their usage limit.\n\n'
text += '[Design](../DESIGN.md), [source review](../implementation01/source-review.json), [complete group analysis](../GROUP-ANALYSIS.json). '
text += 'These single-run timings are observations, not a benchmark or real-time guarantee. '
text += 'Full semantic composition, trusted setup/run association, enforced aggregate storage, public qualification and learning remain unfinished. '
text += 'Live HMS, the adjacent Harness, physical hardware and intelligence-hub services were not changed or exercised.\n'
(R / 'README.md').write_text(text)
print(json.dumps(dict(distinctPassingMethods=len(passed), groups=[dict(attempt=g['attempt'], testSeconds=g['testSeconds'], charged=g['accounting']['charged'], rawScratchBytes=g['rawScratchBytes'], endpointEffects=g['endpointEffects']) for g in groups])))

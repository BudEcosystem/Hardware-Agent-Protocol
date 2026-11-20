"""Seal retained terminal evidence and reviewed disjoint follow-up harnesses."""
import hashlib
import json
from pathlib import Path
import stat

BASE = Path('artifacts/implementation/pat-io-refusal-history')
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2) + '\n')
def seal(folder, scope):
    rows = []
    assert not (folder / 'index.json').exists()
    for path in sorted(folder.rglob('*')):
        assert not path.is_symlink()
        if path.is_dir(): continue
        assert stat.S_ISREG(path.stat().st_mode)
        rows.append(dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    write(folder / 'index.json', dict(scope=scope, files=rows))
    return dict(path=(folder / 'index.json').as_posix(), sha256=sha(folder / 'index.json'), files=len(rows), bytes=sum(row['bytes'] for row in rows))

out = BASE / 'results/attempts01-02'
proof = read(out / 'proof.json')
assert proof['allSelectionsPassed'] is False
assert [p['status'] for p in proof['attempts']] == ['passed', 'timed_out']
retained = seal(out, 'Actual passing regression72 and timed-out refusal56 attempts, unchanged source; not a complete 128-method pass.')
original_path = BASE / 'selection-plan.json'
assert sha(original_path) == '87ce18c5926154c353a784e62ded44a6404b23307e89734082572117bec9113d'
original = read(original_path)
groups = []
for name, count in [('harness03-observation27', 27), ('harness04-refusal29', 29)]:
    folder = BASE / name
    review = dict(scope='Primary-agent complete adaptation diff review before release.',
        sourceIndexSha256=original['sourceIndexSha256'], borrowedHarnessIndexSha256=original['groups'][1]['indexSha256'],
        closedMethods=count, projectFiles=7060, frozenFiles=7065, deadlineSeconds=180,
        reviewed=['Only scope labels, exact counts and closed class selection change.',
                  'Original deadline, child ownership/finalization, package/origin checks and scratch retention are unchanged.',
                  'Both selections exactly partition the original timed-out 56 methods; source, tests and fixtures are unchanged.',
                  'Earlier passing72 is reused with the identical source pin. No larger single-run verdict is claimed.',
                  'No protocol, effect, evidence or scratch limit widening.'],
        independentReview=False, releasedBy='primary-agent', projectExecutionDuringPreparation=False)
    write(folder / 'source-review.json', review)
    index = seal(folder, 'Frozen reviewed ' + name + ' pure harness; original execution and evidence bounds unchanged.')
    assert index['files'] == 12
    groups.append(dict(harness=name, testCount=count, indexSha256=index['sha256'], targetsSha256=sha(folder / 'targets.json')))
targets = [t for g in groups for t in read(BASE / g['harness'] / 'targets.json')['targets']]
assert targets == read(BASE / original['groups'][1]['harness'] / 'targets.json')['targets']
reused = read(BASE / original['groups'][0]['harness'] / 'targets.json')['targets']
assert reused + targets == original['targets'] and len(set(reused + targets)) == 128
plan = dict(scope='Reuse unchanged passing72; split the retained timed-out56 into unchanged27 and29, each with its original180-second deadline.',
    originalSelectionPlanSha256=sha(original_path), retainedOriginalResultIndexSha256=retained['sha256'],
    sourceIndexSha256=original['sourceIndexSha256'],
    reusedPassingGroup=dict(original['groups'][0], attempt='attempt01-regression72'),
    groups=groups, totalDistinctMethods=128, inheritedMethods=99, newMethods=29,
    targetUnion=reused + targets, noSingle128MethodInvocation=True,
    preparationScriptSha256=sha(BASE / 'prepare-followup-harnesses.py'))
write(BASE / 'followup-selection-plan.json', plan)
print(json.dumps(dict(retained=retained, harnesses=groups, planSha256=sha(BASE / 'followup-selection-plan.json'))))

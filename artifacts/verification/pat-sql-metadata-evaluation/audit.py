"""Read-only result/source audit; no SQLite connection or benchmark replay."""
import collections
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


index = BASE / 'inputs.json'
assert sha(index) == 'c1c79e17db9a9cc77ce1d1ed4e0ce11856e64ccb5f5dcca93adcabdcbed61c2b'
rows = read(index)['files']
assert len(rows) == 39
for row in rows:
    path = BASE / row['path']
    assert not path.is_symlink() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
attempt = BASE / 'attempt01'
assert read(attempt / 'inputs-before.json') == read(attempt / 'inputs-after.json') == rows
result = read(attempt / 'result.json')
assert result['status'] == 'passed' and result['currentPass'] and result['exitCode'] == 0
assert result['childState'] == 'exited' and result['inputIndexUnchanged'] and result['inputsUnchanged']
assert (attempt / 'stderr.log').stat().st_size == 0
command = read(attempt / 'command.json')
assert command['wallLimitSeconds'] == 60 and command['cpuLimitSeconds'] == 30
assert command['retainedOutputLimitBytes'] == 4194304 and command['inputIndexSha256'] == sha(index)
assert command['argv'][1:4] == ['-I', '-S', '-B']
report = read(attempt / 'stdout.json')
assert report['status'] == 'passed' and not report['prohibitedAttempts'] and report['inputsUnchanged']
assert report['differentialCases'] == len(report['cases']) == 410
assert len({r['id'] for r in report['cases']}) == 410
assert sum(r['status'] == 'accepted' for r in report['cases']) == report['accepted'] == 130
assert sum(r['status'] == 'refused' for r in report['cases']) == report['refused'] == 280
for row in report['cases']:
    if row['status'] == 'accepted':
        assert row['referenceSqlCalls'] == row['candidateSqlCalls'] + 1
assert report['retainedTables'] == 15 and report['retainedPageBytesExact']
assert report['rowGuardPreserved'] and report['freshDataBetweenCaptures']
assert report['persistentDatabasesOpened'] == 0 and not report['hmsRuntimeImported']
assert not report['qualifiedWorkerLaunched'] and not report['durableEvidencePublished']
assert report['evidenceWriterSubstituted'] and not report['productionAdopted']
pairs = report['timingPairs']
assert len(pairs) == 9 and report['capturesPerTablePerSample'] == 16
for i, pair in enumerate(pairs):
    assert pair['order'] == (['reference', 'candidate'] if i % 2 == 0 else ['candidate', 'reference'])
    assert pair['cpuRatio'] == pair['candidate']['cpuNs'] / pair['reference']['cpuNs']
left = sorted(p['reference']['cpuNs'] for p in pairs)[4]
right = sorted(p['candidate']['cpuNs'] for p in pairs)[4]
assert report['referenceMedianCpuNs'] == left and report['candidateMedianCpuNs'] == right
assert report['candidateToReferenceMedianCpuRatio'] == right / left
assert report['fasterPairs'] == sum(p['cpuRatio'] < 1 for p in pairs) == 3
assert report['integrationScreenPassed'] is False
for row in read(BASE / 'borrowed-inputs.json'):
    assert sha(ROOT / row['source']) == sha(BASE / row['copy']) == row['sha256']
runtime = read(BASE / 'runtime-inputs.json')
for row in runtime['files']:
    path = Path(row['path'])
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
summary = {k: v for k, v in report.items() if k != 'cases'}
summary.update(retentionAuditPassed=True, inputIndexSha256=sha(index),
    rawReportSha256=sha(attempt / 'stdout.json'), attemptResultSha256=sha(attempt / 'result.json'),
    frozenInputsVerified=len(rows), borrowedInputsVerified=26,
    selectedRuntimeInputsVerified=len(runtime['files']),
    refusalCounts=dict(collections.Counter(r['refusal'] for r in report['cases'] if r['status'] == 'refused')),
    auditDatabaseConnectionsOpened=0, benchmarkRepeated=False,
    sourceReviewSha256=sha(BASE / 'SOURCE_REVIEW.json'))
with (BASE / 'RESULTS.json').open('x') as stream:
    json.dump(summary, stream, indent=2); stream.write('\n')
decision = {'adopted': False, 'advanceToWholeWorkerIntegration': False,
    'semanticComparisonPassed': True, 'performanceScreenPassed': False,
    'reason': 'Median CPU was 6.3335% higher and only three of nine pairs were faster.',
    'candidateToReferenceMedianCpuRatio': right / left, 'fasterPairs': 3,
    'repeatBenchmarkPlanned': False, 'productionRuntimeChanged': False,
    'wholeWorkerQualificationPerformed': False}
with (BASE / 'DECISION.json').open('x') as stream:
    json.dump(decision, stream, indent=2); stream.write('\n')
print(json.dumps({'retentionAuditPassed': True, 'differentialCases': 410,
                  'candidateToReferenceMedianCpuRatio': right / left, 'adopted': False}))

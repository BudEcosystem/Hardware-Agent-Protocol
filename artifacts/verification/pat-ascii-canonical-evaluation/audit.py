"""Audit retained pure-comparison bytes and derive fixed paired measurements."""
import ast
import hashlib
import json
from pathlib import Path
import statistics

BASE = Path(__file__).resolve().parent
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE / 'inputs.json') == '0122055e25f6bb669e8ac8458702a2a2a8356096edba242982519520fd118090'
rows = read(BASE / 'inputs.json')['files']
assert len(rows) == 42 and rows == read(BASE / 'attempt01/inputs-before.json') == read(BASE / 'attempt01/inputs-after.json')
for row in rows:
    p = BASE / row['path']
    assert not p.is_symlink() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
for row in read(BASE / 'borrowed-inputs.json'):
    assert sha(Path(row['source'])) == row['sha256'] == sha(BASE / row['copy'])
for row in read(BASE / 'runtime-inputs.json')['files']:
    p = Path(row['path'])
    assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
body = (BASE / 'references/contracts.py').read_text()
nodes = {n.name: n for n in ast.parse(body).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
reference = ast.parse((BASE / 'reference_functions.py').read_bytes())
assert len(reference.body) == 7 and all(ast.dump(n) == ast.dump(nodes[n.name]) for n in reference.body)
assert (BASE / 'reference_functions.py').read_bytes() == (BASE / 'candidate_functions.py').read_bytes()
helpers = body[body.index('from types import FunctionType as _FunctionType'):body.index('_SCHEMA =')].rstrip() + '\n'
assert helpers == (BASE / 'reference_helpers.py').read_text()
assert (BASE / 'candidate-contracts.py').read_text() == body.replace(helpers.rstrip(), (BASE / 'candidate_helpers.py').read_text().rstrip())
old = {n.name: n for n in ast.parse(helpers).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
new = {n.name: n for n in ast.parse((BASE / 'candidate_helpers.py').read_bytes()).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
assert set(new) == set(old) | {'_UseUtf16Order', '_ascii_integer_tree'}
assert all(ast.dump(n) == ast.dump(new[k]) for k, n in old.items() if k != '_canonical_bytes')
attempt = read(BASE / 'attempt01/result.json')
report = read(BASE / 'attempt01/stdout.json')
assert attempt['currentPass'] and attempt['exitCode'] == 0 and attempt['childState'] == 'exited'
assert attempt['inputsUnchanged'] and attempt['inputIndexUnchanged'] and not (BASE / 'attempt01/stderr.log').read_bytes()
assert report['status'] == 'passed' and report['prohibitedAttempts'] == [] and report['customHooksInvoked'] == 0
assert report['inputsUnchanged'] and report['documentInputsUnchanged'] and report['referenceValidationUnchanged']
assert report['referenceIsCurrentGuardedEncoder'] and report['vendorOracleCheckedOnUnmodifiedDependencies']
assert len(report['cases']) == len({c['id'] for c in report['cases']}) == report['differentialCases'] == 1875
assert sum(c['status'] == 'accepted' for c in report['cases']) == 1342
assert report['unicodeScalarValues'] == 1112064 and len(report['fallbackChecks']) == 13
assert report['originalEncoderRouting'] == [dict(input='integer', originalEncoderCalls=0), dict(input='root-float', originalEncoderCalls=1), dict(input='nested-float', originalEncoderCalls=1)]
assert report['detachedAsciiContainers'] and len(report['asciiRoutes']) == 6
assert report['asciiRoutes'] == [dict(input=n, utf16Fallback=u, vendorFallback=v) for n, u, v in (
    ('ascii-fields', False, False), ('unicode-values', False, False), ('nested-unicode-field', True, False),
    ('astral-order', True, False), ('float-before-unicode', False, True), ('float-after-unicode', True, True))]
assert len(report['upstreamVectors']) == 6 and all(r['upstreamBytesMatched'] for r in report['upstreamVectors'])
assert [r['name'] for r in report['upstreamVectors'] if r['hostProfileOutcome'] == 'refused'] == ['values.json']
samples = report['samples']
assert len(samples) == 18 and all(s['calls'] == 256 for s in samples)
medians = {label: statistics.median(s['cpuNanoseconds'] for s in samples if s['implementation'] == label) for label in ('reference', 'candidate')}
assert medians == report['medianCpuNanoseconds']
ratios = []
for i in range(9):
    pair = samples[2*i:2*i+2]
    assert [r['implementation'] for r in pair] == (['candidate', 'reference'] if i % 2 else ['reference', 'candidate'])
    assert all(r['round'] == i and r['cpuNanoseconds'] > 0 and r['wallNanoseconds'] > 0 for r in pair)
    measured = {r['implementation']: r['cpuNanoseconds'] for r in pair}
    ratios.append(measured['candidate']/measured['reference'])
ratio = medians['candidate']/medians['reference']
assert ratio == report['candidateToReferenceMedianCpuRatio'] == attempt['candidateToReferenceMedianCpuRatio']
summary = dict(status='verified-pure-candidate', differentialCases=1875, acceptedCases=1342, refusedCases=533,
    unicodeScalarValues=1112064, helperFallbackChecks=13, explicitAsciiRoutes=6,
    detachedAsciiContainers=True, publicDefinitionAstsUnchanged=7, referenceIsCurrentGuardedEncoder=True,
    vendorOracleCheckedOnUnmodifiedDependencies=True, inputIndexSha256=sha(BASE / 'inputs.json'),
    resultSha256=sha(BASE / 'attempt01/result.json'), reportSha256=sha(BASE / 'attempt01/stdout.json'),
    inputFiles=len(rows), inputsUnchanged=True, benchmarkRounds=9, callsPerSample=256,
    medianCpuNanoseconds=medians, candidateToReferenceMedianCpuRatio=ratio, pairedCpuRatios=ratios,
    allNinePairsLower=all(r < 1 for r in ratios), projectChanged=False, projectPackageImported=False,
    workerExecuted=False, physicalObjectiveVerified=False, integrationQualified=False,
    wholeWorkerPerformanceQualified=False, independentReview=False, goalStatus='active')
with (BASE / 'RESULTS.json').open('x') as out: json.dump(summary, out, indent=2); out.write('\n')
print(json.dumps(summary))

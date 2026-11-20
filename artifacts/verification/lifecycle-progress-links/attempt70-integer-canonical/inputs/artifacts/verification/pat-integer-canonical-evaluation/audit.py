"""Independently verify fixed pure-evaluation receipts and derive paired timings."""
import ast
import hashlib
import json
from pathlib import Path
import statistics

BASE=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(BASE/'inputs.json')=='a0df3095c4225e11c4b1b0bfdeac21751ed1970cc0313c4c2d8f5dba853aba61'
rows=read(BASE/'inputs.json')['files']
assert rows==read(BASE/'attempt01/inputs-before.json')==read(BASE/'attempt01/inputs-after.json')
for row in rows:
    path=BASE/row['path'];assert not path.is_symlink()
    assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
for row in read(BASE/'borrowed-inputs.json'):
    assert sha(Path(row['source']))==row['sha256']==sha(BASE/row['copy'])
for row in read(BASE/'runtime-inputs.json')['files']:
    assert Path(row['path']).stat().st_size==row['bytes'] and sha(Path(row['path']))==row['sha256']
original=ast.parse((BASE/'references/contracts.py').read_bytes())
nodes={n.name:n for n in original.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
reference=ast.parse((BASE/'reference_functions.py').read_bytes())
assert len(reference.body)==7 and all(ast.dump(n)==ast.dump(nodes[n.name]) for n in reference.body)
assert (BASE/'reference_functions.py').read_text().replace('result = rfc8785.dumps(value)','result = _canonical_bytes(value)')==(BASE/'candidate_functions.py').read_text()
attempt=read(BASE/'attempt01/result.json');report=read(BASE/'attempt01/stdout.json')
assert attempt['currentPass'] and attempt['exitCode']==0 and attempt['childState']=='exited'
assert attempt['inputsUnchanged'] and attempt['inputIndexUnchanged'] and not (BASE/'attempt01/stderr.log').read_bytes()
assert report['status']=='passed' and report['prohibitedAttempts']==[] and report['customHooksInvoked']==0
assert report['inputsUnchanged'] and report['documentInputsUnchanged'] and report['referenceValidationUnchanged']
assert len(report['cases'])==len({c['id'] for c in report['cases']})==report['differentialCases']==1668
assert report['unicodeScalarValues']==1112064 and len(report['fallbackChecks'])==13
assert report['originalEncoderRouting']==[dict(input='integer',originalEncoderCalls=0),dict(input='root-float',originalEncoderCalls=1),dict(input='nested-float',originalEncoderCalls=1)]
assert len(report['upstreamVectors'])==6 and all(r['upstreamBytesMatched'] for r in report['upstreamVectors'])
assert [r['name'] for r in report['upstreamVectors'] if r['hostProfileOutcome']=='refused']==['values.json']
samples=report['samples'];assert len(samples)==18 and all(s['calls']==256 for s in samples)
medians={label:statistics.median(s['cpuNanoseconds'] for s in samples if s['implementation']==label) for label in ('reference','candidate')}
assert medians==report['medianCpuNanoseconds']
ratios=[]
for i in range(9):
    pair=samples[2*i:2*i+2]
    assert [r['implementation'] for r in pair]==(['candidate','reference'] if i%2 else ['reference','candidate'])
    assert all(r['round']==i and r['cpuNanoseconds']>0 and r['wallNanoseconds']>0 for r in pair)
    measured={r['implementation']:r['cpuNanoseconds'] for r in pair}
    ratios.append(measured['candidate']/measured['reference'])
ratio=medians['candidate']/medians['reference']
assert ratio==report['candidateToReferenceMedianCpuRatio']==attempt['candidateToReferenceMedianCpuRatio']
summary=dict(status='verified-pure-candidate',differentialCases=1668,acceptedCases=1135,refusedCases=533,
    unicodeScalarValues=1112064,helperFallbackChecks=13,upstreamVectorPairs=6,guardedFloatFallbackObserved=True,
    inputIndexSha256=sha(BASE/'inputs.json'),resultSha256=sha(BASE/'attempt01/result.json'),reportSha256=sha(BASE/'attempt01/stdout.json'),
    inputFiles=len(rows),inputsUnchanged=True,referenceAstAndOnlyCallChangeVerified=True,
    benchmarkRounds=9,callsPerSample=256,medianCpuNanoseconds=medians,candidateToReferenceMedianCpuRatio=ratio,
    pairedCpuRatios=ratios,allNinePairsLower=all(r<1 for r in ratios),
    projectChanged=False,projectPackageImported=False,workerExecuted=False,physicalObjectiveVerified=False,
    integrationQualified=False,wholeWorkerPerformanceQualified=False,independentReview=False,goalStatus='active')
assert sum(c['status']=='accepted' for c in report['cases'])==summary['acceptedCases']
with (BASE/'RESULTS.json').open('x') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
print(json.dumps(summary))

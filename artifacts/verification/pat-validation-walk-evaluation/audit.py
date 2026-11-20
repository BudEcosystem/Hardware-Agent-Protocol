"""Audit the one completed pure evaluation without rerunning either function."""
import ast
import hashlib
import json
from pathlib import Path
import statistics

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
PIN='96436730209b848d37913ac7015adcfe2c7fd82cdd8636c70b7b4497ad849b4f'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.stat().st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(path,row):assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
assert sha(BASE/'inputs.json')==PIN
rows=read(BASE/'inputs.json')['files'];assert len(rows)==16
for row in rows:verify(BASE/row['path'],row)
attempt=BASE/'attempt01';result=read(attempt/'result.json');report=read(attempt/'stdout.json')
assert result['status']=='passed' and result['currentPass'] and result['childState']=='exited' and result['exitCode']==0
assert result['inputIndexUnchanged'] and result['inputsUnchanged'] and result['goalStatus']=='active'
assert read(attempt/'inputs-before.json')==rows==read(attempt/'inputs-after.json')
assert (attempt/'stderr.log').stat().st_size==0
command=read(attempt/'command.json')
assert command['inputIndexSha256']==PIN and command['argv'][1:4]==['-I','-S','-B']
assert command['wallLimitSeconds']==60 and command['cpuLimitSeconds']==30 and command['retainedOutputLimitBytes']==4194304
assert sha(Path(command['argv'][0]).resolve())==command['pythonExecutableSha256']
assert report['status']=='passed' and report['differentialCases']==468 and report['customHooksInvoked']==0 and report['prohibitedAttempts']==[]
assert report['inputsUnchanged'] and report['documentInputsUnchanged'] and report['sourceFunctionsOnly']
assert all(report[key] is False for key in ('publicParserTested','canonicalizerTested','workerExecuted','productionChanged','physicalObjectiveVerified','timingQualified'))
sources={}
for folder,pin,prefix in ((ROOT/'artifacts/implementation/pat-vault-original-run/implementation02','4a1f5b97cb29e897fc865ca5dcf46397bfdec6c4154a302dfdac1b546e66c4f4',ROOT),
    (ROOT/'artifacts/verification/pat-vault-worker-profile','3dfd5586c4256b8e77a8d9ce3cbcf99eea515653d600e75deeb3a6ddb1383325',ROOT/'artifacts/verification/pat-vault-worker-profile')):
    assert sha(folder/'index.json')==pin
    for row in read(folder/'index.json')['files']:sources[str(prefix/row['path'])]=row
for row in read(BASE/'borrowed-inputs.json'):
    source=ROOT/row['source'];verify(source,sources[str(source)])
    verify(source,row);verify(BASE/row['copy'],row)
original=ast.parse((BASE/'references/contracts.py').read_bytes())
node=next(n for n in original.body if isinstance(n,ast.FunctionDef) and n.name=='check_tree')
assert ast.dump(node)==ast.dump(ast.parse((BASE/'reference_check_tree.py').read_bytes()).body[0])
failed=read(BASE/'failed-preparation01/result.json')
assert not failed['childLaunched'] and not failed['projectExecuted']
assert sha(BASE/'failed-preparation01/child.py.txt')==failed['failedChildSha256']
samples=report['samples'];assert len(samples)==18 and report['benchmarkRounds']==9 and report['callsPerSample']==256
ratios=[];slower=[]
for number in range(9):
    pair=samples[number*2:number*2+2]
    assert [r['implementation'] for r in pair]==(['reference','candidate'] if number%2==0 else ['candidate','reference'])
    assert all(r['round']==number and r['calls']==256 and r['cpuNanoseconds']>0 and r['wallNanoseconds']>0 for r in pair)
    pair={r['implementation']:r for r in pair}
    ratio=pair['candidate']['cpuNanoseconds']/pair['reference']['cpuNanoseconds'];ratios.append(ratio)
    if ratio>1:slower.append(number)
medians={name:statistics.median(row['cpuNanoseconds'] for row in samples if row['implementation']==name) for name in ('reference','candidate')}
assert medians==report['medianCpuNanoseconds']
ratio=medians['candidate']/medians['reference']
assert ratio==report['candidateToReferenceMedianCpuRatio']==result['candidateToReferenceMedianCpuRatio']
assert slower==[2,3]
summary=dict(status='verified-pure-evaluation',inputIndexSha256=PIN,inputs=16,differentialCases=468,
    originalFunctionAstVerified=True,retainedInputsVerified=True,originalPreparationFailureRetained=True,
    medianCpuNanoseconds=medians,candidateToReferenceMedianCpuRatio=ratio,
    pairedCpuRatios=ratios,candidateSlowerRounds=slower,measurementCallsPerImplementation=2304,
    adopted=False,decision='Modest inconsistent local measurement; insufficient basis for a deadline correction. Preserve candidate, keep production unchanged.',
    workerExecuted=False,publicParserTested=False,canonicalizerTested=False,
    productionChanged=False,deadlineCauseEstablished=False,physicalObjectiveVerified=False,
    independentReview=False,goalStatus='active')
with (BASE/'RESULTS.json').open('x') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
print(json.dumps({key:summary[key] for key in ('status','differentialCases','candidateToReferenceMedianCpuRatio','adopted','goalStatus')}))

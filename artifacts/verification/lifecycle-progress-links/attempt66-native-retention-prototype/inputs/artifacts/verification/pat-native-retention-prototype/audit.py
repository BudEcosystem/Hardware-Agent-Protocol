"""Recompute prototype evidence and preserve the separate failed trace preparation."""
import ast
import hashlib
import json
from pathlib import Path
import stat
import statistics

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PRIOR=ROOT/'artifacts/verification/pat-retention-scan-cost'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
assert sha(BASE/'inputs.json')=='7a7319c430af6302a2617c190a5eebe6ce5dd2eebab029540c2b12dd36276023'
for row in read(BASE/'inputs.json')['files']:
    path=BASE/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
for row in read(PRIOR/'inputs.json')['files']:
    path=PRIOR/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
reference={node.name:node for node in ast.parse((BASE/'reference.py').read_text()).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
for row in read(PRIOR/'preparation.json')['extracted']:
    if row['name'] in reference:
        assert hashlib.sha256(ast.dump(reference[row['name']],include_attributes=False).encode()).hexdigest()==row['astSha256']
build=read(BASE/'build01/build.json')
assert build['returnCode']==0 and build['stdout']==build['stderr']==''
assert sha(BASE/'scan.c')==build['sourceSha256'] and sha(BASE/'build01/scan')==build['binarySha256']
assert sha(Path(build['compiler']))==build['compilerSha256']
result=read(BASE/'attempt01/result.json');controls=read(BASE/'attempt01/controls.json')
assert result['status']==controls['status']=='passed' and result['error'] is None
assert result['sourceInputsUnchanged'] and result['sourceInputsSha256']==sha(BASE/'inputs.json')
assert result['deniedEvents']==[] and len(result['launches'])==34
assert controls['controls']==result['controls'] and len(result['controls'])==20
assert len({row['name'] for row in result['controls']})==20
for row in result['controls']:
    actual=row['native']['result'];expected=row['expected']
    assert {key:actual[key] for key in expected}==expected
    assert row['native']['exitCode']==(0 if expected['reason']=='OK' else 1)
assert {row['expected']['reason'] for row in result['controls']}=={'OK','OS_ERROR','QUALIFICATION_UNSAFE_FILE','QUALIFICATION_RETENTION_UNKNOWN'}
before=read(BASE/'attempt01/original-metadata-before.json')
assert before==read(BASE/'attempt01/original-metadata-after.json')==read(PRIOR/'attempt01/metadata-after.json')
assert len(before)==3227 and sum(row['size'] for row in before if stat.S_ISREG(row['mode']))==11889866
assert result['originalMetadataUnchanged'] and len(result['originalOwnerWriterLocks'])==49
assert result['caseDatabaseReads']==result['qualificationWorkersLaunched']==0
samples=result['samples'];assert len(samples)==14
ratios=[]
for number in range(7):
    pair=samples[2*number:2*number+2]
    assert [row['mode'] for row in pair]==(['python','native'] if number%2==0 else ['native','python'])
    for row in pair:
        value=row['result'];assert row['round']==number and row['exitCode']==0
        assert {key:value[key] for key in ('reason','errno','files','logicalBytes','scans')}==dict(reason='OK',errno=0,files=3227,logicalBytes=11889866,scans=5)
        assert value['cpuMicroseconds']>0 and row['outerWallNanoseconds']>0
    values={row['mode']:row['result']['cpuMicroseconds'] for row in pair};ratios.append(values['native']/values['python'])
medians={mode:statistics.median(row['result']['cpuMicroseconds']/5 for row in samples if row['mode']==mode) for mode in ('python','native')}
assert medians==result['medianCpuMicrosecondsPerScan'] and ratios==result['pairedCpuRatios']
ratio=medians['native']/medians['python'];assert ratio==result['nativeToPythonMedianCpuRatio']
trace=read(BASE/'trace02/result.json');assert trace['status']=='passed' and len(trace['scopes'])==5
assert trace['fixtureMetadataUnchanged'] and not trace['originalCaseTreeTouched']
assert trace['binarySha256']==build['binarySha256'] and sha(BASE/'trace02.py')==trace['scriptSha256']
assert sha(Path(read(BASE/'trace02/started.json')['tracer']))==trace['tracerSha256']
assert read(BASE/'trace02/metadata-before.json')==read(BASE/'trace02/metadata-after.json')
for row in trace['scopes']:
    assert row==read(BASE/'trace02'/(row['name']+'.json'))
    assert sha(BASE/'trace02'/(row['name']+'.trace'))==row['traceSha256']
    assert row['nativePhaseReadCalls']==0 and row['directoryDescriptorsClosed'] and not row['originalCaseTreeTouched']
    assert row['result']['reason']==row['expectedReason'] and row['result']['errno']==row['expectedErrno']
assert [row['injection'] for row in trace['scopes'][:4]]==[None,None,'getuid:retval=0:when=1','getdents64:error=EIO:when=1']
assert trace['scopes'][4]['injection'].startswith('openat:error=EACCES:when=')
failed=read(BASE/'trace01/failure.json')
assert failed['status']=='failed-trace-parser' and failed['nativeExitCode']==0
assert sha(BASE/'trace.py')==failed['scriptSha256'] and sha(BASE/'trace01/ordinary.trace')==failed['traceSha256']
assert not (BASE/'trace01/result.json').exists()
summary=dict(status='verified-isolated-native-prototype',controlsPassed=20,tracedScopesPassed=5,
    originalTraceParserFailureRetained=True,unchangedNativeBinaryAcrossScopes=True,
    binarySha256=build['binarySha256'],sourceSha256=build['sourceSha256'],inputsSha256=sha(BASE/'inputs.json'),
    resultSha256=sha(BASE/'attempt01/result.json'),traceResultSha256=sha(BASE/'trace02/result.json'),
    medianCpuMicrosecondsPerScan=medians,nativeToPythonMedianCpuRatio=ratio,pairedCpuRatios=ratios,
    originalOwnerWriterLocks=49,originalMetadataUnchanged=True,originalEntries=3227,originalLogicalBytes=11889866,
    nativeFileContentReadsObservedInTracedScannerPhase=0,foreignUidRefusalInjected=True,readdirErrorInjected=True,childOpenErrorInjected=True,
    caseDatabaseReads=0,qualificationWorkersLaunched=0,productionIntegrated=False,publicRuntimeChanged=False,
    concurrentMutationTested=False,allCleanupFailuresTested=False,signalBindingQualified=False,
    fullToolchainClosureAttested=False,wholeWorkerTimingQualified=False,timeoutCauseEstablished=False,
    independentReview=False,goalStatus='active')
with (BASE/'RESULTS.json').open('x') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
print(json.dumps({key:summary[key] for key in ('status','controlsPassed','tracedScopesPassed','nativeToPythonMedianCpuRatio','productionIntegrated','goalStatus')}))

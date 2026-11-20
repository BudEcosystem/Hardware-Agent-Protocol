"""Check source fidelity and retained metadata/timing arithmetic; no database opens."""
import ast
import hashlib
import json
from pathlib import Path
import stat
import statistics

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
inputs=read(BASE/'inputs.json');receipt=read(BASE/'attempt01/result.json');prepared=read(BASE/'preparation.json')
assert sha(BASE/'inputs.json')=='60991fe51d22140c0cb3b9c3811f6471e512108a0c77b764c5e6351b766ce707'
for row in inputs['files']:
    path=BASE/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
for row in prepared['borrowed']:
    assert sha(ROOT/row['source'])==sha(BASE/row['copy'])==row['sha256']
for row in prepared['extracted']:
    tree=ast.parse((BASE/'references'/row['source']).read_bytes())
    node=next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==row['name'])
    assert hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()==row['astSha256']
assert receipt['status']=='passed' and receipt['error'] is None and receipt['metadataUnchanged']
assert receipt['deniedEvents']==receipt['originalAuditProhibitedEvents']==[]
assert receipt['sqliteConnections']==receipt['caseDatabaseReads']==receipt['workerProcessesLaunched']==0
assert receipt['sourceInputsUnchanged'] and receipt['sourceInputsSha256']==sha(BASE/'inputs.json')
assert 0<receipt['elapsedNanoseconds']<60000000000
before=read(BASE/'attempt01/metadata-before.json');assert before==read(BASE/'attempt01/metadata-after.json')
assert len(before)==3227 and sum(row['size'] for row in before if stat.S_ISREG(row['mode']))==11889866
directories=1+sum(stat.S_ISDIR(row['mode']) for row in before)
assert len(receipt['ownerWriterLocks'])==49
samples=receipt['samples'];warm=receipt['warmScans'];assert len(samples)==14 and len(warm)==2
expected_usage=dict(files=3227,logicalBytes=11889866,totalDiskQuotaEnforced=False)
for row in samples+warm:
    assert row['usage']==expected_usage and row['events']=={'open':directories*row['scans'],'os.scandir':directories*row['scans']}
    assert row['cpuNanoseconds']>0 and row['wallNanoseconds']>0
assert [row['mode'] for row in warm]==['without-original-audit','original-audit']
assert all(row['scans']==1 and row['round']==-1 for row in warm)
ratios=[]
for number in range(7):
    pair=samples[2*number:2*number+2]
    assert [row['mode'] for row in pair]==(['without-original-audit','original-audit'] if number%2==0 else ['original-audit','without-original-audit'])
    assert all(row['round']==number and row['scans']==5 for row in pair)
    values={row['mode']:row['cpuNanoseconds'] for row in pair}
    ratios.append(values['original-audit']/values['without-original-audit'])
medians={mode:statistics.median(row['cpuNanoseconds']/5 for row in samples if row['mode']==mode)
    for mode in ('without-original-audit','original-audit')}
assert medians==receipt['medianCpuNanosecondsPerScan'] and ratios==receipt['pairedCpuRatios']
ratio=medians['original-audit']/medians['without-original-audit']
assert ratio==receipt['originalAuditToWithoutMedianCpuRatio']
summary=dict(status='verified-readonly-scan-evaluation',sourceInputsSha256=sha(BASE/'inputs.json'),
    resultSha256=sha(BASE/'attempt01/result.json'),scans=72,entriesPerScan=3227,directoriesPerScan=directories,
    logicalBytesPerScan=11889866,ownerWriterLocks=49,metadataUnchanged=True,
    medianCpuNanosecondsPerScan=medians,originalAuditToWithoutMedianCpuRatio=ratio,pairedCpuRatios=ratios,
    originalRawTreeMeasured=True,liveGrowingTreeMeasured=False,commonGuardInBothModes=True,
    caseDatabaseReads=0,workerProcessesLaunched=0,productionChanged=False,timeoutCauseEstablished=False,
    sourceFidelityAndArithmeticVerified=True,independentReview=False,goalStatus='active')
with (BASE/'RESULTS.json').open('x') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
print(json.dumps(summary))

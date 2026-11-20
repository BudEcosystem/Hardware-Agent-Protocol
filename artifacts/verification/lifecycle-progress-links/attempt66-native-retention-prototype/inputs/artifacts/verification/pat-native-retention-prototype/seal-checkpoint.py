"""Seal read-only scan evidence, native prototype evidence and research coverage."""
import hashlib
import json
import os
from pathlib import Path
import stat

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SCAN=ROOT/'artifacts/verification/pat-retention-scan-cost'
RESEARCH=ROOT/'research/host-contract/native-retention'
PRIOR=ROOT/'artifacts/verification/lifecycle-progress-links/attempt65-worker-accounting/index.json'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt66-native-retention-prototype'
def read(path):return json.loads(path.read_bytes())
def sha(path):
    info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(path,row):assert path.lstat().st_size==row['bytes'] and sha(path)==row['sha256'],str(path)
def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
assert not (BASE/'index.json').exists() and not (SCAN/'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR)=='7af31ebabdff4753f6eaef554903d9be12b1d1a4b52b4d1bdc0bf1b874daad32'
assert sha(RESEARCH/'index.json')=='b6ba9eaf836ad45f89cd97c8fd20650d9c6dcad0268a1eb563d7982e50d5d61a'
for row in read(RESEARCH/'index.json')['files']:verify(RESEARCH/row['path'],row)
assert read(RESEARCH/'reading.json')['totalLfLines']==2311
for folder,pin in ((SCAN,'60991fe51d22140c0cb3b9c3811f6471e512108a0c77b764c5e6351b766ce707'),
        (BASE,'7a7319c430af6302a2617c190a5eebe6ce5dd2eebab029540c2b12dd36276023')):
    assert sha(folder/'inputs.json')==pin
    for row in read(folder/'inputs.json')['files']:verify(folder/row['path'],row)
scan=read(SCAN/'RESULTS.json');native=read(BASE/'RESULTS.json')
assert scan['status']=='verified-readonly-scan-evaluation' and scan['scans']==72 and scan['metadataUnchanged']
assert scan['caseDatabaseReads']==scan['workerProcessesLaunched']==0
assert native['status']=='verified-isolated-native-prototype' and native['controlsPassed']==20 and native['tracedScopesPassed']==5
assert native['originalTraceParserFailureRetained'] and native['unchangedNativeBinaryAcrossScopes']
assert native['originalMetadataUnchanged'] and native['originalOwnerWriterLocks']==49
assert native['caseDatabaseReads']==native['qualificationWorkersLaunched']==0
assert not native['productionIntegrated'] and not native['wholeWorkerTimingQualified']
assert sha(BASE/'attempt01/result.json')==native['resultSha256']
assert sha(BASE/'trace02/result.json')==native['traceResultSha256']
assert sha(BASE/'build01/scan')==native['binarySha256']
assert read(BASE/'attempt01/original-metadata-before.json')==read(BASE/'attempt01/original-metadata-after.json')==read(SCAN/'attempt01/metadata-after.json')
links=read(ROOT/'artifacts/verification/project-links.json')
assert links['missing']==[] and sha(ROOT/'scripts/check_project_links.py')==links['checker_sha256']
for row in links['files']:assert sha(ROOT/row['path'])==row['sha256']

def inventory(folder,fixture_root=None):
    files=[];states=[]
    for parent,directories,names in os.walk(folder,followlinks=False):
        for name in sorted(directories+names):
            path=Path(parent)/name;info=path.lstat();relative=path.relative_to(folder).as_posix()
            if stat.S_ISREG(info.st_mode):files.append(dict(path=relative,bytes=info.st_size,sha256=sha(path)))
            elif not stat.S_ISDIR(info.st_mode):
                assert fixture_root is not None and path.is_relative_to(fixture_root)
                assert stat.S_ISLNK(info.st_mode) or stat.S_ISFIFO(info.st_mode)
            if fixture_root is not None and path.is_relative_to(fixture_root):
                row=dict(path=relative,mode=info.st_mode,uid=info.st_uid,gid=info.st_gid,nlink=info.st_nlink,
                    device=info.st_dev,inode=info.st_ino,size=info.st_size,mtimeNs=info.st_mtime_ns,ctimeNs=info.st_ctime_ns)
                if stat.S_ISLNK(info.st_mode):
                    row['symlinkTarget']=os.readlink(path)
                    assert Path(row['symlinkTarget']).is_relative_to(fixture_root)
                states.append(row)
    return sorted(files,key=lambda row:row['path']),sorted(states,key=lambda row:row['path'])
scan_files,scan_states=inventory(SCAN);assert scan_states==[]
write(SCAN/'index.json',dict(scope='72 exact read-only scans; source fidelity and original metadata verified; production unchanged',files=scan_files))
native_files,native_states=inventory(BASE,BASE/'attempt01/fixtures')
assert sum(stat.S_ISLNK(row['mode']) for row in native_states)==3
assert sum(stat.S_ISFIFO(row['mode']) for row in native_states)==1
assert sum(stat.S_ISREG(row['mode']) and row['nlink']==2 for row in native_states)==2
write(BASE/'index.json',dict(scope='Isolated native prototype: 20 differential controls and five traced scopes pass; earlier parser failure preserved; no runtime integration',
    files=native_files,fixtureStateNodes=native_states,nonregularFixtureNodesFollowed=False))
selected={ROOT/'README.md',ROOT/'PROGRESS.md',ROOT/'docs/control-storage.md',ROOT/'docs/prompt-to-pat.md',
    ROOT/'docs/io-driver-hub-control.md',ROOT/'scripts/check_project_links.py',ROOT/'artifacts/verification/project-links.json',PRIOR}
for folder in (SCAN,BASE):selected.update(path for path in folder.iterdir() if path.is_file())
selected.update(path for path in RESEARCH.rglob('*') if path.is_file())
selected.update((BASE/'build01/build.json',BASE/'trace01/failure.json',BASE/'trace02/result.json',BASE/'attempt01/result.json',SCAN/'attempt01/result.json'))
copies=[]
for path in sorted(selected):
    relative=path.relative_to(ROOT);body=path.read_bytes();target=CHECKPOINT/'inputs'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(body)
    assert target.read_bytes()==path.read_bytes()==body
    copies.append(dict(source=relative.as_posix(),copy=target.relative_to(ROOT).as_posix(),bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT/'index.json',dict(scanIndexSha256=sha(SCAN/'index.json'),scanFiles=len(scan_files),
    nativeIndexSha256=sha(BASE/'index.json'),nativeFiles=len(native_files),nativeFixtureNodes=len(native_states),
    researchIndexSha256=sha(RESEARCH/'index.json'),fullyReadLfLines=2311,
    readOnlyScans=72,differentialControls=20,tracedScopes=5,nativeToPythonMedianCpuRatio=native['nativeToPythonMedianCpuRatio'],
    originalMetadataUnchanged=True,productionIntegrated=False,wholeWorkerTimingQualified=False,goalStatus='active',
    markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],files=copies))
print(json.dumps(dict(scanFiles=len(scan_files),scanIndexSha256=sha(SCAN/'index.json'),nativeFiles=len(native_files),
    nativeIndexSha256=sha(BASE/'index.json'),fixtureStateNodes=len(native_states),checkpointFiles=len(copies),
    checkpointIndexSha256=sha(CHECKPOINT/'index.json'),goalStatus='active')))

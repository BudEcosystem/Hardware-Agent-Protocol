"""Preserve a terminal timeout without inventing absent child receipts."""
import hashlib, json, re, shutil, stat, sys
from pathlib import Path
ROOT=Path.cwd().resolve(); B=ROOT/'artifacts/implementation/pat-io-execution-handoff'
harness,name,destination=sys.argv[1:]; H=B/harness; A=H/'attempts'/name; O=B/'results'/destination
def read(p): return json.loads(p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,row):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
def inventory(folder):
    rows=[]
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_file(): rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return rows
def identity(p):
    s=p.lstat(); assert stat.S_ISDIR(s.st_mode)
    return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
r=read(A/'result.json'); review=read(H/'review.json')
assert r['status']=='timed_out' and r['currentPass'] is False and r['childState']=='exited' and r['counts'] is None
assert r['exitCode']==-15 and not Path('/proc',str(r['pid'])).exists() and r['timeoutSeconds']==180
assert {e['phase'] for e in r['errors']}=={'execution','child-receipts'}
assert r['signalsAttempted']==['terminate'] and r['rawScratchInventoryTerminal'] and r['rawScratchCopyVerified']
assert not (A/'test-return.json').exists()
for row in read(H/'index.json')['files']: verify(H/row['path'],row)
for label,folder,count in [('inputs',A/'project',review.get('projectInputCount',252)),('frozen',ROOT,review.get('frozenPreparationInputCount',255)),('harness',A/'harness',6)]:
    rows=read(A/(label+'-before.json')); assert rows==read(A/(label+'-after.json')) and len(rows)==count
    for row in rows: verify(folder/row['path'],row)
external=read(A/'external-before.json'); assert external==read(A/'external-after.json') and len(external['files'])==159
for row in external['files']: verify(Path(row['resolvedPath']),row)
raw=Path(r['scratchPath']); before=read(A/'raw-scratch-before.json')
assert identity(raw)==before['identity'] and identity(raw.parent)==before['parent']
rawrows=inventory(raw); assert rawrows==inventory(A/'scratch')==read(A/'scratch-index.json')
assert sum(v['bytes'] for v in rawrows)<=review['scratchBytesCeiling']
targets=read(H/'targets.json')['targets']; assert len(targets)==r['expectedTests']==review['tests']
assert sha(H/'targets.json')==review['targetSha256']
log=(A/'output.log').read_text(); completed=re.findall(r'^test_\S+ \(([^\n]+)\) \.\.\. ok$',log,re.M)
assert len(completed)==len(set(completed)) and completed==targets[:len(completed)]
assert '\nOK\n' not in log and 'FAILED (' not in log
rows=inventory(A); assert not O.exists(); O.mkdir(parents=True); shutil.copytree(A,O/'attempt')
assert inventory(O/'attempt')==rows==inventory(A)
proof=dict(scope='Terminal original-deadline failure. Partial log observations are not a passing scope or complete child-origin attestation.',
    harness=harness,harnessIndexSha256=sha(H/'index.json'),sourceIndexSha256=review['sourceIndexSha256'],targetsSha256=sha(H/'targets.json'),
    attempt=name,status=r['status'],counts=None,expectedTests=len(targets),completedOkLines=len(completed),completedLogTargets=completed,
    elapsedSeconds=r['elapsedSeconds'],childExited=True,exitCode=r['exitCode'],timeoutSeconds=180,errors=r['errors'],
    sourceInputsStable=True,externalPinsVerified=159,fullChildReceiptAvailable=False,completeActualOriginEvidence=False,
    attemptFilesAcquired=len(rows),rawScratch=before['identity'],rawScratchFiles=len(rawrows),rawScratchBytes=sum(v['bytes'] for v in rawrows),
    qualificationPassed=False,originalsAndCompleteCopiesRetained=True)
with (O/'proof.json').open('x') as f: f.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps({k:v for k,v in proof.items() if k!='completedLogTargets'}))

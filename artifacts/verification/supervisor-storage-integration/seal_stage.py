"""Seal the completed integration, preserved failures and current status links."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def row(p,root):return dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
def write(p,v):
    with p.open('x') as stream:json.dump(v,stream,indent=2);stream.write('\n')
assert not (BASE/'index.json').exists()
result=read(BASE/'RESULTS.json');audit=read(BASE/'AUDIT.json')
assert result['auditSha256']==sha(BASE/'AUDIT.json') and result['controlAuditSha256']==sha(BASE/'CONTROL_AUDIT.json')
assert result['actualAuditSha256']==sha(BASE/'ACTUAL_RESULTS.json') and not result['goalComplete']
assert audit['distinctPassingControls']==71 and audit['actualCases']==30 and not audit['publicRuntimeChanged']
source=ROOT/'artifacts/implementation/supervisor-storage-bindings/implementation01'
for r in read(source/'index.json')['files']:assert row(ROOT/r['path'],ROOT)==r
for index,root in ((BASE/'control-harness-index.json',BASE),(BASE/'harness02/index.json',BASE/'harness02'),(BASE/'harness01/index.json',BASE/'harness01')):
    for r in read(index)['files']:assert row(root/r['path'],root)==r
runtime=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
for r in read(runtime)['files']:assert sha(ROOT/r['path'])==r['sha256']
docs=['README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md']
for name in docs:assert 'supervisor-storage-integration' in (ROOT/name).read_text()
write(BASE/'documentation-update.json',dict(files=[row(ROOT/name,ROOT) for name in docs],runtimeInputsUnchanged=244,
    candidateInstalledPublicly=False,goalActive=True))
files=[]
for p in sorted(BASE.rglob('*')):
    assert not p.is_symlink()
    if p.is_file():
        assert p.stat().st_size<=16777216;files.append(row(p,BASE))
total=sum(r['bytes'] for r in files)
assert total+audit['additionalOriginalRawScratchBytes']<1024**3
write(BASE/'index.json',dict(files=files))
assert (BASE/'index.json').stat().st_size<=16777216
for r in read(BASE/'index.json')['files']:assert row(BASE/r['path'],BASE)==r
print(json.dumps(dict(indexSha256=sha(BASE/'index.json'),indexedFiles=len(files),indexedBytes=total,
    additionalOriginalRawScratchBytes=audit['additionalOriginalRawScratchBytes'],distinctControls=71,completeCases=30,
    actualApplicationInvocations=1,failedDiagnosticBatchPreserved=True,publicRuntimeUnchanged=True,goalComplete=False)))

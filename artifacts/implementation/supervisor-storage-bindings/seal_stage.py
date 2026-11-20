"""Seal exact source and retained failure; no further experiment."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('x') as stream:json.dump(v,stream,indent=2);stream.write('\n')
def row(p,prefix):return dict(path=p.relative_to(prefix).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
assert not (BASE/'index.json').exists()
audit=read(BASE/'AUDIT.json');result=read(BASE/'RESULTS.json')
assert audit['status']=='verified-retained-failure' and not result['candidateTestsPassed'] and not result['goalComplete']
assert result['auditSha256']==sha(BASE/'AUDIT.json')
assert sha(BASE/'implementation01/index.json')==result['sourceIndexSha256']
for item in read(BASE/'implementation01/index.json')['files']:
    p=ROOT/item['path'];assert row(p,ROOT)==item
runtime=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
for item in read(runtime)['files']:assert sha(ROOT/item['path'])==item['sha256']
documents=['README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md']
for name in documents:assert 'supervisor-storage-bindings' in (ROOT/name).read_text()
write(BASE/'documentation-update.json',dict(files=[row(ROOT/name,ROOT) for name in documents],
    runtimeInputsUnchanged=244,goalActive=True,candidateValidated=False))
files=[]
for p in sorted(BASE.rglob('*')):
    assert not p.is_symlink()
    if p.is_file():
        assert p.stat().st_size<=16*1024*1024
        files.append(row(p,BASE))
assert sum(r['bytes'] for r in files)<1024**3
write(BASE/'index.json',dict(files=files))
for item in read(BASE/'index.json')['files']:assert row(BASE/item['path'],BASE)==item
print(json.dumps(dict(indexSha256=sha(BASE/'index.json'),indexedFiles=len(files),indexedBytes=sum(r['bytes'] for r in files),
    retainedFailureVerified=True,candidateValidationPassed=False,publicRuntimeUnchanged=True)))

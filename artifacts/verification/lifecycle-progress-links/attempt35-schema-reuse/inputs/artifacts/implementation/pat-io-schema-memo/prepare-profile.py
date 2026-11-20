"""Retain the same bounded cProfile diagnostic against the schema-reuse source."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
R=Path.cwd();B=R/'artifacts/implementation/pat-io-schema-memo';O=B/'harness04';H=B/'harness05'
P=R/'artifacts/implementation/pat-io-group-worker/harness09'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
for folder,pin in ((O,'ba41735d1f118a110e11de127e8e84662a2d0f59893bde384941399a972d0f44'),(P,'94b480fdd5556f67d267e45f8a0b04ccb69596e94e2444a8685dce8b4ffafadc')):
 assert sha(folder/'index.json')==pin
 for row in read(folder/'index.json')['files']:assert sha(folder/row['path'])==row['sha256']
H.mkdir();(H/'references').mkdir();borrowed=[]
for name in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
 src=O/name;dst=H/'references'/src.name;shutil.copyfile(src,dst)
 borrowed.append(dict(source=src.relative_to(R).as_posix(),copy=dst.relative_to(H).as_posix(),bytes=src.stat().st_size,sha256=sha(src)))
for name in ['run_attempt.py','attempt_child.py']:
 before=(O/name).read_text();after=(P/name).read_text()if name=='attempt_child.py'else before
 ast.parse(after);(H/name).write_text(after)
 (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/name).relative_to(R).as_posix(),tofile=(H/name).relative_to(R).as_posix())))
for name in ['SCOPE.md','targets.json']:shutil.copyfile(O/name,H/name)
write(H/'borrowed-inputs.json',borrowed)
(H/'README.md').write_text('# Bounded remaining-cost profile\n\nThe same [cutoff test](targets.json), [source](../implementation01/README.md) and\n[scope](SCOPE.md) apply. A previously reviewed standard-library cProfile wrapper\nretains the top100 cumulative/self-time rows after imports. Instrumentation\nchanges elapsed time; this is diagnosis, not another distinct passing method.\n')
write(H/'review.json',dict(scope='Primary-agent full profiling-only harness delta reviewed before execution.',tests=1,
 sourceIndexSha256=sha(B/'implementation01/index.json'),targetSha256=sha(H/'targets.json'),
 reviewed=['Unchanged current source, cutoff target, launcher and SQL scope. Child is byte-identical to previously retained profiler child; only cProfile wraps the exact test after imports.',
 'Same top100 diagnostic JSON within original4MiB bound; no binary dump. Every original group/harness limit and retention check remains.',
 'New measurement justified by full GPIO still failing at60s after25cases, near unchanged scratch ceiling. PWM remains unexecuted pending shared time/storage correction.'],
 independentReview=False,releasedBy='primary-agent'))
rows=[dict(path=p.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(H.rglob('*'))if p.is_file()]
write(H/'index.json',dict(scope='Exact bounded cutoff profiler after schema reuse; all original ceilings retained.',files=rows))
print(json.dumps(dict(harness=H.name,indexSha256=sha(H/'index.json'),files=len(rows))))

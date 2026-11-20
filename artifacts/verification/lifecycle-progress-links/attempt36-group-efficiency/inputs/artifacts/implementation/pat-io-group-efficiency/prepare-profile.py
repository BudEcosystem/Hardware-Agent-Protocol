"""Profile the known failed PWM group with the unchanged source and bounds."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
R=Path.cwd();B=R/'artifacts/implementation/pat-io-group-efficiency';O=B/'harness05';H=B/'harness06'
P=R/'artifacts/implementation/pat-io-group-worker/harness09'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
for folder,pin in [(O,'c03ba72f8f1c5eaee1c42df67a7c5663e01a62ef3655e85eb8c3759c3a95c243'),(P,'94b480fdd5556f67d267e45f8a0b04ccb69596e94e2444a8685dce8b4ffafadc')]:
 assert sha(folder/'index.json')==pin
 for row in read(folder/'index.json')['files']:assert sha(folder/row['path'])==row['sha256']
H.mkdir();(H/'references').mkdir();borrowed=[]
for name in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
 src=O/name;dst=H/'references'/src.name;shutil.copyfile(src,dst)
 borrowed.append(dict(source=src.relative_to(R).as_posix(),copy=dst.relative_to(H).as_posix(),bytes=src.stat().st_size,sha256=sha(src)))
for name in ['run_attempt.py','attempt_child.py']:
 before=(O/name).read_text();after=(P/name).read_text()if name=='attempt_child.py'else before
 if name=='attempt_child.py':after=after.replace('one exact bounded record-cutoff test','one exact bounded full-PWM test')
 ast.parse(after);(H/name).write_text(after)
 (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/name).relative_to(R).as_posix(),tofile=(H/name).relative_to(R).as_posix())))
for name in ['SCOPE.md','targets.json']:shutil.copyfile(O/name,H/name)
write(H/'borrowed-inputs.json',borrowed)
(H/'README.md').write_text('# Remaining PWM-cost profile\n\nThe same [full PWM target](targets.json), [source](../implementation01/README.md)\nand [scope](SCOPE.md) apply. The retained cProfile wrapper records top100\ncumulative/self-time rows after imports. Expected failure is not converted\nto success; the run is retained as a diagnostic, not a distinct passing method.\n')
write(H/'review.json',dict(scope='Primary-agent full profiling-only harness delta reviewed before execution.',tests=1,
 sourceIndexSha256=sha(B/'implementation01/index.json'),targetSha256=sha(H/'targets.json'),
 reviewed=['Current uninstrumented PWM is terminal and failed after28/30cases; raw state and complete acquired attempt are retained. Shared storage is within the original limit. Profiling is a separate fresh synthetic diagnostic, not recovery or replacement-key retry.',
 'Launcher, targets, source, exact SQL paths and original60s group/180s harness/all byte limits unchanged. Previously reviewed cProfile wrapper surrounds the one full PWM test after imports; diagnostic description corrected to PWM.',
 'No binary profile dump; top100 JSON remains under original4MiB bound. Instrumented timings include overhead and cannot be treated as ordinary performance.'],
 independentReview=False,releasedBy='primary-agent'))
rows=[dict(path=p.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(H.rglob('*'))if p.is_file()]
write(H/'index.json',dict(scope='Exact bounded PWM diagnostic profile; all original ceilings retained.',files=rows))
print(json.dumps(dict(harness=H.name,indexSha256=sha(H/'index.json'),files=len(rows))))

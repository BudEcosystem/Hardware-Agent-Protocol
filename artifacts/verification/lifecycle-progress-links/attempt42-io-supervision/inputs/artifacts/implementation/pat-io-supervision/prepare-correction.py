"""Normalize external validation errors; retain the original error and tests."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision';O=B/'implementation01';S=B/'implementation02'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x') as f:f.write(json.dumps(v,indent=2)+'\n')
def inventory(folder,rooted=False):
    rows=[]
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_file():
            if p.suffix=='.py':ast.parse(p.read_bytes())
            rows.append(dict(path=p.relative_to(ROOT if rooted else folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return rows
assert sha(O/'index.json')=='9a6f80b9e6eb9893b719d3e93e723f5efd7babe77a22f3e191e5e37a37ba7f3f'
proof=read(B/'results/attempt01-failed160/proof.json');assert proof['counts']==dict(testsRun=160,failures=0,errors=1,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert proof['sqliteConnections']==0
(S/'project').mkdir(parents=True);inherited=[]
for row in read(O/'index.json')['files']:
    p=ROOT/row['path'];assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
    if p.is_relative_to(O/'project'):
        q=S/'project'/p.relative_to(O/'project');q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);inherited.append(row)
assert len(inherited)==237;write(S/'baseline-inputs.json',dict(sourceIndexSha256=sha(O/'index.json'),inheritedProjectInputs=inherited))
p=S/'project/supervisor/supervisor_contracts.py';before=p.read_text()
anchor='        except (ContractError, KeyError, TypeError, ValueError, IndexError, RecursionError) as error:'
assert before.count(anchor)==1;after=before.replace(anchor,'        except (JournalError, ContractError, KeyError, TypeError, ValueError, IndexError, RecursionError) as error:')
ast.parse(after);p.write_text(after)
(B/'error-correction.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str((O/'project/supervisor/supervisor_contracts.py').relative_to(ROOT)),tofile=str(p.relative_to(ROOT)))))
changed=[]
for row in inherited:
    p=ROOT/row['path'];rel=p.relative_to(O/'project')
    if sha(S/'project'/rel)!=row['sha256']:changed.append(rel.as_posix())
assert changed==['supervisor/supervisor_contracts.py']
reviewed=['One-line exception-boundary correction; own SupervisorError remains the first pass-through branch. Borrowed JournalError validation refusals normalize to QUALIFICATION_INVALID.',
    'All tests and236of237project files unchanged. Exact original160pure selection and process1, original limits and immutable failure retained. Primary-agent review; no independent helper review.']
write(S/'source-review.json',dict(scope='One-line supervisor validation exception normalization reviewed before execution.',changedFiles=changed,unchangedInheritedFiles=236,
    reviewed=reviewed,independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Closed supervisor validation errors\n\n[Correction](../CORRECTION.md), [review](source-review.json).\nOne production line changed; all tests remain.\n')
rows=inventory(S,True);assert len(rows)==240
write(S/'index.json',dict(scope='Supervisor exception normalization; original tests and all limits retained.',files=rows));pin=sha(S/'index.json')
for i,origin in [(3,1),(4,2)]:
    old=B/('harness%02d'%origin);H=B/('harness%02d'%i)
    for row in read(old/'index.json')['files']:assert sha(old/row['path'])==row['sha256']
    H.mkdir();(H/'references').mkdir();borrowed=[]
    for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
        p=old/name;q=H/'references'/p.name;shutil.copyfile(p,q)
        borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    write(H/'borrowed-inputs.json',borrowed)
    for name in ('attempt_child.py','targets.json','SCOPE.md'):shutil.copyfile(old/name,H/name)
    before=(old/'run_attempt.py').read_text();after=before.replace(sha(O/'index.json'),pin).replace('implementation01','implementation02')
    ast.parse(after);(H/'run_attempt.py').write_text(after)
    (H/'run_attempt.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str((old/'run_attempt.py').relative_to(ROOT)),tofile=str((H/'run_attempt.py').relative_to(ROOT)))))
    (H/'README.md').write_text((old/'README.md').read_text().replace('implementation01','implementation02'))
    review=read(old/'review.json');review['sourceIndexSha256']=pin;review['reviewed']+=reviewed;write(H/'review.json',review)
    write(H/'index.json',dict(scope='Original exact scope on source02 exception correction.',files=inventory(H)))
    print(json.dumps(dict(harness=H.name,tests=review['tests'],indexSha256=sha(H/'index.json'))))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=237,frozenFiles=240)))

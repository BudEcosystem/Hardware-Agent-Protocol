"""Finish the original preparation after retaining its syntax-only failure."""
import ast
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
assert not (BASE/'inputs.json').exists() and not (BASE/'attempt01').exists()
old=(BASE/'failed-preparation01/child.py.txt').read_text()
new=(BASE/'child.py').read_text()
assert old.replace("{'a':b'a,'b':", "{'a':b'a','b':")==new
for row in read(BASE/'borrowed-inputs.json'):
    for path in (ROOT/row['source'],BASE/row['copy']):
        assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
original=ast.parse((BASE/'references/contracts.py').read_bytes())
reference=next(node for node in original.body if isinstance(node,ast.FunctionDef) and node.name=='check_tree')
assert ast.dump(reference)==ast.dump(ast.parse((BASE/'reference_check_tree.py').read_bytes()).body[0])
candidate=(BASE/'reference_check_tree.py').read_text()
candidate=candidate.replace('        if type(item) is dict:', '        kind = type(item)\n        if kind is dict:').replace('type(item) is ','kind is ')
candidate=candidate.replace('            for key, child in item.items():','            child_depth = depth + 1\n            for key, child in item.items():')
candidate=candidate.replace('stack.append((key, depth + 1))','stack.append((key, child_depth))').replace('stack.append((child, depth + 1))','stack.append((child, child_depth))')
candidate=candidate.replace('            stack.extend((child, depth + 1) for child in item)','            child_depth = depth + 1\n            stack.extend((child, child_depth) for child in item)')
assert candidate==(BASE/'candidate_check_tree.py').read_text()
files=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        if path.suffix=='.py':ast.parse(path.read_bytes())
        files.append(dict(path=path.relative_to(BASE).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
with (BASE/'inputs.json').open('x') as stream:
    json.dump(dict(scope='Pure validator evaluation only; failed preparation retained; no production adoption',files=files),stream,indent=2);stream.write('\n')
print(json.dumps(dict(inputs=len(files),indexSha256=sha(BASE/'inputs.json'),projectExecution=False)))

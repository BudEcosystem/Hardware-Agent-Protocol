"""Verify exact extracted ASTs and freeze the bounded pure comparison."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import _json

BASE = Path(__file__).resolve().parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, value):
    with p.open('x') as out: json.dump(value, out, indent=2); out.write('\n')
assert not (BASE / 'inputs.json').exists() and not (BASE / 'attempt01').exists()
for row in json.loads((BASE / 'borrowed-inputs.json').read_bytes()):
    for p in (Path(row['source']), BASE / row['copy']):
        assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
body = (BASE / 'references/contracts.py').read_text()
nodes = {n.name: n for n in ast.parse(body).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
reference = ast.parse((BASE / 'reference_functions.py').read_bytes())
assert len(reference.body) == 7 and all(ast.dump(n) == ast.dump(nodes[n.name]) for n in reference.body)
assert (BASE / 'reference_functions.py').read_bytes() == (BASE / 'candidate_functions.py').read_bytes()
helpers = body[body.index('from types import FunctionType as _FunctionType'):body.index('_SCHEMA =')].rstrip() + '\n'
assert (BASE / 'reference_helpers.py').read_text() == helpers
old_nodes = {n.name: n for n in ast.parse(helpers).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
new_nodes = {n.name: n for n in ast.parse((BASE / 'candidate_helpers.py').read_bytes()).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
assert set(new_nodes) == set(old_nodes) | {'_UseUtf16Order', '_ascii_integer_tree'}
assert all(ast.dump(n) == ast.dump(new_nodes[k]) for k, n in old_nodes.items() if k != '_canonical_bytes')
candidate = (BASE / 'candidate-contracts.py').read_text()
assert candidate == body.replace(helpers.rstrip(), (BASE / 'candidate_helpers.py').read_text().rstrip())
paths = [Path(sys.executable).resolve(), Path(json.__file__), Path(json.encoder.__file__), Path(_json.__file__)]
write(BASE / 'runtime-inputs.json', dict(jsonEncoderOrigin=json.encoder.__file__, jsonNativeOrigin=_json.__file__,
    files=[dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p)) for p in paths], systemLibraryClosureAttested=False))
rows = []
for p in sorted(BASE.rglob('*')):
    assert not p.is_symlink()
    if p.is_file():
        if p.suffix == '.py': ast.parse(p.read_bytes())
        rows.append(dict(path=p.relative_to(BASE).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
write(BASE / 'inputs.json', dict(scope='Current guarded encoder versus detached ASCII-field candidate',
    files=rows, projectChanged=False, sourceReview='primary-agent', independentReview=False,
    expectedCases=1875, unchangedPublicDefinitions=7, referenceIsCurrentGuardedEncoder=True))
print(json.dumps(dict(inputs=len(rows), inputIndexSha256=sha(BASE / 'inputs.json'))))

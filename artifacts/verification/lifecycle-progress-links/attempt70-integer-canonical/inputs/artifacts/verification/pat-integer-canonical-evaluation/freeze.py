"""Freeze the reviewed pure scope; execute no project or candidate function."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import _json

BASE = Path(__file__).resolve().parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2);stream.write('\n')
assert not (BASE / 'inputs.json').exists() and not (BASE / 'attempt01').exists()
for row in json.loads((BASE / 'borrowed-inputs.json').read_bytes()):
    for path in (Path(row['source']), BASE / row['copy']):
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
original=ast.parse((BASE/'references/contracts.py').read_bytes())
reference=ast.parse((BASE/'reference_functions.py').read_bytes())
candidate=ast.parse((BASE/'candidate_functions.py').read_bytes())
original_nodes={node.name:node for node in original.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
assert len(reference.body)==7 and all(ast.dump(node)==ast.dump(original_nodes[node.name]) for node in reference.body)
reference_text=(BASE/'reference_functions.py').read_text()
assert reference_text.replace('result = rfc8785.dumps(value)','result = _canonical_bytes(value)')==(BASE/'candidate_functions.py').read_text()
assert all(ast.dump(a)==ast.dump(b) for a,b in zip(reference.body,candidate.body) if a.name!='canonical')
runtime_paths=[Path(sys.executable).resolve(),Path(json.__file__),Path(json.encoder.__file__),Path(_json.__file__)]
put(BASE/'runtime-inputs.json',dict(jsonEncoderOrigin=json.encoder.__file__,jsonNativeOrigin=_json.__file__,
    files=[dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path)) for path in runtime_paths],
    systemLibraryClosureAttested=False))
files=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        if path.suffix=='.py':ast.parse(path.read_bytes())
        files.append(dict(path=str(path.relative_to(BASE)),bytes=path.stat().st_size,sha256=sha(path)))
put(BASE/'inputs.json',dict(scope='Exact extracted parser/validator/canonicalizer and guarded integer-only bytes candidate',
    files=files,projectChanged=False,sourceReview='primary-agent',independentReview=False))
print(json.dumps(dict(inputs=len(files),indexSha256=sha(BASE/'inputs.json'))))

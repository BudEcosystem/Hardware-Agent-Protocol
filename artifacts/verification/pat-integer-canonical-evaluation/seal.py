"""Seal one audited pure evaluation without changing its original inputs."""
import hashlib
import json
from pathlib import Path
BASE=Path(__file__).resolve().parent
assert not (BASE/'index.json').exists()
result=json.loads((BASE/'RESULTS.json').read_bytes())
assert result['status']=='verified-pure-candidate' and result['differentialCases']==1668
rows=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        assert path.stat().st_size<=16777216
        rows.append(dict(path=str(path.relative_to(BASE)),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
with (BASE/'index.json').open('x') as stream:
    json.dump(dict(scope='One audited pure serialization evaluation; no production adoption',files=rows),stream,indent=2);stream.write('\n')
print(json.dumps(dict(files=len(rows),indexSha256=hashlib.sha256((BASE/'index.json').read_bytes()).hexdigest())))

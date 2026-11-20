"""Copy the sealed vault candidate into one new, exclusive integration stage."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = ROOT / 'artifacts/implementation/pat-evidence-vault/implementation02'
PIN = 'aaec11af3df57d6ed02d8390efae851e9f74261ce573089841feebe0f7cfef37'
assert hashlib.sha256((OLD / 'index.json').read_bytes()).hexdigest() == PIN
NEW = BASE / 'implementation01'
NEW.mkdir()
rows = []
for item in json.loads((OLD / 'index.json').read_bytes())['files']:
    path = ROOT / item['path']
    raw = path.read_bytes()
    assert len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256']
    if path.is_relative_to(OLD / 'project'):
        relative = path.relative_to(OLD / 'project')
        target = NEW / 'project' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
        rows.append(dict(path=relative.as_posix(), bytes=len(raw), sha256=item['sha256']))
assert len(rows) == 280
with (NEW / 'baseline-inputs.json').open('x') as stream:
    json.dump(dict(source=OLD.relative_to(ROOT).as_posix(), indexSha256=PIN, files=rows), stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(inheritedFiles=len(rows), output=str(NEW))))

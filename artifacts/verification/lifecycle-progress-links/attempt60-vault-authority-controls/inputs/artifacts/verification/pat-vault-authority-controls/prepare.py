"""Fresh verification copy; preserve all corrected production and prior failures."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = ROOT / 'artifacts/implementation/pat-vault-authority/implementation02'
NEW = BASE / 'implementation01'
PIN = '5d605fa018c9b7673260707cb5cffe630b99a70072e29c16879dd64de4bb975e'
assert hashlib.sha256((OLD / 'index.json').read_bytes()).hexdigest() == PIN
NEW.mkdir()
rows = []
for item in json.loads((OLD / 'index.json').read_bytes())['files']:
    source = ROOT / item['path']; raw = source.read_bytes()
    assert len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256']
    if source.is_relative_to(OLD / 'project'):
        relative = source.relative_to(OLD / 'project'); target = NEW / 'project' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream: stream.write(raw)
        rows.append(dict(path=relative.as_posix(), bytes=len(raw), sha256=item['sha256']))
assert len(rows) == 284
with (NEW / 'baseline-inputs.json').open('x') as stream:
    json.dump(dict(source=OLD.relative_to(ROOT).as_posix(), indexSha256=PIN, files=rows), stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(copiedFiles=284, productionUnchanged=True)))

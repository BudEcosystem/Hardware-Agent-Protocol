"""Copy the sealed current production for a fresh actual original-run scope."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
OLD=ROOT/'artifacts/verification/pat-vault-authority-controls/implementation01'
NEW=BASE/'implementation01'
PIN='38925326d56fca55353eb5e505e2c740426d2d508257fce81984aa085db54eca'
assert hashlib.sha256((OLD/'index.json').read_bytes()).hexdigest()==PIN
NEW.mkdir(); rows=[]
for row in json.loads((OLD/'index.json').read_bytes())['files']:
    source=ROOT/row['path']; body=source.read_bytes()
    assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256']
    if not source.is_relative_to(OLD/'project'): continue
    relative=source.relative_to(OLD/'project'); target=NEW/'project'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream: stream.write(body)
    rows.append(dict(path=relative.as_posix(),bytes=len(body),sha256=row['sha256']))
assert len(rows)==285
with (NEW/'baseline-inputs.json').open('x') as stream:
    json.dump(dict(source=OLD.relative_to(ROOT).as_posix(),indexSha256=PIN,files=rows),stream,indent=2); stream.write('\n')
print(json.dumps(dict(copiedProjectFiles=285,productionChanged=False)))

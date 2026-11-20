"""Copy verified sources and change one authority connection option."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = BASE.parent / 'qualification-package/implementation03'
DEST = BASE / 'implementation01'
PROJECT = DEST / 'project'
PIN = 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    body = value if type(value) is bytes else (value if type(value) is str else json.dumps(value, indent=2) + '\n').encode()
    with p.open('xb') as stream: stream.write(body)

assert not DEST.exists()
assert sha(OLD / 'index.json') == PIN
rows = read(OLD / 'index.json')['files']
assert len(rows) == 312
for row in rows:
    p = ROOT / row['path']
    assert not p.is_symlink() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
prefix = str((OLD / 'project').relative_to(ROOT)) + '/'
copies = []
before_call = 'check_same_thread=False, timeout=0.2)'
after_call = 'check_same_thread=False, timeout=0.2, cached_statements=256)'
for row in rows:
    if not row['path'].startswith(prefix): continue
    name = row['path'][len(prefix):]
    body = (ROOT / row['path']).read_bytes()
    after = body
    if name == 'hms/journal.py':
        text = body.decode()
        assert text.count(before_call) == 1
        after = text.replace(before_call, after_call).encode()
        before_ast, after_ast = ast.parse(body), ast.parse(after)
        calls = [n for n in ast.walk(after_ast) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                 and n.func.value.id == 'sqlite3' and n.func.attr == 'connect']
        assert len(calls) == 1 and calls[0].keywords[-1].arg == 'cached_statements'
        assert ast.literal_eval(calls[0].keywords.pop().value) == 256
        assert ast.dump(before_ast) == ast.dump(after_ast)
        write(DEST / 'journal.patch', ''.join(difflib.unified_diff(text.splitlines(True),
            after.decode().splitlines(True), fromfile='baseline/hms/journal.py', tofile='candidate/hms/journal.py')))
    write(PROJECT / name, after)
    copies.append(dict(path=name, originalSha256=row['sha256'], sha256=hashlib.sha256(after).hexdigest()))
assert len(copies) == 304
assert [r['path'] for r in copies if r['sha256'] != r['originalSha256']] == ['hms/journal.py']
write(DEST / 'original-index.json', (OLD / 'index.json').read_bytes())
write(DEST / 'namespace-map.json', (OLD / 'namespace-map.json').read_bytes())
write(DEST / 'copy-review.json', dict(baselineIndexSha256=PIN, projectFiles=304,
    soleProductionChange='Journal sqlite3.connect cached_statements=256',
    remainingJournalAstExact=True, files=copies, reviewer='primary-agent', independentReview=False))
inspector = (OLD.parent / 'inspect_package.py').read_text()
assert inspector.count('implementation03') == 2
write(BASE / 'inspect_package.py', inspector.replace('implementation03', 'implementation01'))
print(json.dumps(dict(projectFiles=len(copies), changedProductionFiles=['hms/journal.py'], inspectionPending=True)))

"""Seal full local text coverage; never executes acquired examples."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2);stream.write('\n')
sources = json.loads((BASE / 'acquisition.json').read_bytes())['sources']
rows = []
for source in sources:
    for path_key, hash_key in [('rawPath', 'rawSha256'), ('textPath', 'textSha256'), ('surroundingPath', 'surroundingSha256')]:
        assert sha(BASE / source[path_key]) == source[hash_key]
    rows.append(dict(path=source['textPath'], sha256=source['textSha256'], firstLfLine=1,
                     lastLfLine=source['lfLines'], complete=True, surroundingTextRead=True))
policy = json.loads((BASE / 'exec-policy-acquisition.json').read_bytes())
for name, hash_key, line_key in [('mfd_noexec.rst', 'sha256', 'lfLines'),
                                ('installed-memfd.h', 'headerSha256', 'headerLfLines')]:
    assert sha(BASE / name) == policy[hash_key]
    rows.append(dict(path=name, sha256=policy[hash_key], firstLfLine=1, lastLfLine=policy[line_key], complete=True))
assert sum(row['lastLfLine'] for row in rows) == 836
write(BASE / 'reading.json', dict(sources=rows, totalLfLines=836,
    decorativeImagesExcluded=True, technicalFigures=0, linkedImplementationsRead=False,
    acquiredCodeExecuted=False, fullLocalSelectedTextCoverage=True))
files = []
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        files.append(dict(path=str(path.relative_to(BASE)), bytes=path.stat().st_size, sha256=sha(path)))
write(BASE / 'index.json', dict(scope='Three manuals, upstream policy and installed UAPI header; full selected text reading', files=files))
print(json.dumps(dict(files=len(files), lfLines=836, indexSha256=sha(BASE / 'index.json'))))

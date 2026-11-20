"""Record additional full reading without altering the sealed partial packet."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ORIGINAL = ROOT / 'artifacts/verification/pat-native-retention-binding/research'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2);stream.write('\n')
old = json.loads((ORIGINAL / 'reading.json').read_bytes())
assert old['totalReadLfLines'] == 356 and old['totalAcquiredLfLines'] == 5360
with (BASE / 'original-reading.json').open('xb') as stream:
    stream.write((ORIGINAL / 'reading.json').read_bytes())
full = {'long.rst', 'sys.rst', 'module.rst', 'pep-0475.rst'}
sources = []
new_lines = 0
for source in old['sources']:
    source = dict(source)
    path = ORIGINAL / source['path']
    body = path.read_bytes()
    assert sha(path) == source['sha256'] and len(body) == source['bytes']
    assert body.count(b'\n') == source['lfLines']
    with (BASE / source['path']).open('xb') as stream:
        stream.write(body)
    if source['path'] in full:
        new_lines += source['unreadLfLines']
        source.update(coverage='complete', readRanges=[dict(first=1, last=source['lfLines'], sha256=source['sha256'])],
                      readLfLines=source['lfLines'], unreadLfLines=0)
    sources.append(source)
assert new_lines == 1708 and sum(row['readLfLines'] for row in sources) == 2064
put(BASE / 'reading.json', dict(totalAcquiredLfLines=5360, totalReadLfLines=2064, totalUnreadLfLines=3296,
    newlyReadLfLines=new_lines, completeSources=4, completeSourceLfLines=1947, complete=False,
    sources=sources, originalReadingSha256=sha(ORIGINAL / 'reading.json'),
    linkedReferencesFullyRead=False, acquiredCodeExecuted=False, newNetworkAcquisition=False))
files = []
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        files.append(dict(path=str(path.relative_to(BASE)), bytes=path.stat().st_size, sha256=sha(path)))
put(BASE / 'index.json', dict(scope='Four complete primary texts; original two partial API readings retained unchanged', files=files))
print(json.dumps(dict(files=len(files), indexSha256=sha(BASE / 'index.json'), newlyReadLfLines=new_lines,
                      overallReadLfLines=2064, remainingUnreadLfLines=3296)))

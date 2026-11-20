"""Seal the isolated binding, partial reading coverage and current progress links."""
import hashlib
import json
import os
from pathlib import Path
import stat

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt67-native-retention-binding'
PRIOR = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt66-native-retention-prototype/index.json'
def read(path):
    return json.loads(path.read_bytes())
def sha(path):
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_size <= 16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
assert not (BASE / 'index.json').exists() and not CHECKPOINT.exists()
assert sha(PRIOR) == '3ea777c00ea113859cc15c201d146fe2fd439205976c9930d2d0f74885c177f9'
assert sha(BASE / 'inputs.json') == '8a329a70e3f03e105ceffade69cccb81f505e9b4595bcac7cce310eec52348df'
for row in read(BASE / 'inputs.json')['files']:
    assert sha(BASE / row['path']) == row['sha256'] and (BASE / row['path']).stat().st_size == row['bytes']
result = read(BASE / 'RESULTS.json')
assert result['status'] == 'verified-isolated-native-binding'
assert result['controls'] == {'production': 43, 'instrumented': 20} and len(result['tracedScopes']) == 3
assert not result['productionIntegrated'] and not result['wholeWorkerTimingQualified']
reading = read(BASE / 'research/reading.json')
for source in reading['sources']:
    path = BASE / 'research' / source['path']
    assert sha(path) == source['sha256']
    lines = path.read_bytes().splitlines(keepends=True)
    # Exact LF ranges; source bytes contain no alternative line delimiters.
    assert len(lines) == source['lfLines']
    for segment in source['readRanges']:
        assert hashlib.sha256(b''.join(lines[segment['first']-1:segment['last']])).hexdigest() == segment['sha256']
links = read(ROOT / 'artifacts/verification/project-links.json')
assert not links['missing'] and links['checker_sha256'] == sha(ROOT / 'scripts/check_project_links.py')
for row in links['files']:
    assert sha(ROOT / row['path']) == row['sha256']
files = []
nodes = []
for parent, directories, names in os.walk(BASE, followlinks=False):
    for name in sorted(directories + names):
        path = Path(parent) / name
        info = path.lstat()
        relative = path.relative_to(BASE).as_posix()
        if stat.S_ISREG(info.st_mode):
            files.append(dict(path=relative, bytes=info.st_size, sha256=sha(path)))
        elif not stat.S_ISDIR(info.st_mode):
            assert path.is_relative_to(BASE / 'attempt01')
            assert stat.S_ISLNK(info.st_mode) or stat.S_ISFIFO(info.st_mode)
        if path.is_relative_to(BASE / 'attempt01'):
            row = dict(path=relative, mode=info.st_mode, uid=info.st_uid, gid=info.st_gid,
                nlink=info.st_nlink, device=info.st_dev, inode=info.st_ino, size=info.st_size,
                mtimeNs=info.st_mtime_ns, ctimeNs=info.st_ctime_ns)
            if stat.S_ISLNK(info.st_mode):
                row['symlinkTarget'] = os.readlink(path)
                assert Path(row['symlinkTarget']).is_relative_to(BASE / 'attempt01')
            nodes.append(row)
assert sum(stat.S_ISLNK(row['mode']) for row in nodes) == 3
assert sum(stat.S_ISFIFO(row['mode']) for row in nodes) == 1
assert sum(stat.S_ISREG(row['mode']) and row['nlink'] == 2 for row in nodes) == 2
write(BASE / 'index.json', dict(scope='Isolated native binding; 43 production and 20 instrumented controls; three production syscall scopes',
    files=sorted(files, key=lambda row: row['path']), retainedAttemptNodes=sorted(nodes, key=lambda row: row['path']),
    nonregularNodesFollowed=False, productionIntegrated=False, wholeWorkerTimingQualified=False))
selected = {ROOT / 'README.md', ROOT / 'PROGRESS.md', ROOT / 'docs/io-driver-hub-control.md',
    ROOT / 'docs/prompt-to-pat.md', ROOT / 'docs/control-storage.md', ROOT / 'scripts/check_project_links.py',
    ROOT / 'artifacts/verification/project-links.json', PRIOR}
selected.update(path for path in BASE.iterdir() if path.is_file())
selected.update(path for path in (BASE / 'research').iterdir() if path.is_file())
selected.update([BASE / 'build01/receipt.json', BASE / 'build01/installed-loader.py.txt',
    BASE / 'attempt01/result.json', BASE / 'attempt01/production/result.json',
    BASE / 'attempt01/instrumented/result.json', BASE / 'trace01/collection.json'])
copies = []
for path in sorted(selected):
    body = path.read_bytes()
    relative = path.relative_to(ROOT)
    target = CHECKPOINT / 'inputs' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(body)
    assert target.read_bytes() == path.read_bytes()
    copies.append(dict(source=str(relative), copy=str(target.relative_to(ROOT)), bytes=len(body),
                       sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT / 'index.json', dict(bindingIndexSha256=sha(BASE / 'index.json'),
    bindingFiles=len(files), retainedAttemptNodes=len(nodes), controls=result['controls'],
    productionSyscallScopes=3, acquiredLfLines=reading['totalAcquiredLfLines'],
    readLfLines=reading['totalReadLfLines'], readingComplete=False,
    productionIntegrated=False, wholeWorkerTimingQualified=False, goalStatus='active',
    markdownFiles=links['project_markdown_files'], localLinks=links['local_links_checked'], missing=[], files=copies))
print(json.dumps(dict(files=len(files), attemptNodes=len(nodes), bindingIndexSha256=sha(BASE / 'index.json'),
    checkpointFiles=len(copies), checkpointIndexSha256=sha(CHECKPOINT / 'index.json'), goalStatus='active')))

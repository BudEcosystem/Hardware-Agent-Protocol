"""Read-only verification of the completed probe, then write one final index."""
from pathlib import Path
import datetime
import hashlib
import json
import re
from urllib.parse import unquote, urlsplit

STAGE = Path(__file__).resolve().parent
ROOT = STAGE.parents[2]
RESEARCH = ROOT / 'research/host-contract/fuse-storage-boundary'
ATTEMPT = STAGE / 'attempt01'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


result = json.loads((ATTEMPT / 'RESULTS.json').read_text())
assert result['status'] == 'passed' and len(set(result['checks'])) == 14
assert not result['cleanupErrors'] and result['mountAfter'] is None
assert result['serverReturncode'] == result['clientReturncode'] == 0
assert not any(result[key] for key in ['durableStorage', 'totalDiskQuotaEnforced',
                                      'backedControlCapacity', 'productionChanged'])
assert digest(ATTEMPT / 'probe') == result['binarySha256']
before = json.loads((ATTEMPT / 'inputs-before.json').read_text())
after = json.loads((ATTEMPT / 'inputs-after.json').read_text())
assert before == after and len(before) == 14
for item in before:
    assert digest(Path(item['path'])) == item['sha256'], item['path']
for name in ['compile', 'unmount']:
    assert json.loads((ATTEMPT / (name + '.json')).read_text())['returncode'] == 0
    assert (ATTEMPT / (name + '.stderr')).stat().st_size == 0
assert (ATTEMPT / 'client.stderr').stat().st_size == 0
assert (ATTEMPT / 'server.stdout').stat().st_size == 0
assert (ATTEMPT / 'server.stderr').read_text().splitlines() == [
    f"ready pid={result['serverPid']} uid=1000 protocol=7.45",
    f"destroy pid={result['serverPid']}"]

mounted = json.loads((ATTEMPT / 'mounted.json').read_text())
assert mounted['type'] == 'fuse.hmsprobe' and mounted['source'] == 'hms-probe-81'
assert {'ro', 'nosuid', 'nodev', 'noexec'} <= set(mounted['options'])
assert 'default_permissions' in mounted['raw'] and 'allow_other' not in mounted['raw']
assert 'shared:' in mounted['raw']  # Observed limitation, not namespace isolation.
assert not any(line.split()[4] == str(ATTEMPT / 'mount')
               for line in Path('/proc/self/mountinfo').read_text().splitlines())
assert not list((ATTEMPT / 'mount').iterdir())

sources = json.loads((RESEARCH / 'sources.json').read_text())
assert len(sources['files']) == 12
lines = 0
for item in sources['files']:
    path = RESEARCH / item['path']
    assert digest(path) == item['sha256'], item['path']
    body = path.read_bytes()
    assert len(body) == item['bytes'] and body.count(b'\n') == item['lines']
    lines += item['lines']
assert lines == 4378

receipt = ROOT / 'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
assert digest(receipt) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
baseline = json.loads(receipt.read_text())
assert baseline['passed'] and baseline['tests'] == 866 and len(baseline['files_after']) == 244
for item in baseline['files_after']:
    assert digest(ROOT / item['path']) == item['sha256'], item['path']

documents = [ROOT / name for name in ['README.md', 'PROGRESS.md',
    'docs/control-storage.md', 'docs/io-driver-hub-control.md']]
documents += sorted(STAGE.glob('*.md')) + [RESEARCH / 'README.md']
links = 0
for path in documents:
    for value in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', path.read_text()):
        value = value.strip().strip('<>')
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        target = path.parent / unquote(parsed.path)
        assert target.exists(), (path, value)
        links += 1

report = {'schema': 'hms.fuse-probe-audit/1', 'status': 'passed',
          'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'checks': 14, 'frozenProbeInputs': 14, 'publicInputsUnchanged': 244,
          'publicBaselineTests': 866, 'rawSourcesVerified': 12,
          'fullyReadSourceLfLines': lines, 'documentsChecked': len(documents),
          'localLinksChecked': links, 'missingLinks': 0,
          'remainingMountAtPath': False, 'underlyingDirectoryEmpty': True,
          'sharedMountPropagationObserved': True, 'privateMountNamespace': False,
          'totalDiskQuotaEnforced': False, 'backedControlCapacity': False,
          'durableStorage': False, 'productionChanged': False,
          'review': 'primary agent only',
          'documentation': [{'path': str(p.relative_to(ROOT)), 'sha256': digest(p)}
                            for p in documents]}
write_new(STAGE / 'AUDIT.json', report)
for directory in [RESEARCH, STAGE]:
    files = [{'path': str(p.relative_to(directory)), 'bytes': p.stat().st_size,
              'sha256': digest(p)} for p in sorted(directory.rglob('*')) if p.is_file()]
    write_new(directory / 'index.json', {'schema': 'hms.file-index/1', 'files': files})
    print(json.dumps({'root': str(directory.relative_to(ROOT)), 'files': len(files),
                      'indexSha256': digest(directory / 'index.json')}))
print(json.dumps({k: v for k, v in report.items() if k != 'documentation'}, sort_keys=True))

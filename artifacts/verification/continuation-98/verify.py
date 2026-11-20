"""Read-only joins for retained evidence; no candidate imports or test reruns."""
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PUBLIC = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
PUBLIC_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
DOCS = ('README.md', 'PROGRESS.md', 'docs/control-storage.md',
        'docs/io-driver-hub-control.md', 'docs/prompt-to-pat.md', 'docs/embedded-evidence.md')
NEW = (
    ('artifacts/implementation/owned-hub-recovery', 'e97e4cf1ac3448f44b3ef2c1d3369da25f662dd72b337970c485b1dc245847fe'),
    ('artifacts/implementation/owned-hub-crash-harness', 'fa94f2dac2c9f36fbe78a56e7c3a47fbb7ae5e76729827e3ab8028c3ccb3e91e'),
    ('research/host-contract/subreaper-review', '3fa34dea3d48def5fe3182949b8575196689e74d9f05315217750ab62167c9a7'),
)


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def packet(name, expected):
    folder = ROOT/name; index = folder/'index.json'
    assert digest(index) == expected
    value = read(index); paths = set(); links = value.get('symlinks', [])
    for row in value['files']:
        path = folder/row['path']
        assert not path.is_symlink() and path.is_file()
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
        assert row['path'] not in paths; paths.add(row['path'])
    for row in links:
        path = folder/row['path']
        assert path.is_symlink() and os.readlink(path) == row['target']
        assert row['path'] not in paths; paths.add(row['path'])
    actual = {str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() or p.is_symlink()}
    assert actual == paths | {'index.json'}
    return dict(path=name, indexSha256=expected, files=len(value['files']), symlinks=len(links))


def main():
    assert digest(PUBLIC) == PUBLIC_SHA
    baseline = read(PUBLIC)
    assert baseline['passed'] is True and baseline['tests'] == 866
    assert len(baseline['files']) == 244
    assert all(digest(ROOT/r['path']) == r['sha256'] for r in baseline['files'])
    prior = read(ROOT/'artifacts/verification/continuation-97/receipt.json')
    packets = [packet(r['path'], r['indexSha256']) for r in prior['sealedPackets']]
    packets += [packet(name, pin) for name, pin in NEW]
    checks = []
    for group in ('structural', 'live', 'faults', 'recovery', 'limits'):
        value = read(ROOT/'artifacts/implementation/owned-hub-recovery'/(group+'-attempt-1')/'RESULTS.json')
        assert value['passed'] and value['returnCode'] == 0 and value['reaped']
        assert not value['remainingObservedLiveProcesses'] and not value['interruptsPendingAfterCleanup']
        checks.append(value['control']['checks'])
    assert checks == [23, 102, 92, 531, 50]
    crash = read(ROOT/'artifacts/implementation/owned-hub-crash-harness/owner-crash-attempt01/RESULTS.json')
    assert crash['passed'] and crash['actualOwnerDeaths'] == 12
    assert crash['control']['childrenReaped'] == 20
    assert crash['controlExit']['reaped'] and crash['controlExit']['exitCode'] == 0
    assert not crash['adoptedAfterControlExit'] and not crash['interruptsPendingAfterCleanup']
    cases = read(ROOT/'artifacts/implementation/owned-hub-crash-harness/owner-crash-attempt01/state/checks.json')['cases']
    counts = {name: sum(r['execution'] == name for r in cases) for name in ('not_started', 'unknown', 'completed')}
    assert counts == dict(not_started=6, unknown=3, completed=3)
    assert all(not r['leaseDeferred'] for r in cases)
    documents = {}; missing = []; links = 0
    for name in DOCS:
        path = ROOT/name; documents[name] = digest(path)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
            target = target.strip().strip('<>')
            split = urlsplit(target)
            if split.scheme or split.netloc or not split.path:
                continue
            candidate = Path(unquote(split.path))
            if not candidate.is_absolute():
                candidate = path.parent/candidate
            links += 1
            if not candidate.exists():
                missing.append(dict(document=name, target=target))
    assert not missing, missing
    result = dict(status='verified', goalStatus='active-incomplete',
        verificationSourceSha256=digest(Path(__file__)), rootDocuments=documents,
        sealedPackets=packets, publicReceiptSha256=PUBLIC_SHA, publicInputsExact=244,
        publicTestsRerun=False, recoveryObservedChecks=sum(checks), actualOwnerDeaths=12,
        ownerDeathOutcomes=counts, deliberateLiveWriterDeferralTested=False,
        standingBuildOrTestsExecuted=False, standingTargetFitEstablished=False,
        storageReplacementModelExecuted=False, storageFullWriterPassed=False,
        physicalIOExecuted=False, localLinksChecked=links, missingLocalLinks=missing)
    with (HERE/'receipt.json').open('x') as target:
        json.dump(result, target, indent=2, sort_keys=True); target.write('\n')
        target.flush(); os.fsync(target.fileno())
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()

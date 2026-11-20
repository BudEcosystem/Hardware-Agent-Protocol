"""Seal only the two completed isolated evidence packets; execute no candidate."""
import hashlib
import json
import os
from pathlib import Path
import sys

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAMES = ('standing-endpoint-shared-kernel', 'standing-host-boundaries')

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def main(name):
    assert name in NAMES
    folder = ROOT/'artifacts/implementation'/name
    assert not (folder/'index.json').exists() and not (folder/'.AUDIT.json.pending').exists()
    audit = read(folder/'AUDIT.json')
    assert audit['passed'] and audit['auditSourceSha256'] == digest(folder/'audit_retained.py')
    assert all((folder/file).is_file() for file in ('RESULTS.md', 'NEXT.md'))
    if name == NAMES[0]:
        assert audit['totalCommands'] == audit['totalReaps'] == audit['observedOwnedIdentitiesAbsent'] == 50
        assert audit['currentSourcesNativeCompleted'] and not audit['currentSourcesAvrCompleted']
        assert not audit['targetFitEstablished'] and not audit['combinedStackProof']
        generated = read(folder/'codegen-review.json')
        assert not any(generated['qualifications'].values())
        facts = dict(nativeChecksCompleted=True, avrLinkSucceeded=False, flashLoadBytes=39902,
            physicalFlashOverflowBytes=7134, applicationFlashOverflowBytes=7646,
            combinedFlashReductionFromParentBytes=1908, staticSramBytes=1503,
            commandReaps=50, fullTraceSha256='086bc3496901dc560e4aef0f51abb426e5d90698d27920ca57a27dd1a3e85541')
    else:
        assert audit['completedCases'] == 18 and audit['completedProfiles'] == 2 and audit['failedProfiles'] == 1
        assert audit['nativeChildrenReaped'] == 19 and audit['outerChildrenReaped'] == 3
        assert audit['ownedIdentitiesCurrentlyAbsent'] == 22 and audit['attemptFiles'] == 995
        assert not audit['full24CaseMatrixPassed'] and not audit['simultaneousMaximumHistoriesEstablished']
        facts = dict(completedCases=18, completedProfileControlChecks=258, failedCapacityProfiles=1,
            mutationCapacityFailure='CONTROL_WALL_LIMIT', failedMutationRecords=68,
            nativeReaps=19, outerReaps=3, full24CaseMatrixPassed=False,
            unexecutedProfiles=['episodes','activations','keys','fixed','accounting'])
    files = []
    for path in sorted(folder.rglob('*')):
        assert not path.is_symlink() and '__pycache__' not in path.parts
        if path.is_file():
            before = path.stat(); pin = digest(path); after = path.stat()
            assert (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) == (after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
            files.append(dict(path=str(path.relative_to(folder)),bytes=before.st_size,sha256=pin))
    assert len({row['path'] for row in files}) == len(files)
    index = dict(profile='hms-isolated-evidence-packet/1',status='sealed-partial-results-with-preserved-failure',
        sealSourceSha256=digest(Path(__file__)),fileCount=len(files),totalBytes=sum(row['bytes'] for row in files),
        facts=facts,targetFitEstablished=False,combinedStackProof=False,physicalIOQualified=False,
        publicStandingMountEligible=False,completeGoalClaimed=False,files=files)
    with (folder/'index.json').open('x') as stream:
        json.dump(index,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps(dict(path=str(folder.relative_to(ROOT)),indexSha256=digest(folder/'index.json'),
        files=len(files),bytes=index['totalBytes']),sort_keys=True))

if __name__ == '__main__':
    assert len(sys.argv) == 2
    main(sys.argv[1])

"""Seal the completed diagnostic and audit without executing their code."""
import hashlib
import json
import os
from pathlib import Path
import sys

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FOLDER = ROOT/'artifacts/implementation/standing-host-history-cost'
PINS = {
    'SOURCE-REVIEW.json':'75bb8a047304aa6b2cd4348837e68843b01983a947640c356b8a2764ea75f082',
    'audit_retained.py':'16bb0303d87e72ab815f85199159f5a441961503d6187abae23845785c9f2579',
    'AUDIT.json':'ad43b0a46898e13a0c8d59bb92ed48a31beeb16c07f816d44ad7e1a6fe64ef0e',
    'AUDIT-INPUT-PINS.json':'411c75b8a22b50a51c6e2fe9cc09cf688ab89be8c0246759499a21ed3eee970d',
    'history-cost-attempt01/RESULTS.json':'72e01321f52654d5cbdabfaa42c04eb647845445cec579ff1a6afffc54adcd19',
    'RESULTS.md':'3742a221046ec8a12d28679e5288887421010643d28e79cedc31ce75b7122672',
    'NEXT.md':'e6ec109129074d640ffd7ff4c7060a2e592f2312ee652966934ee370ae812bb0',
    'audit-history/draft01/audit_retained.py':'16bb0303d87e72ab815f85199159f5a441961503d6187abae23845785c9f2579',
    'audit-history/draft01/AUDIT-PLAN.md':'591ca768751af3d135db344711db8e1d6d4930e5b4790f21160db7d4224a61f6',
    'review-history/results-draft01/RESULTS.md':'dcc63aebca9b1eae4685c39a9441aa9a0186924c2f532ae0bf7281267b73461e',
    'review-history/results-draft01/NEXT.md':'82f088711f9d543645a17d5b4d779aeed7a761ebcb7ca4df41efc174bf11e403',
}

def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    assert len(sys.argv) == 1 and not (FOLDER/'index.json').exists()
    assert not (FOLDER/'.AUDIT.json.pending').exists()
    for name,pin in PINS.items(): assert digest(FOLDER/name) == pin
    audit = json.loads((FOLDER/'AUDIT.json').read_bytes())
    assert audit['passed'] and audit['checks'] == 61794
    assert audit['attemptFiles'] == 309 and audit['sourceFilesReverified'] == 299
    assert audit['completedCases'] == 1 and audit['loopCount'] == 32 and audit['mutationValidations'] == 2176
    assert audit['nativeReaps'] == audit['outerReaps'] == 1 and audit['ownedIdentitiesCurrentlyAbsent'] == 2
    assert audit['database']['retainedMutations'] == 32 and audit['database']['retainedClaims'] == 3
    assert audit['database']['wireRequests'] == audit['database']['wireResponses'] == 70
    assert audit['database']['selectors'] == 28 and audit['timing']['metricRows'] == 981
    assert audit['oldFailedCapacityProfileRemainsFailed']
    assert not any(audit[k] for k in ('productionChanged','qualificationRerun','full128RecordQualification',
        'physicalEligible','protectedCapacity','publicMountEligible'))
    files = []
    for path in sorted(FOLDER.rglob('*')):
        assert not path.is_symlink() and '__pycache__' not in path.parts
        if path.is_file():
            before=path.stat();pin=digest(path);after=path.stat()
            signature=lambda s:(s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            assert signature(before) == signature(after)
            files.append(dict(path=str(path.relative_to(FOLDER)),bytes=before.st_size,sha256=pin))
    review = json.loads((FOLDER/'SOURCE-REVIEW.json').read_bytes())
    source_names = {row['path'] for row in review['files']}
    outside = {row['path'] for row in files if not row['path'].startswith('history-cost-attempt01/')} - source_names
    assert outside == {'AUDIT-INPUT-PINS.json','AUDIT-PLAN.md','AUDIT.json','NEXT.md','RESULTS.md',
        'SOURCE-REVIEW.json','audit_retained.py','audit-history/draft01/AUDIT-PLAN.md',
        'audit-history/draft01/audit_retained.py','review-history/results-draft01/NEXT.md',
        'review-history/results-draft01/RESULTS.md'}
    assert len(source_names) == 299 and len(files) == 619
    result = dict(profile='hms-isolated-evidence-packet/1',status='sealed-bounded-diagnostic-not-full-capacity',
        sealSourceSha256=digest(Path(__file__)),fileCount=len(files),totalBytes=sum(row['bytes'] for row in files),
        facts=dict(completedCases=1,loops=32,mutationValidations=2176,rawPackets=140,retainedClaims=3,
            auditRetainedChecks=61794,auditFinalReceiptSizeChecks=1,nativeReaps=1,outerReaps=1,
            controlObservedElapsedNs='9642591362',full128RecordQualification=False,productionChanged=False),
        physicalIOQualified=False,publicStandingMountEligible=False,completeGoalClaimed=False,files=files)
    with (FOLDER/'index.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps(dict(path=str(FOLDER.relative_to(ROOT)),indexSha256=digest(FOLDER/'index.json'),
        files=len(files),bytes=result['totalBytes']),sort_keys=True))

if __name__ == '__main__': main()

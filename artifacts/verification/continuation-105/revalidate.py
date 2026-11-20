"""Read-only revalidation of continuation104 before new work."""
import hashlib
import json
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import unquote,urlsplit

assert not sys.flags.optimize
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PRIOR=ROOT/'artifacts/verification/continuation-104/receipt.json'
PRIOR_SHA='176f0dd7e71c17ee89f0bddc0ec36fdf1de7203e93219c357532d867f9138e03'
HELPER=ROOT/'artifacts/verification/continuation-99/verify.py'
HELPER_SHA='c8eeecf02031c1203f030719e409c84863838ae79acd8c2164e7940d56513c2a'

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    assert digest(PRIOR)==PRIOR_SHA and digest(HELPER)==HELPER_SHA
    previous=json.loads(PRIOR.read_bytes())
    assert previous['status']=='verified' and previous['goalStatus']=='active-incomplete'
    assert previous['hostCompletedBoundaryCases']==18 and previous['combinedFlashReductionBytes']==1908
    assert len(previous['sealedPackets'])==25
    packet=runpy.run_path(str(HELPER))['packet']
    packets=[packet(row['path'],row['indexSha256']) for row in previous['sealedPackets']]
    assert digest(PRIOR.parent/'verify.py')==previous['verificationSourceSha256']
    for name,row in previous['rootSupportingFiles'].items():
        path=PRIOR.parent/name;assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size==row['bytes'] and digest(path)==row['sha256']
    count=0
    for name,pin in previous['rootDocuments'].items():
        path=ROOT/name;assert digest(path)==pin
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            split=urlsplit(target.strip().strip('<>'))
            if split.scheme or split.netloc or not split.path:continue
            target_path=Path(unquote(split.path))
            if not target_path.is_absolute():target_path=path.parent/target_path
            assert target_path.exists(),(name,target)
            count+=1
    assert count==previous['localLinksChecked']==756
    public=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(public)==previous['publicReceiptSha256']
    baseline=json.loads(public.read_bytes())
    assert baseline['passed'] and baseline['tests']==866 and len(baseline['files'])==244
    assert all(digest(ROOT/row['path'])==row['sha256'] for row in baseline['files'])
    result=dict(previousTurnClassification='progress',previousReceiptSha256=PRIOR_SHA,
        classificationEvidence='Implemented and measured shared firmware kernel:1908 flash bytes saved;18 additional host boundary cases passed; actual capacity wall failure retained and audited, changing next work to growing-history cost analysis.',
        sealedPackets=packets,rootDocuments=previous['rootDocuments'],localLinksChecked=count,
        previousSupportingFilesExact=len(previous['rootSupportingFiles']),publicInputsExact=244,
        publicTestsPreviouslyPassed=866,publicTestsRerun=False,candidateExecuted=False,
        goalStatus='active-incomplete',verificationSourceSha256=digest(Path(__file__)))
    with (HERE/'revalidation.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sealedPackets','rootDocuments')},sort_keys=True))

if __name__=='__main__':main()

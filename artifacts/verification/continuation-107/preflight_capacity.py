"""Root source/data check before the one complete original capacity attempt."""
from pathlib import Path
import difflib
import hashlib
import json
import sys

assert not sys.flags.optimize
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
P=ROOT/'artifacts/implementation/standing-host-selection-capacity'
BASE=ROOT/'artifacts/implementation/standing-host-selection-reuse'
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def read(path):return json.loads(path.read_bytes())
def contained(base,name):
    relative=Path(name);assert not relative.is_absolute() and '..' not in relative.parts
    p=base/relative;assert not p.is_symlink() and p.resolve().is_relative_to(base.resolve())
    return p
def main():
    assert len(sys.argv)==1
    assert sha(P/'SOURCE-REVIEW.json')=='d72b3d26053adbd54bdf06a6b848c00fbe490cf078585b561d684057a39f9c96'
    review=read(P/'SOURCE-REVIEW.json');pins=read(P/'source-pins.json');rows=review['files']
    assert len(rows)==review['inputFiles']==289 and len({r['path'] for r in rows})==289
    assert sum(r['bytes'] for r in rows)==review['inputBytes']==5476258
    for row in rows:
        p=contained(P,row['path']);assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
    assert len(pins['copies'])==262 and len(pins['originalProvenance'])==18
    for row in pins['copies']+pins['originalProvenance']:
        source=contained(ROOT,row['source']);copy=contained(P,row['copy'])
        assert source.stat().st_size==copy.stat().st_size==row['bytes']
        assert sha(source)==sha(copy)==row['sha256']
    current={str(p.relative_to(P/'project')):sha(p) for p in (P/'project').rglob('*') if p.is_file()}
    baseline={str(p.relative_to(BASE/'project')):sha(p) for p in (BASE/'project').rglob('*') if p.is_file()}
    assert current==baseline and len(current)==259 and review['modifiedProductionFiles']==[]
    parent_files=0
    for key in ('parentPacket','secondParentPacket','thirdParentPacket'):
        folder=ROOT/pins[key]['path'];assert sha(folder/'index.json')==pins[key]['indexSha256']
        contents=read(folder/'index.json')['files'];parent_files+=len(contents)
        assert {str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file()}=={r['path'] for r in contents}|{'index.json'}
        for row in contents:
            p=contained(folder,row['path']);assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
    assert parent_files==5969
    for old,new,patch,left,right in (
        (P/'originals/selection-reuse/run_checks.py',P/'run_checks.py','runner.patch','originals/selection-reuse/run_checks.py','run_checks.py'),
        (BASE/'owner/guardian.py',P/'owner/guardian.py','guardian-variant.patch','../standing-host-selection-reuse/owner/guardian.py','owner/guardian.py')):
        delta=''.join(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile=left,tofile=right))
        assert delta.encode()==(P/patch).read_bytes()
    assert sha(P/'boundary_controls.py')=='01e91d85d9da351af7f1c8dc8cd42bf375898959ff1264754408311042517e5d'
    assert sha(P/'owner/guardian.py')=='b9451d90c845f86b9e41cfc527c3fb7fa0ed8e7e58b65ab0cd5c0bc0d2a60792'
    assert sha(P/'owner/libharness-owner.so')=='a6ee94bcf3dc03df19f0dd07a81663badd4875ef1a6c429afbc55d7b2373b977'
    for key in ('previousReceipt','publicReceipt'):assert sha(ROOT/pins[key]['path'])==pins[key]['sha256']
    public=read(ROOT/pins['publicReceipt']['path'])['files'];assert len(public)==244
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in public)
    assert not list(P.glob('selection-capacity-*-attempt*'))
    result=dict(passed=True,sourceReviewSha256=sha(P/'SOURCE-REVIEW.json'),inputFilesExcludingSelf=289,
        frozenFilesIncludingSelf=290,inputBytesExcludingSelf=5476258,projectFilesExact=259,
        reusedFilesExact=262,provenanceCopiesExact=18,parentFilesExact=5969,publicInputsExact=244,
        rootCompleteRead=['capacity_controls.py','run_checks.py','runner.patch','guardian-variant.patch','README.md','PLAN.md','REVIEW-NOTES.md'],
        rootFocusedRead='Exact boundary imports/helpers/classes1–140 and complete original mutation_capacity320–367; exact Fixture reused from prior full review.',
        originalWorkloadUnchanged=True,productionUnchangedFromValidatedSelection=True,
        runnerDeltaRegenerated=True,guardianVariantDeltaRegenerated=True,
        candidateImported=False,candidateExecuted=False,originalQualifierRerun=False)
    with (HERE/'capacity-preflight.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()

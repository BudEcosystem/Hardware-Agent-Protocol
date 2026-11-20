"""Data-only input/provenance join before the first reviewed process-death run."""
import ast
import hashlib
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LANE=ROOT/'artifacts/implementation/standing-host-owner-death'
PARENT=ROOT/'artifacts/implementation/standing-host-deployment'
REVIEW_SHA='4dca9bff924a726520952e9beae2a4b7d18bd73f46a4735e2fd1c227f2aba9fe'
PINS={'owner_death_controls.py':'dc869ef7f7d92f823004722ac1c08232db8e69372ad4ae716290b043e68e70d5',
      'run_checks.py':'ef0c4fad446ecfda9fd6cec83e2d7c1b6d2ca77f64f74c79083e29a2e0136c00'}


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):return json.loads(path.read_bytes())


def exact(path,row):
    assert not path.is_symlink() and path.is_file()
    assert path.stat().st_size==row['bytes'] and digest(path)==row['sha256']


def main():
    assert digest(LANE/'SOURCE-REVIEW.json')==REVIEW_SHA
    review=read(LANE/'SOURCE-REVIEW.json');assert len(review['files'])==287
    assert review['productionChanges']==[] and not review['candidateExecuted'] and review['notSealed']
    names=set()
    for row in review['files']:
        assert row['path'] not in names;names.add(row['path']);exact(LANE/row['path'],row)
    assert {str(p.relative_to(LANE)) for p in LANE.rglob('*') if p.is_file() or p.is_symlink()}==names|{'SOURCE-REVIEW.json'}
    for name,pin in PINS.items():
        assert digest(LANE/name)==pin and digest(HERE/'inputs'/(name+'.freeze01'))==pin
        ast.parse((LANE/name).read_bytes(),filename=name)
    inputs=read(LANE/'source-pins.json')
    assert len(inputs['copies'])==261 and len(inputs['originalProvenance'])==19
    for row in inputs['copies']+inputs['originalProvenance']:
        exact(ROOT/row['source'],row);exact(LANE/row['copy'],row)
    assert digest(PARENT/'index.json')==inputs['parentPacket']['indexSha256']=='72371ef7752f2e90f6e8b185c125b00b165b8b64ce50d8121680c5a24951249b'
    parent=read(PARENT/'index.json');assert len(parent['files'])==3755
    for row in parent['files']:exact(PARENT/row['path'],row)
    assert {str(p.relative_to(PARENT)) for p in PARENT.rglob('*') if p.is_file() or p.is_symlink()}=={r['path'] for r in parent['files']}|{'index.json'}
    old=PARENT/'host-attempt04';result=read(old/'RESULTS.json');assert result['passed'] and not result['physicalEligible']
    assert digest(old/'RESULTS.json')=='fa91f9fa7aece57fe2cbdc9f1326c1946b7a466ffae13768776c8158b3ba9a40'
    assert inputs['nativeImage']==str(old/'standing-host-pipe') and inputs['qualificationRoot']==str(old/'qualification')
    assert digest(old/'standing-host-pipe')=='5ab180cb56526a352691583bbcec4033b85af0c38c6d46057b1f4ae0cd607399'
    evidence=old/'qualification';manifest=read(evidence/'manifest.json');receipt=read(evidence/'receipt.json');reservation=read(evidence/'reservation.json')
    assert manifest['runId']==receipt['runId']==reservation['runId']=='native-standing-original:4'
    assert receipt['attemptId']==reservation['attemptId']=='native-standing-attempt:4'
    assert manifest['argv']==receipt['argv']==reservation['argv']==[str(evidence/'standing-controls')]
    assert receipt['exitCode']==0 and receipt['terminationSignal']==0
    for field in ('binary','reservation','receipt','stdout','stderr'):
        assert manifest[field+'Digest']=='sha256:'+digest(evidence/manifest[field+'Path'])
    assert receipt['reservationDigest']=='sha256:'+digest(evidence/'reservation.json')
    actual=read(old/'original-qualification.receipt.json')
    assert actual['argv']==manifest['argv'] and actual['executableSha256']==manifest['binaryDigest'][7:]
    assert actual['heldImageBefore']==actual['heldImageAfter'] and actual['heldImageBefore']['sha256']==actual['executableSha256']
    assert actual['exit']['exitCode']==0 and actual['exit']['reaped'] and actual['childrenReaped']==[actual['exit']]
    assert actual['exit']['pid']==receipt['ownership']['pid']==receipt['ownership']['waitedPid']
    for key in ('startedMonotonicNs','finishedMonotonicNs'):assert actual[key]==receipt[key]
    for name,pin in manifest['sourcePins'].items():
        assert 'sha256:'+digest(LANE/'project'/name)=='sha256:'+digest(old/'frozen/project'/name)==pin
    assert json.loads((evidence/'stdout').read_bytes())=={'cases':12,'assertions':638,'physical_qualification':False}
    assert not (evidence/'stderr').read_bytes()
    public=ROOT/inputs['publicReceipt']['path'];assert digest(public)==inputs['publicReceipt']['sha256']
    baseline=read(public);assert baseline['passed'] and baseline['tests']==866 and len(baseline['files'])==244
    assert all(digest(ROOT/row['path'])==row['sha256'] for row in baseline['files'])
    assert not (LANE/'owner-death-attempt01').exists()
    report=dict(status='verified-before-first-run',verificationSourceSha256=digest(Path(__file__)),
        reviewedSourceSha256=REVIEW_SHA,newExecutableSourcePins=PINS,reviewedFiles=287,
        exactSourceHelperCopies=261,exactAuditOnlyProvenanceCopies=19,exactSealedParentFiles=3755,
        originalQualificationRunId=manifest['runId'],originalQualificationCases=12,originalQualificationAssertions=638,
        originalQualificationRoot=str(evidence),originalAbsoluteArgvPreserved=True,publicInputsExact=244,
        candidateImported=False,candidateExecuted=False,qualifierRerun=False,physicalIOExecuted=False)
    with (HERE/'owner-death-preflight.json').open('x') as out:
        json.dump(report,out,sort_keys=True,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':main()

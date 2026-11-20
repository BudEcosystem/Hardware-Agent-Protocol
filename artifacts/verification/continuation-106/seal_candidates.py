"""Root data-only seals after reviewed controls and auditors have finished."""
import hashlib
import json
from pathlib import Path
import sys

assert not sys.flags.optimize
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()
def read(path):return json.loads(path.read_bytes())
def main():
    assert len(sys.argv)==2 and sys.argv[1] in ('firmware','host')
    firmware=sys.argv[1]=='firmware'
    name='standing-endpoint-phase-kernels' if firmware else 'standing-host-selection-reuse'
    packet=ROOT/'artifacts/implementation'/name
    assert not (packet/'index.json').exists()
    final=read(HERE/'final-review.json')
    expected=final['firmwareFinalFiles' if firmware else 'hostFinalFiles']
    for path,pin in expected.items():assert sha(packet/path)==pin
    assert read(packet/'AUDIT.json')['passed']
    if firmware:
        review=read(packet/'project-source-review.json')
        pins=dict(review['all_other_prepared_files_sha256'])
        pins['project-source-review.json']='8a2b1fafb71d84ae49fc83cf6edcf07520613f7d46fbe2d46e52958d64a3f7d5'
        assert len(pins)==139
        audit=read(packet/'AUDIT.json')
        assert audit['totalCommands']==audit['totalReaps']==58
        assert audit['currentSourcesNativeCompleted'] and not audit['currentSourcesAvrCompleted']
        assert not (packet/'build/avr/runtime.elf').exists()
        measurement=read(packet/'codegen-measurements.json')
        assert measurement['current']['flashBytes']==39186 and measurement['current']['staticBytes']==1503
        assert measurement['flashReductionBytes']==716 and measurement['applicationOverflowBytes']==6930
        assert measurement['completeStackProof'] is False
        assert sha(packet/'reader-history/draft01/attempt01.json')==sha(HERE/'codegen-reader-attempt01.json')
        assert sha(packet/'reader-history/draft01/codegen_measure.py')=='196c91a2308d5e9c0b83d05f3fa31b218850d1397d23709303bea7470b2b4893'
    else:
        review=read(packet/'SOURCE-REVIEW.json')
        pins={row['path']:row['sha256'] for row in review['files']}
        pins['SOURCE-REVIEW.json']='25e1be4db68cec9b639667e034656f45fc985923bdf4bc8a2b8ab8a3a060bdb1'
        assert len(pins)==284
        for profile,cases,checks,legacy,native,pin in (
            ('pure',1,84,0,0,'8fe7ffc6364242c6c148192edcaf09b295ef0d544b4d06f140c88c569e40443f'),
            ('live',9,267,76,9,'28025c9ac0a136bee36f3a14b2d30116611779bfb9d55674421b210c7be2538c')):
            folder=packet/('selection-reuse-'+profile+'-attempt01')
            assert sha(folder/'RESULTS.json')==pin
            result=read(folder/'RESULTS.json');inner=read(folder/'state/CONTROL-RESULTS.json')
            assert result['passed'] and inner['passed'] and result['innerCases']==cases
            assert inner['checks']==checks and inner['legacyChecks']==legacy
            assert len(inner['nativeChildrenReaped'])==native and len(result['outerChildrenReaped'])==1
            assert not result['full128RecordQualification'] and not result['qualificationRerun']
            assert all(sha(folder/'frozen'/path)==pin for path,pin in pins.items())
    assert all(sha(packet/path)==pin for path,pin in pins.items())
    files=[]
    for path in sorted(packet.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():
            assert '__pycache__' not in path.parts and path.suffix!='.pyc'
            files.append(dict(path=str(path.relative_to(packet)),bytes=path.stat().st_size,sha256=sha(path)))
    result=dict(schema='hms-continuation106-evidence-seal/1',fileCount=len(files),totalBytes=sum(r['bytes'] for r in files),
        files=files,sealSourceSha256=sha(Path(__file__)),rootReviewSha256=sha(HERE/'final-review.json'),
        originalFrozenInputs=len(pins),candidateRerun=False,physicalExecution=False,
        scope='Exact retained source and evidence; failed AVR and incomplete capacity remain explicit.')
    with (packet/'index.json').open('x') as out:
        json.dump(result,out,indent=2,sort_keys=True);out.write('\n')
    print(json.dumps(dict(packet=str(packet.relative_to(ROOT)),files=len(files),bytes=result['totalBytes'],indexSha256=sha(packet/'index.json'))))

if __name__=='__main__':main()

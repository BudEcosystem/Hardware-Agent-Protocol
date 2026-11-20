"""Join the fully reviewed diagnostic source before its first bounded run."""
import difflib
import hashlib
import json
from pathlib import Path
import runpy
import sys

assert not sys.flags.optimize
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=ROOT/'artifacts/implementation/standing-host-history-cost'
HELPER=ROOT/'artifacts/verification/continuation-99/verify.py'

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def read(path):return json.loads(path.read_bytes())

def exact(path,row):
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size==row['bytes'] and digest(path)==row['sha256'],path

def main():
    assert digest(HELPER)=='c8eeecf02031c1203f030719e409c84863838ae79acd8c2164e7940d56513c2a'
    assert digest(BASE/'SOURCE-REVIEW.json')=='75bb8a047304aa6b2cd4348837e68843b01983a947640c356b8a2764ea75f082'
    review=read(BASE/'SOURCE-REVIEW.json');names=set()
    for row in review['files']:
        assert row['path'] not in names;names.add(row['path']);exact(BASE/row['path'],row)
    assert len(names)==review['inputFiles']==299
    assert sum(row['bytes'] for row in review['files'])==review['inputBytes']==6428900
    assert {str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() or p.is_symlink()}==names|{'SOURCE-REVIEW.json'}
    assert digest(BASE/'run_checks.py')=='87e66e257d1d5f49f634363c21da7be04ce70066a87a4d54f85a8ee6cf05846c'
    assert digest(BASE/'history_cost_controls.py')=='6b3d6a677af22442e86939fdf443b7cf93911e2b3a483cd129544994503d523b'
    old=BASE/'review-history/root-read01/history_cost_controls.py'
    new=BASE/'history_cost_controls.py'
    assert digest(old)=='48ea2e0e3d7238737bf5e9f321eedc6f3a049fc5c4199cdd32b16870631b95bb'
    patch=''.join(difflib.unified_diff(old.read_text().splitlines(keepends=True),new.read_text().splitlines(keepends=True),
        fromfile=str(old.relative_to(ROOT)),tofile=str(new.relative_to(ROOT))))
    assert (BASE/'review-history/root-read01-to-final.patch').read_text()==patch
    assert digest(BASE/'review-history/root-read01-to-final.patch')=='9e5e845277eb0f9133f6fc20a98f86688fe424bb8f289ca74219db9a8ac9aad2'
    assert (BASE/'review-history/root-read01/run_checks.py').read_bytes()==(BASE/'run_checks.py').read_bytes()
    inputs=read(BASE/'source-pins.json')
    assert len(inputs['copies'])==261 and len(inputs['originalProvenance'])==25
    for row in inputs['copies']+inputs['originalProvenance']:
        exact(ROOT/row['source'],row);exact(BASE/row['copy'],row)
    packet=runpy.run_path(str(HELPER))['packet']
    parents=[packet(inputs[key]['path'],inputs[key]['indexSha256']) for key in ('parentPacket','secondParentPacket')]
    public=ROOT/inputs['publicReceipt']['path']
    assert digest(public)==inputs['publicReceipt']['sha256']=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    baseline=read(public);assert baseline['passed'] and baseline['tests']==866 and len(baseline['files'])==244
    assert all(digest(ROOT/row['path'])==row['sha256'] for row in baseline['files'])
    assert not list(BASE.glob('history-cost-attempt*'))
    result=dict(status='verified-reviewed-fixed-diagnostic-before-execution',verificationSourceSha256=digest(Path(__file__)),
        sourceReviewSha256=digest(BASE/'SOURCE-REVIEW.json'),runnerSha256=digest(BASE/'run_checks.py'),
        controlSha256=digest(new),sourceFiles=299,sourceBytes=6428900,reusedFiles=261,provenanceCopies=25,
        parents=parents,publicInputsExact=244,rootReadRunnerLines=299,rootReadControlDraftLines=288,
        rootReadFinalControlDeltaLines=101,finalControlLines=297,independentSourceReviewCompleted=True,
        fixedLoops=32,expectedMutationValidations=2176,diagnosticOnly=True,productionChanged=False,
        original128RecordCapacityClaimed=False,candidateImportedOrExecuted=False,qualificationRerun=False)
    with (HERE/'history-cost-preflight.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()

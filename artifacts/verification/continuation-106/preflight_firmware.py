"""Verify reviewed source and exact parent joins before any candidate launch."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys

assert not sys.flags.optimize
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FOLDER=ROOT/'artifacts/implementation/standing-endpoint-phase-kernels'
PARENT=ROOT/'artifacts/implementation/standing-endpoint-shared-kernel'
REVIEW_SHA='8a2b1fafb71d84ae49fc83cf6edcf07520613f7d46fbe2d46e52958d64a3f7d5'
RUNNER_SHA='225dcb6c523f275ed64c11a02874e4a60ccc561cfac31cc136e47c19ff9c13f1'
BASELINE_SHA='de3f25d2d07d94660ac4d3336bed1214657b0df2e23cbac58070b6546d5d332c'

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def read(path):return json.loads(path.read_bytes())

def main():
    assert len(sys.argv)==1 and digest(FOLDER/'project-source-review.json')==REVIEW_SHA
    review=read(FOLDER/'project-source-review.json');files=review['all_other_prepared_files_sha256']
    assert len(files)==138 and review['hash_inventory_excludes']=='this self-referential project-source-review.json only'
    found={str(p.relative_to(FOLDER)) for p in FOLDER.rglob('*') if p.is_file() or p.is_symlink()}
    assert found==set(files)|{'project-source-review.json'}
    assert sum((FOLDER/name).stat().st_size for name in found)==1617450
    for name,pin in files.items():
        path=FOLDER/name;assert path.is_file() and not path.is_symlink() and digest(path)==pin
    assert not (FOLDER/'build').exists() and not list(FOLDER.glob('checks-*.json'))
    assert review['independent_core_controls_runner_review_complete'] and review['preserved_original_control_bodies']==19
    assert digest(FOLDER/'INDEPENDENT-REVIEW.md')=='8b1901cb054ce8684a3b796d884c321a931a3a3d16830cfba9f4b2e008671274'
    assert digest(PARENT/'index.json')=='0a4a518555e08415a9d893bba106616323a3f1a237b61bf0bc171ee8f2979909'
    parent=read(PARENT/'index.json');assert len(parent['files'])==746
    for row in parent['files']:
        path=PARENT/row['path'];assert not path.is_symlink()
        assert path.stat().st_size==row['bytes'] and digest(path)==row['sha256']
    assert {str(p.relative_to(PARENT)) for p in PARENT.rglob('*') if p.is_file() or p.is_symlink()}=={r['path'] for r in parent['files']}|{'index.json'}
    originals=review['original_project_sha256'];project=review['project_sha256']
    assert len(originals)==40 and len(project)==41
    for name,pin in originals.items():assert digest(FOLDER/'originals/project'/name)==digest(PARENT/'project'/name)==pin
    for name,pin in project.items():assert digest(FOLDER/'project'/name)==pin
    assert {str(p.relative_to(FOLDER/'project')) for p in (FOLDER/'project').rglob('*') if p.is_file()}==set(project)
    changed={n for n in originals if originals[n]!=project[n]};added=set(project)-set(originals)
    assert changed=={'protocol/endpoint/endpoint.c','protocol/endpoint/standing.c','protocol/endpoint/endpoint_kernel.c',
        'protocol/endpoint/endpoint_kernel.h','scripts/check_endpoint_native.py','tests/kernel_controls.c','tests/endpoint_equivalence.c'}
    assert added=={'tests/phase_access.c'}
    delta=[]
    for name in sorted(project):
        old=FOLDER/'originals/project'/name;new=FOLDER/'project'/name
        delta.extend(difflib.unified_diff(old.read_text().splitlines(True) if old.exists() else [],new.read_text().splitlines(True),
            fromfile='originals/project/'+name if old.exists() else '/dev/null',tofile='project/'+name))
    assert ''.join(delta)==(FOLDER/'project.diff').read_text()
    assert digest(FOLDER/'project.diff')==review['project_delta_sha256']=='ecf522f2ff86b1d084b98c059f210890179cab15bd44fb838110fc34b592fd70'
    for group in ('core-draft01','controls-draft03'):
        snapshot=FOLDER/'history'/group
        for row in read(snapshot/'index.json')['files']:
            assert digest(snapshot/row['path'])==row['sha256']
            if row['path'].startswith('project/'):assert digest(FOLDER/row['path'])==row['sha256']
    assert digest(FOLDER/'runner-baseline.py')==digest(FOLDER/'originals/run_checks.py')==digest(PARENT/'run_checks.py')==BASELINE_SHA
    assert digest(FOLDER/'run_checks.py')==review['runner_sha256']==RUNNER_SHA
    delta=''.join(difflib.unified_diff((FOLDER/'runner-baseline.py').read_text().splitlines(True),
        (FOLDER/'run_checks.py').read_text().splitlines(True),fromfile='runner-baseline.py',tofile='run_checks.py'))
    assert delta==(FOLDER/'runner-diff.patch').read_text()
    assert digest(FOLDER/'runner-diff.patch')==review['runner_delta_sha256']=='1a6e84ba3ab89dd7d9d52fb5e362500b4e9c22716ff313b2e3dbd4dc27506289'
    coverage=read(FOLDER/'native-coverage.json');assert len(coverage['unchanged_case_bodies'])==14
    assert len(coverage['other_unchanged_functions'])==5
    assert {r['name'] for r in coverage['other_unchanged_functions']}=={'numeric_boundaries','overlapping_snapshots',
        'sequential_wire_groups','finite_callback_boundaries','public_lease_boundaries'}
    for row in coverage['unchanged_case_bodies']+coverage['other_unchanged_functions']:
        old=(FOLDER/row.get('baseline_source',coverage['baseline_source'])).read_bytes()
        new=(FOLDER/row.get('current_source',coverage['current_source'])).read_bytes()
        a,b=row['baseline_span'];c,d=row['current_span']
        assert old[a:b]==new[c:d] and hashlib.sha256(old[a:b]).hexdigest()==row['sha256']
    assert (FOLDER/'project/tests/standing_controls.c').read_bytes()==(FOLDER/'originals/project/tests/standing_controls.c').read_bytes()
    for name in ('retention.json','toolchain-pins.json','plugin-lookup-source-pins.json','PLUGIN-LOOKUP-REVIEW.md','WIRE.md','wire-vectors.json','runner-owner-pins.json'):
        assert digest(FOLDER/name)==digest(PARENT/name)
    retention=read(FOLDER/'retention.json')
    assert len(retention['function_roots'])==29 and len(retention['storage_roots'])==9 and retention['other_required_symbols']==['main']
    assert retention['stack_reserved_bytes']==512 and retention['maximum_static_delta_bytes']==160
    for row in read(FOLDER/'runner-owner-pins.json')['files']:
        assert digest(FOLDER/row['target'])==digest(ROOT/row['source'])==row['sha256']
        assert (FOLDER/row['target']).stat().st_size==row['bytes']
    public=read(ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json')
    assert public['passed'] and public['tests']==866 and len(public['files'])==244
    assert all(digest(ROOT/r['path'])==r['sha256'] for r in public['files'])
    assert all(digest(FOLDER/name)==pin for name,pin in files.items())
    result=dict(status='verified-reviewed-firmware-before-first-launch',sourceReviewSha256=REVIEW_SHA,
        frozenFiles=139,frozenBytes=1617450,parentFiles=746,projectFiles=41,originalProjectCopies=40,
        changedOriginals=sorted(changed),newProjectFiles=sorted(added),oldControlBodiesExact=19,
        rootReadBaselineRunnerLines=836,runnerDeltaLines=157,runnerSha256=RUNNER_SHA,
        publicInputsExact=244,publicTestsPreviouslyPassed=866,publicTestsRerun=False,candidateExecuted=False,
        nativeStagesExecuted=False,avrStageExecuted=False,verificationSourceSha256=digest(Path(__file__)))
    with (HERE/'firmware-preflight.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()

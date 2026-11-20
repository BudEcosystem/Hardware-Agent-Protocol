"""Read-only source/pin joins before the two reviewed isolated runners."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EMBEDDED = ROOT/'artifacts/implementation/standing-endpoint-shared-kernel'
HOST = ROOT/'artifacts/implementation/standing-host-boundaries'
HELPER = ROOT/'artifacts/verification/continuation-99/verify.py'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def pin(path, expected, size=None):
    assert path.is_file() and not path.is_symlink(), path
    assert digest(path) == expected, path
    if size is not None:
        assert path.stat().st_size == size, path

def main():
    pin(HELPER, 'c8eeecf02031c1203f030719e409c84863838ae79acd8c2164e7940d56513c2a')
    packet = runpy.run_path(str(HELPER))['packet']
    pin(EMBEDDED/'project-source-review.json', '6c1a5fc11d1b5c6dc57d49e8dcc618434a2e6036e703ce3b5ee2c8446c68940c')
    review = read(EMBEDDED/'project-source-review.json')
    for field, base in [('project_sha256', EMBEDDED/'project'), ('original_project_sha256', EMBEDDED/'originals/project')]:
        assert set(review[field]) == {str(p.relative_to(base)) for p in base.rglob('*') if p.is_file() or p.is_symlink()}
        for name, expected in review[field].items():
            pin(base/name, expected)
    assert len(review['project_sha256']) == 40 and len(review['original_project_sha256']) == 36
    for name, expected in review['reviews_and_inputs'].items():
        pin(EMBEDDED/name, expected)
    assert len(review['reviews_and_inputs']) == 37
    pin(EMBEDDED/'run_checks.py', 'de3f25d2d07d94660ac4d3336bed1214657b0df2e23cbac58070b6546d5d332c')
    pin(EMBEDDED/'run_checks.py', review['runner_sha256'])
    assert (HERE/'inputs/embedded-runner-draft02.py').read_bytes() == (EMBEDDED/'run_checks.py').read_bytes()
    for row in read(EMBEDDED/'source-pins.json')['originals']:
        for path in (ROOT/row['source'], EMBEDDED/row['target']):
            pin(path, row['sha256'], row['bytes'])
    for name, row in read(EMBEDDED/'runner-input-pins.json')['copies'].items():
        for path in (ROOT/row['source'], EMBEDDED/name):
            pin(path, row['sha256'], row['bytes'])
    parents = [packet(row['path'], row['index_sha256']) for row in read(EMBEDDED/'parent-pins.json')['parents']]
    pin(HOST/'SOURCE-REVIEW.json', '0634a6a8bc8ac78be1e2f4a3f2e9239da02206d331fd2dfebf7b97f29b7ab302')
    host = read(HOST/'SOURCE-REVIEW.json')
    names = set()
    for row in host['files']:
        assert row['path'] not in names and row['path'] != 'SOURCE-REVIEW.json'
        names.add(row['path']); pin(HOST/row['path'], row['sha256'], row['bytes'])
    assert len(names) == 306 and sum(row['bytes'] for row in host['files']) == 6412176
    assert 'originals/SOURCE-REVIEW.json' in names
    for name, expected in {
        'boundary_controls.py': '01e91d85d9da351af7f1c8dc8cd42bf375898959ff1264754408311042517e5d',
        'run_checks.py': '0d4ef343502a4e0983584d131c777c02764d9ae38177fc95d9900e5e6389f43b',
        'owner/guardian.py': 'b9451d90c845f86b9e41cfc527c3fb7fa0ed8e7e58b65ab0cd5c0bc0d2a60792',
        'history/draft01-to-current.patch': '16b6718337b2d878cd3b90ea1336c5af13ab0c08557bc2eab21335d9b9501559',
    }.items():
        pin(HOST/name, expected)
    sources = read(HOST/'source-pins.json')
    assert len(sources['copies']) == 260 and len(sources['originalProvenance']) == 20
    for row in sources['copies'] + sources['originalProvenance']:
        for path in (ROOT/row['source'], HOST/row['copy']):
            pin(path, row['sha256'], row['bytes'])
    for field in ('parentPacket', 'secondParentPacket'):
        row = sources[field]; parents.append(packet(row['path'], row['indexSha256']))
    public_path = ROOT/sources['publicReceipt']['path']
    pin(public_path, 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e')
    public = read(public_path)
    assert public['passed'] and public['tests'] == 866 and len(public['files']) == 244
    for row in public['files']:
        pin(ROOT/row['path'], row['sha256'])
    assert not (EMBEDDED/'build').exists() and not (EMBEDDED/'native-checks.json').exists()
    assert not list(HOST.glob('boundary-*-attempt*'))
    result = {
        'status': 'verified-frozen-reviewed-inputs-before-execution',
        'verificationSourceSha256': digest(Path(__file__)),
        'embeddedReviewSha256': digest(EMBEDDED/'project-source-review.json'),
        'embeddedProjectFiles': 40, 'embeddedOriginalFiles': 36, 'embeddedReviewInputs': 37,
        'hostReviewSha256': digest(HOST/'SOURCE-REVIEW.json'), 'hostFrozenFiles': 306,
        'hostExactSourceCopies': 260, 'hostExactProvenanceCopies': 20,
        'parents': parents, 'publicFiles': 244, 'publicTestsPreviouslyPassed': 866,
        'rootReadFinalControlsAndRunnerDeltas': True,
        'candidateImportedOrExecuted': False, 'oldTestsRerun': False,
        'priorNonexistentHostReviewDocRead': 'Two guessed markdown paths absent; actual REVIEW-NOTES.md and PLAN.md subsequently read in full.',
    }
    with (HERE/'preflight.json').open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(result, sort_keys=True))

if __name__ == '__main__':
    main()

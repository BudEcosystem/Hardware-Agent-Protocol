"""Compare the exact built-file inventory before and after this test lane."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKTREE = Path('/home/bud/Desktop/bud/hms-harness-a1626788')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

before_path = HERE / 'built-artifacts-before.json'
before = json.loads(before_path.read_text())['sha256']
after = {}
for directory in sorted([*WORKTREE.glob('packages/*/*/lib'), *WORKTREE.glob('apps/*/lib')]):
    for path in sorted(directory.rglob('*')):
        if path.is_file():
            after[str(path.relative_to(WORKTREE))] = digest(path)
assert after == before, 'Built bytes or inventory changed'
report = {'passed': True, 'built_files_verified': len(before),
          'before_manifest_sha256': digest(before_path),
          'scope': 'Existing built bytes and inventory unchanged across this validation run; not a new build or a historical artifact-time hash assertion.'}
(HERE/'verification/built-artifact-stability.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))

"""Freeze current HMS against the unchanged, previously built a162 overlay."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIOR = HERE.parent / 'revalidation-a1626788'
WORKTREE = Path('/home/bud/Desktop/bud/hms-harness-a1626788')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2) + '\n')


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


prior = json.loads((PRIOR / 'verification.json').read_text())
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=WORKTREE, text=True).strip() == prior['harness_base_commit']
changed_tracked = subprocess.check_output(['git', 'diff', 'HEAD', '--name-only'], cwd=WORKTREE, text=True).splitlines()
assert set(changed_tracked) == set(prior['shared_overlay_sources_sha256'])
for name, expected in prior['all_overlay_inputs_sha256'].items():
    assert digest(WORKTREE / name) == expected, name
for name, expected in prior['runtime_fixture_inputs_sha256'].items():
    assert digest(PRIOR / 'runtime-fixture' / name) == expected, name
    copy(PRIOR / 'runtime-fixture' / name, HERE / 'runtime-fixture' / name)
current, changed = {}, []
for name, old in prior['hms_inputs_sha256'].items():
    current[name] = digest(ROOT / name)
    if current[name] != old:
        changed.append(name)
    copy(ROOT / name, HERE / 'runtime-fixture' / name)
assert set(changed) == {'hms/runtime.py', 'hms/registry.py', 'hms/simulator.py', 'hms/endpoint_binding.py'}, changed
for name, expected in prior['native_source_inputs_sha256'].items():
    assert digest(ROOT / name) == expected, name
for name, expected in prior['harness_package_sources_sha256'].items():
    source = PRIOR / 'packages' / Path(name).relative_to('packages/experimental')
    assert digest(source) == expected
    copy(source, HERE / 'packages' / Path(name).relative_to('packages/experimental'))
for name in prior['shared_overlay_sources_sha256']:
    copy(WORKTREE / name, HERE / 'shared-overlay' / name)
for name in ('harness.patch', 'endpoint-scenarios-build-receipt.json', 'run-command.py'):
    copy(PRIOR / name, HERE / name)
copy(PRIOR / 'verification.json', HERE / 'prior-verification.json')
for name in ('AGENTS.md', 'packages/AGENTS.md', 'packages/experimental/AGENTS.md', 'docs/testing.md'):
    copy(WORKTREE / name, HERE / 'instructions' / name)
fixture = {name: digest(HERE / 'runtime-fixture' / name) for name in prior['runtime_fixture_inputs_sha256']}
assert len(fixture) == 44
root_receipt = json.loads((ROOT / 'artifacts/verification/local-runtime.json').read_text())
assert root_receipt['tests'] == 289 and not root_receipt['errors'] and not root_receipt['failures'] and not root_receipt['skipped']
for item in root_receipt['files']:
    assert digest(ROOT / item['path']) == item['sha256'], item['path']
copy(ROOT / 'artifacts/verification/local-runtime.json', HERE / 'root-runtime-verification.json')
dump('hms-inputs.json', {'sha256': current, 'changed_from_prior': changed})
dump('fixture-inputs.json', {'sha256': fixture, 'scope': 'Exact current32 HMS inputs plus unchanged original native source/binary files; bytecode caches excluded.'})
dump('patch-inputs.json', {key: prior[key] for key in ('all_overlay_inputs_sha256', 'harness_package_sources_sha256', 'shared_overlay_sources_sha256', 'patch_sha256')})
artifacts = {}
for directory in sorted([*WORKTREE.glob('packages/*/*/lib'), *WORKTREE.glob('apps/*/lib')]):
    for path in sorted(directory.rglob('*')):
        if path.is_file():
            artifacts[str(path.relative_to(WORKTREE))] = digest(path)
assert artifacts
dump('built-artifacts-before.json', {'sha256': artifacts, 'scope': 'Existing worktree built lib artifacts pinned immediately before this test. No new build; no claim these hashes were recorded at the earlier build time.'})
dump('reuse-check.json', {
    'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'harness_base_commit': prior['harness_base_commit'], 'worktree': str(WORKTREE),
    'prior_receipt': {'path': str((PRIOR / 'verification.json').relative_to(ROOT)), 'sha256': digest(PRIOR / 'verification.json')},
    'unchanged_overlay_files': len(prior['all_overlay_inputs_sha256']),
    'changed_hms_files': changed, 'fixture_files': len(fixture),
    'pinned_existing_built_files': len(artifacts),
    'reused_checks': {key: prior['checks'][key] for key in ('build_artifacts', 'build_check', 'focused_oxlint', 'built_exports_smoke')},
    'qualification': 'Same a162 source base and all38 exact overlay input hashes; new changes are external Python HMS only. Reuse prior7 artifact stages and3 aggregate checks. Existing built bytes are additionally pinned before/after this run, not represented as a new build.'})
print(json.dumps({'fixture_files': len(fixture), 'changed_hms_files': changed, 'built_files': len(artifacts)}))

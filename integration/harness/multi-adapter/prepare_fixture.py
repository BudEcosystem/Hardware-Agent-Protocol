"""Freeze checked HMS sources against the unchanged, previously built a162 overlay."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIOR = HERE.parent / 'installed-support'
BUILD = HERE.parent / 'revalidation-a1626788'
WORKTREE = Path('/home/bud/Desktop/bud/hms-harness-a1626788')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(name, value):
    path = HERE / name
    if path.exists():
        raise RuntimeError('Refuse to overwrite retained record: ' + str(path))
    path.write_text(json.dumps(value, indent=2) + '\n')


def copy(source, destination):
    if destination.exists():
        raise RuntimeError('Refuse to overwrite retained file: ' + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


if (HERE / 'runtime-fixture').exists():
    raise SystemExit('Refuse to replace frozen runtime fixture')
root_receipt = json.loads((ROOT / 'artifacts/verification/local-runtime.json').read_text())
assert root_receipt['tests'] > 289 and not any(root_receipt[key] for key in ('errors', 'failures', 'skipped'))
for item in root_receipt['files'] + root_receipt['outputs']:
    assert digest(ROOT / item['path']) == item['sha256'], item['path']
prior = json.loads((PRIOR / 'verification.json').read_text())
build = json.loads((BUILD / 'verification.json').read_text())
repair = json.loads((HERE / 'assertion-repair.json').read_text())
for item in (repair['original'], repair['copied_test']):
    assert digest(WORKTREE / item['path']) == item['sha256'], item['path']
assert digest(HERE / repair['copied_test']['snapshot_path']) == repair['copied_test']['sha256']
assert digest(HERE / repair['patch']['path']) == repair['patch']['sha256']
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=WORKTREE, text=True).strip() == prior['harness_base_commit']
changed_tracked = subprocess.check_output(['git', 'diff', 'HEAD', '--name-only'], cwd=WORKTREE, text=True).splitlines()
assert set(changed_tracked) == set(prior['shared_overlay_sources_sha256'])
assert prior['all_overlay_inputs_sha256'] == build['all_overlay_inputs_sha256']
for name, expected in prior['all_overlay_inputs_sha256'].items():
    assert digest(WORKTREE / name) == expected, name
for name, expected in prior['runtime_fixture_inputs_sha256'].items():
    assert digest(PRIOR / 'runtime-fixture' / name) == expected, name
for name, expected in prior['native_source_inputs_sha256'].items():
    assert digest(ROOT / name) == expected, name
names = set(prior['hms_inputs_sha256']) | {str(path.relative_to(ROOT)) for path in (ROOT/'hms').rglob('*.py')}
current = {name: digest(ROOT / name) for name in sorted(names)}
changed = sorted(name for name, value in current.items() if prior['hms_inputs_sha256'].get(name) != value)
added = sorted(names - set(prior['hms_inputs_sha256']))
assert added == ['hms/adapter_catalog.py', 'hms/installations.py', 'hms/local_adapter.py'], added
runtime_files = {item['path']:item['sha256'] for item in root_receipt['files']}
for name, expected in current.items():
    if name.startswith('hms/'):
        assert runtime_files[name] == expected, name
fixture_names = set(prior['runtime_fixture_inputs_sha256']) | names
for name in sorted(fixture_names):
    source = ROOT / name if name in current else PRIOR / 'runtime-fixture' / name
    copy(source, HERE / 'runtime-fixture' / name)
for name, expected in prior['harness_package_sources_sha256'].items():
    source = PRIOR / 'packages' / Path(name).relative_to('packages/experimental')
    assert digest(source) == expected
    copy(source, HERE / 'packages' / Path(name).relative_to('packages/experimental'))
for name in prior['shared_overlay_sources_sha256']:
    copy(WORKTREE / name, HERE / 'shared-overlay' / name)
for name in ('harness.patch', 'endpoint-scenarios-build-receipt.json'):
    copy(PRIOR / name, HERE / name)
copy(PRIOR / 'verification.json', HERE / 'prior-verification.json')
copy(BUILD / 'verification.json', HERE / 'build-baseline-verification.json')
for name in ('AGENTS.md', 'packages/AGENTS.md', 'packages/experimental/AGENTS.md', 'docs/testing.md', 'docs/architecture.md'):
    copy(WORKTREE / name, HERE / 'instructions' / name)
copy(ROOT / 'artifacts/verification/local-runtime.json', HERE / 'root-runtime-verification.json')
fixture = {name: digest(HERE / 'runtime-fixture' / name) for name in sorted(fixture_names)}
dump('hms-inputs.json', {'sha256': current, 'changed_from_prior': changed, 'added_from_prior': added})
dump('fixture-inputs.json', {'sha256': fixture, 'scope': 'Current HMS inputs plus unchanged original native source/binary files; bytecode caches excluded.'})
overlay = {key: dict(prior[key]) if isinstance(prior[key], dict) else prior[key] for key in ('all_overlay_inputs_sha256', 'harness_package_sources_sha256', 'shared_overlay_sources_sha256', 'patch_sha256')}
for key in ('all_overlay_inputs_sha256', 'harness_package_sources_sha256'):
    overlay[key][repair['copied_test']['path']] = repair['copied_test']['sha256']
overlay['inherited_overlay_inputs_sha256'] = prior['all_overlay_inputs_sha256']
overlay['additional_test_inputs_sha256'] = {repair['copied_test']['path']: repair['copied_test']['sha256']}
dump('patch-inputs.json', overlay)
artifacts = {}
for directory in sorted([*WORKTREE.glob('packages/*/*/lib'), *WORKTREE.glob('apps/*/lib')]):
    for path in sorted(directory.rglob('*')):
        if path.is_file():
            artifacts[str(path.relative_to(WORKTREE))] = digest(path)
assert artifacts
dump('built-artifacts-before.json', {'sha256': artifacts, 'scope': 'Existing worktree built lib artifacts pinned before this test. No new build; no claim these hashes were recorded at the earlier build time.'})
dump('reuse-check.json', {
    'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'harness_base_commit': prior['harness_base_commit'], 'worktree': str(WORKTREE),
    'prior_receipt': {'path': str((PRIOR / 'verification.json').relative_to(ROOT)), 'sha256': digest(PRIOR / 'verification.json')},
    'build_baseline_receipt': {'path': str((BUILD / 'verification.json').relative_to(ROOT)), 'sha256': digest(BUILD / 'verification.json')},
    'unchanged_overlay_files': len(prior['all_overlay_inputs_sha256']),
    'current_overlay_and_test_files': len(overlay['all_overlay_inputs_sha256']),
    'assertion_repair': repair,
    'changed_hms_files': changed, 'added_hms_files': added, 'fixture_files': len(fixture),
    'pinned_existing_built_files': len(artifacts),
    'reused_checks': {key: build['checks'][key] for key in ('build_artifacts', 'built_exports_smoke')},
    'qualification': 'Same a162 base and 38 exact inherited overlay input hashes; one additional copied test repairs an assertion without changing emitted artifact inputs. Reuse prior 7 artifact stages and built-export check; rerun 3 aggregate checks and focused lint. Existing built bytes are pinned before/after, not represented as a new build.'})
print(json.dumps({'fixture_files': len(fixture), 'hms_files': len(current), 'changed_hms_files': changed,
                  'built_files': len(artifacts), 'runtime_tests': root_receipt['tests']}))

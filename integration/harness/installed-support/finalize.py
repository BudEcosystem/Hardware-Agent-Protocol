"""Record the completed compatibility run without rerunning tests or devices."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORKTREE = Path('/home/bud/Desktop/bud/hms-harness-a1626788')
LIVE = Path('/home/bud/Desktop/bud/Bud-Meta-Harness')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name):
    return json.loads((HERE / name).read_text())


prior = load('prior-verification.json')
command = load('verification/focused-tests.command.json')
captures = load('verification/capture-and-source-check.json')
stability = load('verification/built-artifact-stability.json')
current = load('hms-inputs.json')['sha256']
fixture = load('fixture-inputs.json')['sha256']
root_runtime = load('root-runtime-verification.json')
assert command['exit_code'] == 0 and captures['passed'] and stability['passed']
log = (HERE / 'verification/focused-tests.log').read_text()
assert re.search(r'Test Files\s+4 passed \(4\)', log)
assert re.search(r'Tests\s+16 passed \(16\)', log)
duration = float(re.search(r'Duration\s+([0-9.]+)s', log)[1])
assert not (HERE / 'compact-diagnostics.jsonl').exists()
assert root_runtime['tests'] == 289 and not any(root_runtime[k] for k in ('failures', 'errors', 'skipped'))
for name, expected in current.items():
    assert digest(ROOT / name) == digest(HERE / 'runtime-fixture' / name) == expected
for name, expected in prior['all_overlay_inputs_sha256'].items():
    assert digest(WORKTREE / name) == expected
assert digest(HERE / 'harness.patch') == prior['patch_sha256']
assert digest(HERE / prior['native_binary']['path']) == prior['native_binary']['sha256']
assert digest(HERE / prior['native_build_receipt']['path']) == prior['native_build_receipt']['sha256']
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=WORKTREE, text=True).strip() == prior['harness_base_commit']
sdk = [json.loads(line) for line in (HERE / 'sdk-capture.jsonl').read_text().splitlines() if line]
assert len(sdk) == 2
sdk_results = [{'scenario': row['scenario'], 'plant': row['plant']} for row in sdk]
assert sdk_results == [
    {'scenario': 'work-replay-reopen', 'plant': {'value': 55, 'effects': 1}},
    {'scenario': 'work-cancel-is-not-hms-cancel', 'plant': {'value': 0, 'effects': 0}},
]
report = {
    'recorded_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'terminal_status': 'passed_single_current_HMS_run_prior_intermittent_refusal_unresolved',
    'harness_base_commit': prior['harness_base_commit'], 'isolated_worktree': str(WORKTREE),
    'live_checkout_head_at_finish': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=LIVE, text=True).strip(),
    'live_checkout_tracked_status_at_finish': subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=LIVE, text=True),
    'live_head_qualification': 'Later live commits are not covered. This lane changed no live or worktree production/package source.',
    'node': prior['node'], 'pnpm': prior['pnpm'], 'python': prior['python'], 'platform': prior['platform'],
    'hms_inputs_sha256': current, 'hms_inputs_snapshot_root': 'runtime-fixture',
    'hms_inputs_snapshot_scope': 'Current32 HMS inputs; four production files differ from a162 baseline.44 total fixture files include unchanged native evidence.',
    'runtime_fixture_inputs_sha256': fixture,
    'harness_package_sources_sha256': prior['harness_package_sources_sha256'],
    'all_overlay_inputs_sha256': prior['all_overlay_inputs_sha256'],
    'shared_overlay_snapshot_root': 'shared-overlay',
    'shared_overlay_sources_sha256': prior['shared_overlay_sources_sha256'],
    'native_source_inputs_sha256': prior['native_source_inputs_sha256'],
    'native_binary': prior['native_binary'], 'native_build_receipt': prior['native_build_receipt'],
    'patch_sha256': prior['patch_sha256'], 'lockfile_sha256': prior['lockfile_sha256'],
    'base_overlay': {
        'path': 'integration/harness/revalidation-a1626788/harness.patch', 'sha256': prior['patch_sha256'],
        'verification_path': 'integration/harness/revalidation-a1626788/verification.json',
        'verification_sha256': digest(HERE / 'prior-verification.json'),
    },
    'tests': {
        'command': command['argv'], 'environment': command['test_environment'],
        'runner': 'run_tests.py through run-command.py', 'passed': 16, 'files': 4, 'skipped': 0,
        'duration_seconds': duration, 'wrapper_elapsed_seconds': command['elapsed_seconds'],
        'runs_in_this_lane': 1, 'coverage': prior['tests']['coverage'],
        'not_covered': prior['tests']['not_covered'] + [
            'Every new unsupported-installation condition through native Harness calls; separate289-test HMS suite covers core denial paths.',
            'Multiple coexisting adapters or route-scoped scheduling.'],
        'sdk_case_plant_results': sdk_results, 'completed_native_operations': len(captures['decoded_native_receipts']),
        'operation_evidence': captures['decoded_native_receipts'],
    },
    'checks': {
        'current_HMS_suite': 'Separate289-test suite passed; exact receipt copied locally.',
        'capture_and_source_check': 'PASS six decoded completed C receipts, exact one-OP handoffs, post-restart QUERY and44 fixture/32 HMS/33 package/38 overlay hashes.',
        'build_artifacts': 'REUSED prior successful7 stages at identical Harness base and exact38 overlay inputs; no build in this lane.',
        'build_check': 'REUSED prior successful3 aggregate checks at unchanged TypeScript/build/dependency inputs; no aggregate rerun in this lane.',
        'focused_lint_and_built_exports': 'REUSED prior passing checks with unchanged package inputs; actual built SDK/profile tests rerun here.',
        'existing_built_file_stability': 'PASS14406 built lib files unchanged across this test run. Before/after pins are not historical build-time hashes.',
        'native_C_build': 'REUSED exact original binary and13 source hashes plus retained native build receipt; no C rebuild in this lane.',
    },
    'build_reuse': load('reuse-check.json'),
    'built_artifacts_manifest': {'path': 'built-artifacts-before.json', 'sha256': digest(HERE / 'built-artifacts-before.json'), 'files': stability['built_files_verified']},
    'unresolved_intermittent_failure': {
        'code': 'DEVICE_UNAVAILABLE', 'status': 'unresolved',
        'retained_run': '../revalidation-a1626788/failed-availability-run',
        'new_run_pass_does_not_explain_failure': True, 'no_failure_diagnostic_in_this_run': True,
    },
    'session_capture_sha256': digest(HERE / 'session-capture.json'),
    'sdk_capture_sha256': digest(HERE / 'sdk-capture.jsonl'),
    'compact_capture_sha256': digest(HERE / 'compact-capture.jsonl'),
    'root_runtime_verification': {
        'path': 'artifacts/verification/local-runtime.json', 'sha256': digest(HERE / 'root-runtime-verification.json'),
        'tests': 289, 'snapshot_path': 'root-runtime-verification.json',
        'scope': 'Separate current Python runtime suite; not16 additional Harness tests.'},
    'limitations': [
        'No physical device, target program, acquired controller, external provider or live model inference ran.',
        'Synthetic frame/effect evidence and keyless Session projections do not establish physical completion, per-agent authority or production persistence.',
        'The earlier intermittent DEVICE_UNAVAILABLE refusal remains unexplained. One additional passing run is not a reliability qualification.',
        'No new JavaScript artifact build, package install, release acceptance or shipped-profile snapshot gate is claimed.',
        'Current-HMS compatibility is scoped to pinned a162 overlay and these scenarios; later live Harness commits remain unvalidated.',
    ],
}
assert digest(ROOT / report['root_runtime_verification']['path']) == report['root_runtime_verification']['sha256']
report['receipts_sha256'] = {
    str(path.relative_to(HERE)): digest(path)
    for path in sorted(HERE.rglob('*'))
    if path.is_file() and path.name != 'verification.json' and '__pycache__' not in path.parts
    and path.relative_to(HERE).parts[0] not in {'runtime-fixture', 'packages', 'shared-overlay'}
}
(HERE / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': True, 'tests': 16, 'fixture_files': 44,
                  'receipt': str(HERE / 'verification.json'), 'sha256': digest(HERE / 'verification.json')}))

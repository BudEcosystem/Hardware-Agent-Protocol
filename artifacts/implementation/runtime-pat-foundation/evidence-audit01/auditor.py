#!/usr/bin/env python3
"""Check retained endpoint/runtime evidence against current inputs; run no devices/tests."""
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'artifacts/verification'
checks = 0
unique = set()
receipts = []


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path, expected):
    global checks
    path = path.resolve()
    if digest(path) != expected:
        raise ValueError('Retained evidence mismatch: ' + str(path))
    checks += 1
    unique.add(path)


def read(path):
    receipts.append({'path': str(path.relative_to(ROOT)), 'sha256': digest(path)})
    return json.loads(path.read_text())


def records(items, base=ROOT):
    for item in items:
        verify(base / item['path'], item['sha256'])


def main():
    current = read(DEST / 'local-runtime-current.json')
    if current['status'] != 'passed' or current['current_pass'] is not True:
        raise ValueError('Latest runtime attempt is not a pass; last-success receipt is historical')
    verify(ROOT / current['receipt']['path'], current['receipt']['sha256'])
    verify(DEST / 'local-runtime.json', current['receipt']['sha256'])
    runtime = read(DEST / 'local-runtime.json')
    if (runtime['failures'] or runtime['errors'] or runtime['skipped'] or runtime['expected_failures'] or
            not runtime['passed'] or not runtime['inputs_stable'] or not runtime['compiler_identity_stable']):
        raise ValueError('Local runtime suite did not fully pass')
    records(runtime['files'])
    records(runtime['outputs'])
    for item in runtime['files_before'] + runtime['files_after']:
        verify(ROOT / item['snapshot_path'], item['sha256'])
    checkpoint_523 = read(DEST / 'runtime-523-checkpoint/index.json')
    records(checkpoint_523['files'])
    records(checkpoint_523['references'])
    prior_523 = read(ROOT / checkpoint_523['references'][0]['path'])
    if (prior_523['tests'], prior_523['failures'], prior_523['errors'], prior_523['skipped']) != (523, 0, 0, 0):
        raise ValueError('Historical523 checkpoint is not the passing baseline')
    if not prior_523['passed'] or not prior_523['inputs_stable'] or not prior_523['compiler_identity_stable']:
        raise ValueError('Historical523 checkpoint input proof differs')
    records(prior_523['outputs'])
    for item in prior_523['files_before'] + prior_523['files_after']:
        verify(ROOT / item['snapshot_path'], item['sha256'])
    for item in checkpoint_523['references'][1:]:
        records(read(ROOT / item['path'])['files'])
    checkpoint_586 = read(DEST / 'runtime-586-checkpoint/index.json')
    records(checkpoint_586['files'])
    records(checkpoint_586['references'])
    prior_586 = read(ROOT / checkpoint_586['references'][0]['path'])
    if (prior_586['tests'], prior_586['failures'], prior_586['errors'], prior_586['skipped']) != (586, 0, 0, 0):
        raise ValueError('Historical586 checkpoint is not the passing baseline')
    if not prior_586['passed'] or not prior_586['inputs_stable'] or not prior_586['compiler_identity_stable']:
        raise ValueError('Historical586 checkpoint input proof differs')
    records(prior_586['outputs'])
    for item in prior_586['files_before'] + prior_586['files_after']:
        verify(ROOT / item['snapshot_path'], item['sha256'])
    checkpoint_643 = read(DEST / 'runtime-643-checkpoint/index.json')
    records(checkpoint_643['files'])
    records(checkpoint_643['references'])
    prior_643 = read(ROOT / checkpoint_643['references'][0]['path'])
    if (prior_643['tests'], prior_643['failures'], prior_643['errors'], prior_643['skipped']) != (643, 0, 0, 0):
        raise ValueError('Historical643 checkpoint is not the passing baseline')
    if not prior_643['passed'] or not prior_643['inputs_stable'] or not prior_643['compiler_identity_stable']:
        raise ValueError('Historical643 checkpoint input proof differs')
    records(prior_643['outputs'])
    for item in prior_643['files_before'] + prior_643['files_after']:
        verify(ROOT / item['snapshot_path'], item['sha256'])
    checkpoint_696 = read(DEST / 'runtime-696-checkpoint/index.json')
    records(checkpoint_696['files'])
    records(checkpoint_696['references'])
    prior_696 = read(ROOT / checkpoint_696['references'][0]['path'])
    if (prior_696['tests'], prior_696['failures'], prior_696['errors'], prior_696['skipped']) != (696, 0, 0, 0):
        raise ValueError('Historical696 checkpoint is not the passing baseline')
    if (not prior_696['passed'] or not prior_696['inputs_stable'] or not prior_696['compiler_identity_stable'] or
            prior_696['expected_failures'] or prior_696['unexpected_successes'] or
            len(prior_696['files_before']) != 139 or len(prior_696['files_after']) != 139):
        raise ValueError('Historical696 checkpoint input proof differs')
    # Its Runtime/CLI sources predate public I/O mounting. Verify the immutable
    # snapshots, while the current runtime gate above still checks live files.
    records(prior_696['outputs'])
    for item in prior_696['files_before'] + prior_696['files_after']:
        verify(ROOT / item['snapshot_path'], item['sha256'])
    checkpoint_748 = read(DEST / 'runtime-748-checkpoint/index.json')
    records(checkpoint_748['files'])
    records(checkpoint_748['references'])
    prior_748 = read(ROOT / checkpoint_748['references'][0]['path'])
    if (prior_748['tests'], prior_748['failures'], prior_748['errors'], prior_748['skipped']) != (748, 0, 0, 0):
        raise ValueError('Historical748 checkpoint is not the passing baseline')
    if (not prior_748['passed'] or not prior_748['inputs_stable'] or not prior_748['compiler_identity_stable'] or
            prior_748['expected_failures'] or prior_748['unexpected_successes'] or
            len(prior_748['files_before']) != 151 or len(prior_748['files_after']) != 151):
        raise ValueError('Historical748 checkpoint input proof differs')
    # The public PAT foundation changes selected source identities. Historical
    # I/O recovery remains tied to its exact 748-test source snapshots; today's
    # complete runtime is independently checked against current files above.
    records(prior_748['outputs'])
    for item in prior_748['files_before'] + prior_748['files_after']:
        verify(ROOT / item['snapshot_path'], item['sha256'])
    runtime_369 = read(DEST / 'runtime-369-snapshot/index.json')
    records(runtime_369['files'])
    archived_369 = {item['original_path']: item for item in runtime_369['files']}
    old_369_receipt = read(ROOT / archived_369['artifacts/verification/local-runtime.json']['path'])
    if (old_369_receipt['tests'], old_369_receipt['failures'], old_369_receipt['errors'], old_369_receipt['skipped']) != (369, 0, 0, 0):
        raise ValueError('369-test baseline receipt is not a passing run')
    for item in old_369_receipt['files'] + old_369_receipt['outputs']:
        archived = archived_369.get(item['path'])
        if archived is None or archived['sha256'] != item['sha256']:
            raise ValueError('Missing or mismatched 369-test baseline source: ' + item['path'])
        verify(ROOT / archived['path'], item['sha256'])
    runtime_280_base = DEST / 'runtime-280-snapshot'
    runtime_280 = read(runtime_280_base / 'index.json')
    records(runtime_280['files'])
    archived_280 = {item['original_path']: item for item in runtime_280['files']}

    def historical_280_records(items):
        # Explicitly scope pre-installation-check evidence to its exact source
        # archive. Unchanged non-Python assets still have their original paths.
        for item in items:
            archived = archived_280.get(item['path'])
            if archived is None:
                if item['path'].startswith(('hms/', 'tests/', 'scripts/')):
                    raise ValueError('Missing historical source: ' + item['path'])
                records([item])
            else:
                if archived['sha256'] != item['sha256']:
                    raise ValueError('Historical source identity differs: ' + item['path'])
                verify(ROOT / archived['path'], item['sha256'])
    runtime_289 = read(DEST / 'runtime-289-snapshot/index.json')
    records(runtime_289['files'])
    archived_289 = {item['original_path']: item for item in runtime_289['files']}
    runtime_315 = read(DEST / 'runtime-315-snapshot/index.json')
    records(runtime_315['files'])
    archived_315 = {item['original_path']: item for item in runtime_315['files']}

    def historical_315_records(items):
        for item in items:
            archived = archived_315.get(item['path'])
            if archived is None:
                if item['path'].startswith(('hms/', 'tests/', 'scripts/', 'schemas/')):
                    raise ValueError('Missing 315-test source: ' + item['path'])
                records([item])
            else:
                if archived['sha256'] != item['sha256']:
                    raise ValueError('315-test source identity differs: ' + item['path'])
                verify(ROOT / archived['path'], item['sha256'])

    def historical_289_records(items):
        for item in items:
            archived = archived_289.get(item['path'])
            if archived is None:
                if item['path'].startswith(('hms/', 'tests/', 'scripts/')):
                    raise ValueError('Missing 289-test source: ' + item['path'])
                records([item])
            else:
                if archived['sha256'] != item['sha256']:
                    raise ValueError('289-test source identity differs: ' + item['path'])
                verify(ROOT / archived['path'], item['sha256'])
    native = read(DEST / 'endpoint-native.json')
    integration = read(DEST / 'endpoint-integration.json')
    scenarios = read(DEST / 'endpoint-scenarios.json')
    for value in (native, integration, scenarios):
        if not value['passed']:
            raise ValueError('Endpoint check did not pass')
        records(value['files'])
        records(value['outputs'])
    records([integration['executable'], integration['native_build_receipt']])
    avr = read(DEST / 'endpoint-avr.json')
    if not avr['passed_compile_link'] or not avr['passed_static_reservation_scenario']:
        raise ValueError('AVR compile/link or declared reservation scenario failed')
    if avr['target_runtime_fit_demonstrated']:
        raise ValueError('Unexpected target-execution claim')
    for path, expected in avr['source_hashes'].items():
        verify(ROOT / path, expected)
    for path, expected in avr['artifact_hashes'].items():
        verify(ROOT / path, expected)
    records([avr['toolchain_archive'], avr['toolchain_provenance_manifest']])
    review_base = DEST / 'endpoint-code-review'
    review = read(review_base / 'endpoint-code-review.json')
    if not review['passed'] or review['outstanding_concrete_findings']:
        raise ValueError('Independent review has unresolved concrete findings')
    for path, expected in review['retained_artifacts'].items():
        verify(review_base / path, expected)
    for path, expected in json.loads((review_base / 'source-pins.json').read_text()).items():
        verify(ROOT / path, expected)
        verify(review_base / 'snapshot' / path, expected)
    host_review_base = DEST / 'compact-host-review'
    host_review = read(host_review_base / 'review.json')
    if not host_review['passed'] or host_review['outstanding_confirmed_findings']:
        raise ValueError('Compact host review has unresolved confirmed findings')
    records(host_review['retained_artifacts'])
    for item in json.loads((host_review_base / 'source-pins.json').read_text()):
        historical_280_records([item])
        verify(ROOT / item['snapshot'], item['sha256'])
    design = read(DEST / 'endpoint-design-snapshot/index.json')
    records(design['files'])
    historical_base = DEST / 'endpoint-host-before'
    historical = read(historical_base / 'index.json')
    records(historical['files'])
    runtime_278_base = DEST / 'runtime-278-snapshot'
    runtime_278 = read(runtime_278_base / 'index.json')
    records(runtime_278['files'])
    harness_base = ROOT / 'integration/harness'
    harness = read(harness_base / 'verification.json')
    for path, expected in harness['hms_inputs_sha256'].items():
        verify(historical_base / path, expected)
    for path, expected in harness['harness_package_sources_sha256'].items():
        prefix = 'packages/experimental/'
        if not path.startswith(prefix):
            raise ValueError('Unexpected Harness overlay source path')
        verify(harness_base / 'packages' / path[len(prefix):], expected)
    for path, expected in harness['receipts_sha256'].items():
        verify(harness_base / path, expected)
    verify(harness_base / 'harness.patch', harness['patch_sha256'])
    verify(harness_base / 'session-capture.json', harness['session_capture_sha256'])
    records([harness['root_runtime_verification']], base=historical_base)
    current_base = harness_base / 'revalidation-335a82eb'
    current_harness = read(current_base / 'verification.json')
    for path, expected in current_harness['hms_inputs_sha256'].items():
        historical_280_records([{'path': path, 'sha256': expected}])
        verify(current_base / current_harness['hms_inputs_snapshot_root'] / path, expected)
    for path, expected in current_harness['harness_package_sources_sha256'].items():
        prefix = 'packages/experimental/'
        if not path.startswith(prefix):
            raise ValueError('Unexpected current Harness overlay source path')
        verify(current_base / 'packages' / path[len(prefix):], expected)
    for path, expected in current_harness['receipts_sha256'].items():
        verify(current_base / path, expected)
    verify(current_base / 'harness.patch', current_harness['patch_sha256'])
    records([current_harness['root_runtime_verification']], base=runtime_278_base)
    mcp = read(DEST / 'mcp-sdk-compact-host.json')
    if mcp['status'] != 'passed':
        raise ValueError('Current-host MCP SDK check failed')
    for path, expected in mcp['inputsSha256'].items():
        historical_280_records([{'path': path, 'sha256': expected}])
    compact_mcp = read(DEST / 'compact-mcp/verification.json')
    if not compact_mcp['passed'] or compact_mcp['exitCode'] != 0:
        raise ValueError('Compact MCP integration failed')
    historical_280_records(compact_mcp['inputs'])
    for key in ('inputSnapshots', 'outputs'):
        records(compact_mcp[key])
    for distribution in compact_mcp['testerDependencies']['distributions']:
        records(distribution['metadata'])
    records(compact_mcp['testerDependencies']['sdkPythonFiles'])
    compact_base = harness_base / 'compact-endpoint'
    compact_harness = read(compact_base / 'verification.json')
    for path, expected in compact_harness['hms_inputs_sha256'].items():
        historical_280_records([{'path': path, 'sha256': expected}])
        verify(compact_base / compact_harness['hms_inputs_snapshot_root'] / path, expected)
    for path, expected in compact_harness['native_source_inputs_sha256'].items():
        verify(ROOT / path, expected)
    for path, expected in compact_harness['harness_test_sources_sha256'].items():
        prefix = 'packages/experimental/'
        if not path.startswith(prefix):
            raise ValueError('Unexpected compact Harness test source path')
        verify(compact_base / compact_harness['harness_test_sources_snapshot_root'] / path[len(prefix):], expected)
    for path, expected in compact_harness['receipts_sha256'].items():
        verify(compact_base / path, expected)
    verify(compact_base / compact_harness['patch_path'], compact_harness['patch_sha256'])
    records([compact_harness['native_binary'],compact_harness['native_build_receipt']], base=compact_base)
    records([compact_harness['base_overlay']])
    verify(ROOT / compact_harness['base_overlay']['verification_path'], compact_harness['base_overlay']['verification_sha256'])
    compact_review = read(compact_base / 'independent-review.json')
    compact_review_archive = read(compact_base / 'review-inputs/index.json')
    verify(ROOT / compact_review_archive['review_path'], compact_review_archive['review_sha256'])
    records(compact_review_archive['files'])
    review_archived = {item['original_path']: item for item in compact_review_archive['files']}
    for item in compact_review['inputs']:
        archived = review_archived.get(item['path'])
        if archived:
            if archived['sha256'] != item['sha256']:
                raise ValueError('Reviewed Harness source archive identity differs')
            verify(ROOT / archived['path'], item['sha256'])
        else:
            records([item])
    records(compact_review['verifiedArtifacts'])
    a162_base = harness_base / 'revalidation-a1626788'
    a162 = read(a162_base / 'verification.json')
    for path, expected in a162['hms_inputs_sha256'].items():
        historical_280_records([{'path': path, 'sha256': expected}])
        verify(a162_base / a162['hms_inputs_snapshot_root'] / path, expected)
    for path, expected in a162['runtime_fixture_inputs_sha256'].items():
        verify(a162_base / a162['hms_inputs_snapshot_root'] / path, expected)
    for path, expected in a162['harness_package_sources_sha256'].items():
        prefix = 'packages/experimental/'
        if not path.startswith(prefix):
            raise ValueError('Unexpected a162 overlay source path')
        verify(a162_base / 'packages' / path[len(prefix):], expected)
    for path, expected in a162['shared_overlay_sources_sha256'].items():
        verify(a162_base / a162['shared_overlay_snapshot_root'] / path, expected)
    for path, expected in a162['receipts_sha256'].items():
        verify(a162_base / path, expected)
    for path, expected in a162['native_source_inputs_sha256'].items():
        verify(ROOT / path, expected)
    verify(a162_base / 'harness.patch', a162['patch_sha256'])
    records([a162['native_binary'], a162['native_build_receipt']], base=a162_base)
    records(a162['prior_overlays'] + [a162['source_drift_review']])
    records([a162['root_runtime_verification']], base=runtime_280_base)
    boot = read(DEST / 'boot-epoch.json')
    if not boot['passed'] or boot['avr']['executed'] or boot['avr']['linked_firmware']:
        raise ValueError('Unexpected boot allocator build/qualification claim')
    records(boot['files']); records(boot['outputs']); records([boot['avr']['toolchain_archive']])
    for path, item in boot['avr']['toolchain_files'].items():
        verify(Path(path), item['sha256'])
    boot_review = read(DEST / 'boot-epoch-review/review.json')
    if not boot_review['passed'] or boot_review['sourceReview']['blockingFindings']:
        raise ValueError('Boot allocator review failed')
    for key in ('inputs','sourceSnapshots','outputs'):
        records(boot_review[key])
    eeprom = read(DEST / 'avr-eeprom/review.json')
    if not eeprom['passed'] or eeprom['avr']['executed']:
        raise ValueError('Unexpected AVR EEPROM result or execution claim')
    records(eeprom['files']); records(eeprom['outputs'])
    records([eeprom['avr']['toolchain_archive'], eeprom['host_compiler']])
    for path, item in eeprom['avr']['archive_verified_files'].items():
        verify(Path(path), item['sha256'])
    eeprom_review = read(DEST / 'avr-eeprom-review/review.json')
    if not eeprom_review['passed'] or eeprom_review['independentNativeResults']['target_executed']:
        raise ValueError('Unexpected independent EEPROM review result')
    for key in ('inputs', 'sourceSnapshots', 'outputs'):
        records(eeprom_review[key])
    records([eeprom_review['authorReceipt'], eeprom_review['hostCompiler'], eeprom_review['objdump']])
    uart = read(DEST / 'avr-uart/review.json')
    if not uart['passed'] or uart['avr']['executed']:
        raise ValueError('UART producer scope or result mismatch')
    records(uart['files']); records(uart['outputs'])
    records([uart['avr']['toolchain_archive'], uart['host_compiler']])
    for path, item in uart['avr']['archive_verified_files'].items():
        verify(Path(path), item['sha256'])
    uart_review = read(DEST / 'avr-uart-review/review.json')
    if (not uart_review['passed'] or uart_review['blocking_findings'] or
            uart_review['target_executed'] or uart_review['emulator_executed']):
        raise ValueError('UART independent review scope or result mismatch')
    records(uart_review['files']); records(uart_review['inputs'])
    records([uart_review['producer_receipt'], uart_review['independent_probe_receipt']])
    route_design = read(DEST / 'multi-adapter-design-review/review.json')
    route_clock = read(DEST / 'multi-adapter-design-review/monotonic-review.json')
    historical_289_records(route_design['inputs'])
    records(route_design['sourceSnapshots']); records(route_design['outputs'])
    records(route_clock['inputs']); records(route_clock['outputs'])
    startup_debug = read(DEST / 'multi-adapter-startup-debug/index.json')
    records(startup_debug['files'])
    multi_review = read(DEST / 'multi-adapter-code-review/review.json')
    if multi_review['status'] != 'complete' or any(not item['passed'] for item in multi_review['tests']):
        raise ValueError('Multi-adapter independent review incomplete')
    records(multi_review['integrity_files']); records([multi_review['native_fixture']])
    multi_pins = read(ROOT / multi_review['source_set']['manifest'])
    if len(multi_pins) != multi_review['source_set']['count']:
        raise ValueError('Independent multi-adapter source inventory differs')
    # This review describes the frozen pre-procedure runtime. Its supporting
    # no-retry CLI test predates the explicit pre-admission retry integration.
    for item in multi_pins:
        if item['path'] == 'tests/test_multi_cli.py':
            verify(DEST / 'runtime-315-freshness' / item['path'], item['sha256'])
        else:
            historical_315_records([item])
    records(multi_pins, ROOT / multi_review['source_set']['retained_copies'])
    retry_review = read(DEST / 'multi-adapter-code-review/cli-retry-supplement/review.json')
    if retry_review['status'] != 'complete' or retry_review['blocking_findings']:
        raise ValueError('Retry boundary supplement incomplete')
    historical_315_records(retry_review['current_inputs']); records(retry_review['integrity_files'])
    records([retry_review['original_review']])
    failed_runtime = read(DEST / 'runtime-314-failed/index.json')
    records(failed_runtime['files'])
    mcp_race = read(DEST / 'runtime-314-mcp-race/index.json')
    records(mcp_race['files'])
    freshness_run = read(DEST / 'runtime-315-freshness/index.json')
    records(freshness_run['files'])
    procedure_catalog_run = read(DEST / 'runtime-369-catalog-failed/index.json')
    records(procedure_catalog_run['files'])
    routing_baseline = read(DEST / 'adapter-routing-review/review.json')
    if not routing_baseline['passed']:
        raise ValueError('Routing baseline probes were not verified')
    historical_280_records(routing_baseline['inputs'])
    records(routing_baseline['sourceSnapshots']); records(routing_baseline['outputs'])
    support_review = read(DEST / 'installed-support-review/review.json')
    if not support_review['passed'] or support_review['outstandingConfirmedFindings']:
        raise ValueError('Installed support review failed')
    historical_289_records(support_review['inputs'])
    records(support_review['sourceSnapshots']); records(support_review['outputs'])
    support_base = harness_base / 'installed-support'
    support_harness = read(support_base / 'verification.json')
    if support_harness['tests']['passed'] != 16 or support_harness['tests']['skipped']:
        raise ValueError('Current installed-support Harness tests did not pass')
    for path, expected in support_harness['hms_inputs_sha256'].items():
        historical_289_records([{'path':path,'sha256':expected}])
        verify(support_base / support_harness['hms_inputs_snapshot_root'] / path, expected)
    for path, expected in support_harness['runtime_fixture_inputs_sha256'].items():
        verify(support_base / support_harness['hms_inputs_snapshot_root'] / path, expected)
    for path, expected in support_harness['harness_package_sources_sha256'].items():
        prefix = 'packages/experimental/'
        if not path.startswith(prefix):
            raise ValueError('Unexpected installed-support Harness package path')
        verify(support_base / 'packages' / path[len(prefix):], expected)
    for path, expected in support_harness['shared_overlay_sources_sha256'].items():
        verify(support_base / support_harness['shared_overlay_snapshot_root'] / path, expected)
    for path, expected in support_harness['receipts_sha256'].items():
        verify(support_base / path, expected)
    for path, expected in support_harness['native_source_inputs_sha256'].items():
        verify(ROOT / path, expected)
    records([support_harness['native_binary'], support_harness['native_build_receipt'],
             support_harness['built_artifacts_manifest']], base=support_base)
    records([support_harness['base_overlay']])
    historical_289_records([support_harness['root_runtime_verification']])
    verify(ROOT / support_harness['base_overlay']['verification_path'],
           support_harness['base_overlay']['verification_sha256'])
    verify(support_base / support_harness['root_runtime_verification']['snapshot_path'],
           support_harness['root_runtime_verification']['sha256'])
    worktree = Path(support_harness['isolated_worktree'])
    for path, expected in support_harness['all_overlay_inputs_sha256'].items():
        verify(worktree / path, expected)
    built = read(support_base / support_harness['built_artifacts_manifest']['path'])
    if len(built['sha256']) != support_harness['built_artifacts_manifest']['files']:
        raise ValueError('Built artifact count differs')
    for path, expected in built['sha256'].items():
        verify(worktree / path, expected)
    multi_base = harness_base / 'multi-adapter'
    multi_harness = read(multi_base / 'verification.json')
    if multi_harness['tests']['passed'] != 16 or multi_harness['tests']['skipped']:
        raise ValueError('Historical 315-test Harness tests did not pass')
    for path, expected in multi_harness['hms_inputs_sha256'].items():
        historical_315_records([{'path':path,'sha256':expected}])
        verify(multi_base / multi_harness['hms_inputs_snapshot_root'] / path, expected)
    for path, expected in multi_harness['runtime_fixture_inputs_sha256'].items():
        verify(multi_base / multi_harness['hms_inputs_snapshot_root'] / path, expected)
    for path, expected in multi_harness['harness_package_sources_sha256'].items():
        prefix = 'packages/experimental/'
        if not path.startswith(prefix):
            raise ValueError('Unexpected multi-adapter Harness package path')
        verify(multi_base / 'packages' / path[len(prefix):], expected)
    for path, expected in multi_harness['shared_overlay_sources_sha256'].items():
        verify(multi_base / multi_harness['shared_overlay_snapshot_root'] / path, expected)
    for path, expected in multi_harness['receipts_sha256'].items():
        verify(multi_base / path, expected)
    for path, expected in multi_harness['native_source_inputs_sha256'].items():
        verify(ROOT / path, expected)
    records([multi_harness['native_binary'], multi_harness['native_build_receipt'],
             multi_harness['built_artifacts_manifest']], base=multi_base)
    records([multi_harness['base_overlay']])
    historical_315_records([multi_harness['root_runtime_verification']])
    verify(ROOT / multi_harness['base_overlay']['verification_path'],
           multi_harness['base_overlay']['verification_sha256'])
    verify(multi_base / multi_harness['root_runtime_verification']['snapshot_path'],
           multi_harness['root_runtime_verification']['sha256'])
    worktree = Path(multi_harness['isolated_worktree'])
    for path, expected in multi_harness['all_overlay_inputs_sha256'].items():
        verify(worktree / path, expected)
    multi_built = read(multi_base / multi_harness['built_artifacts_manifest']['path'])
    if len(multi_built['sha256']) != multi_harness['built_artifacts_manifest']['files']:
        raise ValueError('Built artifact count differs')
    for path, expected in multi_built['sha256'].items():
        verify(worktree / path, expected)
    clock = read(DEST / 'avr-clock/review.json')
    if not clock['passed']:
        raise ValueError('AVR clock producer checks did not pass')
    records(clock['files']); records(clock['outputs'])
    clock_review = read(DEST / 'avr-clock-review/review.json')
    verify(DEST / 'avr-clock/review.json', clock_review['producer_receipt_sha256'])
    records(clock_review['files'])
    clock_snapshots = read(DEST / 'avr-clock-review/input-snapshots.json')
    for item in clock_snapshots['files']:
        verify(ROOT / item['snapshot_path'], item['sha256'])
    clock_results = read(DEST / 'avr-clock-review/results.json')
    if (not clock_results['passed'] or any(clock_results[key] for key in
            ('target_executed', 'emulator_executed', 'hardware_contacted', 'acquired_research_code_executed'))):
        raise ValueError('Clock independent review result/scope mismatch')
    records(clock_results['inputs'] + [clock_results['command_log']])
    records([item['binary'] for item in clock_results['baselines']])
    for item in clock_results['source_mutations']:
        if not item['rejected']:
            raise ValueError('Clock source mutation was not rejected')
        records([item['source'], item['binary']])
    records([clock['avr']['toolchain_archive']])
    if clock['avr']['executed']:
        raise ValueError('Unexpected AVR clock target execution claim')
    procedure_design_base = DEST / 'procedure-design-review'
    procedure_design = read(procedure_design_base / 'artifact-manifest.json')
    records(procedure_design['files'], base=procedure_design_base)
    glue_base = DEST / 'procedure-glue-review'
    glue = read(glue_base / 'verification.json')
    if glue['failures'] or glue['errors'] or glue['skipped'] or glue['tests'] != 20:
        raise ValueError('Procedure glue checks did not fully pass')
    glue_manifest = read(glue_base / 'artifact-manifest.json')
    records(glue_manifest['files'], base=glue_base)
    glue_sources = read(glue_base / glue['sourcePins'])
    records(glue_sources['files'])
    for item in glue_sources['files']:
        # This independent review predates the later freshness/effect-boundary
        # changes. Its exact executable inputs are the frozen369 baseline; the
        # current whole-suite run separately executes its tests on current code.
        if item['sourcePath'].startswith(('hms/', 'tests/', 'scripts/', 'schemas/')):
            archived = archived_369.get(item['sourcePath'])
            if archived is None or archived['sha256'] != item['sha256']:
                raise ValueError('Missing historical procedure-glue input')
            verify(ROOT / archived['path'], item['sha256'])
    integration_before = read(DEST / 'pat-service-current-integration-before/index.json')
    records(integration_before['files'])
    integration_before_paths = {item['originalPath']: item for item in integration_before['files']}
    corpus = read(DEST / 'corpus-authorizer-audit.json')
    authorizer_integration = read(DEST / 'corpus-authorizer-integration.json')
    if not authorizer_integration['passed'] or corpus['source_records'] != 323:
        raise ValueError('Authorizer corpus integration differs')
    records(authorizer_integration['files'])
    authorizer_index = read(ROOT / 'research/host-contract/authorizer-followup/index.json')
    records(authorizer_index['files'])
    lrll_integration = read(DEST / 'corpus-lrll-integration.json')
    for item in lrll_integration['files']:
        # The prior aggregate auditor is historical after the authorizer lane.
        archived = integration_before_paths.get(item['path'])
        if archived is not None:
            if archived['sha256'] != item['sha256']:
                raise ValueError('Historical LRLL integration input differs')
            verify(ROOT / archived['path'], item['sha256'])
        else:
            records([item])
    lrll_before = read(DEST / 'corpus-lrll-before/index.json')
    records(lrll_before['files'])
    corpus_handoff = read(DEST / 'corpus-pat-integration-snapshot/index.json')
    records(corpus_handoff['files'])
    harness_design = read(ROOT / 'integration/harness/procedure-design/review.json')
    if harness_design['harness_execution'] or harness_design['builds_or_tests_run']:
        raise ValueError('Unexpected procedure design review execution claim')
    records(harness_design['outputs'])
    pat_design_base = DEST / 'pat-design-review'
    pat_design_manifest = read(pat_design_base / 'artifact-manifest.json')
    records(pat_design_manifest['files'], base=pat_design_base)
    pat_review_base = DEST / 'pat-catalog-review'
    pat_review = read(pat_review_base / 'review.json')
    if (pat_review['tests'], pat_review['failures'], pat_review['errors'], pat_review['skips']) != (20, 0, 0, 0):
        raise ValueError('PAT catalog independent checks did not fully pass')
    if not pat_review['sourceUnchangedAcrossFinalRun']:
        raise ValueError('PAT catalog independent inputs changed')
    for path, item in pat_review['outputs'].items():
        verify(pat_review_base / path, item['sha256'])
    for path, item in pat_review['projectSourceClosure'].items():
        # The review's final-run copies predate the effect-veto/freshness patch.
        # Preserve that scope; current whole-suite results cover current inputs.
        verify(pat_review_base / pat_review['finalAttempt'] / 'inputs' / path, item['sha256'])
    pat_run = read(pat_review_base / pat_review['finalAttempt'] / 'run.json')
    if len(pat_run['trace']['crashCases']) != 6:
        raise ValueError('Missing PAT catalog crash cases')
    for case in pat_run['trace']['crashCases']:
        inside = case['phase'].endswith('_inside')
        if (case['reopenedIntegrity'] != 'ok' or case['exitCode'] != (79 if inside else 80) or
                (inside and not (case['dirtyRollbackObserved'] and case['partialBusinessTransitionAbsent'])) or
                (not inside and not case['committedStateRetained'])):
            raise ValueError('PAT catalog crash trace failed')
    failed_424 = read(DEST / 'runtime-424-failed/index.json')
    records(failed_424['files'])
    retention_base = DEST / 'runtime-459-retention'
    retention = read(retention_base / 'result.json')
    if not retention['passed_retention_check'] or retention['full_suite_passed']:
        raise ValueError('Failed459 retention evidence scope differs')
    records(retention['files'])
    verify(retention_base / 'check.py', retention['checker_sha256'])
    verify(retention_base / 'current-pointer.json', retention['pointer_sha256'])
    runtime_522_before = read(DEST / 'runtime-522-integration-before/index.json')
    records(runtime_522_before['files'])
    observer_diagnosis_base = DEST / 'runtime-522-observer-diagnosis'
    observer_diagnosis = read(observer_diagnosis_base / 'review.json')
    retention_522 = observer_diagnosis['retentionValidation']
    if (observer_diagnosis['summary']['status'] != 'failed' or
            observer_diagnosis['summary']['tests'] != 522 or
            observer_diagnosis['summary']['errors'] != 2 or
            observer_diagnosis['summary']['failures'] != 0 or
            retention_522['beforeSnapshots'] != 112 or retention_522['afterSnapshots'] != 112 or
            retention_522['outputs'] != 25 or
            not all(retention_522[field] is True for field in (
                'allRecordedHashesVerified', 'compilerIdentityBytesEqual',
                'compilerIdentityStableReceiptFlag', 'currentPointerCopied',
                'sourceHashSetsEqual', 'sourceStableReceiptFlags'))):
        raise ValueError('Failed522 observer diagnosis retention scope differs')
    for path, item in observer_diagnosis['outputPins'].items():
        verify(observer_diagnosis_base / path, item['sha256'])
    observer_diagnosis_inputs = read(observer_diagnosis_base / observer_diagnosis['inputPinsFile'])
    for path, item in observer_diagnosis_inputs.items():
        verify(ROOT / path, item['sha256'])
    availability_base = DEST / 'runtime-availability-diagnosis'
    availability = read(availability_base / 'review.json')
    if availability['productionEdits'] or availability['testExecutions']:
        raise ValueError('Unexpected availability diagnosis execution or change')
    for path, item in availability['outputs'].items():
        verify(availability_base / path, item['sha256'])
    availability_inputs = read(availability_base / 'input-pins.json')
    for item in availability_inputs:
        verify(availability_base / item['retainedPath'], item['sha256'])
        verify(ROOT / item['origin'], item['sha256'])
    observer_handoff = read(DEST / 'endpoint-cli-observer-integration.json')
    records(observer_handoff['files'])
    observer_base = DEST / 'endpoint-cli-observer'
    observer = read(observer_base / 'index.json')
    if observer['exitCode'] or observer['testCount'] != 5 or observer['sourcesChangedDuringRun']:
        raise ValueError('Observer correction checks failed or changed inputs')
    records(observer['sources'], base=observer_base / 'after/sources')
    verify(observer_base / 'after/tests.log', observer['logSha256'])
    verify(observer_base / 'after/report.json', observer['reportSha256'])
    shared_observer_base = DEST / 'shared-sqlite-observer'
    shared_observer = read(shared_observer_base / 'index.json')
    if (shared_observer['passed'] or shared_observer['controlled'] != {
            'tests': 5, 'failures': 0, 'errors': 0, 'skipped': 0, 'passed': True, 'inputsStable': True} or
            shared_observer['transport'] != {
            'tests': 9, 'failures': 1, 'errors': 0, 'skipped': 0, 'passed': False, 'inputsStable': True} or
            shared_observer['actualTransportObservers']['errors'] != 0):
        raise ValueError('Historical shared-observer focused scope differs')
    records(shared_observer['files'])
    extraction = read(shared_observer_base / 'after/helper-extraction.json')
    unchanged_case = read(shared_observer_base / 'after/operational-class-extraction.json')
    if not extraction['readonlyRowsAstIdentical'] or not unchanged_case['compactCliRestartTestsAstIdentical']:
        raise ValueError('Shared observer extraction changed existing behavior')
    cli_capture_base = DEST / 'endpoint-cli-failure-capture'
    cli_capture = read(cli_capture_base / 'review.json')
    for path, item in cli_capture['outputs'].items():
        verify(cli_capture_base / path, item['sha256'])
    cli_capture_external = read(cli_capture_base / cli_capture['externalEvidencePinsFile'])
    for path, item in cli_capture_external.items():
        verify(ROOT / path, item['sha256'])
    cli_capture_checks = read(cli_capture_base / 'selfcheck.json')
    cli_capture_actual = read(cli_capture_base / 'actual-runtime.json')
    cli_capture_assertions = read(cli_capture_base / 'assertion-check.json')
    if (not cli_capture_checks['passed'] or not cli_capture_checks['inputsUnchanged'] or
            (cli_capture_checks['tests'], cli_capture_checks['failures'], cli_capture_checks['errors']) != (3, 1, 2) or
            cli_capture_actual['passed'] or not cli_capture_actual['inputsUnchanged'] or
            (cli_capture_actual['tests'], cli_capture_actual['failures'], cli_capture_actual['errors']) != (1, 1, 0) or
            not cli_capture_assertions['mainTestAssertionsAndRequestCallsAstUnchanged']):
        raise ValueError('CLI failure-capture diagnostic scope differs')
    cli_semantics_base = DEST / 'endpoint-cli-observation-semantics'
    cli_semantics = read(cli_semantics_base / 'review.json')
    for path, item in cli_semantics['outputs'].items():
        verify(cli_semantics_base / path, item['sha256'])
    records([cli_semantics['beforeProof'], cli_semantics['ownedSource']])
    if (cli_semantics['summary']['tests'] != 7 or not cli_semantics['summary']['passed'] or
            not cli_semantics['summary']['inputsUnchanged'] or
            cli_semantics['summary']['historicalBranchReachedInThisRun']):
        raise ValueError('CLI observation semantics focused scope differs')
    if [case['forwardedOpCount'] for case in cli_semantics['summary']['scenarios']] != [1, 2, 3]:
        raise ValueError('CLI observation semantics replay emitted extra commands')
    cli_aged_base = DEST / 'endpoint-cli-aged-observation'
    cli_aged = read(cli_aged_base / 'review.json')
    for path, item in cli_aged['outputs'].items():
        verify(cli_aged_base / path, item['sha256'])
    cli_aged_inputs = read(cli_aged_base / cli_aged['inputReferencesFile'])
    for path, item in cli_aged_inputs.items():
        verify(ROOT / path, item['sha256'])
    cli_aged_result = cli_aged['result']
    cli_aged_checks = cli_aged_result['checks']
    if (not cli_aged_result['passed'] or not cli_aged_result['inputsUnchanged'] or
            (cli_aged_result['tests'], cli_aged_result['failures'], cli_aged_result['errors']) != (1, 0, 0) or
            cli_aged_checks['firstStrictOutcome'] != 'OBSERVATION_STALE' or
            cli_aged_checks['firstProjection'] != 'historical' or
            cli_aged_checks['firstKnownAgeUpperBoundMs'] <= 10000 or
            not cli_aged_checks['allOriginalSampleTicksPreserved'] or
            cli_aged_checks['forwardedOpCounts'] != [1, 2, 3] or
            cli_aged['controlledWait']['opFramesBeforeWait'] != 1 or
            cli_aged['controlledWait']['opFramesAfterWait'] != 1):
        raise ValueError('CLI controlled aging proof differs')
    pat_execution_before = read(DEST / 'pat-execution-before/index.json')
    records(pat_execution_before['files'])
    pat_execution_handoff = read(DEST / 'pat-execution-integration.json')
    records(pat_execution_handoff['files'])
    pat_execution_base = DEST / 'pat-execution-after'
    pat_execution = read(pat_execution_base / 'index.json')
    if (pat_execution['exitCode'] or pat_execution['testCount'] != 23 or
            pat_execution['sourcesChangedDuringRun'] or
            not pat_execution['procedureExtraction']['submitTransactionAstIdentical'] or
            not pat_execution['procedureExtraction']['allOtherOriginalMethodsAstIdentical']):
        raise ValueError('PAT execution checks or procedure extraction differ')
    records(pat_execution['sources'], base=pat_execution_base / 'sources')
    # This23-test proof predates environment extraction and the evidence hook.
    # Current source equality/coverage belongs to the full runtime gate above.
    verify(pat_execution_base / 'tests.log', pat_execution['logSha256'])
    verify(pat_execution_base / 'compiler-identity.json', pat_execution['compilerIdentitySha256'])
    pat_execution_review_base = DEST / 'pat-execution-review'
    pat_execution_review_index = read(pat_execution_review_base / 'index.json')
    records(pat_execution_review_index['files'])
    pat_execution_review = read(pat_execution_review_base / 'review.json')
    if (pat_execution_review['status'] != 'no_blocking_defect_identified_in_reviewed_scope' or
            pat_execution_review['production_modified_by_reviewer'] or
            pat_execution_review['tests_executed_by_reviewer'] or
            pat_execution_review['runtime_or_hardware_executed_by_reviewer']):
        raise ValueError('PAT source review scope/result differs')
    pat_review_inputs = read(pat_execution_review_base / 'acquisition.json')
    for item in pat_review_inputs['items']:
        verify(ROOT / item['snapshot'], item['sha256'])
        # The review's current_live_matches flag describes its original seal,
        # not today's compiler/catalog after the service changes.
    pat_review_verification = read(pat_execution_review_base / 'verification.json')
    if (pat_review_verification['status'] != 'verified' or
            not pat_review_verification['review_before_after_stable'] or
            not pat_review_verification['current_live_matches']):
        raise ValueError('PAT source review input consistency failed')
    service_design_base = DEST / 'pat-service-design'
    service_design = read(service_design_base / 'index.json')
    records(service_design['files'])
    service_design_verification = read(service_design_base / 'verification.json')
    if (service_design_verification['status'] != 'verified' or
            not service_design_verification['all_before_after_match'] or
            service_design_verification['runtime_test_execution']):
        raise ValueError('PAT service design evidence scope differs')
    service_review = read(DEST / 'pat-service-review/index.json')
    records(service_review['files'])
    if service_review['tests_executed'] or service_review['status'] != 'accepted_with_required_design_corrections':
        raise ValueError('PAT service review scope differs')
    service_before = read(DEST / 'pat-service-integration-before/index.json')
    records(service_before['files'])
    pure_service = read(DEST / 'pat-service-pure-integration/index.json')
    records(pure_service['files'])
    pure_result = pure_service['result']
    if (not pure_result['passed'] or pure_result['tests'] != 126 or
            not pure_result['inputsStable'] or not pure_result['compilerIdentityStable']):
        raise ValueError('Pure PAT service integration proof differs')
    # These are copied historical inputs; the current compiler/catalog changed.
    hook = read(DEST / 'pat-evidence-hook/index.json')
    records(hook['files'])
    if [(r['tests'], r['failures'], r['errors'], r['passed']) for r in hook['results']] != [(9, 1, 0, False), (10, 0, 0, True)]:
        raise ValueError('PAT evidence-hook attempt history differs')
    if not all(r['inputsStable'] and r['compilerIdentityStable'] for r in hook['results']):
        raise ValueError('PAT evidence-hook inputs changed')
    hook_review = read(DEST / 'pat-evidence-hook-review/index.json')
    records(hook_review['files'])
    if hook_review['blockingFindings'] or not hook_review['readOnly'] or hook_review['testsExecuted']:
        raise ValueError('PAT evidence-hook review scope differs')
    worker_index = read(DEST / 'pat-simulation-worker/index.json')
    records(worker_index['files'])
    worker_review = read(DEST / 'pat-simulation-worker/review.json')
    if not worker_review['passed'] or worker_review['tests'] != 16 or worker_review['inputCount'] != 43:
        raise ValueError('PAT simulation worker proof differs')
    records(worker_review['sourcePins'])
    resource_design = read(DEST / 'io-driver-hub-resource-design/index.json')
    records(resource_design['files'])
    focused = {}
    expected_focused = {
        'pat-bounded-evidence': [(12, 5, 2, False), (12, 0, 0, True)],
        'resource-topology-integration': [(21, 0, 0, True)],
        'pat-evaluation-integrity': [(4, 8, 5, False), (4, 0, 0, True),
                                     (7, 5, 0, False), (7, 0, 0, True)],
        'pat-current-combined': [(179, 0, 0, True)],
    }
    for name, expected in expected_focused.items():
        seal = read(DEST / name / 'index.json')
        records(seal['files'])
        attempts = seal['attempts']
        if [(a['tests'], a['failures'], a['errors'], a['passed']) for a in attempts] != expected:
            raise ValueError('Focused attempt history differs: ' + name)
        for attempt in attempts:
            if not all(attempt[k] for k in ('inputSnapshotsEqual', 'compilerPairsEqual',
                    'compilerImportedMatchesCapturedCurrent', 'retainedInputHashesVerified')):
                raise ValueError('Focused retained input proof differs: ' + name)
        focused[name] = attempts[-1]['tests']
    resolution = read(DEST / 'pat-evaluation-integrity-review/resolution-01/review.json')
    records(resolution['inputs'])
    records([resolution['priorReview']])
    for evidence in resolution['producerEvidence']:
        records(evidence['records'])
    # Frozen staging claims apply to their copied/historical inputs only.
    for name in ('resource-topology', 'pat-simulation-evidence'):
        base = ROOT / 'artifacts/implementation' / name
        staged = read(base / 'index.json')
        # Original topology and evidence stages intentionally retain different
        # path conventions; neither index is rewritten for this aggregate view.
        records(staged['files'], base=ROOT if name == 'resource-topology' else base)
    resource_admission_base = ROOT / 'artifacts/implementation/io-resource-admission'
    resource_admission = read(resource_admission_base / 'index.json')
    records(resource_admission['files'])
    resource_admission_proof = read(resource_admission_base / 'proof.json')
    resource_admission_verification = read(resource_admission_base / 'verification.json')
    if (not resource_admission_proof['passed'] or resource_admission_proof['tests'] != 26 or
            not resource_admission_proof['inputsUnchanged'] or not resource_admission_proof['packagesUnchanged'] or
            not resource_admission_verification['passed'] or resource_admission_verification['latestTests'] != 26):
        raise ValueError('Staged resource admission proof differs')
    verify(resource_admission_base / 'index.json', resource_admission_verification['indexSha256'])
    live_evidence = read(DEST / 'pat-evidence-live-integration/index.json')
    records(live_evidence['files'])
    if [(a['tests'], a['failures'], a['errors'], a['passed']) for a in live_evidence['attempts']] != [(46, 0, 0, True)] * 2:
        raise ValueError('Current-code evidence integration attempt history differs')
    for attempt in live_evidence['attempts']:
        if not all(attempt[k] for k in ('inputSnapshotsEqual', 'compilerPairsEqual', 'inputHashesVerified')):
            raise ValueError('Evidence integration input proof differs')
        actual_workers = [(w['case'], w['outcome'], w['completedCases'], w['childOperations'])
                          for w in attempt['workers']]
        if actual_workers != [('case-04', 'passed', 27, 25), ('case-01', 'passed', 10, 9),
                              ('case-00', 'inconclusive', 0, 0)]:
            raise ValueError('Fresh evidence worker result history differs')
    memo_base = ROOT / 'artifacts/implementation/pat-evidence-fast-verification'
    memo_index = read(memo_base / 'index.json')
    records(memo_index['files'], base=memo_base)
    memo_proof = read(memo_base / 'proof.json')
    if ((memo_proof['testsRun'], memo_proof['passed'], memo_proof['failures'], memo_proof['errors']) != (17, 17, 0, 0)
            or not memo_proof['copiedInputsStableAfterBenchmark']):
        raise ValueError('Staged evidence memo proof differs')
    memo_before = read(DEST / 'pat-memo-resource-integration-before/index.json')
    records(memo_before['files'])
    memo_live = read(DEST / 'pat-memo-live-integration/index.json')
    records(memo_live['files'])
    if [(a['tests'], a['failures'], a['errors'], a['passed']) for a in memo_live['attempts']] != [
            (2, 2, 0, False), (77, 0, 0, True)]:
        raise ValueError('Live memo/dependency attempt history differs')
    for attempt in memo_live['attempts']:
        if not all(attempt[k] for k in ('inputSnapshotsEqual', 'inputHashesVerified', 'compilerPairsEqual')):
            raise ValueError('Live memo input proof differs')
    memo_current = memo_live['attempts'][-1]
    if [(w['case'], w['outcome'], w['completedCases'], w['childOperations']) for w in memo_current['workers']] != [
            ('case-04', 'passed', 27, 25), ('case-01', 'passed', 10, 9),
            ('case-00', 'inconclusive', 0, 0), ('case-02', 'passed', 27, 25)]:
        raise ValueError('Live memo actual worker history differs')
    if memo_current['catalog'] != {'coldPromotion': 'PAT_EVIDENCE_UNAVAILABLE',
            'warmAmbiguity': 'PAT_AMBIGUOUS', 'coldSelection': 'PAT_EVIDENCE_UNAVAILABLE',
            'historicalReplayPreserved': True, 'refusalsAllocateNothing': True}:
        raise ValueError('Live memo catalog selection evidence differs')
    resource_live_review = read(DEST / 'resource-admission-live-review/review.json')
    records(resource_live_review['files'])
    if (resource_live_review['blockingFindings'] or resource_live_review['testsExecutedByReviewer'] or
            resource_live_review['productionEditedByReviewer']):
        raise ValueError('Live resource review scope differs')
    resource_live = read(DEST / 'resource-admission-live-integration/index.json')
    records(resource_live['files'])
    records([resource_live['independentReview']])
    if [(a['tests'], a['failures'], a['errors'], a['passed']) for a in resource_live['attempts']] != [
            (5, 48, 0, False), (32, 0, 0, True)]:
        raise ValueError('Live resource storage attempt history differs')
    for attempt in resource_live['attempts']:
        if not all(attempt[k] for k in ('inputSnapshotsEqual', 'bothInputSnapshotsVerified',
                'compilerPairsEqual', 'compilerSourcesMatchCapturedInputs', 'compilerDigestRecomputed')):
            raise ValueError('Live resource retained source proof differs')
    if (resource_live['attempts'][-1]['poisonedValuesMaterialized'] != 0 or
            resource_live['attempts'][-1]['storageProbeCases'] != 48):
        raise ValueError('Live resource bounded-fetch observations differ')
    scalar_before = resource_live['scalarBefore']
    if ((scalar_before['tests'], scalar_before['failures'], scalar_before['errors'], scalar_before['passed']) !=
            (1, 1, 0, False) or not scalar_before['compilerStable'] or not scalar_before['inputsUnchanged'] or
            not scalar_before['retainedInputHashesVerified']):
        raise ValueError('Live binding scalar regression history differs')
    provider_base = ROOT / 'artifacts/implementation/io-synthetic-provider'
    provider_index = read(provider_base / 'index.json')
    records(provider_index['files'])
    provider_proof = read(provider_base / 'proof.json')
    provider_verification = read(provider_base / 'verification.json')
    if (not provider_proof['passed'] or provider_proof['tests'] != 24 or
            not provider_proof['inputsUnchanged'] or not provider_proof['validationPackagesUnchanged'] or
            not provider_verification['passed'] or provider_verification['latestTests'] != 24 or
            provider_verification['changedInputsBetweenAttempts'] != ['test_io_synthetic_provider.py']):
        raise ValueError('Staged synthetic provider proof differs')
    verify(provider_base / 'index.json', provider_verification['indexSha256'])
    lifecycle_design = read(ROOT / 'artifacts/implementation/io-lifecycle-settlement-design/index.json')
    records(lifecycle_design['files'])
    lifecycle_amendment = read(ROOT / 'artifacts/implementation/io-lifecycle-settlement-design/amendment-01-index.json')
    records(lifecycle_amendment['files'])
    lifecycle_binding_amendment = read(ROOT / 'artifacts/implementation/io-lifecycle-settlement-design/amendment-02-index.json')
    records(lifecycle_binding_amendment['files'])
    lifecycle_review_index = read(DEST / 'io-lifecycle-settlement-review/index.json')
    records(lifecycle_review_index['files'])
    lifecycle_review = read(DEST / 'io-lifecycle-settlement-review/review.json')
    if lifecycle_review['sourceImports'] or lifecycle_review['testsExecuted'] or lifecycle_review['liveEdits']:
        raise ValueError('Lifecycle design review scope differs')
    lifecycle_preliminary_base = DEST / 'io-lifecycle-preliminary-review/01'
    lifecycle_preliminary_index = read(lifecycle_preliminary_base / 'index.json')
    records(lifecycle_preliminary_index['files'], base=lifecycle_preliminary_base)
    lifecycle_preliminary = read(lifecycle_preliminary_base / 'review.json')
    if (any(value is not False for value in lifecycle_preliminary['activity'].values()) or
            len(lifecycle_preliminary['sources']) != 11 or
            [finding['status'] for finding in lifecycle_preliminary['findings']] != [
                'unresolved-in-frozen01-owner-correction-planned',
                'unresolved-in-frozen01-owner-correction-planned',
                'unresolved-in-frozen01-owner-correction-planned',
                'known-unfinished-profile-port']):
        raise ValueError('Preliminary lifecycle review no-execution/unresolved scope differs')
    # The initial implementation review remains unfinished. Hash only its
    # retained copies, never the concurrently corrected staging source.
    for item in lifecycle_preliminary['sources']:
        verify(lifecycle_preliminary_base / item['copy'], item['sha256'])
    lifecycle_delta_base = DEST / 'io-lifecycle-preliminary-review/02'
    lifecycle_delta_index = read(lifecycle_delta_base / 'index.json')
    records(lifecycle_delta_index['files'], base=lifecycle_delta_base)
    lifecycle_delta = read(lifecycle_delta_base / 'review.json')
    verify(lifecycle_delta_base / lifecycle_delta['previousReview'], lifecycle_delta['previousReviewSha256'])
    if (lifecycle_delta['activity'] != {'projectImports': False, 'projectTests': False,
            'runtimeOrWorker': False, 'databaseOpens': False, 'liveEdits': False,
            'ownerSourceEdits': False, 'stdlibAstComparisonExecuted': True} or
            len(lifecycle_delta['sources']) != 11 or
            [finding['status'] for finding in lifecycle_delta['resolutions']] != [
                'resolved-in-reviewed02-source', 'resolved-in-reviewed02-source',
                'resolved-in-reviewed02-source', 'explicitly-unfinished-public-profile'] or
            lifecycle_delta['noAdditionalBlockingFindingInTargetedDelta'] is not True or
            lifecycle_delta['staticComparison']['projectImports'] is not False or
            lifecycle_delta['staticComparison']['projectExecution'] is not False):
        raise ValueError('Targeted lifecycle delta static/unexecuted scope differs')
    for item in lifecycle_delta['sources']:
        verify(lifecycle_delta_base / item['copy'], item['sha256'])
    lifecycle_runner_review_base = DEST / 'io-lifecycle-source-preparation-review'
    lifecycle_runner_review_index = read(lifecycle_runner_review_base / 'index.json')
    records(lifecycle_runner_review_index['files'])
    lifecycle_runner_review = read(lifecycle_runner_review_base / 'review.json')
    if (lifecycle_runner_review['sourceSnapshot'] != '03' or
            any(lifecycle_runner_review[key] is not False for key in
                ('projectImported', 'testsExecuted', 'databaseOpened', 'sourcesEdited')) or
            lifecycle_runner_review['acceptanceCasesDeferredUntilSmoke'] is not True or
            len(lifecycle_runner_review['findings']) != 5):
        raise ValueError('Lifecycle source-preparation unfinished review scope differs')
    for item in lifecycle_runner_review['inputs']:
        verify(ROOT / item['copy'], item['sha256'])
    # These immutable source-preparation snapshots are not executed lifecycle
    # evidence. Never compare an old snapshot to a later mutable staging tree.
    lifecycle_snapshots = {}
    for number, count in (('03', 163), ('04', 164), ('05', 165)):
        base = ROOT / 'artifacts/implementation/io-lifecycle-settlement/review-inputs' / number
        manifest = read(base / 'manifest.json')
        if len(manifest['files']) != count:
            raise ValueError('Lifecycle source snapshot inventory differs')
        for item in manifest['files']:
            verify(ROOT / item['copy'], item['sha256'])
        preparation = read(base / 'source-preparation.json')
        if any(preparation[key] is not False for key in
               ('projectImported', 'testsExecuted', 'runtimeExecuted', 'executionReleased')):
            raise ValueError('Lifecycle source preparation overclaims execution')
        lifecycle_snapshots[number] = {item['path']: item['sha256'] for item in manifest['files']}
    baseline_hms = {path: value for path, value in lifecycle_snapshots['03'].items()
                    if path.startswith('project/hms/')}
    if len(baseline_hms) != 48 or any(
            {path: value for path, value in lifecycle_snapshots[number].items() if path.startswith('project/hms/')} != baseline_hms
            for number in ('04', '05')):
        raise ValueError('Lifecycle harness remediation changed effect source')
    for number, status in (('04', 'unresolved_in04'), ('05', 'resolved_in_read05_source')):
        base = DEST / 'io-lifecycle-harness-remediation-review' / number
        index = read(base / 'index.json')
        records(index['files'], base=base)
        review = read(base / 'review.json')
        if (review['snapshot'] != number or
                any(review[key] != 0 for key in ('reviewerProjectImports', 'reviewerTests',
                    'reviewerRuntimeOrSubprocessExecution', 'reviewerLiveEdits')) or
                len(review['findings']) != 2 or
                any(finding['status'] != status for finding in review['findings']) or
                review['staticChecks']['hmsFilesUnchangedFrom03'] != 48):
            raise ValueError('Lifecycle harness source-review scope differs')
        manifest_key = 'manifestSha256' if number == '04' else 'sourceManifestSha256'
        verify(ROOT / 'artifacts/implementation/io-lifecycle-settlement/review-inputs' / number / 'manifest.json',
               review[manifest_key])
        if number == '05':
            verify(base / review['priorReview'], review['priorReviewSha256'])
            if review['status'] != 'no_remaining_blocking_source_issue_in_narrow_reviewed_scope':
                raise ValueError('Lifecycle harness correction conclusion differs')
    io_pat_design_base = DEST / 'io-pat-qualification-design'
    io_pat_design_index = read(io_pat_design_base / 'index.json')
    records(io_pat_design_index['files'], base=io_pat_design_base)
    io_pat_design = read(io_pat_design_base / 'review.json')
    if (io_pat_design_index['designOnly'] is not True or
            io_pat_design_index['fileCount'] != 26 or len(io_pat_design_index['files']) != 26 or
            io_pat_design['status'] != 'design_only_not_implemented' or
            io_pat_design['lifecycleExecutionReleased'] is not False or
            io_pat_design['selectedInputs'] != 22 or io_pat_design['selectedInputsUnchangedAtSeal'] is not True or
            any(type(io_pat_design[key]) is not int or io_pat_design[key] != 0 for key in
                ('liveSourceEdits', 'projectImports', 'projectTests', 'runtimeExecutions', 'workerExecutions')) or
            {item['id'] for item in io_pat_design['concretePrerequisites']} != {
                'IO-PAT-SEMANTICS', 'IO-PAT-INVENTORY', 'IO-PAT-DURATION', 'IO-PAT-ORACLE'} or
            len(io_pat_design['concretePrerequisites']) != 4):
        raise ValueError('I/O PAT qualification design-only scope differs')
    # selectedInputsUnchangedAtSeal is historical; all selected copies above
    # remain hashed without comparing changing live implementation or docs.
    io_pat_inputs = read(io_pat_design_base / io_pat_design['files']['inputs'])
    if len(io_pat_inputs['inputs']) != 22:
        raise ValueError('I/O PAT design selected-input inventory differs')
    for item in io_pat_inputs['inputs']:
        verify(io_pat_design_base / item['snapshot'], item['sha256'])
    current_provider_index = read(DEST / 'io-provider-current-integration/index.json')
    records(current_provider_index['files'])
    current_provider = read(DEST / 'io-provider-current-integration/proof.json')
    if ((current_provider['tests'], current_provider['failures'], current_provider['errors'], current_provider['skips']) !=
            (24, 0, 0, 0) or current_provider['baselineInputs'] != 139 or current_provider['preparedInputs'] != 146 or
            not all(current_provider[key] for key in ('preparedAndCopiedInputHashesVerified', 'compilerPairVerified',
                'providerIdentityPairVerified', 'runnerPairVerified', 'evidenceHashesVerified', 'scopedImportsVerified'))):
        raise ValueError('Current-baseline copied provider proof differs')
    verify(ROOT / current_provider['parentReceipt'], current_provider['parentReceiptSha256'])
    verify(ROOT / current_provider['attempt'] / 'result.json', current_provider['resultSha256'])
    io_entry_review_base = DEST / 'io-runtime-entry-review'
    io_entry_review_index = read(io_entry_review_base / 'index.json')
    records(io_entry_review_index['files'], base=io_entry_review_base)
    io_entry_review = read(io_entry_review_base / 'review.json')
    if (any(value is not False for value in io_entry_review['execution'].values()) or
            io_entry_review['remainingBlockersInReviewedScope']):
        raise ValueError('I/O entry selected-source review scope differs')
    # This static review preceded the first focused37 run. Its conclusions are
    # not a passing integration result; retain exactly its original inputs.
    for item in io_entry_review['files']:
        verify(io_entry_review_base / item['retained'], item['sha256'])
    io_response_diagnosis_base = DEST / 'io-response-contract-diagnosis'
    io_response_diagnosis_index = read(io_response_diagnosis_base / 'index.json')
    records(io_response_diagnosis_index['files'], base=io_response_diagnosis_base)
    io_response_diagnosis = read(io_response_diagnosis_base / 'result.json')
    if (io_response_diagnosis['runtimeOrDaemonExecuted'] is not False or
            io_response_diagnosis['databaseOpened'] is not False or
            len(io_response_diagnosis['cases']) != 4):
        raise ValueError('Archived I/O response diagnosis scope differs')
    # These are projections reconstructed from later retained terminal rows,
    # not captured rejected wire bodies or independent transport executions.
    for item in io_response_diagnosis['cases']:
        if (item['jsonSchemaErrors'] or item['crossFieldFailure']['class'] != 'ResponseError' or
                not any(frame['function'] == 'validate_result' and
                        frame['source'] == '_require(type(output.get("effectCommitted")) is bool)'
                        for frame in item['crossFieldFailure']['frames'])):
            raise ValueError('Archived I/O response diagnosis reason differs')
    io_response_review_base = DEST / 'io-response-contract-resolution-review'
    io_response_review_index = read(io_response_review_base / 'index.json')
    records(io_response_review_index['files'], base=io_response_review_base)
    records(io_response_review_index['references'])
    io_response_review = read(io_response_review_base / 'review.json')
    if (any(value is not False for value in io_response_review['execution'].values()) or
            io_response_review['remainingBlockersInReviewedScope'] or
            len(io_response_review['files']) != 10 or len(io_response_review['previousFiles']) != 4):
        raise ValueError('I/O response static resolution review scope differs')
    for item in io_response_review['files'] + io_response_review['previousFiles']:
        verify(io_response_review_base / item['retained'], item['sha256'])
    io_response_structure = read(io_response_review_base / io_response_review['structuralChecks'])
    if (io_response_structure['apiTestMethodCount'] != 14 or
            len(io_response_structure['apiTestMethods']) != 14 or
            not all(io_response_structure[key] is True for key in (
                'legacySimulationBranchAstUnchanged',
                'validateResultAstEqualsPriorAfterRemovingOnlyNewProfileBranch',
                'adapterResultAstEqualsPriorAfterRemovingOnlyProfileTag',
                'blueprintChangesOnlyTwoDriverProfileValues'))):
        raise ValueError('I/O response static delta checks differ')
    io_session_base = DEST / 'io-transport-session-resolution'
    io_session_index = read(io_session_base / 'index.json')
    records(io_session_index['files'], base=io_session_base)
    records(io_session_index['references'])
    io_session_resolution = read(io_session_base / 'resolution.json')
    if (any(value is not False for value in io_session_resolution['execution'].values()) or
            io_session_resolution['failedAttemptCounts'] != {
                'tests': 52, 'failures': 1, 'errors': 1, 'inputs': 152, 'inputsUnchanged': True} or
            len(io_session_resolution['cases']) != 2 or
            io_session_resolution['staticChecks']['originalFunctionDefsUnchangedExceptRunMcp'] is not True or
            io_session_resolution['staticChecks']['boundsAndRequestBuildersUnchanged'] is not True):
        raise ValueError('I/O stale-session test correction scope differs')
    verify(io_session_base / 'before/tests/test_io_transport.py', io_session_resolution['beforeTestSha256'])
    verify(io_session_base / 'after/tests/test_io_transport.py', io_session_resolution['afterTestSha256'])
    for item in io_session_resolution['cases']:
        resume_calls = [call for call in item['actualMcpCalls']
                        if call['call']['name'] == 'hardware_procedure_resume']
        if (len(resume_calls) != 1 or resume_calls[0]['structuredContent'] != {
                'ok': False, 'error': {'code': 'IO_SESSION_CHANGED', 'outcome': 'unconfirmed'}} or
                resume_calls[0]['isError'] is not True or
                item['originalChildSession'] == item['capturedBoardSession'] or
                item['capturedParent']['state'] != 'interrupted' or
                item['capturedParent']['sequence'] != 2 or item['capturedChildOperation'] is not None or
                item['capturedCounts'] != {'operations': 4, 'claims': 0, 'io_dispatch_links': 3,
                                          'pr_keys': 5, 'replay_keys': 4, 'allocatedChildRows': 2} or
                not all(item[key] is True for key in ('effectsBeforeAndCapturedAfterEqual',
                    'unallocatedChildReplayKeyAbsent', 'childReservationRetained'))):
            raise ValueError('Archived I/O session refusal evidence differs')
    io_timeout_base = DEST / 'io-status-read-timeout-diagnosis'
    io_timeout_index = read(io_timeout_base / 'index.json')
    records(io_timeout_index['files'], base=io_timeout_base)
    records(read(io_timeout_base / io_timeout_index['references']))
    io_timeout = read(io_timeout_base / 'diagnosis.json')
    if (any(value is not False for value in io_timeout['execution'].values()) or
            io_timeout['retainedInputCount'] != 151 or
            io_timeout['facts']['failedRead']['method'] != 'procedure_status' or
            io_timeout['facts']['failedRead']['error']['code'] != 'TRANSPORT_TIMEOUT' or
            io_timeout['facts']['failedReadElapsedMs'] != 2005 or
            io_timeout['facts']['captureParent']['state'] != 'running' or
            io_timeout['facts']['captureParent']['cursor'] != 1):
        raise ValueError('Failed747 status-read diagnosis scope differs')
    failed_747 = read(ROOT / io_timeout['attempt'] / 'receipt.json')
    if ((failed_747['tests'], failed_747['failures'], failed_747['errors'], failed_747['skipped']) !=
            (747, 0, 1, 0) or failed_747['passed'] is not False or
            failed_747['inputs_stable'] is not True or failed_747['compiler_identity_stable'] is not True):
        raise ValueError('Failed747 historical runtime result differs')
    io_runtime_base = DEST / 'io-provider-runtime-integration'
    io_runtime_index = read(io_runtime_base / 'index.json')
    records(io_runtime_index['files'])
    io_runtime_proof = read(io_runtime_base / 'proof.json')
    records(io_runtime_proof['references'])
    if (io_runtime_proof['schema'] != 'hms-io-runtime-integration-proof/1' or
            len(io_runtime_proof['attempts']) != 3 or io_runtime_proof['finalInputs'] != 152 or
            io_runtime_proof['finalCoreInputsExcludingRunner'] != 151 or
            io_runtime_proof['finalInputsMatchLiveAtSeal'] is not True or
            io_runtime_proof['changedCommonInputsAfterFailed52'] != ['tests/test_io_transport.py'] or
            io_runtime_proof['productionInputsChangedAfterFailed52'] is not False or
            io_runtime_proof['finalTransportTests'] != 4 or
            io_runtime_proof['claims'] != {'publicRuntimeMounted': True, 'newPerDeviceMcpTools': False,
                'physicalIo': False, 'neuralModelExecution': False, 'targetMcuExecution': False,
                'driverOrHubLifecycleEffects': False, 'ioPatQualification': False,
                'autonomousPulseOrStopGuarantee': False, 'fullSuiteProof': False}):
        raise ValueError('Public I/O focused-family scope differs')
    io_runtime_maps, io_runtime_results = [], []
    io_expected = [(37, 1, 9, 151, False), (52, 1, 1, 152, False), (4, 0, 0, 152, True)]
    for item, expected in zip(io_runtime_proof['attempts'], io_expected):
        records([item['result']])
        result = read(ROOT / item['result']['path'])
        attempt_base = (ROOT / item['result']['path']).parent
        if (tuple(result[key] for key in ('tests', 'failures', 'errors', 'inputs', 'passed')) != expected or
                any(result[key] for key in ('skips', 'expectedFailures', 'unexpectedSuccesses',
                    'inputCaptureErrors', 'runnerErrors')) or
                not all(result[key] is True for key in ('inputsUnchanged', 'compilerStable', 'providerStable')) or
                any(item[key] != result[key] for key in ('tests', 'failures', 'errors', 'skips',
                    'inputs', 'seconds', 'passed', 'providerDigest'))):
            raise ValueError('Public I/O focused attempt history differs')
        records(result['outputs'])
        before = read(attempt_base / 'inputs-before.json')
        after = read(attempt_base / 'inputs-after.json')
        before_map = {row['path']: (row['sha256'], row['bytes']) for row in before}
        after_map = {row['path']: (row['sha256'], row['bytes']) for row in after}
        if len(before) != expected[3] or len(before_map) != len(before) or before_map != after_map:
            raise ValueError('Public I/O focused source snapshots differ')
        for row in before + after:
            verify(ROOT / row['snapshot_path'], row['sha256'])
        compiler_before = read(attempt_base / 'compiler-before.json')
        compiler_after = read(attempt_base / 'compiler-after.json')
        if compiler_before != compiler_after or compiler_before['import_matches_current'] is not True:
            raise ValueError('Public I/O focused compiler pair differs')
        if (read(attempt_base / 'provider-before.json') != {'digest': result['providerDigest']} or
                read(attempt_base / 'provider-after.json') != {'digest': result['providerDigest']}):
            raise ValueError('Public I/O focused provider pair differs')
        io_runtime_maps.append(before_map)
        io_runtime_results.append(result)
    # Keep both failed controllers and the final transport controller distinct.
    # This earlier four-transport core matches failed747 exactly. The following
    # recovery proof separately checks the current core; never rewrite this pass.
    io_controllers = {'artifacts/verification/io-provider-runtime-integration/run.py',
                      'artifacts/verification/io-provider-runtime-integration/run_transports.py'}
    io_common = set(io_runtime_maps[1]) & set(io_runtime_maps[2])
    if (sorted(path for path in io_common if io_runtime_maps[1][path] != io_runtime_maps[2][path]) !=
            ['tests/test_io_transport.py'] or
            io_runtime_results[1]['providerDigest'] != io_runtime_results[2]['providerDigest']):
        raise ValueError('Public I/O post-failed52 change scope differs')
    final_io_core = {path: value for path, value in io_runtime_maps[2].items() if path not in io_controllers}
    if (len(final_io_core) != 151 or final_io_core != {
            row['path']: (row['sha256'], row['bytes']) for row in failed_747['files_before']}):
        raise ValueError('Historical four-transport core differs from failed747 exact inputs')
    if io_runtime_proof['finalResult'] != io_runtime_proof['attempts'][-1]['result']:
        raise ValueError('Public I/O focused final pointer differs')
    passed52 = io_runtime_proof['passedComponentsWithinFailed52']
    if passed52 != {'syntheticProvider': 24, 'runtimeProfiles': 9, 'typedIoApi': 14,
                   'existingCliLifecycle': 1, 'cliAndCrashTransport': 2}:
        raise ValueError('Public I/O failed52 passing-component scope differs')
    failed52_base = (ROOT / io_runtime_proof['attempts'][1]['result']['path']).parent
    successful_lines = [line for line in (failed52_base / 'tests.txt').read_text().splitlines()
                        if line.endswith(' ... ok')]
    for module, count in [('test_io_synthetic_provider', 24), ('test_runtime_profiles', 9),
                          ('test_io_api_contracts', 14), ('test_ipc', 1), ('test_io_transport', 2)]:
        if sum('(' + module + '.' in line for line in successful_lines) != count:
            raise ValueError('Public I/O failed52 component log differs')
    records([io_runtime_proof['finalTransportReport']])
    io_transport_report = read(ROOT / io_runtime_proof['finalTransportReport']['path'])
    io_transport_cases = io_transport_report['cases']
    if len(io_transport_cases) != 4 or any(case['passed'] is not True or case.get('failureArtifacts')
                                         for case in io_transport_cases.values()):
        raise ValueError('Public I/O final transport report differs')
    io_tools = sorted('hardware_' + method for method in ('cancel', 'describe', 'discover', 'events',
        'invoke', 'namespace', 'observe', 'operation', 'prepare', 'procedure_cancel', 'procedure_events',
        'procedure_resume', 'procedure_status', 'procedure_submit'))
    if len(io_runtime_proof['mcp']) != 2:
        raise ValueError('Public I/O MCP channel count differs')
    for channel in io_runtime_proof['mcp']:
        case = io_transport_cases[channel['case']]
        refused = case['results']['refusedResume']
        final = case['results']['canceledProcedure']
        if (case['calledTools'] != io_tools or channel['calledTools'] != io_tools or
                case['validatedToolReplies'] != 32 or channel['validatedReplies'] != 32 or
                channel['refusedResumeCounts'] != [4, 0, 3, 2] or
                refused['before'] != refused['after'] or refused['before']['counts'] != [[4, 0, 3, 2]] or
                refused['response'] != {'ok': False, 'error': {'code': 'IO_SESSION_CHANGED', 'outcome': 'unconfirmed'}} or
                refused['originalSession'] == refused['currentSession'] or
                refused['statusAfter'] != case['results']['interruptedProcedure'] or
                refused['statusAfter']['executionState'] != 'interrupted' or
                refused['statusAfter']['steps'][0]['operationId'] is not None or
                final['executionState'] != 'canceled' or final['steps'][0]['operationId'] is not None):
            raise ValueError('Public I/O actual MCP tool/refusal/cancellation evidence differs')
    io_observers = [entry for case in io_transport_cases.values() for entry in case['observerReads']]
    if (len(io_observers) != 150 or io_runtime_proof['observerReads'] != 150 or
            sum(entry['busyRetries'] for entry in io_observers) != 0 or io_runtime_proof['observerBusyRetries'] != 0 or
            any(entry['succeeded'] is not True for entry in io_observers) or
            io_runtime_proof['allObserverReadsSucceeded'] is not True):
        raise ValueError('Public I/O recorded observer outcomes differ')
    # startupRefusals.stateCreated records post-call existence, not creation.
    # Existing-authority refusal cases may therefore correctly record true.
    io_crash = io_transport_cases['test_io_transport.IoTransportTests.test_SIGKILL_pending_pulse_reopens_idle_without_second_activation']
    pending, reconciled = io_crash['results']['pendingObserved'], io_crash['results']['reconciled']
    if (pending['state'] != 'pending' or pending['result']['activationCommitted'] is not True or
            pending['result']['safeIdle'] is not False or reconciled['executionState'] != 'canceled' or
            reconciled['mayHaveActed'] is not True or reconciled['resourceClaims'] or
            reconciled['result']['output']['result'] != {'activationCommitted': True, 'cycleCompleted': False,
                'safeIdle': True, 'reason': 'board_owner_reopened'}):
        raise ValueError('Public I/O controlled crash/reopen facts differ')
    for key in ('effects', 'receipts', 'dispatchLinks', 'operations', 'events'):
        if (io_crash['snapshots']['second-reopen-exact-replay'][key] !=
                io_crash['snapshots']['reconciled-after-reopen'][key]):
            raise ValueError('Public I/O controlled-crash exact replay differs')
    io_recovery_base = DEST / 'io-status-read-timeout-resolution'
    io_recovery_index = read(io_recovery_base / 'index.json')
    records(io_recovery_index['files'])
    records(io_recovery_index['references'])
    io_recovery = read(io_recovery_base / 'proof.json')
    if (io_recovery['schema'] != 'hms-io-status-recovery-proof/1' or
            len(io_recovery['attempts']) != 2 or io_recovery['coreInputs'] != 151 or
            io_recovery['inputsIncludingRunner'] != 152 or
            io_recovery['claims'] != {'testOnlyChange': True, 'productionChanged': False,
                'productionRpcTimeoutChanged': False, 'mutationRetried': False, 'preparationRetried': False,
                'sessionOrKeyChanged': False, 'operationBoundsChanged': False, 'fullSuiteProof': False,
                'physicalIo': False, 'boundedAvailabilityQualified': False}):
        raise ValueError('I/O status-read recovery scope differs')
    if (io_recovery['finalResult'] != io_recovery['attempts'][-1]['result'] or
            io_recovery['pollingSemantics'] != {'methods': ['operation', 'procedure_status'],
                'retryCode': 'TRANSPORT_TIMEOUT', 'paramsCopiedOnce': True, 'defaultOuterBudgetSeconds': 15,
                'productionRpcTimeoutSeconds': 2, 'absoluteDeadlineNotReset': True,
                'postResponseAndPredicateDeadlineChecks': True, 'allFailedClientReadsRetained': True,
                'inFlightRpcCanFinishAfterOuterDeadline': True, 'lateSuccessAccepted': False}):
        raise ValueError('I/O recovery deadline/read-only semantics differ')
    for item, expected in zip(io_recovery['attempts'], [(1, 0, 1, False), (5, 0, 0, True)]):
        records([item['result']])
        result = read(ROOT / item['result']['path'])
        attempt_base = (ROOT / item['result']['path']).parent
        if (tuple(result[key] for key in ('tests', 'failures', 'errors', 'passed')) != expected or
                result['inputs'] != 152 or any(result[key] for key in ('skips', 'expectedFailures',
                    'unexpectedSuccesses', 'inputCaptureErrors', 'runnerErrors')) or
                any(item[key] != result[key] for key in ('tests', 'failures', 'errors', 'skips',
                    'inputs', 'passed', 'seconds', 'providerDigest')) or
                not all(result[key] is True for key in ('inputsUnchanged', 'compilerStable', 'providerStable'))):
            raise ValueError('I/O status-read before/after result differs')
        records(result['outputs'])
        before = read(attempt_base / 'inputs-before.json')
        after = read(attempt_base / 'inputs-after.json')
        recovery_map = {row['path']: (row['sha256'], row['bytes']) for row in before}
        if (len(before) != 152 or len(after) != 152 or len(recovery_map) != 152 or recovery_map != {
                row['path']: (row['sha256'], row['bytes']) for row in after}):
            raise ValueError('I/O status-read retained source pairs differ')
        for row in before + after:
            verify(ROOT / row['snapshot_path'], row['sha256'])
        compiler_before = read(attempt_base / 'compiler-before.json')
        if (compiler_before != read(attempt_base / 'compiler-after.json') or
                compiler_before['import_matches_current'] is not True or
                read(attempt_base / 'provider-before.json') != {'digest': result['providerDigest']} or
                read(attempt_base / 'provider-after.json') != {'digest': result['providerDigest']}):
            raise ValueError('I/O status-read compiler/provider identity pairs differ')
    recovery_core = {path: value for path, value in recovery_map.items()
                     if path != 'artifacts/verification/io-status-read-timeout-resolution/run.py'}
    if (len(recovery_core) != 151 or recovery_core != {
            row['path']: (row['sha256'], row['bytes']) for row in prior_748['files_before']} or
            sorted(path for path in final_io_core if final_io_core[path] != recovery_core.get(path)) !=
            ['tests/test_io_transport.py']):
        raise ValueError('I/O recovery core differs from its historical full748 run or changed production')
    records([io_recovery['sourceComparison'], io_recovery['finalTransportReport']])
    io_recovery_source = read(ROOT / io_recovery['sourceComparison']['path'])
    if (io_recovery_source['changedCoreInputsFromFailed747'] != ['tests/test_io_transport.py'] or
            not all(io_recovery_source[key] is True for key in ('productionInputsUnchanged',
                'beforeHelperAstEqualsFailed747', 'allOriginalFunctionsExceptWaitAstUnchanged',
                'controlledRegressionAstIdenticalBeforeAfter'))):
        raise ValueError('I/O recovery source extraction scope differs')
    io_recovery_report = read(ROOT / io_recovery['finalTransportReport']['path'])
    if len(io_recovery_report['cases']) != 5 or any(case['passed'] is not True
                                                  for case in io_recovery_report['cases'].values()):
        raise ValueError('I/O recovery five-transport report differs')
    controlled = io_recovery_report['cases'][
        'test_io_transport.IoTransportTests.test_status_polling_recovers_only_read_timeouts_within_original_deadline'
    ]['results']['controlledPolling']
    if (controlled['finalBusinessUnchanged'] is not True or len(controlled['cases']) != 9 or
            controlled['cases'] != io_recovery['controlledCases'] or
            io_recovery['latePredicateObservation']['entered'] is not True):
        raise ValueError('I/O recovery controlled read observations differ')
    for method in ('operation', 'procedure_status'):
        calls = [item for item in controlled['requests'] if item['mode'] == 'delay-first' and item['method'] == method]
        if (len(calls) != 2 or calls[0]['params'] != calls[1]['params'] or
                calls[0]['result'] != calls[1]['result'] or any(item['forwarded'] is not True for item in calls)):
            raise ValueError('I/O actual same-identity read recovery differs')
    io_recovery_review_base = DEST / 'io-status-read-timeout-resolution-review'
    io_recovery_review_index = read(io_recovery_review_base / 'index.json')
    records(io_recovery_review_index['files'], base=io_recovery_review_base)
    io_recovery_review = read(io_recovery_review_base / 'review.json')
    if (io_recovery_review['status'] != 'no_blocking_issue_in_reviewed_scope' or
            any(io_recovery_review[key] != 0 for key in ('reviewerDatabaseOpens', 'reviewerExecutedProjectTests',
                'reviewerLiveSourceEdits', 'reviewerProjectImports', 'reviewerRuntimeOrWorkerExecutions')) or
            io_recovery_review['sourceComparison']['unchangedProductionModuleCount'] != 43 or
            io_recovery_review['finalTestSourceSha256'] != recovery_core['tests/test_io_transport.py'][0]):
        raise ValueError('I/O recovery independent static review scope differs')
    mapping_correction = read(DEST / 'runtime-696-audit/attempt-01/failure.json')
    records([mapping_correction['auditorBefore']])
    records(mapping_correction['verifiedHistoricalSources'])
    prior_696_audit = read(DEST / 'runtime-696-audit/attempt-02/index.json')
    records(prior_696_audit['files'])
    provider_696_audit = read(DEST / 'runtime-696-audit/attempt-03/index.json')
    records(provider_696_audit['files'])
    supervisor_base = ROOT / 'artifacts/implementation/pat-qualification-supervisor'
    supervisor_index = read(supervisor_base / 'index.json')
    records(supervisor_index['files'], base=supervisor_base)
    for item in supervisor_index['symlinksNotFollowed']:
        link = supervisor_base / item['path']
        if not link.is_symlink() or str(link.readlink()) != item['target']:
            raise ValueError('Retained supervisor negative-test symlink differs')
    supervisor_proof = read(supervisor_base / 'proof.json')
    if ((supervisor_proof['testsRun'], supervisor_proof['passed'], supervisor_proof['failures'],
            supervisor_proof['errors'], supervisor_proof['skipped']) != (19, 19, 0, 0, 0) or
            not supervisor_proof['copiedInputsStable'] or not supervisor_proof['selectedExternalInputsStable'] or
            supervisor_proof['copiedInputs'] != 54 or supervisor_proof['selectedExternalInputs'] != 139):
        raise ValueError('Staged supervisor combined proof differs')
    if any(supervisor_proof['claims'][key] for key in ('semanticQualificationPublished', 'currentRuntimeQualification',
            'totalDiskQuotaEnforced', 'hardTerminationDeadline', 'publicServiceMounted', 'physicalHardwareUsed',
            'externalModelUsed', 'acquiredControllerExecuted')):
        raise ValueError('Staged supervisor scope differs')
    verify(supervisor_base / supervisor_proof['finalAttempt'] / 'result.json', supervisor_proof['finalResultSha256'])
    verify(ROOT / supervisor_proof['review']['repositoryPath'], supervisor_proof['review']['sha256'])
    supervisor_review_index = read(DEST / 'pat-supervisor-review/final/index.json')
    records(supervisor_review_index['files'])
    supervisor_current_base = DEST / 'pat-supervisor-current-integration'
    supervisor_current_index = read(supervisor_current_base / 'index.json')
    records(supervisor_current_index['files'], base=supervisor_current_base)
    if len(supervisor_current_index['symlinksNotFollowed']) != 1:
        raise ValueError('Current696 supervisor negative-path inventory differs')
    for item in supervisor_current_index['symlinksNotFollowed']:
        link = supervisor_current_base / item['path']
        if not link.is_symlink() or str(link.readlink()) != item['target']:
            raise ValueError('Current696 supervisor negative-test symlink differs')
    supervisor_current = read(supervisor_current_base / 'proof.json')
    if supervisor_current['counts'] != {
            'baselineInputs': 139, 'supervisorImplementationInputs': 4, 'ownTestInputs': 4,
            'executionInputs': 147, 'runnerAdditionalInputs': 1, 'selectedExternalInputs': 139,
            'retainedTrustedSetups': 3}:
        raise ValueError('Current696 supervisor source closure differs')
    if (supervisor_current['baseline']['laterLiveProviderPortsIncluded'] is not False or
            any(value is not False for value in supervisor_current['claims'].values()) or
            supervisor_current['storageDesign']['enforcementConfigured'] is not False or
            supervisor_current['storageDesign']['negativeAcceptanceTestsExecuted'] is not False):
        raise ValueError('Current696 supervisor scope differs')
    if ((supervisor_current_base / supervisor_current['baseline']['receipt']).resolve() !=
            (ROOT / checkpoint_696['references'][0]['path']).resolve()):
        raise ValueError('Current696 supervisor baseline receipt differs')
    # The copied rebase predates the live I/O port. Keep its exact historical
    # baseline and unchanged supervisor implementation separate from live code.
    records(prior_696['files'], base=supervisor_current_base / 'baseline/current')
    records(supervisor_current['implementationUnchanged'], base=supervisor_current_base)
    records(supervisor_current['implementationUnchanged'], base=supervisor_base)
    supervisor_current_attempt = supervisor_current['finalAttempt']
    if ((supervisor_current_attempt['testsRun'], supervisor_current_attempt['failures'],
            supervisor_current_attempt['errors'], supervisor_current_attempt['skips']) != (19, 0, 0, 0) or
            not supervisor_current_attempt['inputsUnchanged'] or
            not supervisor_current_attempt['externalInputsUnchanged']):
        raise ValueError('Current696 supervisor combined result differs')
    records([supervisor_current_attempt[key] for key in ('result', 'report', 'log')], base=supervisor_current_base)
    supervisor_current_result = read(supervisor_current_base / supervisor_current_attempt['result']['path'])
    supervisor_current_report = read(supervisor_current_base / supervisor_current_attempt['report']['path'])
    if ((supervisor_current_result['exitCode'], supervisor_current_result['inputCount'],
            supervisor_current_result['externalInputCount']) != (0, 147, 139) or
            supervisor_current_result['targets'] or not supervisor_current_result['inputsUnchanged'] or
            not supervisor_current_result['externalInputsUnchanged'] or
            (supervisor_current_report['testsRun'], supervisor_current_report['failures'],
             supervisor_current_report['errors'], supervisor_current_report['skips']) != (19, 0, 0, 0)):
        raise ValueError('Current696 supervisor retained attempt differs')
    supervisor_current_attempt_base = supervisor_current_base / supervisor_current_attempt['path']
    supervisor_current_inputs = read(supervisor_current_attempt_base / 'inputs-before.json')
    if (len(supervisor_current_inputs) != 147 or
            supervisor_current_inputs != read(supervisor_current_attempt_base / 'inputs-after.json')):
        raise ValueError('Current696 supervisor copied input pair differs')
    records(supervisor_current_inputs, base=supervisor_current_attempt_base / 'tree')
    supervisor_current_external = read(supervisor_current_attempt_base / 'external-before.json')
    if (len(supervisor_current_external) != 139 or
            supervisor_current_external != read(supervisor_current_attempt_base / 'external-after.json')):
        raise ValueError('Current696 supervisor selected dependency pair differs')
    verify(supervisor_current_attempt_base / 'run_attempt.py', supervisor_current_result['runnerSha256'])
    verify(supervisor_current_base / 'run_attempt.py', supervisor_current_result['runnerSha256'])
    setups = sorted((supervisor_current_attempt_base / 'trusted-setup').glob('*.json'))
    historical_compiler = read(DEST / 'runtime-696-checkpoint/compiler-at-seal.json')
    if (len(setups) != 3 or not historical_compiler['import_matches_current'] or
            historical_compiler['manifest'] != historical_compiler['currentManifest']):
        raise ValueError('Current696 supervisor trusted setup provenance differs')
    for path in setups:
        setup = read(path)
        if (setup['configurationDigest'] != 'sha256:' + path.stem or
                setup['workerIdentities']['compilerDigest'] != historical_compiler['compilerDigest'] or
                setup['evaluator']['policyDigest'] != setup['workerIdentities']['policyDigest']):
            raise ValueError('Current696 supervisor test configuration association differs')
    if {item['phase'] for item in supervisor_current_report['crashes']} != {
            'admitted', 'launching', 'spawned', 'producer_settled', 'archived'}:
        raise ValueError('Current696 supervisor process-loss coverage differs')
    for item in supervisor_current_report['workers'] + supervisor_current_report['crashes']:
        archive = item['row']['archive']
        if (archive['semanticQualificationVerified'] is not False or archive['totalDiskQuotaEnforced'] is not False or
                archive['unresolvedEffects'] is not None):
            raise ValueError('Current696 supervisor archive overclaims qualification')
    compact_before_base = DEST / 'compact-availability-before'
    compact_before = read(compact_before_base / 'review.json')
    if (compact_before['run']['tests'] != 4 or not compact_before['run']['passed'] or
            not compact_before['run']['frozenInputsUnchanged']):
        raise ValueError('Compact availability reproduction did not pass')
    for path, item in compact_before['inputPins'].items():
        verify(compact_before_base / 'inputs' / path, item['sha256'])
    for path, item in compact_before['outputPins'].items():
        verify(compact_before_base / path, item['sha256'])
    for path, item in compact_before['historicalEvidence'].items():
        verify(ROOT / path, item['sha256'])
    compact_design_base = DEST / 'compact-admission-design'
    compact_design = read(compact_design_base / 'review.json')
    for path, item in compact_design['outputs'].items():
        verify(compact_design_base / path, item['sha256'])
    for path, item in compact_design['readSources'].items():
        verify(ROOT / path, item['sha256'])
    compact_after_base = DEST / 'compact-admission-after'
    compact_after = read(compact_after_base / 'review.json')
    if (compact_after['run']['tests'] != 25 or not compact_after['run']['passed'] or
            not compact_after['run']['frozenInputsUnchanged']):
        raise ValueError('Compact admission refresh checks did not pass')
    compact_after_inputs = read(compact_after_base / compact_after['inputClosureFile'])
    for path, item in compact_after_inputs.items():
        verify(compact_after_base / 'inputs' / path, item['sha256'])
    for path, item in compact_after['outputPins'].items():
        verify(compact_after_base / path, item['sha256'])
    for path, item in compact_after['ownedSourcesAfterRun'].items():
        # This25-test copied proof predates resource-aware Registry admission.
        # Its own immutable inputs preserve those exact implementation bytes;
        # the full current-source gate above covers today's Registry separately.
        verify(compact_after_base / 'inputs' / path, item['sha256'])
    freshness_before_base = DEST / 'local-freshness-before'
    freshness_before = read(freshness_before_base / 'index.json')
    records(freshness_before['files'], base=freshness_before_base / 'sources')
    verify(freshness_before_base / 'tests.log', freshness_before['logSha256'])
    extended_base = freshness_before_base / 'extended'
    extended_before = read(extended_base / 'index.json')
    verify(extended_base / 'test_local_freshness.py', extended_before['testSha256'])
    verify(extended_base / 'tests.log', extended_before['logSha256'])
    freshness_after_base = DEST / 'local-freshness-after'
    freshness_after = read(freshness_after_base / 'index.json')
    if freshness_after['exitCode'] or freshness_after['sourcesChangedDuringRun']:
        raise ValueError('Local effect-boundary regression checks failed or changed inputs')
    records(freshness_after['files'], base=freshness_after_base / 'sources')
    # This intermediate proof precedes the subsequent start-boundary fix.
    verify(freshness_after_base / 'tests.log', freshness_after['logSha256'])
    start_before_base = DEST / 'local-start-boundary-probe'
    start_before = read(start_before_base / 'index.json')
    records(start_before['sources'], base=start_before_base / 'sources')
    verify(start_before_base / 'probe.py', start_before['probeSha256'])
    verify(start_before_base / 'result.json', start_before['resultSha256'])
    start_after_base = DEST / 'local-start-boundary-after'
    start_after = read(start_after_base / 'index.json')
    if start_after['exitCode'] or start_after['probeExitCode'] or start_after['sourcesChangedDuringRun']:
        raise ValueError('Local start-boundary checks failed or changed inputs')
    records(start_after['sources'], base=start_after_base / 'sources')
    verify(start_after_base / 'tests.log', start_after['logSha256'])
    verify(start_after_base / 'probe.py', start_after['probeSha256'])
    verify(start_after_base / 'probe-result.json', start_after['probeResultSha256'])
    start_probe = read(start_after_base / 'probe-result.json')
    if len(start_probe['cases']) != 5:
        raise ValueError('Missing local start-boundary probe cases')
    for case in start_probe['cases']:
        control = case['case'] == 'control'
        if (case['status']['executionState'] != ('completed' if control else 'rejected_before_start') or
                case['effectCount'] != int(control) or case['status']['mayHaveActed'] != control or
                case['status']['resourceClaims'] or not case['replaySameOperation']):
            raise ValueError('Local start-boundary probe outcome differs')
    exclusion_base = DEST / 'local-start-atomic-exclusion'
    exclusion = read(exclusion_base / 'index.json')
    if exclusion['exitCode'] or exclusion['sourcesChangedDuringRun'] or exclusion['testCount'] != 23:
        raise ValueError('Atomic start-exclusion checks failed or changed inputs')
    records(exclusion['sources'], base=exclusion_base / 'sources')
    # The later admission-refresh/PAT composition changes are covered by the
    # current whole-suite run; this earlier focused proof retains its own inputs.
    verify(exclusion_base / 'tests.log', exclusion['logSha256'])
    diagnosis_base = DEST / 'runtime-424-diagnosis'
    diagnosis = read(diagnosis_base / 'review.json')
    if not diagnosis['failureCaptureChecks']['passed'] or not diagnosis['focusedRun']['passed']:
        raise ValueError('Transport diagnosis or failure-capture checks did not pass')
    for path, item in diagnosis['outputs'].items():
        verify(diagnosis_base / path, item['sha256'])
    for item in diagnosis['externalSelfCheckManifests']:
        verify(ROOT / item['path'], item['sha256'])
        retained = read(ROOT / item['path'])
        records(retained['files'], base=(ROOT / item['path']).parent)
    report = {
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'command': 'python3 scripts/audit_endpoint_evidence.py', 'passed': True,
        'scope': 'Retained input/output hash consistency for the current Python runtime and original endpoint/platform primitives. Current runtime receipt includes sequential before/after source snapshots and immutable outputs. Prior primitive Harness, compact host/MCP and installed-support evidence uses explicit 241/278/280/289/315-test source archives and frozen fixtures; those receipts do not validate subsequent procedure changes. Independent glue/catalog reviews and intermediate effect/start proofs use their exact historical source copies; current regression coverage is separate. Historical Harness flows remain single-route scenarios. Built-file hashes establish stability during their recorded Harness run, not hashes captured at the earlier build time. No tests or acquired programs executed by this audit.',
        'hash_assertions_verified': checks, 'unique_files_verified': len(unique),
        'receipts': receipts, 'auditor_sha256': digest(Path(__file__).resolve()),
        'summary': {'python_tests': runtime['tests'], 'native_cases': native['native_tests'],
                    'historical_748_checkpoint_tests': prior_748['tests'],
                    'historical_696_checkpoint_tests': prior_696['tests'],
                    'multi_adapter_independent_cases': multi_review['tests'][0]['cases'],
                    'multi_adapter_independent_realtime_scenarios': multi_review['tests'][1]['completed_scenarios'],
                    'historical_315_harness_tests': multi_harness['tests']['passed'],
                    'historical_315_harness_built_files_verified': len(multi_built['sha256']),
                    'historical_289_harness_tests': support_harness['tests']['passed'],
                    'historical_289_harness_built_files_verified': len(built['sha256']),
                    'historical_host_mcp_sdk_replies': mcp['validatedReplies'],
                    'historical_compact_mcp_scenarios': compact_mcp['summary']['scenarioExecutions'],
                    'boot_allocator_native_cases_per_build': boot['native'][0]['results']['cases'],
                    'avr_uart_register_model_cases_per_build': uart['native'][0]['result']['cases'],
                    'procedure_glue_adversarial_tests': glue['tests'],
                    'pat_catalog_independent_tests': pat_review['tests'],
                    'pat_execution_tests': pat_execution['testCount'],
                    'pat_execution_reviewed_sources': len(pat_review_inputs['items']),
                    'pat_pure_service_focused_tests': pure_result['tests'],
                    'pat_evidence_hook_focused_tests': hook['results'][-1]['tests'],
                    'pat_simulation_worker_focused_tests': worker_review['tests'],
                    'pat_bounded_evidence_focused_tests': focused['pat-bounded-evidence'],
                    'pat_evaluation_integrity_focused_tests': focused['pat-evaluation-integrity'],
                    'resource_topology_focused_tests': focused['resource-topology-integration'],
                    'pat_evidence_library_integration_tests': live_evidence['attempts'][-1]['tests'],
                    'staged_resource_admission_tests': resource_admission_proof['tests'],
                    'staged_evidence_memo_tests': memo_proof['testsRun'],
                    'live_memo_compiler_integration_tests': memo_current['tests'],
                    'live_resource_admission_tests': resource_live['attempts'][-1]['tests'],
                    'staged_synthetic_io_provider_tests': provider_proof['tests'],
                    'current_baseline_copied_io_provider_tests': current_provider['tests'],
                    'io_entry_static_reviewed_inputs': len(io_entry_review['files']),
                    'io_response_archived_schema_valid_projections': len(io_response_diagnosis['cases']),
                    'io_response_resolution_static_reviewed_inputs': len(io_response_review['files']),
                    'io_transport_archived_session_refusals': len(io_session_resolution['cases']),
                    'io_runtime_focused_attempt_tests': [item['tests'] for item in io_runtime_proof['attempts']],
                    'io_runtime_passed_components_within_failed52': sum(passed52.values()),
                    'io_runtime_final_transport_tests': io_runtime_proof['finalTransportTests'],
                    'io_runtime_final_mcp_validated_replies': sum(item['validatedReplies'] for item in io_runtime_proof['mcp']),
                    'historical_failed747_tests': failed_747['tests'],
                    'io_status_recovery_focused_tests': io_recovery['attempts'][-1]['tests'],
                    'lifecycle_preliminary_unresolved_findings': len(lifecycle_preliminary['findings']),
                    'lifecycle_delta_source_resolutions_unexecuted': 3,
                    'lifecycle_runner_preparation_findings_unexecuted': len(lifecycle_runner_review['findings']),
                    'io_pat_design_unimplemented_prerequisites': len(io_pat_design['concretePrerequisites']),
                    'staged_qualification_supervisor_tests': supervisor_proof['testsRun'],
                    'historical_696_copied_supervisor_tests': supervisor_current_attempt['testsRun'],
                    'current_supervisor_negative_test_symlinks_checked_without_following': len(supervisor_current_index['symlinksNotFollowed']),
                    'supervisor_negative_test_symlinks_checked_without_following': len(supervisor_index['symlinksNotFollowed']),
                    'compact_admission_refresh_tests': compact_after['run']['tests'],
                    'local_start_freshness_tests': exclusion['testCount'],
                    'avr_clock_source_mutations_rejected': clock_results['source_mutations_rejected'],
                    'avr_eeprom_register_model_cases_per_build': eeprom['native'][0]['result']['cases'],
                    'framed_integration_scenarios': integration['scenarios'],
                    'avr_flash_bytes': avr['linked_harness_flash_bytes'],
                    'avr_static_ram_bytes': avr['linked_harness_static_ram_bytes'],
                    'avr_foreground_static_stack_bound': avr['foreground_stack_bound_bytes'],
                    'research_source_records_in_separate_corpus_audit': corpus['source_records']},
        'limitations': ['Hash consistency is not an independent rerun, hardware validation or trust attestation.',
                       'Research corpus integrity is checked by scripts/audit_corpus.py; this audit fingerprints its retained report.',
                       'Native Harness tests remain pinned to their tested commits; subsequent live-head movement is not validated by these receipts.',
                       'Multi-adapter live probes retain stale-readiness failures under load; isolated passes do not qualify bounded availability.',
                       'AVR compiler stack analysis and planning reservations do not measure runtime fit, interrupts or physical deadlines.'],
    }
    (DEST / 'endpoint-evidence-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'hash_assertions': checks, 'unique_files': len(unique),
                      'artifact': 'artifacts/verification/endpoint-evidence-audit.json'}))


if __name__ == '__main__':
    main()

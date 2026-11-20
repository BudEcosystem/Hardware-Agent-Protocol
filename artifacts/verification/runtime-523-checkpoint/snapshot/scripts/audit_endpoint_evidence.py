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
    corpus = read(DEST / 'corpus-lrll-audit.json')
    lrll_integration = read(DEST / 'corpus-lrll-integration.json')
    records(lrll_integration['files'])
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
    records(pat_execution['sources'])
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
        verify(ROOT / item['source'], item['sha256'])
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
        verify(ROOT / path, item['sha256'])
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

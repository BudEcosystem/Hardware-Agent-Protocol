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
    runtime = read(DEST / 'local-runtime.json')
    if runtime['failures'] or runtime['errors'] or runtime['skipped']:
        raise ValueError('Local runtime suite did not fully pass')
    records(runtime['files'])
    records(runtime['outputs'])
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
        verify(ROOT / item['path'], item['sha256'])
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
        verify(ROOT / path, expected)
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
        verify(ROOT / path, expected)
    compact_mcp = read(DEST / 'compact-mcp/verification.json')
    if not compact_mcp['passed'] or compact_mcp['exitCode'] != 0:
        raise ValueError('Compact MCP integration failed')
    for key in ('inputs', 'inputSnapshots', 'outputs'):
        records(compact_mcp[key])
    for distribution in compact_mcp['testerDependencies']['distributions']:
        records(distribution['metadata'])
    records(compact_mcp['testerDependencies']['sdkPythonFiles'])
    compact_base = harness_base / 'compact-endpoint'
    compact_harness = read(compact_base / 'verification.json')
    for path, expected in compact_harness['hms_inputs_sha256'].items():
        verify(ROOT / path, expected)
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
    corpus = read(DEST / 'corpus-platform-audit.json')
    report = {
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'command': 'python3 scripts/audit_endpoint_evidence.py', 'passed': True,
        'scope': 'Retained input/output hash consistency and cross-receipt links for current original endpoint/compact host, 280-test Python runtime, compact MCP, finite boot allocator and pinned Harness evidence; prior 241-test/1f0762af and 278-test/335a82eb runtime receipts checked against explicit historical archives. No tests or acquired programs executed by this audit.',
        'hash_assertions_verified': checks, 'unique_files_verified': len(unique),
        'receipts': receipts, 'auditor_sha256': digest(Path(__file__).resolve()),
        'summary': {'python_tests': runtime['tests'], 'native_cases': native['native_tests'],
                    'current_host_mcp_sdk_replies': mcp['validatedReplies'],
                    'compact_mcp_scenarios': compact_mcp['summary']['scenarioExecutions'],
                    'boot_allocator_native_cases_per_build': boot['native'][0]['results']['cases'],
                    'avr_eeprom_register_model_cases_per_build': eeprom['native'][0]['result']['cases'],
                    'framed_integration_scenarios': integration['scenarios'],
                    'avr_flash_bytes': avr['linked_harness_flash_bytes'],
                    'avr_static_ram_bytes': avr['linked_harness_static_ram_bytes'],
                    'avr_foreground_static_stack_bound': avr['foreground_stack_bound_bytes'],
                    'research_source_records_in_separate_corpus_audit': corpus['source_records']},
        'limitations': ['Hash consistency is not an independent rerun, hardware validation or trust attestation.',
                       'Research corpus integrity is checked by scripts/audit_corpus.py; this audit fingerprints its retained report.',
                       'Native Harness tests remain pinned to their tested commits; subsequent live-head movement is not validated by these receipts.',
                       'AVR compiler stack analysis and planning reservations do not measure runtime fit, interrupts or physical deadlines.'],
    }
    (DEST / 'endpoint-evidence-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'hash_assertions': checks, 'unique_files': len(unique),
                      'artifact': 'artifacts/verification/endpoint-evidence-audit.json'}))


if __name__ == '__main__':
    main()

"""Exact-byte joins for retained AVR integration evidence; no executable loading."""
import ast
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    assert not (HERE / 'index.json').exists()
    receipts = {}
    processes = []
    for name, passed in [('checks-native.json', False), ('checks-native-attempt-2.json', True),
                         ('checks-avr.json', False), ('checks-avr-attempt-2.json', True)]:
        receipt = read(HERE / name)
        assert receipt['requested_checks_completed'] is passed
        assert receipt['sources_unchanged'] and receipt['copied_sources_unchanged'] and receipt['owned_groups_absent']
        assert not receipt['target_executed'] and not receipt['public_edits']
        copied = HERE / receipt['frozen_source_copy_root']
        for source, sha in receipt['sources'].items():
            assert digest(copied / source) == sha
            if passed:
                assert digest(HERE / source) == sha
        for command in receipt['commands']:
            assert command['direct_child_reaped'] and not command['group_members_after_cleanup']
            assert not Path('/proc', str(command['pid'])).exists()
            assert command['termination_reason'] is None
            assert not command['leftover_members_after_direct_child']
            if passed:
                assert command['exit_code'] == 0 and not (HERE / command['stderr']).read_bytes()
            processes.append(dict(receipt=name, pid=command['pid'], pgid=command['pgid'],
                                  exitCode=command['exit_code'], reaped=True, absent=True))
        receipts[name] = receipt
    assert len(processes) == 30
    failed_native = receipts['checks-native.json']
    assert len(failed_native['commands']) == 3 and failed_native['commands'][-1]['exit_code'] == 1
    assert (HERE / 'build/native/probe-plain.stderr').read_text() == 'line 232: wire_request(p,12,4)==0\n'
    assert not receipts['checks-avr.json']['commands']
    assert 'No such file or directory' in receipts['checks-avr.json']['error']
    native = receipts['checks-native-attempt-2.json']['native']
    assert digest(Path(native['compiler_path'])) == native['compiler_sha256']
    assert native['original']['passed'] and native['original']['pipe_smoke'] == 'passed'
    assert native['original']['native_tests']['cases'] == 26
    assert native['original']['native_tests']['assertions'] == 2548
    for mode in ('plain', 'asan'):
        probe = native['integration'][mode]
        assert probe['status'] == 'passed' and probe['cases'] == 11 and probe['assertions'] == 143471
        assert probe['wireOracleSteps'] == 20000 and probe['interruptSnapshots'] == 256
        assert not probe['targetExecuted']
    avr = receipts['checks-avr-attempt-2.json']['avr']
    assert avr['flash_bytes'] == 21778 and avr['static_sram_bytes'] == 1343
    assert avr['static_plus_512_stack_bytes'] == 1855 and not avr['target_executed']
    assert not avr['target_runtime_fit_demonstrated']
    for path, row in avr['toolchain_pins'].items():
        assert digest(Path(path)) == row['sha256']
    restorations = list((HERE / 'toolchains').glob('*/restoration.json'))
    assert len(restorations) == 1
    restoration = read(restorations[0])
    assert restoration['completed'] and not restoration['acquired_code_executed']
    assert digest(HERE / 'restore_toolchain.py') == restoration['script_sha256']
    assert digest(Path(restoration['archive'])) == restoration['archive_sha256']
    for name, sha in restoration['regular_or_link_hashes'].items():
        assert digest(restorations[0].parent / name) == sha
    for row in read(HERE / 'source-inputs.json')['originalFiles']:
        assert digest(ROOT / row['path']) == row['sha256']
    source_review = read(HERE / 'source-reading.json')
    manual = ROOT / source_review['manual']
    assert digest(manual) == source_review['manualSha256']
    for row in source_review['coverage']:
        assert digest(HERE / row['path']) == row['sha256']
    arduino = source_review['arduinoTxOrdering']
    assert digest(ROOT / arduino['path']) == arduino['sha256']
    assert digest(HERE / arduino['extract']) == arduino['extractSha256']
    stack = read(HERE / 'combined-stack-analysis.json')
    for name, sha in stack['inputs'].items():
        assert digest(HERE / name) == sha
    assert stack['indirect_sites'] == 17 and stack['steady_foreground']['bytes'] == 295
    assert stack['startup_interrupts_disabled']['bytes'] == 149
    assert stack['reservation']['actual_max_non_nested_isr_bytes'] == 38
    assert stack['reservation']['planning_stack_requirement_bytes'] == 487
    assert stack['reservation']['passes_combined_arithmetic_constraints']
    assert not stack['target_runtime_fit_demonstrated'] and not stack['target_executed']
    # Written assessments are required; generated evidence remains separately pinned.
    for name in ('README.md', 'NEXT.md', 'STACK-REVIEW.md', 'GENERATED-USART-ISR-REVIEW.md'):
        assert (HERE / name).is_file() and (HERE / name).stat().st_size > 0
    generated = read(HERE / 'generated-usart-isr-review.json')
    assert not generated['target_executed'] and not generated['target_runtime_fit_demonstrated']
    assert generated['tx']['inclusive_instruction_cycles'] == 8
    assert generated['tx']['minimum_admitted_8n1_frame_cpu_cycles'] == 80
    assert generated['stack_cross_review']['planning_requirement_bytes'] == 487
    for row in generated['pins']:
        assert digest(ROOT / row['path']) == row['sha256']
    baseline = ROOT / 'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    baseline_sha = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    assert digest(baseline) == baseline_sha
    public = read(baseline)['files']
    assert len(public) == 244 and all(digest(ROOT / row['path']) == row['sha256'] for row in public)
    related = []
    for name, sha in [
        ('artifacts/verification/full-storage-attribution', '3f673fabcdab31e027b1d535d63a1a8302350a755fde4be94bb8ed53fecdd165'),
        ('research/embedded/io-feature-review', 'eea75a0908d33058276e721dbcb11263be98d070b1a807b9b0a8d9c890d1e030'),
        ('artifacts/design/hub-provider-gap', '19babba0c893b496d8728681fca60eb729bba6f8f4b22a442b11a35578725a9c')]:
        directory = ROOT / name
        assert digest(directory / 'index.json') == sha
        indexed = read(directory / 'index.json')['files']
        assert all(digest(directory / row['path']) == row['sha256'] for row in indexed)
        related.append(dict(path=name, indexSha256=sha, filesExact=len(indexed)))
    documents = [dict(path=name, sha256=digest(ROOT / name)) for name in [
        'README.md', 'PROGRESS.md', 'docs/control-storage.md', 'docs/io-driver-hub-control.md',
        'docs/prompt-to-pat.md', 'docs/embedded-evidence.md']]
    for path in HERE.glob('*.py'):
        ast.parse(path.read_bytes(), filename=str(path))
    save(HERE / 'RESULTS.json', dict(status='native-models-and-target-static-arithmetic-passed',
         integrationCases=11, integrationAssertionsPerMode=143471, originalEndpointCases=26,
         flashBytes=21778, staticSramBytes=1343, planningStackBytes=487, reservedStackBytes=512,
         staticPlusReservedStackBytes=1855, publicInputsExact=244, publicRuntimeChanged=False,
         persistentApplicationsImplemented=False, physicalIOQualified=False, targetExecuted=False,
         targetRuntimeFitDemonstrated=False, goalComplete=False))
    save(HERE / 'AUDIT.json', dict(status='verified', processes=processes,
         publicInputsExact=244, publicReceiptSha256=baseline_sha,
         receiptHashes={name: digest(HERE / name) for name in receipts},
         combinedStackSha256=digest(HERE / 'combined-stack-analysis.json'),
         relatedEvidence=related, currentDocuments=documents,
         primaryAgentReview=True, independentReview='generated TX, ISR and stack source review',
         publicRuntimeChanged=False))
    rows, links = [], []
    for path in sorted(HERE.rglob('*')):
        if path.is_symlink():
            assert path.is_file() and path.resolve().is_relative_to(HERE / 'toolchains')
            links.append(dict(path=str(path.relative_to(HERE)), target=os.readlink(path),
                              targetSha256=digest(path), allocatedBytes=path.lstat().st_blocks * 512))
        elif path.is_file():
            info = path.stat()
            assert info.st_size <= 16 * 1024**2
            rows.append(dict(path=str(path.relative_to(HERE)), bytes=info.st_size,
                             allocatedBytes=info.st_blocks * 512, sha256=digest(path)))
    assert len(links) == 8
    allocated = sum(row['allocatedBytes'] for row in rows + links)
    assert allocated < 1024**3
    save(HERE / 'index.json', dict(files=rows, symlinks=links, filesBeforeIndex=len(rows),
         allocatedBytesBeforeIndex=allocated, status='sealed-isolated-model-and-static-evidence',
         publicRuntimeChanged=False, targetExecuted=False))
    assert all(digest(HERE / row['path']) == row['sha256'] for row in rows)
    assert all(os.readlink(HERE / row['path']) == row['target'] and
               digest(HERE / row['path']) == row['targetSha256'] for row in links)
    print(json.dumps(dict(indexSha256=digest(HERE / 'index.json'), files=len(rows),
                         symlinks=len(links), bytes=sum(r['bytes'] for r in rows), allocatedBytesBeforeIndex=allocated)))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Independent original host probes and read-only AVR instruction review.

No AVR ELF is executed. Only the native shim and an archive-pinned objdump run.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
AUTHOR = ROOT / 'artifacts/verification/avr-eeprom'
SOURCES = ('protocol/platform/avr_eeprom.c', 'protocol/platform/avr_eeprom.h',
           'protocol/platform/boot_epoch.c', 'protocol/platform/boot_epoch.h',
           'tests/avr_eeprom_probe.c', 'scripts/check_avr_eeprom.py')
PRIMARY = ROOT / 'research/constrained/clock-boot-platform'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size}


def main():
    author = json.loads((AUTHOR / 'review.json').read_text())
    assert sha(AUTHOR / 'review.json') == '57c9def7a3a8bb6e7bdb35d495bc2d88b997bf1eaf848c090d1172992e7176de'
    assert author['passed'] is True
    for item in author['files'] + author['outputs']:
        assert sha(ROOT / item['path']) == item['sha256'], item['path']
    inputs = [record(ROOT / relative) for relative in SOURCES]
    inputs.extend(record(path) for path in (OUT / 'probes.c', Path(__file__).resolve(), AUTHOR / 'review.json',
        AUTHOR / 'disassembly.txt', AUTHOR / 'avr-eeprom-probe.elf', AUTHOR / 'instruction-review.json',
        PRIMARY / 'raw/atmega328p-family-ds40002061b.pdf', PRIMARY / 'text/atmega328p-family-ds40002061b.txt'))
    compiler = Path('/usr/bin/gcc').resolve()
    report = {'schema': 'hms.avr-eeprom-independent-review/1', 'passed': False,
              'startedUtc': datetime.now(timezone.utc).isoformat(), 'inputs': inputs, 'commands': [],
              'sourceCoverage': {'fullFiles': list(SOURCES),
                'scope': 'Adapter, header, original native probe and checker read completely; generic boot module rereviewed from preceding independent review.'},
              'authorReceipt': record(AUTHOR / 'review.json'),
              'authorArtifactHashesVerified': len(author['files']) + len(author['outputs']),
              'hostCompiler': {'path': str(compiler), 'sha256': sha(compiler),
                  'version': subprocess.check_output([str(compiler), '--version'], text=True).splitlines()[0]},
              'primarySourceCrosscheck': {
                'url': 'https://ww1.microchip.com/downloads/en/DeviceDoc/ATmega48A-PA-88A-PA-168A-PA-328-P-DS-DS40002061B.pdf',
                'version': 'Microchip DS40002061B, 2020',
                'selectedTextLfRanges': [[1255, 1326], [1555, 1758]],
                'scope': 'SREG/CLI example and EEPROM register/address/mode/launch/read sequence; not a whole datasheet or errata review.',
                'onlineAttempt': 'Public official PDF open failed because 33,319,446 bytes exceeds browser content limit. Exact already-retained official PDF/text were used.'},
              'manualCurrentInstructionConclusion': {
                'status': 'Current pinned compiled sequence matches reviewed source for EEPROM mode/data, masked launch, saved SREG restoration and address guard.',
                'details': [
                  'ready reads EECR 0x1f, rejects EERIE bit 3, waits EEPE bit 1, then checks SPMCSR 0x37 bit 0. exclusive_ready is a single-budget masked recheck.',
                  'read_at saves SREG 0x3f into r28 at 0x112, executes CLI, and restores the same r28 at 0x12a on both successful and refused paths.',
                  'program saves SREG into r15 at 0x28e before CLI. exclusive_ready does not clobber r15. Refusal and launch paths restore r15 at 0x2aa or 0x2c2.',
                  'Program checks erased 0xff, writes EEDR 0 via ABI zero register r1 at 0x2b8, loads r25=0x20 at 0x2ba and writes EECR at 0x2bc: EEPM1=1,EEPM0=0 (write-only),EERIE=0.',
                  'Adjacent SBI 0x1f,2 at 0x2be and SBI 0x1f,1 at 0x2c0 provide the reviewed four-cycle launch sequence while masked.',
                  'Unsigned 32-bit address guards precede EEPROM accesses. Busy waiting remains outside explicit masked windows; read_at masks only its recheck/access window.'
                ]},
              'findings': [{
                'id': 'automated-instruction-dataflow-scope', 'severity': 'non-blocking validation scope limitation',
                'status': 'Acknowledged; frozen source/binary unchanged and manually correct.',
                'description': 'inspect_launch checks adjacency, guard/mask control-flow and register-write presence, but does not establish the selected mode value or SREG saved-value dataflow.',
                'acceptedTextMutations': [],
                'qualification': 'These mutate disassembly text only, not ELF bytes or the actual adapter. They demonstrate checker scope, not a production defect.'}],
              'limitations': [
                'Independent host shim tests register-flow choices, not AVR instruction timing, silicon behavior, electrical power loss, retention or target-only write-fault containment.',
                'All 256 SREG patterns refer to simulated saved/restored snapshots at the masked-window callbacks. Actual ALU flags may change after restoration; no C-call ABI guarantee to preserve all flags is claimed.',
                'Poll budget bounds readiness checks across one callback, not wall time or interrupt latency. ISR/EEPROM/SPM ownership and immutable configuration remain platform obligations.',
                'Generic boot reservation latches callback failure. A timeout after launch or completion does not mean no effect; only a new startup may consume/skip the cell under the declared storage model.',
                'No AVR target binary, MCU emulator, physical EEPROM/peripheral, programmer or acquired endpoint implementation ran.',
                'No electrical durability/BOOT_QUALIFIED assertion, complete firmware fit, whole-call-stack bound, watchdog deadline or independent stop is established.',
                'Original 12-case suite results remain in the author receipt; this review runs separate 5-group native probes and read-only objdump/checker analysis.'
              ]}
    started = time.monotonic()
    environment = os.environ.copy()
    environment.update(ASAN_OPTIONS='detect_leaks=1:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')

    def run(name, command):
        result = subprocess.run([str(x) for x in command], cwd=ROOT, env=environment,
                                capture_output=True, text=True, timeout=60)
        (OUT / (name + '.stdout.log')).write_text(result.stdout)
        (OUT / (name + '.stderr.log')).write_text(result.stderr)
        report['commands'].append({'argv': [str(x) for x in command], 'exitCode': result.returncode,
                                   'stdout': name + '.stdout.log', 'stderr': name + '.stderr.log'})
        assert result.returncode == 0 and not result.stderr, result.stderr
        return result.stdout

    try:
        flags = ['-std=c11', '-g', '-Wall', '-Wextra', '-Wconversion', '-Werror', '-Wvla', '-O1',
                 '-DHMS_AVR_EEPROM_TEST', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie']
        run('compile', [compiler, *flags, '-I', 'protocol/platform', 'protocol/platform/avr_eeprom.c',
            'protocol/platform/boot_epoch.c', OUT / 'probes.c', '-o', OUT / 'probes-asan'])
        result = json.loads(run('native-probes', [OUT / 'probes-asan']))
        assert result['cases'] == 5 and result['sreg_patterns'] == 256 and result['write_budget_scenarios'] == 360
        assert result['nonzero_readback_values'] == 255 and result['target_executed'] is False
        report['independentNativeResults'] = result
        objdump_path, objdump_pin = next((Path(path), pin) for path, pin in author['avr']['archive_verified_files'].items()
                                        if path.endswith('/bin/avr-objdump'))
        assert sha(objdump_path) == objdump_pin['sha256']
        report['objdump'] = {'path': str(objdump_path), **objdump_pin}
        disassembly = run('objdump', [objdump_path, '-d', AUTHOR / 'avr-eeprom-probe.elf'])
        assert disassembly == (AUTHOR / 'disassembly.txt').read_text(), 'Pinned ELF/disassembly correspondence changed'
        spec = importlib.util.spec_from_file_location('original_avr_eeprom_checker', ROOT / 'scripts/check_avr_eeprom.py')
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        checker.inspect_launch(disassembly)
        mutations = [
            ('erase_only_mode', ' 2ba:\t90 e2       \tldi\tr25, 0x20', ' 2ba:\t90 e2       \tldi\tr25, 0x10'),
            ('wrong_sreg_restore_source', ' 2c2:\tff be       \tout\t0x3f, r15', ' 2c2:\tff be       \tout\t0x3f, r1')]
        for name, original, changed in mutations:
            assert original in disassembly
            mutated = disassembly.replace(original, changed, 1)
            checker.inspect_launch(mutated)
            report['findings'][0]['acceptedTextMutations'].append({'name': name, 'original': original,
                'changed': changed, 'checkerAccepted': True, 'mutatedTextSha256': hashlib.sha256(mutated.encode()).hexdigest()})
        for item in inputs:
            assert sha(ROOT / item['path']) == item['sha256'], item['path']
        for relative in SOURCES:
            destination = OUT / 'sources' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / relative).read_bytes())
        lines = (PRIMARY / 'text/atmega328p-family-ds40002061b.txt').read_bytes().split(b'\n')
        for start, end in report['primarySourceCrosscheck']['selectedTextLfRanges']:
            (OUT / f'ds40002061b-lines-{start}-{end}.txt').write_bytes(b'\n'.join(lines[start-1:end]) + b'\n')
        report['sourceSnapshots'] = [record(path) for path in sorted((OUT / 'sources').rglob('*')) if path.is_file()]
        report['passed'] = True
    except BaseException as error:
        report['failure'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['elapsedSeconds'] = round(time.monotonic() - started, 3)
        report['finishedUtc'] = datetime.now(timezone.utc).isoformat()
        report['outputs'] = [record(path) for path in sorted([*OUT.glob('*.log'), *OUT.glob('*.txt'), OUT / 'probes-asan']) if path.is_file()]
        (OUT / 'review.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': report['passed'], **report['independentNativeResults'],
                      'acceptedCheckerTextMutations': len(report['findings'][0]['acceptedTextMutations']),
                      'targetExecuted': False}))


if __name__ == '__main__':
    main()

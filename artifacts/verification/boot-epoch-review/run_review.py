#!/usr/bin/env python3
"""Reproduce the independent original native allocator probes, not hardware qualification."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size}


def main():
    compiler = Path('/usr/bin/gcc').resolve()
    sources = [ROOT / 'protocol/platform/boot_epoch.c', ROOT / 'protocol/platform/boot_epoch.h',
               ROOT / 'tests/boot_epoch_tests.c', OUT / 'probes.c', Path(__file__).resolve()]
    before = [record(path) for path in sources]
    report = {'schema': 'hms.boot-epoch-independent-review/1', 'passed': False,
              'startedUtc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
              'inputs': before, 'compiler': {'path': str(compiler), 'sha256': sha(compiler),
              'version': subprocess.check_output([str(compiler), '--version'], text=True).splitlines()[0]},
              'commands': [], 'sourceReview': {
                  'scope': 'Entire current boot_epoch.c, boot_epoch.h and boot_epoch_tests.c read; original allocator only.',
                  'blockingFindings': [],
                  'resolvedFindings': [{'id': 'incarnation-agreement-test',
                      'finding': 'The original endpoint reset-domain test used different allocator and endpoint incarnation bytes; it established only numeric boot mismatch.',
                      'resolution': 'Root changed the native fixture incarnation to 0102030405060708090a0b0c0d0e0f10 and added 16 bytewise callback equality assertions before endpoint initialization. Independently reread before this receipt.',
                      'status': 'resolved-in-reviewed-source'}],
                  'conclusions': [
                      'No algorithmic defect found under the declared immutable header, exclusive owner, stable completed-byte and target-only interrupted-write assumptions.',
                      'Every non-0xff cell is consumed. A failed attempt publishes no epoch; a reset either retries an unchanged erased cell or skips the torn consumed cell.',
                      'Inclusive final byte at UINT32_MAX is permitted without overflow; capacity is bounded to 1..65535 and exhaustion never wraps.',
                      'Attempt latch precedes callbacks. Same-owner reentry returns IN_PROGRESS; no epoch is exposed until successful durable programming and exact zero readback.',
                      'Existing setjmp tests only use unchanged or subsequently assigned automatic values after longjmp; no indeterminate-local defect found.',
                      'Existing test provisioning uses the production header helper, so an independent literal-header oracle was added here.',
                      'Existing tests explicitly demonstrate rollback of the last consumed cell to 0xff can reuse an epoch; they do not falsely claim rollback immunity.'
                  ]},
              'limitations': [
                  'No electrical EEPROM/flash, brownout, retention, NVM controller, address corruption or physical power-cut qualification.',
                  'Native synthetic storage model only. No device, peripheral, MCU binary or emulator was executed.',
                  'Callbacks/configuration remain trusted, immutable, bounded and serialized. Deliberate callback memory corruption or arbitrary invalid pointers are outside the API contract.',
                  'RAM reservation initialization is a startup/reset boundary. Reinitializing it during ordinary endpoint activity is forbidden by the header contract.',
                  'Native sanitizer execution is this review evidence; original 11-case suite results are owned by the root build receipt and were not rerun here.',
                  'Assertion count includes callback address/phase checks; 6 independent groups are not 546374 distinct fault scenarios.'
              ]}
    started = time.monotonic()
    flags = ['-std=c11', '-g', '-Wall', '-Wextra', '-Wconversion', '-Werror', '-Wvla',
             '-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie']
    compile_command = [str(compiler), *flags, '-I', 'protocol/platform', 'protocol/platform/boot_epoch.c',
                       str((OUT / 'probes.c').relative_to(ROOT)), '-o', str(OUT / 'probes-asan')]
    try:
        for name, command in [('compile', compile_command), ('run', [str(OUT / 'probes-asan')])]:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
            (OUT / (name + '.stdout.log')).write_text(result.stdout)
            (OUT / (name + '.stderr.log')).write_text(result.stderr)
            report['commands'].append({'argv': command, 'cwd': str(ROOT), 'exitCode': result.returncode,
                                       'stdout': name + '.stdout.log', 'stderr': name + '.stderr.log'})
            assert result.returncode == 0 and not result.stderr, result.stderr
            if name == 'run':
                report['independentProbeResults'] = json.loads(result.stdout)
                assert report['independentProbeResults']['cases'] == 6
        assert [record(path) for path in sources] == before, 'Reviewed sources changed during probes'
        snapshot = OUT / 'reviewed-sources'
        for path in sources:
            destination = snapshot / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
        report['sourceSnapshots'] = [record(path) for path in sorted(snapshot.rglob('*')) if path.is_file()]
        report['passed'] = True
    except BaseException as error:
        report['failure'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['elapsedSeconds'] = round(time.monotonic() - started, 3)
        report['finishedUtc'] = datetime.now(timezone.utc).isoformat()
        report['outputs'] = [record(path) for path in sorted([OUT / 'probes-asan', *OUT.glob('*.log')]) if path.is_file()]
        (OUT / 'review.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': report['passed'], **report['independentProbeResults']}))


if __name__ == '__main__':
    main()

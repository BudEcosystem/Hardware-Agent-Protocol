#!/usr/bin/env python3
"""Compile and run only the retained original HMS endpoint review probes."""
from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import time

HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    pins = json.loads((HERE / 'source-pins.json').read_text())
    for path, digest in pins.items():
        assert sha(HERE / 'snapshot' / path) == digest, path
    inputs = [HERE / 'probe.c', HERE / 'vectors.h', HERE / 'run_review.py', HERE / 'source-pins.json']
    before = {str(path.relative_to(HERE)): sha(path) for path in inputs}
    command = ['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined,address', '-g', '-Isnapshot',
               'probe.c', 'snapshot/protocol/endpoint/endpoint.c', 'snapshot/protocol/endpoint/link.c',
               'snapshot/protocol/serial/frame.c', 'snapshot/tests/endpoint_fixture.c', '-o', 'build/probe']
    (HERE / 'build').mkdir(exist_ok=True)
    started = time.monotonic()
    compiled = subprocess.run(command, cwd=HERE, capture_output=True, text=True, timeout=60)
    (HERE / 'compile.stdout.txt').write_text(compiled.stdout)
    (HERE / 'compile.stderr.txt').write_text(compiled.stderr)
    compiled.check_returncode()
    binary_hash = sha(HERE / 'build/probe')
    run_command = ['./build/probe']
    result = subprocess.run(run_command, cwd=HERE, capture_output=True, text=True, timeout=30)
    (HERE / 'run.stdout.txt').write_text(result.stdout)
    (HERE / 'run.stderr.txt').write_text(result.stderr)
    result.check_returncode()
    assert result.stdout.count('PASS ') == 16
    assert result.stdout.endswith('16 independent original-code probes passed\n')
    for path, digest in pins.items():
        assert sha(HERE / 'snapshot' / path) == digest, path
    assert before == {str(path.relative_to(HERE)): sha(path) for path in inputs}
    assert sha(HERE / 'build/probe') == binary_hash
    version = subprocess.run(['cc', '--version'], cwd=HERE, capture_output=True, text=True, timeout=10)
    version.check_returncode()
    (HERE / 'compiler-version.txt').write_text(version.stdout)
    record = {
        'schema': 'hms-endpoint-independent-probes/1',
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'passed': True, 'probes': 16, 'elapsed_seconds': round(time.monotonic() - started, 6),
        'cwd': str(HERE), 'compile_argv': command, 'compile_exit_code': compiled.returncode,
        'run_argv': run_command, 'run_exit_code': result.returncode,
        'source_hashes': pins, 'review_inputs': before,
        'outputs': {name: sha(HERE / name) for name in ['build/probe', 'compile.stdout.txt', 'compile.stderr.txt',
                    'run.stdout.txt', 'run.stderr.txt', 'compiler-version.txt']},
        'scope': 'Original native C code plus synthetic fixture only; no acquired code or physical hardware execution.',
        'limitations': ['Synthetic trusted flags/clock and direct public storage mutation deliberately exercise boundaries.',
                       'No hardware timing, actual preemption, native controller queue, physical stop, NVM or durable effect guarantee.',
                       'The probe is bounded regression evidence, not exhaustive state-space verification.'],
    }
    (HERE / 'probe-run.json').write_text(json.dumps(record, indent=2) + '\n')
    print(result.stdout, end='')

if __name__ == '__main__':
    main()

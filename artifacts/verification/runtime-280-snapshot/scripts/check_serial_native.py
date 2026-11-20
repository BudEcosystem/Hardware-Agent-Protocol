#!/usr/bin/env python3
"""Compile only original HMS framing code; stress it with synthetic bytes.

Requires native gcc with address/undefined sanitizers. No serial port is opened.
"""
from pathlib import Path
import datetime
import hashlib
import json
import platform
import random
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ['protocol/serial/frame.c', 'protocol/serial/frame.h', 'protocol/serial/frame.py',
           'tests/test_serial_frame.py', 'tests/serial_frame_driver.c',
           'tests/fixtures/serial-frames.json', 'scripts/check_serial_native.py']
FLAGS = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Wconversion', '-Werror',
         '-fsanitize=address,undefined', '-fno-omit-frame-pointer']


def main():
    with tempfile.TemporaryDirectory(prefix='hms-frame-verify-') as directory:
        binary = Path(directory) / 'frame-sanitized'
        subprocess.run(['gcc', *FLAGS, str(ROOT / 'protocol/serial/frame.c'),
                        str(ROOT / 'tests/serial_frame_driver.c'), '-o', str(binary)],
                       check=True, capture_output=True)
        rng = random.Random(20261106)
        wire = bytes(rng.randrange(256) for _ in range(1_000_000))
        vectors = json.loads((ROOT / 'tests/fixtures/serial-frames.json').read_text())
        wire += b'\x7e' + b''.join(bytes.fromhex(v['wire_hex']) for v in vectors)
        result = subprocess.run([str(binary)], input=wire, capture_output=True, check=True)
        frames = [line for line in result.stdout.splitlines() if line.startswith(b'F ')]
        if result.stderr or len(frames) != len(vectors):
            raise RuntimeError('Unexpected sanitizer output or recovered-frame count')
        for line, vector in zip(frames, vectors):
            expected, escaped = bytearray(), False
            for byte in bytes.fromhex(vector['wire_hex'])[1:-1]:
                if escaped:
                    expected.append(byte ^ 0x20)
                    escaped = False
                elif byte == 0x7D:
                    escaped = True
                else:
                    expected.append(byte)
            if escaped or bytes.fromhex(line[2:].decode()) != bytes(expected):
                raise RuntimeError('Recovered frame differs from retained wire vector')
        native_size = int(subprocess.check_output([str(binary), '--size']))
    report = {
        'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'command': 'python3 scripts/check_serial_native.py',
        'compiler': subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0],
        'platform': platform.platform(), 'flags': FLAGS,
        'native_parser_size_bytes': native_size, 'stress_seed': 20261106,
        'input_bytes': len(wire), 'expected_valid_frames': len(vectors),
        'actual_valid_frames': len(frames), 'sanitizer_exit': result.returncode,
        'sanitizer_stderr': result.stderr.decode(),
        'source_hashes': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
        'scope': 'Native host framing only; no MCU, UART, authority, runtime, device or physical timing test',
    }
    output = ROOT / 'artifacts/verification/serial-frame.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Native parser: {native_size} bytes; {len(wire)} synthetic input bytes; '
          f'{len(frames)} expected frames recovered; ASan/UBSan clean.')
    print('Report:', output.relative_to(ROOT))


if __name__ == '__main__':
    main()

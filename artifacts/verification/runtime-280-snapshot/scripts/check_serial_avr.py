#!/usr/bin/env python3
"""Cross-compile original HMS parser; retain link/ABI/section evidence only.

No target execution, simulator, serial discovery, upload or hardware I/O.
Pass --toolchain-bin for an isolated trusted AVR GCC toolchain, or use PATH.
The acquired Arduino reference core is not compiled or linked by this check.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'artifacts/verification/serial-avr-build'
SOURCES = ['protocol/serial/frame.c', 'protocol/serial/frame.h',
           'tests/serial_frame_avr_driver.c', 'scripts/check_serial_avr.py']
FLAGS = ['-mmcu=atmega328p', '-DF_CPU=16000000UL', '-std=c11', '-Os',
         '-Wall', '-Wextra', '-Wconversion', '-Werror', '-ffunction-sections',
         '-fdata-sections', '-fno-common', '-fstack-usage']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--toolchain-bin', type=Path)
    opts = args.parse_args()
    commands = []

    def tool(name):
        path = opts.toolchain_bin / name if opts.toolchain_bin else shutil.which(name)
        if path is None or not Path(path).is_file():
            raise SystemExit(f'Missing trusted tool {name}; provide --toolchain-bin')
        return str(Path(path).resolve())

    def run(argv):
        completed = subprocess.run(argv, cwd=ROOT, check=True, capture_output=True, text=True)
        commands.append({'argv': argv, 'exit_code': completed.returncode,
                         'stdout': completed.stdout, 'stderr': completed.stderr})
        return completed.stdout

    BUILD.mkdir(parents=True, exist_ok=True)
    gcc = tool('avr-gcc')
    compiler = run([gcc, '--version']).splitlines()[0]
    target = run([gcc, '-dumpmachine']).strip()
    objects = []
    for source, name in [('protocol/serial/frame.c', 'frame'),
                         ('tests/serial_frame_avr_driver.c', 'driver')]:
        obj = BUILD / f'{name}.o'
        run([gcc, *FLAGS, '-c', source, '-o', str(obj.relative_to(ROOT))])
        objects.append(str(obj.relative_to(ROOT)))
    elf = str((BUILD / 'serial-frame.elf').relative_to(ROOT))
    map_path = str((BUILD / 'serial-frame.map').relative_to(ROOT))
    # This toolchain's generic avr5 linker script otherwise advertises regions
    # larger than this MCU. Pin physical capacities; also check UNO app limit.
    run([gcc, '-mmcu=atmega328p', '-Os', '-Wl,--gc-sections',
         '-Wl,--defsym=__TEXT_REGION_LENGTH__=32768',
         '-Wl,--defsym=__DATA_REGION_LENGTH__=2048',
         '-Wl,--defsym=__DATA_REGION_ORIGIN__=0x800100',
         '-Wl,--defsym=__EEPROM_REGION_LENGTH__=1024',
         f'-Wl,-Map={map_path}', *objects, '-o', elf])
    sections_text = run([tool('avr-size'), '-A', elf])
    (BUILD / 'sections.txt').write_text(sections_text)
    sections = {}
    for line in sections_text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].startswith('.'):
            sections[parts[0]] = {'bytes': int(parts[1]), 'address': int(parts[2])}
    symbol_text = run([tool('avr-nm'), '-S', '--size-sort', elf])
    (BUILD / 'symbols.txt').write_text(symbol_text)
    symbols = []
    for line in symbol_text.splitlines():
        fields = line.split()
        if len(fields) == 4:
            address, size, kind, name = fields
            symbols.append({'name': name, 'bytes': int(size, 16),
                            'address': int(address, 16), 'type': kind})
    parser = next(s for s in symbols if s['name'] == 'hms_avr_parser')
    if parser['bytes'] != 219:
        raise RuntimeError('Unexpected target parser allocation')
    disassembly = run([tool('avr-objdump'), '-h', '-d', elf])
    (BUILD / 'disassembly.txt').write_text(disassembly)
    undefined = run([tool('avr-nm'), '-u', elf])
    if undefined.strip():
        raise RuntimeError('Unexpected undefined symbols in final ELF')
    stack_records = []
    for name in ('frame.su', 'driver.su'):
        for line in (BUILD / name).read_text().splitlines():
            location, count, qualification = line.split('\t')
            stack_records.append({'location': location, 'bytes': int(count),
                                  'qualification': qualification})
    section_bytes = lambda n: sections.get(n, {}).get('bytes', 0)
    flash_bytes = section_bytes('.text') + section_bytes('.data')
    static_ram_bytes = sum(section_bytes(n) for n in ('.data', '.bss', '.noinit'))
    if flash_bytes > 32256 or static_ram_bytes > 2048:
        raise RuntimeError('Linked sections exceed the UNO profile capacity')
    provenance = ROOT / 'research/constrained/avr/manifest.jsonl'
    report = {
        'schema': 'hms-serial-avr-build/1',
        'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope': 'ATmega328P compile/link and static allocation only; no target execution',
        'compiler': compiler, 'compiler_path': gcc, 'compiler_sha256': digest(Path(gcc)),
        'compiler_target': target, 'host': platform.platform(),
        'mcu': 'atmega328p', 'declared_f_cpu_hz': 16000000,
        'flags': FLAGS, 'lto': False, 'commands': commands,
        'source_hashes': {p: digest(ROOT / p) for p in SOURCES},
        'toolchain_provenance_manifest': str(provenance.relative_to(ROOT)),
        'toolchain_provenance_manifest_sha256': digest(provenance),
        'sections': sections,
        'linked_harness_flash_bytes': flash_bytes,
        'linked_harness_static_ram_bytes': static_ram_bytes,
        'capacity_limits': {'physical_flash_bytes': 32768, 'uno_application_flash_bytes': 32256,
                            'sram_bytes': 2048, 'eeprom_bytes': 1024,
                            'basis': 'UNO R3 manual and retained Arduino AVR 1.8.8 boards.txt UNO profile'},
        'parser_object_bytes': parser['bytes'],
        'parser_text_symbols': [s for s in symbols if s['name'].startswith('hms_frame_')],
        'stack_usage_reports': stack_records,
        'artifact_hashes': {str(p.relative_to(ROOT)): digest(p) for p in sorted(BUILD.iterdir()) if p.is_file()},
        'limitations': [
            'This is a parser plus a two-byte mailbox harness and toolchain startup, not complete HMS firmware.',
            'Arduino UART/core, timers, bootloader, operation/session layer, executor, queues and actuation are absent.',
            'Flash is .text + .data; static RAM is .data + .bss + .noinit. No stack/heap headroom claim follows.',
            'GCC .su records are compiler estimates for individual functions, not whole-program stack high-water measurements.',
            'F_CPU is a compile declaration, not oscillator/baud/timing evidence.',
            'No emitted AVR target binary, research core, simulator, physical port or target device was executed.',
            'No physical timing, worst-case execution time, interrupt load, electrical behavior or device support is established.',
        ],
    }
    output = ROOT / 'artifacts/verification/serial-avr.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"AVR parser object: {parser['bytes']} bytes; linked harness flash: "
          f"{report['linked_harness_flash_bytes']} bytes; static RAM: "
          f"{report['linked_harness_static_ram_bytes']} bytes. No target execution.")
    print(output.relative_to(ROOT))


if __name__ == '__main__':
    main()

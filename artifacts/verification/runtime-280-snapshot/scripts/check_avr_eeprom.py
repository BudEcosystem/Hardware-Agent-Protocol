#!/usr/bin/env python3
"""Original AVR EEPROM adapter checks: host register model + AVR cross-link only.

No target program, MCU emulator, peripheral, uploader or acquired implementation
executes. Only original host tests and approved/archive-verified compiler tools.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'artifacts/verification/avr-eeprom'
ARCHIVE = ROOT / 'research/constrained/avr/raw/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2'
ARCHIVE_SHA = 'bd8c37f6952a2130ac9ee32c53f6a660feb79bee8353c8e289eb60fdcefed91e'
FILES = ['protocol/platform/avr_eeprom.c', 'protocol/platform/avr_eeprom.h',
         'protocol/platform/boot_epoch.c', 'protocol/platform/boot_epoch.h',
         'tests/avr_eeprom_probe.c', 'scripts/check_avr_eeprom.py']
UNITS = [('protocol/platform/avr_eeprom.c', 'avr_eeprom'),
         ('protocol/platform/boot_epoch.c', 'boot_epoch'),
         ('tests/avr_eeprom_probe.c', 'probe')]
COMMON = ['-std=c11', '-g', '-Wall', '-Wextra', '-Wconversion', '-Werror', '-Wvla', '-fno-common']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    return {'path': str(Path(path).relative_to(ROOT)), 'sha256': digest(path)}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def instructions(disassembly):
    functions = {}
    current = None
    for line in disassembly.splitlines():
        match = re.match(r'^([0-9a-f]+) <([^>]+)>:', line)
        if match:
            current = match[2]; functions[current] = []
        match = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*([a-z][a-z0-9]*)\s*(.*)', line)
        if match and current:
            target = re.search(r';\s*0x([0-9a-f]+)', line)
            functions[current].append(dict(address=int(match[1], 16), bytes=len(match[2].split()),
                                           op=match[3], operands=match[4].split(';')[0].strip(), line=line,
                                           target=int(target[1], 16) if target else None))
    return functions


def inspect_launch(disassembly):
    functions = instructions(disassembly)
    name = 'hms_avr_eeprom_program_zero_and_sync'
    code = functions[name]
    sites = [i for i, inst in enumerate(code) if inst['op'] == 'sbi' and inst['operands'] == '0x1f, 2']
    require(len(sites) == 1, 'Expected exactly one EEMPE launch site')
    i = sites[0]
    a, b = code[i:i + 2]
    require(b['op'] == 'sbi' and b['operands'] == '0x1f, 1' and
            b['address'] == a['address'] + 2 and a['bytes'] == b['bytes'] == 2,
            'EEMPE/EEPE SBI instructions are not immediately adjacent')
    cli_sites = [j for j in range(i) if code[j]['op'] == 'cli']
    require(cli_sites, 'No interrupt mask before launch')
    start = cli_sites[-1]
    require(any(x['op'] == 'in' and x['operands'].endswith('0x3f') for x in code[max(0, start - 4):start]),
            'No SREG save immediately before mask')
    restores = [j for j in range(i + 2, len(code)) if code[j]['op'] == 'out' and code[j]['operands'].startswith('0x3f,')]
    require(restores, 'No SREG restore after launch')
    require(any(x['op'] == 'out' and x['operands'].startswith('0x20,') for x in code[start:i]),
            'No EEDR write in launch window')
    require(any(x['op'] == 'out' and x['operands'].startswith('0x1f,') for x in code[start:i]),
            'No explicit EEPM selection in launch window')
    guards = {}
    for function in ('hms_avr_eeprom_read_byte', name):
        body = functions[function]
        for j in range(len(body) - 5):
            part = body[j:j + 6]
            reg = part[1]['operands'].split(',')[0]
            expected = [('cp', 'r20, r1'), ('ldi', reg + ', 0x04'),
                        ('cpc', 'r21, ' + reg), ('cpc', 'r22, r1'), ('cpc', 'r23, r1')]
            if [(x['op'], x['operands']) for x in part[:5]] == expected and part[5]['op'] == 'brcs':
                guards[function] = part
        require(function in guards, 'Expected unsigned32 address<1024 guard missing: ' + function)

    # Follow both sides of conditional branches/skips. A linear instruction
    # slice includes refusal-path SREG restores that cannot reach the launch.
    # Prove that every syntactic path to a register access has crossed the
    # address guard, and every path to either launch SBI has CLI still active.
    starts = {body[0]['address']: function for function, body in functions.items() if body}
    for helper in ('ready', 'exclusive_ready'):
        require(not any(x['op'] in ('cli', 'sei', 'call', 'rcall', 'icall') or
                        (x['op'] == 'out' and x['operands'].startswith('0x3f,')) for x in functions[helper]),
                'Readiness helper no longer preserves interrupt state without calls')
    visited_counts = {}
    for function in ('hms_avr_eeprom_read_byte', name, 'read_at'):
        body = functions[function]; indexes = {x['address']: j for j, x in enumerate(body)}
        work = [(0, False, function == 'read_at')]; visited = set()
        guard_address = guards[function][-1]['address'] if function in guards else None
        while work:
            j, masked, valid = work.pop()
            if (j, masked, valid) in visited: continue
            visited.add((j, masked, valid)); inst = body[j]; op = inst['op']; operands = inst['operands']
            if op == 'cli': masked = True
            if op == 'sei' or (op == 'out' and operands.startswith('0x3f,')): masked = False
            if op == 'out' and operands.startswith(('0x21,', '0x22,', '0x20,', '0x1f,')):
                require(valid and masked, 'Unguarded/unmasked EEPROM register write')
            if op == 'sbi' and operands.startswith('0x1f,'):
                require(valid and masked, 'Unguarded/unmasked EEPROM strobe')
            if op == 'ret':
                require(not masked, 'Return without SREG restore'); continue
            if op in ('icall', 'ijmp', 'eicall', 'eijmp'): raise RuntimeError('Unexpected indirect control in adapter')
            if op in ('call', 'rcall'):
                if op == 'rcall' and inst['target'] == inst['address'] + inst['bytes']:
                    pass  # fixed local stack allocation
                else:
                    target = starts.get(inst['target'])
                    require(target in ('ready', 'exclusive_ready', 'read_at'), 'Unreviewed adapter call')
                    if target == 'read_at': require(valid, 'Read helper reached without address check')
                    if masked: require(target == 'exclusive_ready', 'Busy wait/call inside masked region')
            if op in ('jmp', 'rjmp'):
                work.append((indexes[inst['target']], masked, valid)); continue
            if op.startswith('br'):
                work.append((indexes[inst['target']], masked, True if inst['address'] == guard_address else valid))
            if op in ('cpse', 'sbrc', 'sbrs', 'sbic', 'sbis'):
                work.append((j + 2, masked, valid))
            require(j + 1 < len(body), 'Unexpected function fallthrough')
            work.append((j + 1, masked, valid))
        visited_counts[function] = len(visited)
    return {'function': name, 'eempe_address': a['address'], 'eepe_address': b['address'],
            'instructions': [a['line'], b['line']],
            'sbi_cycles_each': 2, 'launch_basis': 'Adjacent ATmega328P two-cycle SBI, within four-cycle EEMPE window; interrupts masked.',
            'masked_launch_region': [x['line'] for x in code[start:restores[0] + 1]],
            'address_guard_instructions': {k: [x['line'] for x in v] for k, v in guards.items()},
            'control_flow_states_checked': visited_counts,
            'scope': 'Compiled instruction/layout evidence, not target execution or wall-time/voltage qualification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain-bin', type=Path, default=Path('/tmp/hms-avr-toolchain-7.3.0-atmel3.6.1-arduino7/avr/bin'))
    args = parser.parse_args()
    before = {p: digest(ROOT / p) for p in FILES}
    BUILD.mkdir(parents=True, exist_ok=True)
    excluded = {'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
                'OBJC_INCLUDE_PATH', 'LIBRARY_PATH', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_AUDIT',
                'DEPENDENCIES_OUTPUT', 'SUNPRO_DEPENDENCIES'}
    environment = {k: v for k, v in os.environ.items() if k not in excluded}
    environment['LC_ALL'] = 'C'
    commands = []

    def run(argv, env=None):
        result = subprocess.run([str(v) for v in argv], cwd=ROOT, env=environment if env is None else env,
                                capture_output=True, text=True, timeout=90)
        commands.append(dict(argv=[str(v) for v in argv], exit_code=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        (BUILD / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        require(result.returncode == 0, f'Command failed: {argv}\n{result.stderr}\n{result.stdout}')
        return result.stdout

    gcc = Path(shutil.which('gcc')).resolve()
    host_compiler = dict(path=str(gcc), sha256=digest(gcc), version=run([gcc, '--version']).splitlines()[0])
    sanitizer_env = environment.copy()
    sanitizer_env.update(ASAN_OPTIONS='detect_leaks=1:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    native = []
    for variant, extra in [('plain', ['-O2']), ('asan', ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie'])]:
        binary = BUILD / ('probe-' + variant)
        flags = COMMON + extra + ['-DHMS_AVR_EEPROM_TEST']
        run([gcc, *flags, *(p for p, _ in UNITS), '-o', binary])
        result = json.loads(run([binary], sanitizer_env))
        require(result['cases'] == 12 and result['modeled_addresses'] == 1024 and
                result['non_erased_values_refused'] == 255 and result['target_executed'] is False,
                'Unexpected register-model coverage')
        native.append(dict(variant=variant, flags=flags, result=result))

    require(digest(ARCHIVE) == ARCHIVE_SHA, 'Approved compiler archive changed')
    hashes, links = {}, {}
    with tarfile.open(ARCHIVE, 'r|bz2') as archive:
        for member in archive:
            if member.isfile():
                h = hashlib.sha256()
                with archive.extractfile(member) as data:
                    for chunk in iter(lambda: data.read(1024 * 1024), b''):
                        h.update(chunk)
                hashes[member.name] = h.hexdigest()
            elif member.islnk():
                links[member.name] = member.linkname
            elif member.issym():
                links[member.name] = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), member.linkname))
    for _ in range(len(links)):
        resolved = {name: hashes[target] for name, target in links.items() if target in hashes}
        if not resolved: break
        hashes.update(resolved)
        for name in resolved: del links[name]
    toolroot = args.toolchain_bin.resolve().parent
    pins = {}

    def pin(path):
        path = Path(path).resolve()
        require(path.is_relative_to(toolroot), 'Dependency outside approved compiler tree')
        member = 'avr/' + str(path.relative_to(toolroot))
        require(digest(path) == hashes.get(member), 'Archive/dependency mismatch: ' + str(path))
        pins[str(path)] = dict(archive_member=member, sha256=digest(path))
        return path

    tools = {name: pin(toolroot / 'bin' / ('avr-' + name)) for name in ('gcc', 'as', 'ld', 'objdump', 'nm', 'size')}
    for name in ['libexec/gcc/avr/7.3.0/cc1', 'libexec/gcc/avr/7.3.0/collect2',
                 'lib/gcc/avr/7.3.0/device-specs/specs-atmega328p', 'avr/bin/as', 'avr/bin/ld']:
        pin(toolroot / name)
    for name in ('libgcc.a', 'libc.a', 'libm.a', 'libatmega328p.a', 'crtatmega328p.o'):
        pin(run([tools['gcc'], '-mmcu=atmega328p', '-print-file-name=' + name]).strip())
    avr_version = run([tools['gcc'], '--version']).splitlines()[0]
    flags = ['-mmcu=atmega328p', *COMMON, '-Os', '-ffunction-sections', '-fdata-sections',
             '-fstack-usage', '-fno-optimize-sibling-calls', '-MD']
    objects = []
    for source, name in UNITS:
        obj = BUILD / (name + '.o')
        run([tools['gcc'], *flags, '-c', source, '-o', obj])
        dependencies = (BUILD / (name + '.d')).read_text().replace('\\\n', ' ').split(':', 1)[1].split()
        for dep in dependencies:
            path = Path(dep)
            if not path.is_absolute(): path = ROOT / path
            path = path.resolve()
            if path.is_relative_to(toolroot): pin(path)
            else: require(path.is_relative_to(ROOT) and str(path.relative_to(ROOT)) in FILES, 'Unexpected original include')
        objects.append(obj)
    elf = BUILD / 'avr-eeprom-probe.elf'
    run([tools['gcc'], '-mmcu=atmega328p', *objects, '-Wl,-Map=' + str(BUILD / 'avr-eeprom-probe.map'), '-o', elf])
    sections = run([tools['size'], '-A', elf, *objects])
    symbols = run([tools['nm'], '-S', '--size-sort', elf])
    disassembly = run([tools['objdump'], '-d', elf])
    for name, text in [('sections.txt', sections), ('symbols.txt', symbols), ('disassembly.txt', disassembly)]:
        (BUILD / name).write_text(text)
    launch = inspect_launch(disassembly)
    corruptions = [
        disassembly.replace(launch['instructions'][1], launch['instructions'][1].replace('0x1f, 1', '0x1f, 0'), 1),
        disassembly.replace(launch['address_guard_instructions']['hms_avr_eeprom_read_byte'][1],
                            launch['address_guard_instructions']['hms_avr_eeprom_read_byte'][1].replace('0x04', '0x03'), 1),
        disassembly.replace(launch['masked_launch_region'][0], launch['masked_launch_region'][0].replace('cli', 'sei'), 1),
    ]
    for damaged in corruptions:
        require(damaged != disassembly, 'Negative instruction mutation had no effect')
        try:
            inspect_launch(damaged)
        except RuntimeError:
            pass
        else:
            raise RuntimeError('Damaged launch/guard/mask accepted by checker')
    launch['negative_instruction_checks'] = len(corruptions)
    (BUILD / 'instruction-review.json').write_text(json.dumps(launch, indent=2) + '\n')
    stacks = []
    for _, name in UNITS:
        for line in (BUILD / (name + '.su')).read_text().splitlines():
            loc, size, kind = line.split('\t')
            require(kind in ('static', 'dynamic,bounded'), 'Unbounded compiler stack estimate')
            stacks.append(dict(unit=name, function=loc.rsplit(':', 1)[-1], bytes=int(size), qualification=kind))
    require(before == {p: digest(ROOT / p) for p in FILES}, 'Original input changed during check')
    for source in FILES:
        snapshot = BUILD / 'sources' / source
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((ROOT / source).read_bytes())
        require(digest(snapshot) == before[source], 'Snapshot mismatch')
    outputs = [record(p) for p in sorted(BUILD.rglob('*')) if p.is_file() and p != BUILD / 'review.json']
    report = dict(schema='hms-avr-eeprom-register-adapter/1', created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  passed=True, command='python3 scripts/check_avr_eeprom.py', files=[dict(path=p, sha256=h) for p, h in before.items()],
                  outputs=outputs, host_compiler=host_compiler, native=native,
                  avr=dict(target='atmega328p', executed=False, flags=flags, compiler_version=avr_version,
                           toolchain_archive=record(ARCHIVE), archive_verified_files=pins,
                           instruction_review=launch, compiler_stack_records=stacks),
                  limitations=['Host shim models original register flow, not instruction timing, silicon, EEPROM durability or electrical failures.',
                               'AVR ELF is cross-linked inspection evidence only. Never uploaded or executed; no MCU emulator or peripheral I/O.',
                               'Mechanical checks cover launch adjacency, address-guard pattern and mask/guard control-flow paths; full disassembly retained. This is not general AVR formal verification.',
                               'Register poll budget is not elapsed time. Caller supplies bounded interrupt/SPM/exclusive-owner and qualified power/reset/retention assumptions.',
                               'No BOOT_QUALIFIED assertion. Completed-cell stability and interrupted-write target-only containment remain unproved on hardware.',
                               'Linked driver+boot probe is separate from prior endpoint AVR build. Per-function stack records exclude callback chains/ISRs; no whole-firmware fit or timing claim.'])
    (BUILD / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=True, native_cases_per_variant=12, native_assertions=native[0]['result']['assertions'],
                          avr_cross_linked=True, target_executed=False, receipt=str((BUILD / 'review.json').relative_to(ROOT)))))


if __name__ == '__main__':
    main()

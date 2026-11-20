#!/usr/bin/env python3
"""Original UART register-model tests and AVR inspection build; never run AVR."""
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
BUILD = ROOT / 'artifacts/verification/avr-uart'
ARCHIVE = ROOT / 'research/constrained/avr/raw/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2'
ARCHIVE_SHA = 'bd8c37f6952a2130ac9ee32c53f6a660feb79bee8353c8e289eb60fdcefed91e'
FILES = ['protocol/platform/avr_uart.c', 'protocol/platform/avr_uart.h',
         'protocol/serial/frame.c', 'protocol/serial/frame.h', 'tests/avr_uart_probe.c',
         'tests/fixtures/serial-frames.json', 'scripts/check_avr_uart.py',
         'artifacts/verification/avr-uart/primary-source-review.json']
UNITS = [('protocol/platform/avr_uart.c', 'avr_uart'), ('protocol/serial/frame.c', 'frame'),
         ('tests/avr_uart_probe.c', 'probe')]
COMMON = ['-std=c11', '-g', '-Wall', '-Wextra', '-Wconversion', '-Werror', '-Wvla', '-fno-common']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    return {'path': str(Path(path).relative_to(ROOT)), 'sha256': digest(path)}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def instructions(disassembly):
    functions, current = {}, None
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


def inspect_receive(disassembly):
    functions = instructions(disassembly)
    public = ('hms_avr_uart_init', 'hms_avr_uart_receive', 'hms_avr_uart_discontinuity',
              'hms_avr_uart_frame_step')
    helpers = tuple(name for name in ('lose', 'acknowledge') if name in functions)
    body = functions['hms_avr_uart_receive']
    status = [i for i, x in enumerate(body) if x['op'] == 'lds' and x['operands'].endswith('0x00C0')]
    data = [i for i, x in enumerate(body) if x['op'] == 'lds' and x['operands'].endswith('0x00C6')]
    require(len(status) == len(data) == 1 and status[0] < data[0], 'Expected one ordered UCSR0A/UDR0 read')
    a, b = status[0], data[0]
    status_register = body[a]['operands'].split(',')[0]
    guards = [i for i in range(a + 1, b) if body[i]['op'] == 'sbrs' and
              body[i]['operands'] == status_register + ', 7']
    require(len(guards) == 1, 'RXC guard must test the captured status before UDR0')
    guard = guards[0]
    require(body[guard + 1]['op'] in ('rjmp', 'jmp'), 'Unexpected RXC guard shape')
    for function in public + helpers:
        for inst in functions[function]:
            require(inst['op'] != 'sei', 'Unconditional interrupt enable appeared')
            require(not (inst['op'] == 'sts' and re.match(r'0x00C[0-6],', inst['operands'])),
                    'UART configuration or transmit write appeared')
            if function != 'hms_avr_uart_receive':
                require(not (inst['op'] == 'lds' and inst['operands'].endswith(('0x00C0', '0x00C6'))),
                        'Receive registers read outside bounded producer')
    starts = {code[0]['address']: name for name, code in functions.items() if code}
    inspected = {}
    longest_paths = {}
    for function in public + helpers:
        code = functions[function]
        indexes = {x['address']: i for i, x in enumerate(code)}
        edges = {}
        for i, inst in enumerate(code):
            op = inst['op']
            if op == 'ret': edges[i] = []
            elif op in ('rjmp', 'jmp'): edges[i] = [indexes[inst['target']]]
            elif op.startswith('br'): edges[i] = [i + 1, indexes[inst['target']]]
            elif op in ('cpse', 'sbrc', 'sbrs', 'sbic', 'sbis'): edges[i] = [i + 1, i + 2]
            else: edges[i] = [i + 1]
            require(all(j < len(code) for j in edges[i]), 'Unexpected function fallthrough')
        active, lengths = set(), {}

        def length(i):
            require(i not in active, 'Control-flow cycle in UART adapter')
            if i in lengths: return lengths[i]
            active.add(i)
            result = 1 + max((length(j) for j in edges[i]), default=0)
            active.remove(i); lengths[i] = result
            return result

        # A backwards jump to a shared epilogue is not a loop. Prove that the
        # complete local CFG is acyclic, including conservatively possible arms.
        longest_paths[function] = length(0)
        for i in edges: length(i)
    for function in public:
        code = functions[function]
        indexes = {x['address']: i for i, x in enumerate(code)}
        # Module mask state is distinct from the caller's initial I bit. A
        # restore can keep interrupts disabled if they were disabled on entry.
        work = [(0, False, False, False)]
        visited = set()
        while work:
            i, masked, seen_status, ready = work.pop()
            key = (i, masked, seen_status, ready)
            if key in visited:
                continue
            visited.add(key)
            inst = code[i]; op = inst['op']; operands = inst['operands']
            if op == 'cli': masked = True
            if op == 'sei' or (op == 'out' and operands.startswith('0x3f,')): masked = False
            if op == 'lds' and operands.endswith('0x00C0'):
                require(masked, 'Status read outside module critical section'); seen_status = True
            if op == 'lds' and operands.endswith('0x00C6'):
                require(masked and seen_status and ready, 'UDR read without captured status/RXC/mask')
            if op in ('icall', 'ijmp', 'eicall', 'eijmp'):
                raise RuntimeError('Indirect control in UART adapter')
            if op in ('call', 'rcall'):
                if op == 'rcall' and inst['target'] == inst['address'] + inst['bytes']:
                    pass  # compiler's fixed stack allocation
                else:
                    target = starts.get(inst['target'])
                    require(target in ('lose', 'acknowledge', 'hms_frame_feed', 'hms_frame_reset'),
                            'Unreviewed UART call target')
                    if target == 'hms_frame_feed':
                        require(not masked, 'Frame CRC called before restoring caller interrupt state')
                    else:
                        require(masked, 'Loss state/reset helper outside critical section')
            if op == 'ret':
                require(not masked, 'UART return without restoring interrupt state'); continue
            if op in ('jmp', 'rjmp'):
                target_index = indexes[inst['target']]
                work.append((target_index, masked, seen_status, ready)); continue
            if op.startswith('br'):
                target_index = indexes[inst['target']]
                work.append((target_index, masked, seen_status, ready))
            if op in ('cpse', 'sbrc', 'sbrs', 'sbic', 'sbis'):
                is_rxc = function == 'hms_avr_uart_receive' and i == guard
                work.append((i + 2, masked, seen_status, True if is_rxc else ready))
                if is_rxc: ready = False
            require(i + 1 < len(code), 'Unexpected UART function fallthrough')
            work.append((i + 1, masked, seen_status, ready))
        inspected[function] = len(visited)
    # Helpers have no register access, mask changes, indirect calls or loops.
    for function in helpers:
        for inst in functions[function]:
            require(inst['op'] not in ('cli', 'sei', 'icall', 'ijmp') and
                    not (inst['op'] == 'out' and inst['operands'].startswith('0x3f,')), 'Helper changes mask')
            if inst['op'] in ('call', 'rcall'):
                require(function == 'acknowledge' and starts.get(inst['target']) == 'hms_frame_reset',
                        'Unexpected helper call')
    return dict(status_instruction=body[a]['line'], data_instruction=body[b]['line'],
                receive_status_register=status_register,
                rxc_guard=body[guard]['line'], control_flow_states_checked=inspected,
                acyclic_local_instruction_path_bounds=longest_paths,
                path_bound_scope='Instruction counts exclude called frame routines and interrupt wrapper; not cycle or wall-time bounds.',
                receive_function=[x['line'] for x in body],
                foreground_function=[x['line'] for x in functions['hms_avr_uart_frame_step']],
                scope='Selected linked instruction/control-flow properties, not complete dataflow/formal proof or target execution.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain-bin', type=Path,
                        default=Path('/tmp/hms-avr-toolchain-7.3.0-atmel3.6.1-arduino7/avr/bin'))
    args = parser.parse_args()
    before = {p: digest(ROOT / p) for p in FILES}
    primary = json.loads((BUILD / 'primary-source-review.json').read_text())
    for source in primary['inputs']:
        require(digest(ROOT / source['path']) == source['sha256'], 'Primary-source/context input changed')
    manual = (ROOT / primary['inputs'][1]['path']).read_bytes().split(b'\n')
    for coverage in primary['coverage_ranges']:
        excerpt = b'\n'.join(manual[coverage['start_line'] - 1:coverage['end_line']]) + b'\n'
        require(hashlib.sha256(excerpt).hexdigest() == coverage['sha256'] and
                (ROOT / coverage['excerpt_path']).read_bytes() == excerpt, 'Primary excerpt mismatch')
    BUILD.mkdir(parents=True, exist_ok=True)
    excluded = {'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
                'OBJC_INCLUDE_PATH', 'LIBRARY_PATH', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_AUDIT',
                'DEPENDENCIES_OUTPUT', 'SUNPRO_DEPENDENCIES'}
    environment = {k: v for k, v in os.environ.items() if k not in excluded}
    environment['LC_ALL'] = 'C'
    commands = []

    def run(argv, env=None):
        result = subprocess.run([str(v) for v in argv], cwd=ROOT,
            env=environment if env is None else env, capture_output=True, text=True, timeout=90)
        commands.append(dict(argv=[str(v) for v in argv], exit_code=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        (BUILD / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        require(result.returncode == 0, f'Command failed: {argv}\n{result.stderr}\n{result.stdout}')
        return result.stdout

    gcc = Path(shutil.which('gcc')).resolve()
    host_compiler = dict(path=str(gcc), sha256=digest(gcc), version=run([gcc, '--version']).splitlines()[0])
    sanitizer_env = environment.copy()
    sanitizer_env.update(ASAN_OPTIONS='detect_leaks=1:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    fixtures = json.loads((ROOT / 'tests/fixtures/serial-frames.json').read_text())
    source = (ROOT / 'tests/avr_uart_probe.c').read_text()
    require(all('"' + item['wire_hex'] + '"' in source for item in fixtures), 'Retained wire oracle changed')
    native = []
    for variant, extra in [('plain', ['-O2']), ('asan', ['-O1', '-fsanitize=address,undefined',
                          '-fno-omit-frame-pointer', '-fno-pie', '-no-pie'])]:
        binary = BUILD / ('probe-' + variant)
        flags = COMMON + extra + ['-DHMS_AVR_UART_TEST']
        run([gcc, *flags, *(p for p, _ in UNITS), '-o', binary])
        result = json.loads(run([binary], sanitizer_env))
        require(result['cases'] == 12 and result['fault_byte_cases'] == 1792 and
                result['ring_wrap_cases'] == 272 and result['race_cases'] == 11 and
                result['sreg_patterns'] == 256 and result['queue_bytes'] == 41 and
                result['event_bytes'] == 4 and not result['target_executed'], 'Unexpected model coverage')
        native.append(dict(variant=variant, flags=flags, result=result))

    require(digest(ARCHIVE) == ARCHIVE_SHA, 'Approved compiler archive changed')
    hashes, links = {}, {}
    with tarfile.open(ARCHIVE, 'r|bz2') as archive:
        for member in archive:
            if member.isfile():
                h = hashlib.sha256()
                with archive.extractfile(member) as data:
                    for chunk in iter(lambda: data.read(1024 * 1024), b''): h.update(chunk)
                hashes[member.name] = h.hexdigest()
            elif member.islnk(): links[member.name] = member.linkname
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
    # Pin this compilation's complete expected header closure BEFORE compiling.
    for name in ('lib/gcc/avr/7.3.0/include/stdint.h', 'lib/gcc/avr/7.3.0/include/stddef.h',
                 'avr/include/stdint.h', 'avr/include/inttypes.h', 'avr/include/avr/io.h',
                 'avr/include/avr/sfr_defs.h', 'avr/include/avr/iom328p.h',
                 'avr/include/avr/portpins.h', 'avr/include/avr/common.h',
                 'avr/include/avr/version.h', 'avr/include/avr/fuse.h',
                 'avr/include/avr/lock.h', 'avr/include/avr/interrupt.h'):
        pin(toolroot / name)
    precompile_pins = set(pins)
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
            if path.is_relative_to(toolroot):
                require(str(path) in precompile_pins, 'Header was not preverified: ' + str(path)); pin(path)
            else: require(path.is_relative_to(ROOT) and str(path.relative_to(ROOT)) in FILES, 'Unexpected original include')
        objects.append(obj)
    elf = BUILD / 'avr-uart-probe.elf'
    run([tools['gcc'], '-mmcu=atmega328p', *objects, '-Wl,-Map=' + str(BUILD / 'avr-uart-probe.map'), '-o', elf])
    sections = run([tools['size'], '-A', elf, *objects])
    symbols = run([tools['nm'], '-S', '--size-sort', elf])
    disassembly = run([tools['objdump'], '-d', elf])
    for name, text in [('sections.txt', sections), ('symbols.txt', symbols), ('disassembly.txt', disassembly)]:
        (BUILD / name).write_text(text)
    instruction_review = inspect_receive(disassembly)
    code = instructions(disassembly)
    receive_cli = next(x['line'] for x in code['hms_avr_uart_receive'] if x['op'] == 'cli')
    feed_call = next(i for i, x in enumerate(code['hms_avr_uart_frame_step'])
                     if x['op'] == 'call' and '<hms_frame_feed>' in x['line'])
    feed_restore = next(x['line'] for x in reversed(code['hms_avr_uart_frame_step'][:feed_call])
                        if x['op'] == 'out' and x['operands'].startswith('0x3f,'))
    back_jump = next(x for x in code['hms_avr_uart_receive']
                     if x['op'] == 'rjmp' and x['target'] < x['address'])
    corruptions = [
        disassembly.replace(instruction_review['status_instruction'],
                            instruction_review['status_instruction'].replace('0x00C0', '0x00C6'), 1),
        disassembly.replace(instruction_review['rxc_guard'],
                            instruction_review['rxc_guard'].replace(', 7', ', 5'), 1),
        disassembly.replace(receive_cli, receive_cli.replace('\tcli', '\tnop'), 1),
        disassembly.replace(feed_restore, feed_restore.replace('\tout\t', '\tnop\t'), 1),
        disassembly.replace(back_jump['line'], re.sub(r';\s*0x[0-9a-f]+',
            '; 0x' + format(back_jump['address'], 'x'), back_jump['line']), 1),
        disassembly.replace(instruction_review['data_instruction'],
            instruction_review['data_instruction'].replace('lds\tr18, 0x00C6', 'sts\t0x00C6, r18'), 1),
    ]
    for damaged in corruptions:
        require(damaged != disassembly, 'Negative instruction mutation had no effect')
        try: inspect_receive(damaged)
        except RuntimeError: pass
        else: raise RuntimeError('Damaged status/guard accepted')
    instruction_review['negative_instruction_checks'] = len(corruptions)
    (BUILD / 'instruction-review.json').write_text(json.dumps(instruction_review, indent=2) + '\n')
    stacks = []
    for _, name in UNITS:
        for line in (BUILD / (name + '.su')).read_text().splitlines():
            loc, size, kind = line.split('\t')
            require(kind in ('static', 'dynamic,bounded'), 'Unbounded compiler stack estimate')
            stacks.append(dict(unit=name, function=loc.rsplit(':', 1)[-1], bytes=int(size), qualification=kind))
    object_sections = [dict((m[0], int(m[1])) for m in re.findall(r'^(\.[^\s]+)\s+(\d+)\s+\d+', block, re.M))
                       for block in sections.split('\n\n') if 'section' in block]
    symbol_sizes = {m[1]: int(m[0], 16) for m in re.findall(r'^[0-9a-f]+ ([0-9a-f]+) [A-Za-z] (\S+)$', symbols, re.M)}
    require(symbol_sizes['hms_avr_uart_probe_queue'] == 41 and symbol_sizes['hms_avr_uart_probe_parser'] == 219 and
            symbol_sizes['hms_avr_uart_probe_event'] == 4, 'AVR storage layout changed')
    sizes = dict(linked_probe_flash_bytes=object_sections[0].get('.text', 0) + object_sections[0].get('.data', 0),
                 linked_probe_static_sram_bytes=object_sections[0].get('.data', 0) + object_sections[0].get('.bss', 0),
                 driver_function_text_bytes=sum(v for k, v in object_sections[1].items() if k.startswith('.text')),
                 queue_bytes=41, parser_bytes=219, event_bytes=4)
    require(before == {p: digest(ROOT / p) for p in FILES}, 'Original input changed during check')
    for source in primary['inputs']:
        require(digest(ROOT / source['path']) == source['sha256'], 'Primary input changed during check')
    for source in FILES:
        snapshot = BUILD / 'sources' / source
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((ROOT / source).read_bytes())
        require(digest(snapshot) == before[source], 'Snapshot mismatch')
    outputs = [record(p) for p in sorted(BUILD.rglob('*')) if p.is_file() and p != BUILD / 'review.json']
    report = dict(schema='hms-avr-uart-receive-adapter/1', created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        passed=True, command='python3 scripts/check_avr_uart.py', files=[dict(path=p, sha256=h) for p, h in before.items()],
        outputs=outputs, host_compiler=host_compiler, native=native,
        avr=dict(target='atmega328p', executed=False, flags=flags, compiler_version=avr_version,
            toolchain_archive=record(ARCHIVE), archive_verified_files=pins, precompile_tool_header_verification=True,
            toolchain_url='https://downloads.arduino.cc/tools/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2',
            instruction_review=instruction_review, compiler_stack_records=stacks, sizes=sizes),
        limitations=[
            'Host shim tests register flow and injected scheduling points, not AVR cycles, electrical errors or real interrupt latency.',
            'AVR ELF is inspected only; no target, MCU emulator, peripheral, uploader, bootloader or acquired controller executes.',
            'No UART setup/vector/TX or baud/clock/supply/service qualification. The caller owns exclusive eight-bit asynchronous RX configuration.',
            'No module busy waits; one RX status/data access and one foreground-byte/feed per call. Parser CRC has its existing frame-size bound; this is not a wall-time/stop bound.',
            'Saved SREG snapshots are tested; post-return arithmetic flags are not a C ABI preservation promise.',
            'Loss reasons accumulate without invented physical byte counts. Parser reset never clears endpoint identity, commands, fences, receipts or uncertain effects.',
            'Selected instruction properties are mechanically checked; complete register-value/pointer dataflow requires separate manual/source review.',
            'Driver plus parser probe is separate from the prior endpoint firmware reservation. Stack files exclude the installed ISR wrapper/nesting and whole-application call graph.' ])
    (BUILD / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=True, native_cases_per_variant=12,
        native_assertions=native[0]['result']['assertions'], avr_cross_linked=True,
        sizes=sizes, target_executed=False, receipt=str((BUILD / 'review.json').relative_to(ROOT)))))


if __name__ == '__main__':
    main()

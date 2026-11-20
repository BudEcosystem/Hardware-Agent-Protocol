#!/usr/bin/env python3
"""Cross-link the original endpoint/framing/fixture for ATmega328P; never run it.

Only trusted, archive-verified compiler/binutils host tools execute. No Arduino
core, target binary, simulator, UART, peripheral, upload or device is invoked.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import posixpath
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'artifacts/verification/endpoint-avr-build'
OUTPUT = ROOT / 'artifacts/verification/endpoint-avr.json'
DEFAULT_BIN = Path('/tmp/hms-avr-toolchain-7.3.0-atmel3.6.1-arduino7/avr/bin')
ARCHIVE = ROOT / 'research/constrained/avr/raw/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2'
ARCHIVE_SHA = 'bd8c37f6952a2130ac9ee32c53f6a660feb79bee8353c8e289eb60fdcefed91e'
UNITS = [('protocol/endpoint/endpoint.c', 'endpoint'), ('protocol/endpoint/link.c', 'link'),
         ('protocol/serial/frame.c', 'frame'), ('tests/endpoint_fixture.c', 'fixture'),
         ('tests/endpoint_avr_driver.c', 'driver')]
SOURCES = [path for path, _ in UNITS] + [
    'protocol/endpoint/endpoint.h', 'protocol/endpoint/link.h', 'protocol/serial/frame.h',
    'tests/endpoint_fixture.h', 'scripts/check_endpoint_avr.py']
FLAGS = ['-mmcu=atmega328p', '-DF_CPU=16000000UL', '-std=c11', '-Os', '-Wall',
         '-Wextra', '-Wconversion', '-Werror', '-Wvla', '-ffunction-sections',
         '-fdata-sections', '-fno-common', '-fno-optimize-sibling-calls', '-fstack-usage', '-MD']
CALLBACKS = {
    ('endpoint', 'constant_copy'): (1, ['constant_byte']),
    ('endpoint', 'guard_call'): (1, ['guard']),
    ('endpoint', 'sample_clock'): (1, ['sample_clock']),
    ('endpoint', 'hms_endpoint_handle'): (2, ['constant_byte', 'describe']),
    ('endpoint', 'hms_endpoint_poll'): (1, ['step']),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha(path.read_bytes())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def relative(path):
    return str(path.relative_to(ROOT))


def stack_analysis(map_text, disassembly, symbols, records):
    """Conservative interprocedural sum; fails on unknown call/stack patterns."""
    sections = []
    for match in re.finditer(r'^ (\.text[^\s]*)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+(\S+)', map_text, re.M):
        section, address, size, obj = match.groups()
        if obj.startswith(relative(BUILD) + '/'):
            sections.append((int(address, 16), int(size, 16), Path(obj).stem, section))
    instructions = []
    for line in disassembly.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*([a-z][a-z0-9]*)\s*(.*)', line)
        if match:
            address, encoded, op, operands = match.groups()
            instructions.append({'address': int(address, 16), 'bytes': len(encoded.split()),
                                 'op': op, 'operands': operands})
    frames = {(r['unit'], r['function']): r for r in records}
    nodes = {}
    original = {}
    for symbol in symbols:
        if symbol['type'] not in ('T', 't') or symbol['bytes'] == 0:
            continue
        address = symbol['address']
        owner = next((unit for start, size, unit, _ in sections if start <= address < start + size), None)
        key = (owner, symbol['name'])
        code = [i for i in instructions if address <= i['address'] < address + symbol['bytes']]
        nodes[address] = {**symbol, 'unit': owner, 'instructions': code, 'edges': set(), 'indirect': []}
        if key in frames:
            nodes[address]['frame_bytes'] = frames[key]['bytes']
            nodes[address]['frame_basis'] = frames[key]['qualification'] + ' GCC .su'
            original[key] = address
    require(len(original) == len(records), 'A compiler stack record is not represented by a linked function')
    required = ['hms_endpoint_init', 'hms_endpoint_handle', 'hms_endpoint_poll',
                'hms_endpoint_link_init', 'hms_endpoint_link_reset_receive',
                'hms_endpoint_link_set_receive_budget', 'hms_endpoint_link_check_deadline',
                'hms_endpoint_link_feed', 'hms_endpoint_link_next', 'hms_frame_reset',
                'hms_frame_feed', 'hms_endpoint_fixture_init', 'main']
    require(set(required) <= {nodes[a]['name'] for a in original.values()}, 'Required endpoint API was discarded')
    for address in original.values():
        node = nodes[address]
        key = (node['unit'], node['name'])
        for inst in node['instructions']:
            op = inst['op']
            if op in ('icall', 'eicall', 'ijmp', 'eijmp'):
                require(op == 'icall' and key in CALLBACKS, f'Unknown indirect dispatch in {key}')
                node['indirect'].append(inst['address'])
                for target in CALLBACKS[key][1]:
                    node['edges'].add(original[('fixture', target)])
            elif op in ('call', 'rcall', 'jmp', 'rjmp') or op.startswith('br'):
                target_match = re.search(r'0x([0-9a-f]+)', inst['operands'])
                require(target_match is not None, f'Unresolved branch/call at {inst}')
                target = int(target_match.group(1), 16)
                if op == 'rcall' and target == inst['address'] + inst['bytes']:
                    continue  # GCC local stack allocation; included in .su.
                if address <= target < address + node['bytes']:
                    require(op not in ('call', 'rcall'), 'Recursive or internal non-allocation call')
                    continue
                require(target in nodes, f'Unknown cross-function destination 0x{target:x}')
                node['edges'].add(target)
        require(len(node['indirect']) == CALLBACKS.get(key, (0, []))[0],
                f'Indirect-call count changed for {key}; review the callback mapping')

    # The linked arithmetic/memory helpers have no pushes, SP writes, calls or
    # external branches. Inspect that property mechanically rather than giving
    # unreviewed library code an arbitrary zero cost. Two bytes cover its return.
    allowed_helpers = {'__bswapsi2', '__ashldi3', '__lshrdi3', '__adddi3', '__adddi3_s8',
                       '__subdi3', '__cmpdi2', '__cmpdi2_s8', 'memcmp', 'memcpy'}
    helper_addresses = {target for a in original.values() for target in nodes[a]['edges'] if target not in original.values()}
    for address in helper_addresses:
        node = nodes[address]
        require(node['name'] in allowed_helpers, f'Unreviewed library helper {node["name"]}')
        for inst in node['instructions']:
            require(inst['op'] not in ('push', 'pop', 'call', 'rcall', 'icall', 'eicall', 'ijmp', 'eijmp', 'out', 'sts'),
                    f'Library helper stack/control behavior needs review: {node["name"]} {inst}')
            if inst['op'] in ('jmp', 'rjmp') or inst['op'].startswith('br'):
                match = re.search(r'0x([0-9a-f]+)', inst['operands'])
                require(match is not None and address <= int(match.group(1), 16) < address + node['bytes'],
                        f'External helper branch needs review: {node["name"]}')
        require(node['instructions'][-1]['op'] == 'ret', f'Helper fallthrough needs review: {node["name"]}')
        node['frame_bytes'] = 2
        node['frame_basis'] = 'Linked instruction scan: no stack adjustment/call; two-byte return address'

    memo = {}
    def longest(address, active):
        require(address not in active, 'Recursive call graph: no finite bound claimed')
        if address in memo:
            return memo[address]
        node = nodes[address]
        require('frame_bytes' in node, f'Missing frame bound for {node["name"]}')
        choices = [(0, [])]
        for child in node['edges']:
            count, path = longest(child, active | {address})
            choices.append((count + 2, path))  # Extra call margin even where .su already counts return bytes.
        count, path = max(choices, key=lambda item: (item[0], item[1]))
        memo[address] = (node['frame_bytes'] + count, [address] + path)
        return memo[address]
    main = original[('driver', 'main')]
    bound, chain = longest(main, set())
    require(set(original.values()) <= set(memo), 'Required original function is unreachable from main/callback map')
    graph = []
    for address in sorted(memo):
        node = nodes[address]
        graph.append({'address': address, 'name': node['name'], 'unit': node['unit'],
                      'frame_bytes': node['frame_bytes'], 'frame_basis': node['frame_basis'],
                      'callees': sorted(node['edges']), 'indirect_call_sites': node['indirect'],
                      'conservative_subtree_bytes': memo[address][0]})
    return {
        'method': 'Longest acyclic linked call-graph path, summing per-function GCC .su maxima, '
                  'two-byte inspected library leaf frames and an extra two bytes per call edge; '
                  'another two bytes reserved for startup entry to main. Callback edges use the installed fixture only.',
        'main_chain_bytes': bound, 'startup_entry_margin_bytes': 2,
        'conservative_foreground_stack_bytes': bound + 2,
        'max_chain': [{'address': a, 'name': nodes[a]['name'], 'unit': nodes[a]['unit'],
                       'frame_bytes': nodes[a]['frame_bytes']} for a in chain],
        'graph': graph, 'compiler_records': records,
        'indirect_call_sites': sum(len(n['indirect']) for n in nodes.values()),
        'required_api_symbols': required,
        'assumptions': ['Exact compiler, flags, source and linked callbacks retained here; LTO disabled.',
                        'Single nonreentrant owner; no recursion, heap, VLA, ISR or enabled interrupts in this harness.',
                        'GCC dynamic,bounded records bound fixed outgoing argument space; unbounded records are rejected.',
                        'Each caller maximum is charged concurrently with each child maximum, which can overestimate real usage.',
                        'No real clock/NVM/UART/stop/actuator callback or interrupt implementation is covered.',
                        'This is static analysis, not measured stack high-water or a device execution result.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain-bin', type=Path, default=DEFAULT_BIN)
    opts = parser.parse_args()
    toolroot = opts.toolchain_bin.resolve().parent
    require(digest(ARCHIVE) == ARCHIVE_SHA, 'Trusted compiler archive hash mismatch')
    toolpins = {}
    # One forward pass avoids repeatedly decompressing a large bzip2 archive
    # while verifying compiler children and later-discovered include files.
    archive_hashes, archive_links = {}, {}
    with tarfile.open(ARCHIVE, 'r|bz2') as archive:
        for member in archive:
            if member.isfile():
                hasher = hashlib.sha256()
                stream = archive.extractfile(member)
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    hasher.update(chunk)
                archive_hashes[member.name] = hasher.hexdigest()
            elif member.islnk():
                archive_links[member.name] = member.linkname
            elif member.issym():
                archive_links[member.name] = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), member.linkname))
    for _ in range(len(archive_links)):
        resolved = {name: archive_hashes[target] for name, target in archive_links.items() if target in archive_hashes}
        if not resolved:
            break
        archive_hashes.update(resolved)
        for name in resolved:
            del archive_links[name]

    def pin_tool_file(path):
        path = Path(path).resolve()
        require(path.is_relative_to(toolroot), f'File outside isolated compiler tree: {path}')
        if str(path) in toolpins:
            return str(path)
        member = 'avr/' + str(path.relative_to(toolroot))
        actual = path.read_bytes()
        require(sha(actual) == archive_hashes.get(member), f'Toolchain file differs from approved archive: {path}')
        toolpins[str(path)] = {'archive_member': member, 'sha256': sha(actual), 'bytes': len(actual)}
        return str(path)

    # Verify every directly executed compiler/binutils program and GCC child
    # before execution; headers/libraries/specs are additionally pinned below.
    tools = {name: pin_tool_file(toolroot / 'bin' / name)
             for name in ['avr-gcc', 'avr-as', 'avr-ld', 'avr-size', 'avr-nm', 'avr-objdump']}
    for name in ['cc1', 'collect2']:
        pin_tool_file(toolroot / 'libexec/gcc/avr/7.3.0' / name)
    gcc = tools['avr-gcc']
    for path in [toolroot / 'lib/gcc/avr/7.3.0/device-specs/specs-atmega328p',
                 *sorted((toolroot / 'avr/lib/ldscripts').glob('avr5.x*'))]:
        pin_tool_file(path)
    BUILD.mkdir(parents=True, exist_ok=True)
    # Remove only this script's known generated files, retaining unrelated files.
    generated = [f'{name}{suffix}' for _, name in UNITS for suffix in ('.o', '.su', '.d')]
    generated += ['endpoint.elf', 'endpoint.map', 'sections.txt', 'symbols.txt', 'disassembly.txt',
                  'commands.json', 'stack-analysis.json', 'exploratory-commands.json']
    for name in generated:
        (BUILD / name).unlink(missing_ok=True)
    initial_hashes = {name: digest(ROOT / name) for name in SOURCES}
    commands = []

    def run(argv, artifact=None):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
        record = {'argv': argv, 'exit_code': result.returncode, 'stderr': result.stderr}
        if artifact:
            (BUILD / artifact).write_text(result.stdout)
            record['stdout_path'] = relative(BUILD / artifact)
        else:
            record['stdout'] = result.stdout
        commands.append(record)
        (BUILD / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        require(result.returncode == 0, f'Command failed: {argv}: {result.stderr}')
        return result.stdout

    compiler = run([gcc, '--version']).splitlines()[0]
    require(run([gcc, '-dumpmachine']).strip() == 'avr', 'Wrong compiler target')
    for program in ['as', 'ld', 'cc1', 'collect2']:
        pin_tool_file(run([gcc, '-print-prog-name=' + program]).strip())
    objects = []
    for source, name in UNITS:
        obj = relative(BUILD / f'{name}.o')
        run([gcc, *FLAGS, '-c', source, '-o', obj])
        objects.append(obj)
    elf, map_path = relative(BUILD / 'endpoint.elf'), relative(BUILD / 'endpoint.map')
    run([gcc, '-mmcu=atmega328p', '-Os', '-Wl,--gc-sections',
         '-Wl,--defsym=__TEXT_REGION_LENGTH__=32768', '-Wl,--defsym=__DATA_REGION_LENGTH__=2048',
         '-Wl,--defsym=__DATA_REGION_ORIGIN__=0x800100', '-Wl,--defsym=__EEPROM_REGION_LENGTH__=1024',
         '-Wl,-Map=' + map_path, *objects, '-o', elf])
    sections_text = run([tools['avr-size'], '-A', elf], 'sections.txt')
    symbols_text = run([tools['avr-nm'], '-S', '--size-sort', elf], 'symbols.txt')
    disassembly = run([tools['avr-objdump'], '-h', '-d', elf], 'disassembly.txt')
    require(not run([tools['avr-nm'], '-u', elf]).strip(), 'Undefined symbols in final image')
    sections = {}
    for line in sections_text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].startswith('.'):
            sections[parts[0]] = {'bytes': int(parts[1]), 'address': int(parts[2])}
    symbols = []
    for line in symbols_text.splitlines():
        fields = line.split()
        if len(fields) == 4:
            address, size, kind, name = fields
            symbols.append({'name': name, 'bytes': int(size, 16), 'address': int(address, 16), 'type': kind})
    require(not ({s['name'] for s in symbols} & {'malloc', 'calloc', 'realloc', 'free', 'alloca'}),
            'Allocator unexpectedly linked')
    records = []
    for _, unit in UNITS:
        for line in (BUILD / (unit + '.su')).read_text().splitlines():
            location, count, qualification = line.split('\t')
            require(qualification in ('static', 'dynamic,bounded'), 'Unbounded compiler stack record')
            records.append({'unit': unit, 'location': location, 'function': location.split(':', 3)[3],
                            'bytes': int(count), 'qualification': qualification})
    map_text = (BUILD / 'endpoint.map').read_text()
    stack = stack_analysis(map_text, disassembly, symbols, records)
    (BUILD / 'stack-analysis.json').write_text(json.dumps(stack, indent=2) + '\n')
    for _, unit in UNITS:
        dependencies = (BUILD / (unit + '.d')).read_text().replace('\\\n', ' ').split(':', 1)[1].split()
        for name in dependencies:
            path = (ROOT / name).resolve()
            if path.is_relative_to(toolroot):
                pin_tool_file(path)
            else:
                require(relative(path) in initial_hashes, f'Unpinned original include: {path}')
    for match in re.finditer(r'^LOAD (\S+)', map_text, re.M):
        path = Path(match.group(1))
        if path.is_absolute():
            pin_tool_file(path)
    require(initial_hashes == {name: digest(ROOT / name) for name in SOURCES},
            'Source changed during build; retry after source stabilization')
    size = lambda name: sections.get(name, {}).get('bytes', 0)
    flash, static = size('.text') + size('.data'), size('.data') + size('.bss') + size('.noinit')
    foreground = stack['conservative_foreground_stack_bytes']
    stack_reservation, assumed_isr, future_callback = 512, 64, 128
    fits = flash <= 32256 and static + stack_reservation <= 2048 and foreground + assumed_isr + future_callback <= stack_reservation
    objects_by_name = {s['name']: s['bytes'] for s in symbols if s['type'] in ('B', 'D', 'b', 'd')}
    require(objects_by_name['hms_avr_fixture'] + objects_by_name['hms_avr_primitive_reserve'] == 256,
            'Primitive persistent-state reservation is not 256 bytes')
    report = {
        'schema': 'hms-endpoint-avr-build/1', 'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope': 'Original endpoint, serial framing/link and full synthetic installed fixture: target compile/link and conservative static stack analysis only; no execution.',
        'compiler': compiler, 'compiler_path': gcc, 'compiler_sha256': digest(Path(gcc)),
        'compiler_target': 'avr', 'host': platform.platform(), 'mcu': 'atmega328p',
        'declared_f_cpu_hz': 16000000, 'flags': FLAGS, 'lto': False,
        'sibling_call_optimization': False, 'source_hashes': initial_hashes,
        'commands_path': relative(BUILD / 'commands.json'),
        'toolchain_archive': {'path': relative(ARCHIVE), 'sha256': ARCHIVE_SHA},
        'toolchain_files_verified_against_archive': toolpins,
        'toolchain_provenance_manifest': {'path': 'research/constrained/avr/manifest.jsonl',
                                        'sha256': digest(ROOT / 'research/constrained/avr/manifest.jsonl')},
        'sections': sections, 'linked_harness_flash_bytes': flash, 'linked_harness_static_ram_bytes': static,
        'static_allocations': objects_by_name,
        'capacity_limits': {'physical_flash_bytes': 32768, 'uno_application_flash_bytes': 32256,
                            'sram_bytes': 2048, 'eeprom_bytes': 1024,
                            'basis': 'Retained UNO R3 manual and Arduino AVR 1.8.8 boards.txt UNO profile; no connected board identified.'},
        'foreground_stack_bound_bytes': foreground, 'stack_analysis_path': relative(BUILD / 'stack-analysis.json'),
        'reservation_scenario': {
            'stack_reservation_bytes': stack_reservation,
            'assumed_interrupt_stack_allowance_bytes': assumed_isr,
            'future_primitive_callback_growth_allowance_bytes': future_callback,
            'unassigned_within_stack_reservation_bytes': stack_reservation - foreground - assumed_isr - future_callback,
            'static_plus_reserved_stack_bytes': static + stack_reservation,
            'unassigned_sram_bytes': 2048 - static - stack_reservation,
            'unassigned_uno_application_flash_bytes': 32256 - flash,
            'fits_arithmetic_budget': fits,
            'interpretation': '512 bytes is a declared planning reservation checked against the exact synthetic call graph. '
                              '64 ISR and 128 future callback bytes are assumptions, not implemented/measured limits. '
                              'Retained UART/platform/primitive arrays are storage placeholders, not working drivers.'},
        'passed_compile_link': True, 'passed_static_reservation_scenario': fits,
        'target_runtime_fit_demonstrated': False,
        'limitations': [
            'All endpoint/link APIs, maximum wire/argument/result storage and installed fixture callback branches remain linked; no ordinary protocol operation removed to fit.',
            'The AVR conditional fixture uses 80 PROGMEM constant bytes; its host-only editable hex constants helper is not a target feature.',
            'Synthetic epoch/clock/qualification inputs do not implement stable identity, qualified NVM, rollback/brownout recovery or an atomic qualified timer.',
            'No real UART rings/service/ISR, error handling, independent stop, physical interlock or hardware primitive is implemented by this harness.',
            'Static foreground bound assumes exact nonreentrant callbacks and no interrupts; adding drivers requires a new call graph and target measurements.',
            'The GCC .su quantities and linked disassembly are static evidence, never stack high-water/canary or worst-case interrupt/timing measurements.',
            'No target image, simulator, acquired Arduino core, port, peripheral or physical device executed; no flash/upload.',
            'Flash excludes a running bootloader; the UNO application limit reserves 512 bytes. Other bootloaders and real drivers need their own budget.',
        ],
        'artifact_hashes': {relative(p): digest(p) for p in sorted(BUILD.iterdir()) if p.is_file()},
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Endpoint AVR: flash={flash}, static SRAM={static}, conservative foreground stack={foreground}; '
          f'static+512 reservation={static + 512}/2048; scenario fits={fits}. No target execution.')
    print(relative(OUTPUT))
    require(fits, 'Build retained, but declared capacity/reservation scenario fails')


if __name__ == '__main__':
    main()

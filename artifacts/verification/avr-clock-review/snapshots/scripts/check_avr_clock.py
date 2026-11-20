#!/usr/bin/env python3
"""Original Timer1 register-model tests and AVR inspection; never execute AVR."""
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
BUILD = ROOT / 'artifacts/verification/avr-clock'
ARCHIVE = ROOT / 'research/constrained/avr/raw/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2'
ARCHIVE_SHA = 'bd8c37f6952a2130ac9ee32c53f6a660feb79bee8353c8e289eb60fdcefed91e'
FILES = ['protocol/platform/avr_clock.c', 'protocol/platform/avr_clock.h',
         'tests/avr_clock_probe.c', 'scripts/check_avr_clock.py',
         'artifacts/verification/avr-clock/README.md',
         'artifacts/verification/avr-clock/primary-source-review.json']
UNITS = [('protocol/platform/avr_clock.c', 'avr_clock'), ('tests/avr_clock_probe.c', 'probe')]
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


def inspect_clock(disassembly):
    """Selected linked instruction/CFG checks; no cycle or target execution claim."""
    functions = instructions(disassembly)
    names = ['hms_avr_clock_' + s for s in ('start','qualify','invalidate','overflow','read')]
    starts = {body[0]['address']:name for name,body in functions.items() if body}
    helper_names = {'source_config','running_config','__cmpdi2'}
    conversion_names = {'__ashldi3','__udivmodsi4','__adddi3'}
    require(not any(x in functions for x in ('malloc','calloc','realloc','free','__udivdi3')),
            'Unexpected allocator or 64-bit division')

    def edges(body, index):
        item = body[index]; op = item['op']
        address_index = {x['address']:i for i,x in enumerate(body)}
        if op in ('ret','reti'): return []
        if op in ('rjmp','jmp') or op.startswith('br'):
            require(item['target'] in address_index, 'Jump leaves inspected function')
            result = [address_index[item['target']]]
            if op.startswith('br'): result.append(index + 1)
            return result
        if op in ('sbrc','sbrs','sbic','sbis','cpse'): return [index + 1,index + 2]
        require(op not in ('ijmp','icall','eijmp','eicall','sei'), 'Unexpected indirect control/SEI')
        return [index + 1]

    def sreg_out(item): return item['op'] == 'out' and item['operands'].startswith('0x3f,')
    def target(item): return starts.get(item['target'])
    helper_bounds = {}
    def helper_bound(name, ancestors=()):
        require(name in helper_names and name not in ancestors, 'Unexpected/recursive masked helper')
        if name in helper_bounds: return helper_bounds[name]
        body = functions[name]; memo = {}; visiting = set()
        def visit(i):
            require(i < len(body) and i not in visiting, 'Cycle/escape in masked helper')
            if i in memo: return memo[i]
            visiting.add(i); item = body[i]; weight = 1
            require(item['op'] not in ('cli','sei','out','sts','st','std'), 'Masked helper changes state/registers')
            if item['op'] in ('call','rcall'): weight += helper_bound(target(item), ancestors + (name,))
            value = weight + max([visit(n) for n in edges(body,i)] or [0])
            visiting.remove(i); memo[i] = value; return value
        helper_bounds[name] = visit(0); return helper_bounds[name]
    for name in helper_names: helper_bound(name)

    # Counter byte order and W1C setup are exact properties of this build.
    pairs = {}
    for name, expected in [('hms_avr_clock_overflow',1),('hms_avr_clock_read',2)]:
        body = functions[name]
        low = [i for i,x in enumerate(body) if x['op'] == 'lds' and '0x0084' in x['operands']]
        high = [i for i,x in enumerate(body) if x['op'] == 'lds' and '0x0085' in x['operands']]
        require(len(low) == expected and high == [i+1 for i in low], 'TCNT1 must read low then high')
        pairs[name] = [[body[i]['line'],body[i+1]['line']] for i in low]
    body = functions['hms_avr_clock_read']
    flags = [i for i,x in enumerate(body) if x['op'] == 'in' and x['operands'].endswith(', 0x16')]
    low = [i for i,x in enumerate(body) if x['op'] == 'lds' and '0x0084' in x['operands']]
    require(len(flags) == 2 and flags[0] < low[0] < flags[1] < low[1], 'Pending flag/counter order changed')
    body = functions['hms_avr_clock_start']
    writes = [x for x in body if x['op'] == 'sts' or (x['op'] == 'out' and not sreg_out(x))]
    expected = ['0x006F, r1','0x0081, r1','0x0080, r1','0x0082, r1','0x0085, r1',
                '0x0084, r1','0x16, r17','0x006F, r17','0x0081, r24']
    require([x['operands'] for x in writes] == expected, 'Unexpected timer setup write sequence')
    require(any(x['op'] == 'ldi' and x['operands'] == 'r17, 0x01' for x in body) and
            any(x['op'] == 'ldi' and x['operands'] == 'r24, 0x03' for x in body), 'Setup constants changed')
    overflow = functions['hms_avr_clock_overflow']
    require(any(x['op'] == 'sbis' and x['operands'] == '0x16, 0' for x in overflow), 'ISR pending guard changed')
    require(any(x['op'] == 'sbrc' and x['operands'] == 'r24, 7' for x in overflow), 'ISR half-period guard changed')

    windows = {}; state_counts = {}; masked_calls = set(); conversion_calls = []
    for name in names:
        body = functions[name]
        cli_indices = [i for i,x in enumerate(body) if x['op'] == 'cli']
        require(len(cli_indices) == (3 if name.endswith('_read') else 1), 'Unexpected number of saved-SREG windows')
        saves = {}
        for i in cli_indices:
            prior = body[i-1]
            require(prior['op'] == 'in' and prior['operands'].endswith(', 0x3f'), 'CLI lacks preceding SREG save')
            saves[i] = prior['operands'].split(',')[0]
        seen = set(); visiting = set()
        def walk(i, active=None, timer_stage=0):
            state = (i,active,timer_stage)
            require(i < len(body) and state not in visiting, 'Local control-flow cycle/escape')
            if state in seen: return
            visiting.add(state); item = body[i]; op = item['op']; operand = item['operands']
            if op == 'cli':
                require(active is None, 'Nested unmatched CLI'); active = i
            elif sreg_out(item):
                require(active is not None and operand.split(', ')[1] == saves[active], 'Wrong/unmatched SREG restoration')
                if name.endswith('_read'): require(timer_stage in (0,4,6), 'Incomplete timer snapshot at restore')
                if name.endswith('_overflow'): require(timer_stage in (0,2,3), 'Incomplete ISR counter at restore')
                active = None
            elif op in ('call','rcall'):
                callee = target(item)
                if active is not None:
                    require(callee in helper_names, 'Unreviewed helper/conversion in masked window'); masked_calls.add(callee)
                else:
                    require(name.endswith('_read') and callee in conversion_names, 'Unexpected unmasked call')
                    conversion_calls.append(item['line'])
            elif op in ('sts','out'):
                if op == 'out' and operand.startswith(('0x3d,','0x3e,')): pass # Compiler stack pointer maintenance.
                else: require(name.endswith('_start') and active is not None, 'Timer/config write outside startup window')
            is_low = op == 'lds' and '0x0084' in operand
            is_high = op == 'lds' and '0x0085' in operand
            is_flag = (op == 'in' and operand.endswith(', 0x16')) or (op == 'sbis' and operand == '0x16, 0')
            if is_low or is_high or is_flag:
                require(active is not None, 'Timer read outside saved-SREG window')
                if name.endswith('_read'):
                    valid = ({0:1,3:4} if is_flag else ({1:2,4:5} if is_low else {2:3,5:6}))
                else:
                    require(name.endswith('_overflow'), 'Unexpected counter reader')
                    valid = {0:1} if is_low else ({1:2} if is_high else {2:3})
                require(timer_stage in valid, 'Counter/flag CFG order violated'); timer_stage = valid[timer_stage]
            if op == 'ret': require(active is None, 'Function returns with unbalanced SREG')
            for nxt in edges(body,i): walk(nxt,active,timer_stage)
            visiting.remove(state); seen.add(state)
        walk(0); state_counts[name] = len(seen)
        windows[name] = []
        for entry in cli_indices:
            memo = {}; active_path = set()
            def bound(i):
                require(i not in active_path, 'Cycle in masked window')
                if i in memo: return memo[i]
                active_path.add(i); item = body[i]
                if sreg_out(item): value = 1
                else:
                    require(item['op'] != 'ret', 'Masked path exits without restoration')
                    weight = 1 + (helper_bounds[target(item)] if item['op'] in ('call','rcall') else 0)
                    value = weight + max(bound(n) for n in edges(body,i))
                active_path.remove(i); memo[i] = value; return value
            windows[name].append(dict(cli=body[entry]['line'],saved_register=saves[entry],
                                      instruction_upper_bound=bound(entry)))

    # Library arithmetic occurs after caller SREG restoration. Its selected
    # loops are fixed-width arithmetic, not peripheral polls; no CLI/SEI/I/O.
    arithmetic = [name for name in functions if name in conversion_names or name.startswith('__udivmodsi4_')]
    for name in arithmetic:
        require(all(x['op'] not in ('cli','sei','in','out','lds','sts','st','std','call','rcall','icall','ijmp')
                    for x in functions[name]), 'Arithmetic helper unexpectedly touches I/O/state or calls')
    require(functions['__udivmodsi4'][0]['operands'] == 'r26, 0x21' and
            any(x['op'] == 'dec' and x['operands'] == 'r1' for x in functions['__udivmodsi4_ep']),
            '32-bit division loop initializer/decrement changed')
    vector = functions['__vector_13']
    require([target(x) for x in vector if x['op'] in ('call','rcall')] == ['hms_avr_clock_overflow'] and
            vector[-1]['op'] == 'reti' and all(x['op'] not in ('cli','sei','sts') for x in vector),
            'Unexpected ISR wrapper')
    return dict(masked_instruction_path_upper_bounds=windows,helper_instruction_upper_bounds=helper_bounds,
        cfg_states_checked=state_counts,counter_read_pairs=pairs,startup_register_writes=[x['line'] for x in writes],
        masked_calls=sorted(masked_calls),conversion_calls=sorted(set(conversion_calls)),
        arithmetic_functions=arithmetic,vector_instructions=len(vector),
        scope='Selected linked CFG/register-order and saved-SREG properties. Counts include acyclic helper instructions, CLI and restore; not CPU cycles, interrupt latency or time. Read prologue/epilogue each contain a compiler-generated stack-pointer window. Complete pointer/register-value dataflow and whole-application timing remain outside this checker.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain-bin', type=Path,
        default=Path('/tmp/hms-avr-toolchain-7.3.0-atmel3.6.1-arduino7/avr/bin'))
    args = parser.parse_args()
    before = {p: digest(ROOT / p) for p in FILES}
    primary = json.loads((BUILD / 'primary-source-review.json').read_text())
    for item in primary['inputs']:
        require(digest(ROOT / item['path']) == item['sha256'], 'Primary/context input changed')
    for item in primary['coverage_ranges']:
        lines = (ROOT / item['source_path']).read_bytes().split(b'\n')
        excerpt = b'\n'.join(lines[item['start_line'] - 1:item['end_line']]) + b'\n'
        require(hashlib.sha256(excerpt).hexdigest() == item['sha256'] and
                (ROOT / item['excerpt_path']).read_bytes() == excerpt, 'Source excerpt mismatch')
    BUILD.mkdir(parents=True, exist_ok=True)
    excluded = {'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
        'OBJC_INCLUDE_PATH', 'LIBRARY_PATH', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_AUDIT',
        'DEPENDENCIES_OUTPUT', 'SUNPRO_DEPENDENCIES'}
    environment = {k:v for k,v in os.environ.items() if k not in excluded}
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
    host_compiler = dict(path=str(gcc), sha256=digest(gcc), version=run([gcc,'--version']).splitlines()[0])
    sanitizer_env = environment.copy()
    sanitizer_env.update(ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                         UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    native = []
    for variant, extra in [('plain',['-O2']),('asan-ubsan',['-O1','-fsanitize=address,undefined',
                          '-fno-omit-frame-pointer','-fno-pie','-no-pie'])]:
        binary = BUILD / ('probe-' + variant)
        flags = COMMON + extra + ['-DHMS_AVR_CLOCK_TEST']
        run([gcc,*flags,*(p for p,_ in UNITS),'-o',binary])
        result = json.loads(run([binary], sanitizer_env))
        require(result['cases'] == 10 and result['low_counter_cases'] == 131072 and
                result['rollover_cases'] == 47 and result['sreg_patterns'] == 256 and
                result['bounded_sequence_cases'] == 50000 and result['alias_counterexamples'] == 1 and
                not result['target_executed'], 'Unexpected model coverage')
        native.append(dict(variant=variant,flags=flags,result=result))
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
    flags = ['-mmcu=atmega328p', '-DF_CPU=16000000UL', *COMMON, '-Os', '-ffunction-sections', '-fdata-sections',
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
    elf = BUILD / 'avr-clock-probe.elf'
    run([tools['gcc'],'-mmcu=atmega328p',*objects,'-Wl,-Map=' + str(BUILD / 'avr-clock-probe.map'),'-o',elf])
    sections = run([tools['size'],'-A',elf,*objects])
    symbols = run([tools['nm'],'-S','--size-sort',elf])
    disassembly = run([tools['objdump'],'-d',elf])
    for name, content in [('sections.txt',sections),('symbols.txt',symbols),('disassembly.txt',disassembly)]:
        (BUILD / name).write_text(content)
    instruction_review = inspect_clock(disassembly)
    code = instructions(disassembly)
    snapshot = code['hms_avr_clock_read']
    low_line = instruction_review['counter_read_pairs']['hms_avr_clock_read'][0][0]
    cli_line = instruction_review['masked_instruction_path_upper_bounds']['hms_avr_clock_read'][1]['cli']
    restore_line = next(x['line'] for x in snapshot if x['op'] == 'out' and x['operands'] == '0x3f, r17')
    irq_guard = next(x['line'] for x in code['hms_avr_clock_overflow'] if x['op'] == 'sbis')
    late_guard = next(x['line'] for x in code['hms_avr_clock_overflow'] if x['op'] == 'sbrc')
    setup_constant = next(x['line'] for x in code['hms_avr_clock_start'] if x['op'] == 'ldi' and x['operands'] == 'r17, 0x01')
    high_write = next(x['line'] for x in code['hms_avr_clock_start'] if x['op'] == 'sts' and x['operands'] == '0x0085, r1')
    backward = next(x for x in snapshot if x['op'] == 'rjmp' and x['target'] < x['address'])
    masked_call = next(x['line'] for x in snapshot if x['op'] == 'call' and '<running_config>' in x['line'])
    division_call = next(x['line'] for x in snapshot if x['op'] == 'call' and '<__udivmodsi4>' in x['line'])
    mutations = [
        (low_line,low_line.replace('0x0084','0x0085')),
        (cli_line,cli_line.replace('\tcli','\tnop')),
        (restore_line,restore_line.replace('\tout\t','\tnop\t')),
        (irq_guard,irq_guard.replace('0x16, 0','0x16, 1')),
        (late_guard,late_guard.replace('r24, 7','r24, 6')),
        (setup_constant,setup_constant.replace('r17, 0x01','r17, 0x02')),
        (high_write,high_write.replace('0x0085','0x0084')),
        (backward['line'],re.sub(r';\s*0x[0-9a-f]+','; 0x' + format(backward['address'],'x'),backward['line'])),
        (masked_call,masked_call.split('\tcall\t')[0] + '\tcall\t' + division_call.split('\tcall\t')[1]),
    ]
    for original, changed in mutations:
        require(original != changed, 'Negative instruction fixture unchanged')
        try: inspect_clock(disassembly.replace(original,changed,1))
        except RuntimeError: pass
        else: raise RuntimeError('Damaged instruction fixture accepted: ' + changed)
    instruction_review['rejected_negative_text_fixtures'] = len(mutations)
    instruction_review['negative_scope'] = 'Mutated disassembly text tests checker sensitivity, not executed/corrupted AVR images.'
    (BUILD / 'instruction-review.json').write_text(json.dumps(instruction_review,indent=2)+'\n')
    stacks = []
    for _,name in UNITS:
        for line in (BUILD / (name + '.su')).read_text().splitlines():
            loc,size,kind = line.split('\t')
            require(kind in ('static','dynamic,bounded'), 'Unbounded compiler stack estimate')
            stacks.append(dict(unit=name,function=loc.rsplit(':',1)[-1],bytes=int(size),qualification=kind))
    object_sections = [dict((m[0],int(m[1])) for m in re.findall(r'^(\.[^\s]+)\s+(\d+)\s+\d+',block,re.M))
                       for block in sections.split('\n\n') if 'section' in block]
    symbol_sizes = {m[1]:int(m[0],16) for m in re.findall(r'^[0-9a-f]+ ([0-9a-f]+) [A-Za-z] (\S+)$',symbols,re.M)}
    require(symbol_sizes['hms_avr_clock_probe_state'] == 22 and
            symbol_sizes['hms_avr_clock_probe_sample'] == 24, 'AVR layout changed')
    sizes = dict(linked_probe_flash_bytes=object_sections[0].get('.text',0)+object_sections[0].get('.data',0),
                 linked_probe_static_sram_bytes=object_sections[0].get('.data',0)+object_sections[0].get('.bss',0),
                 driver_function_text_bytes=sum(v for k,v in object_sections[1].items() if k.startswith('.text')),
                 clock_state_bytes=22,sample_bytes=24)
    require(before == {p:digest(ROOT / p) for p in FILES}, 'Original input changed during check')
    for item in primary['inputs']:
        require(digest(ROOT / item['path']) == item['sha256'], 'Primary input changed during check')
    for source in FILES:
        snapshot = BUILD / 'sources' / source
        snapshot.parent.mkdir(parents=True,exist_ok=True)
        snapshot.write_bytes((ROOT / source).read_bytes())
        require(digest(snapshot) == before[source], 'Snapshot mismatch')
    outputs = [record(p) for p in sorted(BUILD.rglob('*')) if p.is_file() and p != BUILD / 'review.json']
    report = dict(schema='hms-avr-timer1-clock/1',created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        passed=True,command='python3 scripts/check_avr_clock.py',files=[dict(path=p,sha256=h) for p,h in before.items()],
        outputs=outputs,host_compiler=host_compiler,native=native,
        avr=dict(target='atmega328p',executed=False,flags=flags,compiler_version=avr_version,
            toolchain_archive=record(ARCHIVE),archive_verified_files=pins,precompile_tool_header_verification=True,
            toolchain_url='https://downloads.arduino.cc/tools/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2',
            instruction_review=instruction_review,compiler_stack_records=stacks,sizes=sizes),
        limitations=[
            'Host register model checks declared semantics and injected scheduling, not AVR cycles, electrical behavior, oscillator tolerance, interrupt latency or physical inhibition.',
            'AVR ELF is statically inspected only; no AVR target, emulator, peripheral, uploader, acquired controller or SDK runs.',
            'Qualification is an explicit external trusted source/service/continuity attestation. Register setup and F_CPU do not qualify time.',
            'Every overflow must be accounted strictly before 32768 subsequent timer ticks (nominal 131.072 ms). Arbitrary missed wraps can alias undetectably; retained counterexample demonstrates the limitation.',
            'Exclusive Timer1 and shared TEMP ownership; no Servo, Timer1 PWM/capture or other Timer1 users. Shared prescaler changes and unaccounted sleep/debug pause require prior invalidation.',
            'Clock state cannot be reinitialized or restarted during a live endpoint boot. Supplied epoch must already be durable and nonreused; no endpoint boot/inhibit flags are manufactured.',
            'Snapshots linearize inside saved-SREG windows; an ISR may fault after restoration and before function return. Fresh effect-boundary sampling and independent inhibition remain necessary.',
            'Preserved SREG writes do not promise C-ABI preservation of arithmetic flags after return.',
            'Separate clock inspection image only. Static flash/SRAM and compiler .su records do not establish combined endpoint/UART/EEPROM fit, worst-case complete call-stack, nested interrupts or time bounds.' ])
    (BUILD / 'review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,native_assertions=native[0]['result']['assertions'],
        avr_cross_linked=True,sizes=sizes,target_executed=False,receipt='artifacts/verification/avr-clock/review.json')))

if __name__ == '__main__':
    main()

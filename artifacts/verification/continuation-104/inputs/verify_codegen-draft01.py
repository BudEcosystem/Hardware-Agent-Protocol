"""Independently join generated text; execute no compiler or candidate."""
import hashlib
import json
from pathlib import Path
import re
import sys

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT/'artifacts/implementation/standing-endpoint-shared-kernel'
PIN = 'e703da177edb24a1beeaa9e828fecb975967fdaf331e612276ecd017c4ddfde0'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def main():
    assert digest(BASE/'codegen-review.json') == PIN
    report = read(BASE/'codegen-review.json')
    for row in report['inputs']:
        path = BASE/row['path']
        assert path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ROOT)
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
    for row in report['exactParentFiles']:
        assert digest(BASE/row['path']) == digest(Path(row['parentPath'])) == row['sha256']
    assembly_path = BASE/'build/avr/compiler-tmp/ccwk0Cum.ltrans0.ltrans.s'
    assembly_bytes = assembly_path.read_bytes().splitlines(keepends=True)
    assembly = assembly_path.read_text(); lines = assembly.splitlines()
    mapped = (BASE/'build/avr/runtime.map').read_text()
    backend = (BASE/'build/avr/compiler-tmp/ccwk0Cum.ltrans0.ltrans.su').read_text().splitlines()
    definitions = re.findall(r'^\s*\.type\s+([^,\s]+),\s*@function\s*$', assembly, re.M)
    assert len(definitions) == len(set(definitions)) == report['functionDefinitionsScanned'] == 131
    aliases = dict(re.findall(r'^\s*\.set\s+([^,\s]+),\s*([^,\s]+)\s*$', assembly, re.M))
    direct = []
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r'\t(?:call|rcall)[ \t]+([^ \t;]+)(?:[ \t]*;.*)?', line)
        if match:
            name = match[1]; direct.append((number, name, aliases.get(name, name)))
    assert len(direct) == report['assemblyDirectCallScanCount'] == 676
    for row in report['manualAssemblyCoverage']:
        data = (BASE/row['path']).read_bytes().splitlines(keepends=True)
        assert 1 <= row['startLine'] <= row['endLine'] <= len(data)
        assert hashlib.sha256(b''.join(data[row['startLine']-1:row['endLine']])).hexdigest() == row['sha256']
    roots = report['functionRoots']; storage = report['chargedStorage']
    retention = read(BASE/'retention.json')
    assert {r['name'] for r in roots} == {r['name'] for r in retention['function_roots']}|{'main'}
    assert {r['name']:r['bytes'] for r in storage} == {r['name']:r['bytes'] for r in retention['storage_roots']}
    assert len(roots) == 30 and len(storage) == 9
    for row in roots+storage+report['kernelBodies']+report['phaseBodies']:
        found = re.findall(r'^ '+re.escape(row['section'])+r'\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)', mapped, re.M)
        assert len(found) == 1 and tuple(int(n, 16) for n in found[0]) == (row['address'], row['bytes']), row['name']
        symbols = re.findall(r'^\s+(0x[0-9a-f]+)\s+'+re.escape(row['name'])+r'\s*$', mapped, re.M)
        assert len(symbols) == 1 and int(symbols[0], 16) == row['address'], row['name']
    ordered = sorted(storage, key=lambda row:row['address'])
    assert sum(row['bytes'] for row in ordered) == 1477
    assert all(0x80011a <= row['address'] < row['address']+row['bytes'] <= 0x8006df for row in ordered)
    assert all(a['address']+a['bytes'] <= b['address'] for a,b in zip(ordered, ordered[1:]))
    kernel_names = {row['name'] for row in report['kernelBodies']}
    assert len(kernel_names) == 19 and {name for name in definitions if name.startswith('hms_ep_')} == kernel_names
    assert not report['kernelSuffixedClonesObserved']
    for row in report['kernelBodies']+report['phaseBodies']:
        first, last = row['assemblyStartLine'], row['assemblyEndLine']
        body_lines = lines[first-1:last]; body = '\n'.join(body_lines)
        assert body_lines[0] == row['name']+':'
        assert re.search(r'\.size\s+'+re.escape(row['name'])+r',', body_lines[-1])
        assert hashlib.sha256(b''.join(assembly_bytes[first-1:last])).hexdigest() == row['assemblyRangeSha256']
        instructions = []
        for number, line in enumerate(body_lines, first):
            match = re.fullmatch(r'\t([a-z][a-z0-9]*)(?:[ \t]+(.*))?', line)
            if match: instructions.append((number, match[1], match[2] or ''))
            assert not re.match(r'\s*\.(?:word|byte|long|space)\b', line), (row['name'], number)
        size = sum(4 if mnemonic in ('call','jmp','lds','sts') else 2 for _,mnemonic,_ in instructions)
        assert len(instructions) == row['instructions'] and size == row['instructionBytes'] == row['bytes']
        calls = [(number, arg, aliases.get(arg, arg)) for number,mnemonic,arg in instructions if mnemonic in ('call','rcall')]
        assert calls == [(r['line'],r['target'],r['resolvedTarget']) for r in row['directCalls']]
        assert [number for number,mnemonic,_ in instructions if mnemonic in ('icall','eicall')] == row['indirectCallLines']
        su = row['backendSu']; location, size_text, kind = backend[su['suLine']-1].split('\t')
        assert location.split(':')[-1] == row['name'] and int(size_text) == su['bytes'] and kind == su['kind']
        frame = re.search(r'/\* frame size = ([0-9]+) \*/', body)
        stack = re.search(r'/\* stack size = ([0-9]+) \*/', body)
        assert frame and stack
        assert int(frame[1]) == row['localFrameBytes'] and int(stack[1]) == row['localAndSavedBytes']
        assert row['savedRegisterBytes'] == int(stack[1])-int(frame[1])
        assert row['maximumExplicitOutgoingBytesImpliedBySu'] == su['bytes']-int(stack[1])-2
    assert sum(row['bytes'] for row in report['kernelBodies']) == report['kernelBodyBytes'] == 2348
    sections = {n:int(re.search(r'^\.'+n+r'\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)', mapped, re.M)[1],16) for n in ('text','data','bss','noinit')}
    assert sections == dict(text=39876,data=26,bss=1477,noinit=0)
    memory = report['memory']
    assert memory == dict(actualWholeStackBound=None,applicationFlashBytes=32256,applicationOverflowBytes=7646,
        arithmeticSramHeadroomBytes=33,bssBytes=1477,combinedFlashReductionBytes=1908,dataBytes=26,
        flashBytes=39902,noinitBytes=0,parentFlashBytes=41810,physicalFlashBytes=32768,physicalOverflowBytes=7134,
        stackReservationBytes=512,staticBaselineBytes=1343,staticDeltaBytes=160,staticPlusReservedStackBytes=2015,
        staticSramBytes=1503,textBytes=39876)
    assert not any(report['qualifications'].values()) and not (BASE/'build/avr/runtime.elf').exists()
    intent = read(BASE/'build/avr/avr-link.intent.json')
    assert all(flag in intent['argv'] for flag in report['requiredFlagsPresent'])
    result = dict(status='verified-generated-text-joins', verificationSourceSha256=digest(Path(__file__)),
        codegenReviewSha256=PIN,inputPinsVerified=19,exactParentFiles=7,manualRangeHashesVerified=14,
        retainedFunctionRoots=30,chargedStorageObjects=9,kernelBodies=19,kernelBodyBytes=2348,
        phaseBodies=25,functionDefinitionsScanned=131,directCallsScanned=676,memory=memory,
        completeStackProof=False,targetFitEstablished=False,candidateOrCompilerExecuted=False)
    with (HERE/'codegen-verification.json').open('x') as stream:
        json.dump(result,stream,indent=2); stream.write('\n')
    print(json.dumps(result,sort_keys=True))

if __name__ == '__main__':
    main()

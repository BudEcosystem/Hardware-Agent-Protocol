"""Read pinned failed-link text only. No candidate imports or child processes.

Prepared for root review; invocation creates one new exclusive JSON output.
Instruction widths are for the retained ATmega328P assembly, not a general ISA
parser. Backend frame differences are not a control-flow or whole-stack proof.
"""
import collections
import hashlib
import json
from pathlib import Path
import re
import sys

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CURRENT = 'artifacts/implementation/standing-endpoint-phase-kernels/'
PARENT = 'artifacts/implementation/standing-endpoint-shared-kernel/'
PINS = {
    CURRENT+'build/avr/runtime.map': '12336960e81dbb8d6dd998ea2d061fabb5db1df8a509a1bd8d9a50585610328c',
    CURRENT+'build/avr/compiler-tmp/ccyhFurg.ltrans0.ltrans.s': 'e78c50ce5dbae980a41a1fc0fe2fedf59060da8dc0c0ceb0aba2b3187bfef5db',
    CURRENT+'build/avr/compiler-tmp/ccyhFurg.ltrans0.ltrans.su': '882f38944c3d9cd56dbdd411e20c6f5c45f0657cb291aae75966bc73df0ad525',
    CURRENT+'retention.json': 'a5dab28795f806d28b1f03282b5af83eba11cb0b9266c1f21102bef748ef3203',
    PARENT+'build/avr/runtime.map': 'f18a9cd604435d904390a47247575589786f4bf3cd2661b837cb2d8ab88326a5',
    PARENT+'build/avr/compiler-tmp/ccwk0Cum.ltrans0.ltrans.s': '519cad7b1b898022ace7ec479df93f6dca162c1a99f5c6a420fde5c5c7969213',
    PARENT+'build/avr/compiler-tmp/ccwk0Cum.ltrans0.ltrans.su': '2d226831c9c87e76d7310be3e2ebedc7d25b1b6898561f018834d93f6959b669',
    PARENT+'retention.json': 'a5dab28795f806d28b1f03282b5af83eba11cb0b9266c1f21102bef748ef3203',
    PARENT+'index.json': '0a4a518555e08415a9d893bba106616323a3f1a237b61bf0bc171ee8f2979909',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def text(name):
    return (ROOT/name).read_text()


def measure(base, assembly_leaf, expected):
    map_lines = text(base+'build/avr/runtime.map').splitlines()
    allocated = []; aggregate = {}; symbols = {}; active = False
    for index, line in enumerate(map_lines):
        if line.startswith('Linker script and memory map'):
            active = True
        if not active:
            continue
        head = re.match(r'^\.(text|data|bss|noinit)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)', line)
        if head:
            assert head[1] not in aggregate
            aggregate[head[1]] = dict(address=int(head[2],16), bytes=int(head[3],16), line=index+1)
        symbol = re.fullmatch(r'\s+0x([0-9a-f]+)\s+([A-Za-z_][A-Za-z_0-9.]*)',line)
        if symbol:
            symbols.setdefault(symbol[2], set()).add(int(symbol[1],16))
        section = re.match(r'^ (\.[^\s]+)\s*(.*)$', line)
        if not section:
            continue
        tail = section[2] or map_lines[index+1].strip()
        body = re.fullmatch(r'0x([0-9a-f]+)\s+0x([0-9a-f]+)(?:\s+(.*))?',tail)
        if body and int(body[2],16):
            allocated.append(dict(section=section[1],address=int(body[1],16),bytes=int(body[2],16),
                                  origin=body[3],mapLine=index+1))
    assert {k:v['bytes'] for k,v in aggregate.items()} == expected
    text_sections = [r for r in allocated if re.match(r'^\.(text|init|fini|vectors|trampolines|jumptables|lowtext)',r['section'])]
    ordered = sorted(text_sections,key=lambda r:r['address'])
    assert ordered[0]['address'] == 0
    assert all(a['address']+a['bytes'] == b['address'] for a,b in zip(ordered,ordered[1:]))
    assert ordered[-1]['address']+ordered[-1]['bytes'] == sum(r['bytes'] for r in ordered) == expected['text']
    assembly_name = base+'build/avr/compiler-tmp/'+assembly_leaf
    assembly = text(assembly_name); lines = assembly.splitlines(); raw = assembly.splitlines(keepends=True)
    aliases = dict(re.findall(r'^\s*\.set\s+([^,]+),([^\s]+)',assembly,re.M))

    def resolve(name):
        visited = set()
        while name in aliases:
            assert name not in visited
            visited.add(name); name = aliases[name]
        return name

    functions = []
    for index,line in enumerate(lines):
        match = re.fullmatch(r'\s*\.type\s+([^,]+), @function',line)
        if not match:
            continue
        name = match[1]
        end = next(i for i in range(index+1,len(lines)) if lines[i].startswith('\t.size\t'+name+','))
        section = next(re.match(r'\s*\.section\s+([^,]+)',lines[i])[1] for i in range(index,-1,-1)
                       if re.match(r'\s*\.section\s+([^,]+)',lines[i]))
        instructions = []; tables = 0; calls = []; operations = collections.Counter(); stack_ops = []
        for i in range(index,end+1):
            instruction = re.fullmatch(r'\t([a-z][a-z0-9]*)(?:[ \t]+([^\n]*))?',lines[i])
            if instruction:
                op,args = instruction[1],instruction[2] or ''
                width = 4 if op in ('call','jmp','lds','sts') else 2
                instructions.append((op,args,i+1,width)); operations[op] += width
                if op in ('call','rcall','icall','jmp','ijmp'):
                    calls.append(dict(line=i+1,opcode=op,target=args,resolved=resolve(args),
                                      kind=('stack-allocation' if op=='rcall' and args=='.' else
                                            'direct-call' if op in ('call','rcall') else
                                            'indirect-call' if op=='icall' else 'jump')))
                if op in ('push','pop') or (op=='out' and args.startswith(('__SP_L__','__SP_H__'))):
                    stack_ops.append(dict(line=i+1,opcode=op,operands=args))
            if re.match(r'^\t\.word[ \t]',lines[i]):
                tables += 2*len(lines[i].split(None,1)[1].split(','))
        rows = [r for r in text_sections if r['section']==section]
        assert len(rows)==1
        size = sum(r[3] for r in instructions)+tables
        assert size == rows[0]['bytes'], (name,size,rows)
        body = '\n'.join(lines[index:end+1])
        frame = re.findall(r'/\* frame size = ([0-9]+) \*/',body)
        stack = re.findall(r'/\* stack size = ([0-9]+) \*/',body)
        assert len(frame)==len(stack)==1
        prologue = next(i for i in range(index,end+1) if lines[i].startswith('/* prologue:'))
        prologue_instructions = [r for r in instructions if r[2]<=prologue+1]
        pushes = [r for r in prologue_instructions if r[0]=='push']
        # This GCC profile uses named __zero_reg__ pushes as one-byte local
        # allocation, and rcall . as two-byte allocation on ATmega328P.
        # IRQ saves use explicit r1/r0 (including the second r0 SREG save),
        # and must remain charged as saves rather than local allocation.
        local_pushes = [r for r in pushes if r[1]=='__zero_reg__']
        saved_pushes = [r for r in pushes if re.fullmatch(r'r(?:[0-9]|[12][0-9]|3[01])',r[1])]
        assert len(saved_pushes)+len(local_pushes)==len(pushes), (name,pushes)
        local_calls = [r for r in prologue_instructions if r[0]=='rcall' and r[1]=='.']
        pushed_local_bytes = len(local_pushes)+2*len(local_calls)
        assert pushed_local_bytes==0 or pushed_local_bytes==int(frame[0]), (name,pushed_local_bytes,frame)
        assert len(saved_pushes)==int(stack[0])-int(frame[0]), (name,saved_pushes,frame,stack)
        functions.append(dict(name=name,section=section,bytes=size,address=rows[0]['address'],
            firstLine=index+1,lastLine=end+1,rangeSha256=sha(''.join(raw[index:end+1]).encode()),
            instructions=len(instructions),instructionBytes=size-tables,tableBytes=tables,
            opcodeBytes=dict(sorted(operations.items())),transfers=calls,stackOperations=stack_ops,
            frameLocalBytes=int(frame[0]),savedRegisterBytes=len(saved_pushes),entryStackBytes=int(stack[0]),
            pushedLocalBytes=pushed_local_bytes,prologueLocalAllocationSites=[
                dict(line=r[2],opcode=r[0],operands=r[1]) for r in local_pushes+local_calls]))
    su_lines = text(assembly_name+'u').splitlines()
    assert len(functions)==len(su_lines)
    owners = collections.Counter(); call_counts = collections.Counter()
    for row,line in zip(functions,su_lines):
        location,count,kind = line.split('\t'); owner,number,column,name = location.split(':',3)
        assert row['name']==name or row['name'].startswith(name+'.'), (row['name'],name)
        row['emittedOwner']=owner
        row['backendFrame']=dict(bytes=int(count),kind=kind,sourceLine=int(number))
        row['backendImpliedMaxAdditionalBytes']=int(count)-row['entryStackBytes']-2
        assert row['backendImpliedMaxAdditionalBytes']>=0
        owners[owner] += row['bytes']
        call_counts.update(t['resolved'] for t in row['transfers'] if t['kind']=='direct-call')
    sections = {row['section'] for row in functions}
    other = [row for row in text_sections if row['section'] not in sections]
    assert sum(owners.values())+sum(r['bytes'] for r in other)==expected['text']
    retention=json.loads(text(base+'retention.json'))
    roots = [r['name'] for r in retention['function_roots']]+retention['other_required_symbols']
    assert len(roots)==30 and len(set(roots))==30
    root_evidence=[]
    for name in roots:
        rows=[r for r in functions if r['name']==name]
        assert len(rows)==1 and symbols[name]=={rows[0]['address']}
        root_evidence.append(dict(name=name,address=rows[0]['address'],bytes=rows[0]['bytes']))
    storage=[]
    for root in retention['storage_roots']:
        rows=[r for r in allocated if r['section']=='.bss.'+root['name']]
        assert len(rows)==1 and rows[0]['bytes']==root['bytes'] and symbols[root['name']]=={rows[0]['address']}
        storage.append(dict(name=root['name'],**rows[0]))
    assert len(storage)==9 and sum(r['bytes'] for r in storage)==expected['bss']
    return dict(base=base,assembly=assembly_name,sections=aggregate,flashBytes=expected['text']+expected['data'],
        staticBytes=expected['data']+expected['bss'],allocatedTextSections=text_sections,
        emittedFunctions=functions,emittedFunctionCount=len(functions),emittedBodyBytes=sum(owners.values()),
        emittedOwnerBodyBytes=dict(sorted(owners.items())),otherTextSections=other,
        otherTextBytes=sum(r['bytes'] for r in other),aliases=aliases,roots=root_evidence,storage=storage,
        directCallCounts=dict(sorted(call_counts.items())),directCallSites=sum(call_counts.values()),
        automaticCoverage=dict(map='all positive allocated text input sections, aggregate sections,30 function roots and9 storage roots',
            assembly='all emitted function ranges and widths, alias definitions, explicit transfers and stack operations',
            backend='all emitted functions joined in order to backend .su; these are not pre-LTO .su'),
        frameLimit='Local/save comments checked against profile-specific register-save and local-allocation pushes, including rcall .; IRQ r1/r0/SREG saves remain charged. Backend additional count is not manual outgoing-lifetime or CFG proof.')


def main():
    assert len(sys.argv)==1
    output=HERE/'codegen-measurements.json'
    assert not output.exists()
    before={name:sha((ROOT/name).read_bytes()) for name in PINS}
    assert before==PINS
    parent=measure(PARENT,'ccwk0Cum.ltrans0.ltrans.s',dict(text=39876,data=26,bss=1477,noinit=0))
    current=measure(CURRENT,'ccyhFurg.ltrans0.ltrans.s',dict(text=39160,data=26,bss=1477,noinit=0))
    old={r['name']:r for r in parent['emittedFunctions']}
    new={r['name']:r for r in current['emittedFunctions']}
    comparison=[]
    for name in sorted(set(old)|set(new)):
        a=old.get(name); b=new.get(name)
        comparison.append(dict(name=name,parentBytes=a['bytes'] if a else 0,currentBytes=b['bytes'] if b else 0,
                               deltaBytes=(b['bytes'] if b else 0)-(a['bytes'] if a else 0)))
    assert sum(r['deltaBytes'] for r in comparison)==current['emittedBodyBytes']-parent['emittedBodyBytes']
    assert before=={name:sha((ROOT/name).read_bytes()) for name in PINS}
    report=dict(schema='hms-phase-kernel-codegen-measurements/1',status='failed-link-retained-data-only',
        inputs=PINS,readerSha256=sha(Path(__file__).read_bytes()),parent=parent,current=current,functionNameComparison=comparison,
        flashReductionBytes=parent['flashBytes']-current['flashBytes'],physicalOverflowBytes=current['flashBytes']-32768,
        applicationOverflowBytes=current['flashBytes']-32256,supportedFit=False,validElf=False,completeStackProof=False,
        comparisonLimit='Combined source/profile result; name deltas include changed inlining ownership and are not isolated per-edit savings.',
        candidateImported=False,compilerExecuted=False,targetExecuted=False)
    with output.open('x') as out:
        json.dump(report,out,indent=2,sort_keys=True); out.write('\n')
    print(json.dumps(dict(functions=current['emittedFunctionCount'],flash=current['flashBytes'],static=current['staticBytes'],
        physicalOverflow=report['physicalOverflowBytes'],applicationOverflow=report['applicationOverflowBytes'],
        reduction=report['flashReductionBytes'],completeStackProof=False)))


if __name__=='__main__':
    main()

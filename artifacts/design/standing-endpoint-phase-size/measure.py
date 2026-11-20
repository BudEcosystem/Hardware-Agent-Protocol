"""Retained text/byte attribution only; never import a candidate or launch a tool."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sys

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 'artifacts/implementation/standing-endpoint-shared-kernel/'
INPUTS_SHA256 = '92ac0f09dc0e4648e08fcce64986560a0b73c1151d0116ea90f70d29925928b9'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source(name):
    return HERE/'inputs'/name


def read(name):
    return source(name).read_text()


def main():
    assert sha((HERE/'inputs.json').read_bytes()) == INPUTS_SHA256
    pins = json.loads((HERE/'inputs.json').read_text())['files']
    for row in pins:
        data = (HERE/row['copy']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
        assert (ROOT/row['source']).read_bytes() == data
    before = {row['source']:sha((ROOT/row['source']).read_bytes()) for row in pins}
    map_lines = read(BASE+'build/avr/runtime.map').splitlines()
    allocated = []; active = False; aggregate = {}
    for index,line in enumerate(map_lines):
        if line.startswith('Linker script and memory map'): active = True
        if not active: continue
        head = re.match(r'^\.(text|data|bss|noinit)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)',line)
        if head:
            assert head[1] not in aggregate
            aggregate[head[1]] = int(head[3],16)
        match = re.match(r'^ (\.(?:text|init|fini|vectors|trampolines|jumptables|lowtext)[^\s]*)\s*(.*)$',line)
        if not match: continue
        tail = match[2] or map_lines[index+1].strip()
        body = re.fullmatch(r'0x([0-9a-f]+)\s+0x([0-9a-f]+)(?:\s+(.*))?',tail)
        if body and int(body[2],16):
            allocated.append(dict(section=match[1],address=int(body[1],16),bytes=int(body[2],16),
                                  origin=body[3],mapLine=index+1))
    assert aggregate == dict(text=39876,data=26,bss=1477,noinit=0)
    ordered = sorted(allocated,key=lambda row:row['address'])
    assert ordered[0]['address'] == 0
    assert all(a['address']+a['bytes'] == b['address'] for a,b in zip(ordered,ordered[1:]))
    assert ordered[-1]['address']+ordered[-1]['bytes'] == sum(row['bytes'] for row in allocated) == aggregate['text']
    assembly_name = BASE+'build/avr/compiler-tmp/ccwk0Cum.ltrans0.ltrans.s'
    assembly = read(assembly_name); lines = assembly.splitlines(); raw = assembly.splitlines(keepends=True)
    aliases = dict(re.findall(r'^\s*\.set\s+([^,]+),([^\s]+)',assembly,re.M))
    def resolve(name):
        visited = set()
        while name in aliases:
            assert name not in visited; visited.add(name); name = aliases[name]
        return name
    functions = []
    for index,line in enumerate(lines):
        match = re.fullmatch(r'\s*\.type\s+([^,]+), @function',line)
        if not match: continue
        name = match[1]
        end = next(i for i in range(index+1,len(lines)) if lines[i].startswith('\t.size\t'+name+','))
        section = next(re.match(r'\s*\.section\s+([^,]+)',lines[i])[1] for i in range(index,-1,-1)
                       if re.match(r'\s*\.section\s+([^,]+)',lines[i]))
        instructions = []; table_bytes = 0; calls = []; categories = collections.Counter()
        for i in range(index,end+1):
            ins = re.fullmatch(r'\t([a-z][a-z0-9]*)(?:[ \t]+([^\n]*))?',lines[i])
            if ins:
                op,args = ins[1],ins[2] or ''; width = 4 if op in ('call','jmp','lds','sts') else 2
                instructions.append((op,args,i+1,width)); categories[op] += width
                if op == 'call': calls.append(dict(line=i+1,target=args,resolved=resolve(args)))
            if re.match(r'^\t\.word[ \t]',lines[i]): table_bytes += 2*len(lines[i].split(None,1)[1].split(','))
        rows = [row for row in allocated if row['section'] == section]
        assert len(rows) == 1
        size = sum(row[3] for row in instructions)+table_bytes
        assert size == rows[0]['bytes'], (name,size,rows)
        functions.append(dict(name=name,section=section,bytes=size,address=rows[0]['address'],
            firstLine=index+1,lastLine=end+1,rangeSha256=sha(''.join(raw[index:end+1]).encode()),
            instructions=len(instructions),instructionBytes=size-table_bytes,tableBytes=table_bytes,
            opcodeBytes=dict(sorted(categories.items())),directCalls=calls))
    su_lines = read(BASE+'build/avr/compiler-tmp/ccwk0Cum.ltrans0.ltrans.su').splitlines()
    assert len(functions) == len(su_lines) == 131
    source_bytes = collections.Counter(); call_counts = collections.Counter()
    for row,line in zip(functions,su_lines):
        location,count,kind = line.split('\t'); owner,number,column,name = location.split(':',3)
        assert row['name'] == name or row['name'].startswith(name+'.'), (row['name'],name)
        row['emittedOwner'] = owner; row['backendFrame'] = dict(bytes=int(count),kind=kind,sourceLine=int(number))
        source_bytes[owner] += row['bytes']
        call_counts.update(item['resolved'] for item in row['directCalls'])
    body_sections = {row['section'] for row in functions}
    other = [row for row in allocated if row['section'] not in body_sections]
    assert sum(source_bytes.values()) == 39322 and sum(row['bytes'] for row in other) == 554
    retention = json.loads(read(BASE+'retention.json'))
    roots = {row['name'] for row in retention['function_roots']}
    root_sizes = {row['name']:row['bytes'] for row in functions if row['name'] in roots}
    wpa_name = BASE+'build/avr/runtime.elf.wpa.078i.inline'; wpa = read(wpa_name).splitlines()
    first = max(i for i,line in enumerate(wpa) if line == 'Symbol table:')
    starts = [i for i in range(first,len(wpa)) if re.match(r'^[^ /]+/[0-9]+ \([^)]+\) @',wpa[i])]
    inline_copies = []
    for start,end in zip(starts,starts[1:]+[len(wpa)]):
        name = wpa[start].split('/')[0]; text = '\n'.join(wpa[start:end])
        match = re.search(r'Function [^\n]+ is inline copy in ([^\n]+)',text)
        if name in roots and match:
            inline_copies.append(dict(name=name,caller=match[1],standaloneBodyBytes=root_sizes[name],
                firstLine=start+1,lastLine=end,rangeSha256=sha(('\n'.join(wpa[start:end])+'\n').encode())))
    assert len(inline_copies) == 10 and sum(row['standaloneBodyBytes'] for row in inline_copies) == 224
    groups = dict(sorted(source_bytes.items()))
    measured = dict(schema='hms-standing-phase-attribution/1',status='retained-source-and-text-only',
        sections=aggregate,flashBytes=39902,physicalGapBytes=7134,applicationGapBytes=7646,
        allocatedTextSections=allocated,allocatedTextSectionCount=len(allocated),emittedFunctions=functions,
        emittedOwnerBodyBytes=groups,emittedBodyBytes=39322,otherTextSections=other,otherTextBytes=554,
        directCallCounts=dict(sorted(call_counts.items())),directCallSites=sum(call_counts.values()),
        retainedRootInlineCopies=inline_copies,weightedStandaloneSizeOfInlineCopies=224,
        inlineCopySizeIsNotSavingsEstimate=True,sourceOwnerIncludesInlinedDescendants=True,
        candidateImplemented=False,expectedSavingsKnown=False,compilerExecuted=False,targetExecuted=False,
        supportedFit=False,completeStackProof=False)
    spans = [(5600,5795,'raw view containing complete add_room body and preceding tail'),
             (5794,6015,'complete elapsed_cmp instruction view'),(6017,6217,'complete time_cmp instruction view'),
             (14380,14450,'finite capture instruction/branch view'),(14725,14865,'finite time checks instruction/branch view'),
             (14980,15060,'finite post-guard checks instruction/branch view'),
             (23900,24120,'standing acquisition/capture instruction/branch view'),
             (24400,24607,'standing acceptance/commit instruction/branch view'),
             (30240,30415,'startup retained calls/init instruction/branch view')]
    coverage = dict(schema='hms-standing-phase-coverage/1',inputsSha256=sha((HERE/'inputs.json').read_bytes()),
        assemblyAutomaticScope='All131 bodies, instructions/table widths, calls, aliases and emitted-owner joins; not a full manual semantic assembly read.',
        mapAutomaticScope='All151 nonzero allocated text input sections; exact contiguous coverage of aggregate text.',
        wpaAutomaticScope='Final symbol-table blocks scanned for copies of29 forced public function roots.',
        manualAssemblyViews=[dict(source=assembly_name,firstLine=a,lastLine=b,scope=scope,
            rawRangeSha256=sha(''.join(raw[a-1:b]).encode())) for a,b,scope in spans],
        manualWpaRanges=[dict(source=wpa_name,firstLine=a,lastLine=b) for a,b in [(11943,12015),(12500,12585),(6780,6915)]],
        completeCFilesRead=[BASE+'project/'+name for name in ['protocol/endpoint/endpoint.c','protocol/endpoint/standing.c',
            'protocol/endpoint/endpoint_kernel.c','protocol/endpoint/endpoint_kernel.h','protocol/endpoint/link.c',
            'protocol/platform/avr_runtime.c','protocol/platform/avr_clock.c','protocol/platform/boot_epoch.c','tests/standing_fixture.c']],
        proposalFilesRead=['artifacts/design/standing-endpoint-size-reduction/'+name for name in ['PROPOSAL.md','SEMANTICS.md','CONTROLS.md']],
        manualReadingIsNotUniversalSemanticProof=True)
    assert before == {row['source']:sha((ROOT/row['source']).read_bytes()) for row in pins}
    for name,value in [('measurements.json',measured),('coverage.json',coverage)]:
        with (HERE/name).open('x') as out: json.dump(value,out,indent=2,sort_keys=True); out.write('\n')
    print(json.dumps(dict(inputFiles=len(pins),functions=len(functions),text=aggregate['text'],flash=39902,
        bodyBytes=39322,otherTextBytes=554,rootInlineCopies=len(inline_copies),candidateExecuted=False)))


if __name__ == '__main__':
    assert len(sys.argv) == 1
    main()

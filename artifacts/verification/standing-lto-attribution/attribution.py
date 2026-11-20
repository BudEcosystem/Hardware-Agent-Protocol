#!/usr/bin/env python3
"""Read retained text/JSON only; never import or invoke candidate/tool code."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LTO = ROOT/'artifacts/implementation/standing-endpoint-lto'
FIT = ROOT/'artifacts/implementation/standing-endpoint-fit'
BUILD = LTO/'build/avr-attempt-2'
ASM = BUILD/'compiler-tmp/cc1w4vmK.ltrans0.ltrans.s'
NAMES = ('hms_standing_poll','hms_standing_handle','hms_endpoint_poll','hms_endpoint_handle')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def new_json(path, value):
    with path.open('x') as out:
        json.dump(value,out,indent=2,sort_keys=True);out.write('\n')

def section(text,name):
    matches=list(re.finditer(r'^ \.text\.'+re.escape(name)+r'\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)',text,re.M))
    assert len(matches)==1,(name,len(matches))
    return {'address':int(matches[0][1],16),'bytes':int(matches[0][2],16)}

def main():
    sources=[ASM,BUILD/'runtime.map',FIT/'build/avr/runtime.map',
             BUILD/'runtime.elf.wpa.078i.inline',BUILD/'runtime.elf.ltrans0.078i.inline',
             BUILD/'runtime.elf.wpa.000i.cgraph',BUILD/'runtime.elf.ltrans0.000i.cgraph',
             BUILD/'pre-lto-stack-records.json',
             BUILD/'compiler-tmp/cc1w4vmK.ltrans0.ltrans.su',
             LTO/'project/protocol/endpoint/standing.c',LTO/'project/protocol/endpoint/endpoint.c']
    validation=[]
    for base in (LTO,FIT):
        index=json.loads((base/'index.json').read_text())
        for row in index['files']:
            path=base/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
        validation.append({'path':str(base.relative_to(ROOT)),'index_sha256':sha(base/'index.json'),
                           'files':len(index['files']),'bytes':sum(row['bytes'] for row in index['files'])})
    lines=ASM.read_text().splitlines()
    files={int(m[1]):m[2] for line in lines if (m:=re.match(r'\s*\.file (\d+) "([^"]+)"',line))}
    aliases={m[1]:m[2] for line in lines if (m:=re.match(r'\s*\.set\s+(\w+),(\w+)',line))}
    current_map=(BUILD/'runtime.map').read_text();parent_map=(FIT/'build/avr/runtime.map').read_text()
    result=[]
    for name in NAMES:
        first=lines.index(name+':')
        last=next(i for i in range(first,len(lines)) if re.match(r'\s*\.size\s+'+name+r',',lines[i]))
        body=lines[first:last+1]
        with (HERE/(name+'.raw.s')).open('x') as out:out.write('\n'.join(body)+'\n')
        loc=None;calls=[];instructions=[];mnemonics=Counter();loc_bytes=Counter();directives=[];table_bytes=0
        compact=[]
        for offset,line in enumerate(body,first+1):
            source=re.match(r'\s*\.loc (\d+) (\d+)',line)
            if source:loc=(files[int(source[1])],int(source[2]))
            instruction=re.match(r'^\t([a-z][a-z0-9]*)\s*(.*?)\s*$',line)
            if instruction:
                op,operand=instruction.groups();width=4 if op in ('call','jmp','lds','sts') else 2
                row={'assembly_line':offset,'opcode':op,'operand':operand,'bytes':width,'location':loc}
                instructions.append(row);mnemonics[op]+=1
                loc_bytes[str(loc)]+=width
                compact.append(str(offset)+':'+op+(' '+operand if operand else ''))
                if op in ('call','rcall','icall','eicall'):
                    calls.append({**row,'resolved_alias':aliases.get(operand,operand)})
            elif re.match(r'^\.L[0-9]+:',line):compact.append(str(offset)+':'+line)
            elif line.strip().startswith(('.byte','.word','.long','.align','.p2align','.balign')):
                directives.append({'assembly_line':offset,'text':line})
                if re.fullmatch(r'\s*\.word gs\(\.L[0-9]+\)',line):table_bytes+=2
                else:
                    assert re.fullmatch(r'\s*\.p2align\s+1',line),(name,line)
                    assert (sum(row['bytes'] for row in instructions)+table_bytes)%2==0
                compact.append(str(offset)+':'+line.strip())
        actual=section(current_map,name);prior=section(parent_map,name)
        assert sum(row['bytes'] for row in instructions)+table_bytes==actual['bytes'],name
        with (HERE/(name+'.instructions.txt')).open('x') as out:
            for i in range(0,len(compact),6):out.write(' | '.join(compact[i:i+6])+'\n')
        direct=Counter(row['resolved_alias'] for row in calls if row['opcode'] in ('call','rcall'))
        result.append({'name':name,'assembly_lines_inclusive':[first+1,last+1],
                       'fit_map':prior,'lto_map':actual,'change_bytes':actual['bytes']-prior['bytes'],
                       'instructions':len(instructions),'instruction_plus_table_bytes_reconcile_map':True,
                       'inline_table_bytes':table_bytes,'inline_data_directives':directives,
                       'mnemonics':dict(mnemonics),'direct_static_call_sites':dict(sorted(direct.items())),
                       'indirect_static_call_sites':sum(row['opcode'] in ('icall','eicall') for row in calls),
                       'call_sites':calls,'debug_location_bytes':dict(loc_bytes),
                       'debug_location_scope':'Exact assembler .loc attribution only; optimizer debug locations are not exclusive semantic cost attribution.'})
    new_json(HERE/'attribution.json',{'schema':'hms-standing-lto-retained-attribution/1','inputs':[
        {'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path)} for path in sources],
        'parent_revalidation':validation,'aliases':aliases,'functions':result,
        'scope':'Text parsing of retained failed maps and assembler listings; static instruction sites, not runtime frequencies or final stack proof.',
        'candidate_or_compiler_executed':False,'target_executed':False,'combined_stack_proof':False})
    print(json.dumps([{'name':row['name'],'fit':row['fit_map']['bytes'],'lto':row['lto_map']['bytes'],
        'instructions':row['instructions'],'direct_calls':row['direct_static_call_sites'],
        'indirect_calls':row['indirect_static_call_sites']} for row in result],indent=2))

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Read retained linked artifacts; execute no compiler, target, or probe.

Exact installed callback graph only. Parent source review precedes invocation.
Output is an arithmetic static bound, never runtime or timing qualification.
"""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
BUILD=HERE/'build/avr-attempt-2'
OUTPUT=HERE/'combined-stack-analysis.json'
CALLBACKS={
    ('endpoint','constant_copy'):(1,[('runtime','constant')]),
    ('endpoint','guard_call'):(1,[('runtime','guard')]),
    ('endpoint','sample_clock'):(1,[('runtime','clock_snapshot')]),
    ('endpoint','hms_endpoint_handle'):(2,[('runtime','constant'),('runtime','describe')]),
    ('endpoint','hms_endpoint_poll'):(1,[('runtime','step')]),
    ('uart','hms_avr_uart_frame_step_hook'):(1,[('runtime','before_feed')]),
    ('boot','hms_boot_header_byte'):(1,[('runtime','incarnation')]),
    ('boot','hms_boot_acquire'):(5,[('runtime','incarnation'),('runtime','read_byte'),('runtime','write_zero')]),
    ('runtime','constant'):(1,[('fixture','constant_byte')]),
    ('runtime','describe'):(1,[('fixture','describe')]),
    ('runtime','guard'):(1,[('fixture','guard')]),
    ('runtime','step'):(1,[('fixture','step')]),
}
HELPERS={'__udivmodsi4','__bswapsi2','__ashldi3','__lshrdi3','__adddi3','__adddi3_s8',
         '__subdi3','__cmpdi2','__cmpdi2_s8','memcmp','memcpy'}

def require(test,message):
    if not test:raise RuntimeError(message)

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    require(not OUTPUT.exists(),'Preserve existing analysis; do not overwrite')
    paths=[BUILD/name for name in ('runtime.elf','runtime.map','avr-disassembly.stdout','symbols.json','stack-records.json')]
    paths += [HERE/'checks-avr-attempt-2.json',Path(__file__)]
    before={str(p.relative_to(HERE)):digest(p) for p in paths}
    map_text=(BUILD/'runtime.map').read_text()
    disassembly=(BUILD/'avr-disassembly.stdout').read_text()
    symbols=json.loads((BUILD/'symbols.json').read_text())
    records=json.loads((BUILD/'stack-records.json').read_text())
    build_receipt=json.loads((HERE/'checks-avr-attempt-2.json').read_text())
    require(build_receipt['requested_checks_completed'] and build_receipt['sources_unchanged'] and
            build_receipt['copied_sources_unchanged'] and build_receipt['owned_groups_absent'],'Build audit did not pass')
    for name,expected in build_receipt['sources'].items():
        require(digest(BUILD/name)==expected,'Copied build source differs: '+name)
    sections=[]
    for match in re.finditer(r'^ (\.text[^\s]*)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+(\S+)',map_text,re.M):
        section,address,size,obj=match.groups()
        if str(obj).startswith(str(BUILD)+'/'):
            sections.append((int(address,16),int(size,16),Path(obj).stem,section))
    instructions=[]
    for line in disassembly.splitlines():
        match=re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*([a-z][a-z0-9]*)\s*(.*)',line)
        if match:
            address,encoded,op,operands=match.groups()
            instructions.append({'address':int(address,16),'bytes':len(encoded.split()),'op':op,'operands':operands})
    frames={(r['unit'],r['function']):r for r in records}
    require(len(frames)==len(records),'Duplicate compiler frame record')
    nodes={};original={}
    for symbol in symbols:
        if symbol['type'] not in ('T','t') or not symbol['bytes']:continue
        address=symbol['address']
        owner=next((unit for start,size,unit,_ in sections if start<=address<start+size),None)
        key=(owner,symbol['name'])
        code=[i for i in instructions if address<=i['address']<address+symbol['bytes']]
        nodes[address]={**symbol,'unit':owner,'instructions':code,'edges':set(),'indirect':[]}
        if key in frames:
            require(frames[key]['qualification'] in ('static','dynamic,bounded'),'Unbounded source frame')
            nodes[address]['frame_bytes']=frames[key]['bytes']
            nodes[address]['frame_basis']='GCC .su '+frames[key]['qualification']
            original[key]=address
    require(len(original)==len(records),'A compiler stack record lacks its linked function')
    for key,address in original.items():
        node=nodes[address]
        for inst in node['instructions']:
            op=inst['op']
            if op in ('icall','eicall','ijmp','eijmp'):
                require(op=='icall' and key in CALLBACKS,'Unknown indirect dispatch '+str(key))
                node['indirect'].append(inst['address'])
                node['edges'].update(original[target] for target in CALLBACKS[key][1])
            elif op in ('call','rcall','jmp','rjmp') or op.startswith('br'):
                match=re.search(r'0x([0-9a-f]+)',inst['operands'])
                require(match is not None,'Unresolved transfer '+str(inst))
                target=int(match.group(1),16)
                if op=='rcall' and target==inst['address']+inst['bytes']:continue # GCC local allocation, in .su.
                if address<=target<address+node['bytes']:
                    require(op not in ('call','rcall'),'Recursive internal call');continue
                require(target in nodes,'Unknown cross-function destination '+hex(target))
                node['edges'].add(target)
        require(len(node['indirect'])==CALLBACKS.get(key,(0,[]))[0],'Indirect count changed: '+str(key))
    helper_addresses={target for address in original.values() for target in nodes[address]['edges'] if target not in original.values()}
    for address in helper_addresses:
        node=nodes[address]
        require(node['name'] in HELPERS,'Unreviewed helper '+node['name'])
        for inst in node['instructions']:
            require(inst['op'] not in ('push','pop','call','rcall','icall','eicall','ijmp','eijmp','out','sts'),
                    'Helper stack/control writes need review: '+str(inst))
            if inst['op'] in ('jmp','rjmp') or inst['op'].startswith('br'):
                match=re.search(r'0x([0-9a-f]+)',inst['operands'])
                require(match is not None and address<=int(match.group(1),16)<address+node['bytes'],
                        'Helper external branch/fallthrough')
        require(node['instructions'][-1]['op']=='ret','Helper lacks closing ret')
        node['frame_bytes']=2
        node['frame_basis']='Inspected linked leaf: no stack adjustment/call; two-byte return address'
    memo={}
    def longest(address,active=frozenset()):
        require(address not in active,'Recursive call graph')
        if address in memo:return memo[address]
        node=nodes[address];require('frame_bytes' in node,'Missing frame '+node['name'])
        choices=[(0,[])]
        for child in sorted(node['edges']):
            count,path=longest(child,active|{address});choices.append((count+2,path))
        count,path=max(choices,key=lambda item:(item[0],item[1]))
        memo[address]=(node['frame_bytes']+count,[address]+path);return memo[address]
    for address in original.values():longest(address)
    def bound(key,extra=0):
        count,path=longest(original[key])
        return {'bytes':count+extra,'extra_margin':extra,
                'path':[{'unit':nodes[a]['unit'],'name':nodes[a]['name'],'address':a,
                         'frame_bytes':nodes[a]['frame_bytes']} for a in path]}
    main_address=original[('target','main')]
    main_instructions=nodes[main_address]['instructions']
    require(main_instructions[0]['op']=='cli','Startup does not mask interrupts first')
    enable=[i['address'] for i in main_instructions if i['op']=='sei']
    require(len(enable)==1,'Unexpected interrupt enabling in main')
    start=original[('runtime','hms_avr_runtime_start')]
    startup_calls=[i['address'] for i in main_instructions if i['op']=='call' and
                   re.search(r'0x([0-9a-f]+)',i['operands']) and int(re.search(r'0x([0-9a-f]+)',i['operands']).group(1),16)==start]
    require(len(startup_calls)==1 and startup_calls[0]<enable[0],'Startup follows interrupt enable')
    for address in original.values():
        if address==main_address:continue
        require(not any(i['op']=='sei' for i in nodes[address]['instructions']),'Unexpected explicit nested IRQ enable')
    main_frame=nodes[main_address]['frame_bytes']
    all_main=bound(('target','main'),2)
    startup=bound(('runtime','hms_avr_runtime_start'),main_frame+4)
    foreground=bound(('runtime','hms_avr_runtime_step'),main_frame+4)
    irq={name:bound(('target',name),2) for name in ('__vector_13','__vector_18')}
    for name in irq:
        code=nodes[original[('target',name)]]['instructions']
        require(code[-1]['op']=='reti','ISR lacks RETI')
        require(sum(i['op']=='push' for i in code)==sum(i['op']=='pop' for i in code),'ISR push/pop mismatch')
        irq[name]['explicit_register_pushes']=sum(i['op']=='push' for i in code)
        irq[name]['hardware_return_margin']=2
    isr=max(value['bytes'] for value in irq.values())
    reserve=512;irq_allowance=max(64,isr);future=128
    planning=max(startup['bytes'],foreground['bytes']+irq_allowance)+future
    avr=build_receipt['avr'];static=avr['static_sram_bytes'];flash=avr['flash_bytes']
    graph=[{'address':a,'unit':nodes[a]['unit'],'name':nodes[a]['name'],
            'frame_bytes':nodes[a]['frame_bytes'],'frame_basis':nodes[a]['frame_basis'],
            'callees':sorted(nodes[a]['edges']),'indirect_sites':nodes[a]['indirect'],
            'conservative_subtree_bytes':memo[a][0]} for a in sorted(memo)]
    report={'schema':'hms-avr-combined-static-stack/1','inputs':before,
            'method':'Acyclic longest path of linked calls plus exact installed indirect targets; sum GCC .su maxima and two extra bytes per call edge, even when return already counted. Two additional startup bytes and ISR hardware return bytes are conservative margins.',
            'callback_union_overestimate':'For a function with several indirect sites, every reviewed installed target is charged as a possible callee at each site; this can overestimate but never omit the configured callback.',
            'all_main':all_main,'startup_interrupts_disabled':startup,'steady_foreground':foreground,'non_nested_isrs':irq,
            'foreground_plus_actual_max_isr_bytes':foreground['bytes']+isr,
            'graph':graph,'compiler_records':records,'indirect_sites':sum(len(nodes[a]['indirect']) for a in original.values()),
            'retained_legacy_api_bounds':{name:bound((unit,name)) for unit,name in [('link','hms_endpoint_link_feed'),('uart','hms_avr_uart_frame_step'),('usart','hms_avr_usart_drained')]},
            'unused_original_clock_callback':bound(('fixture','sample_clock')),
            'reservation':{'stack_bytes':reserve,'actual_max_non_nested_isr_bytes':isr,'retained_isr_allowance_bytes':irq_allowance,
                           'future_callback_growth_bytes':future,'planning_stack_requirement_bytes':planning,
                           'unassigned_within_stack_reservation_bytes':reserve-planning,'static_sram_bytes':static,
                           'static_plus_reserved_stack_bytes':static+reserve,'sram_bytes':2048,
                           'unassigned_sram_bytes':2048-static-reserve,'flash_bytes':flash,'uno_application_limit':32256,
                           'primitive_allowance_bytes':256,'protection_service_reservation_bytes':64,
                           'passes_maximum_stack_constraint':planning<=reserve,
                           'passes_combined_arithmetic_constraints':planning<=reserve and static+reserve<=2048 and flash<=32256},
            'target_runtime_fit_demonstrated':False,'target_executed':False,
            'assumptions':['Exact copied source, compiler/flags and synthetic callbacks only; no recursion/reentry or unmodeled callback.',
                           'Only USART RX and Timer1 overflow interrupts are enabled; ISR handlers do not nest and restore saved I=0 until RETI.',
                           'Source/SREG review supports non-nesting; generated register windows are independently reviewed separately.',
                           'Full caller maxima and each callee maximum are charged concurrently, with extra call margins; this is conservative static arithmetic.',
                           '64 ISR and128 future callback bytes remain planning allowances. The64-byte protection object is only storage reservation.',
                           'No stack high-water, interrupt/scheduler timing, oscillator, NVM power-loss, physical stop, sensor or actuator qualification follows.']}
    require(before=={str(p.relative_to(HERE)):digest(p) for p in paths},'Analysis inputs changed')
    OUTPUT.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'output':str(OUTPUT),'reservation':report['reservation'],'target_executed':False}))

if __name__=='__main__':main()

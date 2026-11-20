"""Independent retained-text verification; no candidate or measurement-script import."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LANE=ROOT/'artifacts/design/standing-endpoint-size-reduction'


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):return json.loads(path.read_bytes())


def exact(path,row):
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size==row['bytes'] and digest(path)==row['sha256']


def main():
    assert digest(LANE/'evidence.json')=='c9f8c76907d59c29f3b55544c264b8adae029fa13c87495331f0093840f57b5e'
    evidence=read(LANE/'evidence.json');names=set()
    for row in evidence['packet_files_before_this_receipt']:
        assert row['path'] not in names;names.add(row['path']);exact(LANE/row['path'],row)
    assert {str(p.relative_to(LANE)) for p in LANE.rglob('*') if p.is_file() or p.is_symlink()}==names|{'evidence.json'}
    assert len(names)+1==31
    pins=read(LANE/'source-pins.json');assert len(pins['inputs'])==11
    raw={}
    for name,row in pins['inputs'].items():exact(ROOT/row['path'],row);raw[name]=(ROOT/row['path']).read_bytes().splitlines(keepends=True)
    for row in evidence['source_inputs']:
        exact(ROOT/row['original'],row)
        if row['copy'] is not None:exact(LANE/row['copy'],row)
    assert sum(row['copy'] is not None for row in evidence['source_inputs'])==9
    coverage=read(LANE/'coverage.json');assert len(coverage['ranges'])==23
    for row in coverage['ranges']:
        first,last=row['first'],row['last'];assert 1<=first<=last<=len(raw[row['input']])
        body=b''.join(raw[row['input']][first-1:last])
        assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256']
    lines=raw['ltrans.s']
    def instructions(first,last):
        rows=[]
        for number in range(first,last+1):
            match=re.fullmatch(rb'\t([a-z][a-z0-9]*)\s*(.*?)\s*',lines[number-1].rstrip(b'\n'))
            if match:rows.append((number,match[1].decode(),match[2].decode()))
        return rows
    measured=read(LANE/'measurements.json');observations=read(LANE/'body-observations.json')
    assert digest(LANE/'source-pins.json')==measured['source_pins_sha256']
    assert (measured['flash'],measured['physical_excess'],measured['application_excess'])==(41810,9042,9554)
    total_instructions=0;total_bytes=0;repeat_count=0;calls=Counter()
    for name,expected in measured['units'].items():
        rows=instructions(*expected['raw_lines']);counts=Counter(row[1] for row in rows)
        direct=Counter(row[2] for row in rows if row[1]=='call');calls.update(direct)
        width=sum(4 if row[1] in ('call','jmp','lds','sts') else 2 for row in rows)
        first,last=expected['raw_lines']
        table=sum(line.lstrip().startswith(b'.word ') for line in lines[first-1:last])*2
        assert len(rows)==expected['instructions'] and width==expected['instruction_width_sum']
        assert table==expected['switch_table_bytes'] and width+table==expected['map_section_bytes']
        assert dict(counts)==expected['opcode_histogram'] and dict(direct)==expected['static_direct_call_sites']
        assert sum(bool(re.search(r'r(?:28|29),\d+-\d+$',row[2])) for row in rows)==expected['y_offset_adjust_instructions']
        assert not expected['machine_byte_identity_established']
        tsv=(LANE/'extracts'/(name+'.instructions.tsv')).read_text().splitlines()
        assert len(tsv)==len(rows)
        for entry,row in zip(tsv,rows):
            fields=entry.split('\t');assert len(fields)==3 and int(fields[0])==row[0]
            assert fields[1]==row[1]+' '+row[2]
        assert len(expected['literal_repeats_verified'])==len(observations['units'][name]['literal_repeated_instruction_runs'])
        for repeat in expected['literal_repeats_verified']:
            left,right=instructions(*repeat['a']),instructions(*repeat['b'])
            assert [(r[1],r[2]) for r in left]==[(r[1],r[2]) for r in right]
            assert len(left)==repeat['instructions']
            assert sum(4 if r[1] in ('call','jmp','lds','sts') else 2 for r in left)==repeat['nominal_instruction_bytes_each']
            repeat_count+=1
        total_instructions+=len(rows);total_bytes+=width+table
    assert (total_instructions,total_bytes,repeat_count)==(8604,17982,22)
    assert sum(calls[name] for name in ('__cmpdi2','__cmpdi2_s8','__adddi3','__subdi3'))==measured['wide_arithmetic_direct_call_sites']==69
    assert calls['r64']+calls['get64']==measured['decoder64_direct_call_sites']==31
    assert calls['w64']+calls['put64']==measured['encoder64_direct_call_sites']==15
    body=b''.join(raw['runtime.map']).decode()
    for name,row in measured['sections'].items():
        match=re.findall(r'^'+re.escape(name)+r'\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)',body,re.M)
        assert len(match)==1 and tuple(int(v,16) for v in match[0])==(row['address'],row['bytes'])
    retention=json.loads(b''.join(raw['retention.json']))
    funcs=measured['function_root_allocations'];storage=measured['charged_storage_allocations']
    assert {row['name'] for row in funcs}=={row['name'] for row in retention['function_roots']}|{'main'}
    assert len(funcs)==30 and len(storage)==9
    assert {row['name']:row['bytes'] for row in storage}=={row['name']:row['bytes'] for row in retention['storage_roots']}
    for rows,region_name in ((funcs,'.text'),(storage,'.bss')):
        region=measured['sections'][region_name];ordered=sorted(rows,key=lambda row:row['address'])
        assert all(a['address']+a['bytes']<=b['address'] for a,b in zip(ordered,ordered[1:]))
        for row in rows:
            symbols=re.findall(r'^\s+0x([0-9a-f]+)\s+'+re.escape(row['name'])+r'$',body,re.M)
            sections=re.findall(r'^ '+re.escape(row['section'])+r'\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)',body,re.M)
            assert len(symbols)==len(sections)==1 and int(symbols[0],16)==row['address']
            assert tuple(int(v,16) for v in sections[0])==(row['address'],row['bytes'])
            assert region['address']<=row['address']<row['address']+row['bytes']<=region['address']+region['bytes']
    assert sum(row['bytes'] for row in storage)==1477
    reproduction=read(LANE/'reproduction.json')
    assert reproduction['status']=='PASS' and digest(LANE/'measure.py')==reproduction['script_sha256']=='cd0511fda604c3851a980ca396f5e1247ed4e280998c3e3dc93277165382f0df'
    assert all(digest(LANE/name)==pin for name,pin in reproduction['outputs'].items())
    old=read(LANE/'history/pre-retention-address-join/measurements.json')
    assert len(old)==16 and all(measured[name]==value for name,value in old.items())
    result=dict(status='verified-retained-text-proposal',verificationSourceSha256=digest(Path(__file__)),
        evidenceSha256=digest(LANE/'evidence.json'),packetFiles=31,packetBytes=sum(p.stat().st_size for p in LANE.rglob('*') if p.is_file()),
        sourceInputs=11,exactCopies=9,readRangesVerified=23,mechanicallyEnumeratedInstructions=8604,
        selectedBodyBytes=17982,repeatedTokenRunsVerified=22,fullWidthArithmeticCallSites=69,
        functionRootsIncludingMain=30,exactStorageRoots=9,staticStorageRootBytes=1477,
        flashLoadBytes=41810,physicalFlashExcessBytes=9042,applicationFlashExcessBytes=9554,
        candidateExecuted=False,compilerExecuted=False,targetExecuted=False,fitEstablished=False,
        combinedStackProof=False,machineByteIdentityEstablished=False)
    with (HERE/'size-proposal-verification.json').open('x') as out:
        json.dump(result,out,indent=2,sort_keys=True);out.write('\n');out.flush();os.fsync(out.fileno())
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()

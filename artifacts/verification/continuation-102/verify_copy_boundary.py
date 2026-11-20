"""Verify retained failed-link text and coverage; never execute candidate code."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LANE = ROOT/'artifacts/implementation/standing-endpoint-copy-boundary'
PINS = {
    'MAP-REVIEW.json':'376f99cb4de4e9899e44a76ff6b2f29dec6b0b05c1d8c5a940ca52c8663fc3cf',
    'boundary-coverage.json':'22cd51878167ddd9c2098eed5e6ba71e40111494e40e544d0cf0307ef6f76e10',
    'GENERATED-BOUNDARY-REVIEW.md':'88deae547ce364adf5c7cb3d0bbaaa069ee24a0e1aba37bc1cc1a747cb66f8a5',
    'RESULTS-REVIEW.md':'17a45965afdc815c13adfc6fa41efcedece05f8185fe11f1e0ae9cfe60ef3985',
    'NEXT.md':'986024c40280e808bbaa823202ad6bb710c58fa1286776d0de19539ccb4f4d07',
}


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):return json.loads(path.read_bytes())


def section(body,name):
    prefix = '' if name in ('.text','.data','.bss','.noinit') else r'[ \t]+'
    match = re.search(r'^'+prefix+re.escape(name)+r'[ \t]*\n?[ \t]*(0x[0-9a-f]+)[ \t]+(0x[0-9a-f]+)',body,re.M)
    assert match,name
    return dict(address=int(match[1],16),bytes=int(match[2],16))


def main():
    assert all(digest(LANE/name) == pin for name,pin in PINS.items())
    mapped = read(LANE/'MAP-REVIEW.json');coverage = read(LANE/'boundary-coverage.json')
    for row in list(mapped['inputs'].values())+list(coverage['inputs'].values()):
        path = ROOT/row['path'];assert digest(path) == row['sha256']
        if 'bytes' in row:assert path.stat().st_size == row['bytes']
    body = (ROOT/mapped['inputs']['map']['path']).read_text()
    parent = (ROOT/mapped['inputs']['parent_map']['path']).read_text()
    for name,expected in (('.text',41784),('.data',26),('.bss',1477),('.noinit',0)):
        observed = section(body,name)
        assert observed == mapped['sections'][name] and observed['bytes'] == expected
    assert mapped['flash_bytes'] == 41784+26 == 41810
    assert mapped['physical_flash_overflow_bytes'] == 41810-32768 == 9042
    assert mapped['application_flash_overflow_bytes'] == 41810-32256 == 9554
    assert mapped['combined_flash_reduction_bytes'] == 41892-41810 == 82
    assert mapped['static_sram_bytes'] == 1477+26 == 1503
    assert mapped['standing_delta_bytes'] == 1503-1343 == 160
    assert mapped['static_plus_reservation'] == 1503+512 == 2015
    assert mapped['arithmetic_remainder'] == 2048-2015 == 33
    retention = read(LANE/'retention.json')
    expected_names = {row['name'] for row in retention['function_roots']}|{'main'}
    assert len(expected_names) == 30
    assert {row['name'] for row in mapped['retained_function_symbols']} == expected_names
    expected_storage = {row['name']:row['bytes'] for row in retention['storage_roots']}
    storage = mapped['retained_storage_objects']
    assert len(storage) == 9 and {row['name']:row['bytes'] for row in storage} == expected_storage
    for row in mapped['retained_function_symbols']+storage:
        match = re.search(r'^\s+(0x[0-9a-f]+)\s+'+re.escape(row['name'])+r'\s*$',body,re.M)
        assert match and int(match[1],16) == row['address'],row['name']
        if row['name'] in expected_storage:
            assert section(body,'.bss.'+row['name']) == dict(address=row['address'],bytes=row['bytes'])
    storage = sorted(storage,key=lambda row:row['address'])
    assert sum(row['bytes'] for row in storage) == 1477
    assert all(a['address']+a['bytes'] <= b['address'] for a,b in zip(storage,storage[1:]))
    assert all(0x800100 <= row['address'] and row['address']+row['bytes'] <= 0x800100+2048 for row in storage)
    for name,row in mapped['selected_function_sections'].items():
        assert section(body,'.text.'+name) == row['current']
        if row['parent'] is not None:assert section(parent,'.text.'+name) == row['parent']
    for name,size in mapped['new_library_sections'].items():
        match = re.search(r'^ \.text\.avr-libc\n[ \t]+(0x[0-9a-f]+)[ \t]+(0x[0-9a-f]+)[^\n]+/libc\.a\('+re.escape(name)+r'\.o\)\n[ \t]+(0x[0-9a-f]+)[ \t]+'+re.escape(name)+r'\n',body,re.M)
        assert match and int(match[2],16) == size and match[1] == match[3],name
    assert not (LANE/'build/avr/runtime.elf').exists()
    assert not any(mapped[key] for key in ('complete_stack_proof','final_elf_exists','runtime_fit_demonstrated','target_executed','per_source_change_savings_established'))
    ranges = coverage['current_units']+coverage['other_read_ranges']
    for row in ranges:
        lines = (ROOT/coverage['inputs'][row['input']]['path']).read_bytes().splitlines(keepends=True)
        first,last = row['inclusive_lines'];assert 1 <= first <= last <= len(lines)
        data = b''.join(lines[first-1:last]);assert len(data) == row['bytes']
        assert hashlib.sha256(data).hexdigest() == row['sha256']
        if 'name' not in row:continue
        assert row['complete_function_unit'] and not row['inline_data_present']
        text = data.decode();assert text.startswith(row['name']+':\n')
        instructions = []
        for number,line in enumerate(lines[first-1:last],first):
            match = re.fullmatch(rb'\t([a-z][a-z0-9]+)(?:\s+([^\n]*))?\n?',line)
            if match:
                instructions.append(dict(line=number,opcode=match[1].decode(),operands=(match[2] or b'').decode()))
        assert sorted({item['opcode'] for item in instructions}) == row['observed_mnemonics']
        assert len(instructions) == row['instruction_count']
        assert sum(4 if item['opcode'] == 'call' else 2 for item in instructions) == row['instruction_bytes'] == row['map_section_bytes']
        assert row['call_sites'] == [item for item in instructions if item['opcode'] in ('call','icall')]
        for plural,opcode in (('pushes','push'),('pops','pop')):
            assert row[plural] == [item for item in instructions if item['opcode'] == opcode]
        assert row['stack_pointer_register_accesses'] == [item for item in instructions if '__SP_' in item['operands']]
    units = {row['name']:row for row in coverage['current_units']}
    wrapper = units['hms_endpoint_poll'];finite = units['poll_finite']
    assert (wrapper['instruction_count'],wrapper['instruction_bytes']) == (40,86)
    assert (finite['instruction_count'],finite['instruction_bytes']) == (1354,2806)
    assert len(wrapper['pushes']) == len(wrapper['pops']) == 6 and not wrapper['stack_pointer_register_accesses']
    assert [row['operands'] for row in wrapper['call_sites']] == ['update','hms_standing_poll','poll_finite']
    assert len(finite['pushes']) == len(finite['pops']) == 22
    frame = coverage['frame_observations']
    assert frame['current_wrapper_local_bytes'] == 0 and frame['current_wrapper_saved_register_bytes'] == 6
    assert frame['current_finite_local_bytes'] == 82 and frame['current_finite_saved_register_bytes'] == 18
    assert frame['standing_call_caller_owned_allocation_reduction_bytes'] == 83+18-6 == 95
    current_su = (ROOT/coverage['inputs']['current_backend_su']['path']).read_text().splitlines()
    parent_su = (ROOT/coverage['inputs']['parent_backend_su']['path']).read_text().splitlines()
    for name,line in coverage['backend_su_records'].items():assert line in (parent_su if name == 'parent_wrapper' else current_su)
    assert len(current_su) == 106
    assert not any(coverage[key] for key in ('combined_stack_proof','final_linked_boundary_qualified','target_fit_proved','finite_frame_retained_on_standing_path'))
    folder = LANE/'build/avr';inventory = read(folder/'lto-artifacts.json')
    assert len(inventory['files']) == 54 and sum(row['bytes'] for row in inventory['files']) == 8457521
    for row in inventory['files']:
        path = folder/row['path'];assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
    assert len(read(folder/'pre-lto-stack-records.json')['records']) == 131
    result = dict(status='verified-retained-failed-link-data',verificationSourceSha256=digest(Path(__file__)),
        reportPins=PINS,coverageRangesVerified=len(ranges),currentCompleteFunctionUnits=2,
        wrapperInstructions=40,finiteInstructions=1354,retainedFunctionSymbols=30,retainedStorageObjects=9,
        flashLoadBytes=41810,physicalFlashOverflowBytes=9042,applicationFlashOverflowBytes=9554,
        combinedFlashReductionBytes=82,standingCallCallerOwnedReductionBytes=95,
        staticBytes=1503,staticDeltaBytes=160,savedArtifacts=54,savedArtifactBytes=8457521,
        possibleBackendStackRecords=106,preLtoStackRecords=131,
        fullStackProof=False,targetFitEstablished=False,candidateExecuted=False,compilerExecuted=False,targetExecuted=False)
    with (HERE/'copy-boundary-verification.json').open('x') as output:
        json.dump(result,output,sort_keys=True,indent=2);output.write('\n');output.flush();os.fsync(output.fileno())
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':main()

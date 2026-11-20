"""Read-only joins for the single retained object-inspection attempt."""
from collections import Counter,defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import sys

if sys.flags.optimize:
    raise RuntimeError('Assertions required')
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    report = read(HERE/'RESULTS.json');pins = read(HERE/'input-pins.json');folder = HERE/'attempt01'
    assert report['status'] == 'passed' and report['requested_checks_completed']
    assert report['owner_empty'] and report['owner_closed'] and not report['owner_cleanup_errors']
    assert not report['interrupts_pending_after_cleanup'] and report['owned_groups_observed_absent']
    assert report['original_inputs_unchanged']
    for row in pins['files']:
        assert digest(ROOT/row['source']) == digest(HERE/row['copy']) == digest(folder/row['copy']) == row['sha256']
    assert all(digest(Path(name)) == pin for name,pin in pins['tools'].items())
    assert all(digest(HERE/name) == digest(folder/name) == pin for name,pin in report['sources'].items())
    commands = report['commands'];assert len(commands) == 9 and len(report['owned_children_reaped']) == 9
    for command in commands:
        assert command['passed'] and command['exit_code'] == 0 and command['direct_child_reaped']
        assert not command['cleanup_errors'] and not command['group_members_after_cleanup']
        assert command['input_pins_stable'] and not command['interrupts_pending_after_cleanup']
        assert command == read(folder/(command['name']+'.result.json'))
        assert digest(HERE/command['stdout']) == command['stdout_sha256']
        assert digest(HERE/command['stderr']) == command['stderr_sha256'] and not (HERE/command['stderr']).read_bytes()
    for child in report['owned_children_reaped']:
        assert child['reaped'] and child['exitCode'] == 0
        try:tail = (Path('/proc')/str(child['pid'])/'stat').read_text().rsplit(')',1)[1].split()
        except FileNotFoundError:continue
        assert int(tail[19]) != child['startTicks']
    fixture = (folder/'standing-fixture-disassembly.stdout').read_text()
    fragment = fixture.split('Disassembly of section .text.finite_describe:',1)[1].split('Disassembly of section ',1)[0]
    assert 'R_AVR_LO8_LDI\t.rodata' in fragment and 'R_AVR_HI8_LDI\t.rodata' in fragment
    assert 'ldi\tr25, 0x08' in fragment and 'ld\tr0, Z+' in fragment and 'st\tX+, r0' in fragment
    constant = (folder/'fixture-constant-bytes.stdout').read_text()
    assert re.search(r'^ 0000 e8030000 03200100\s',constant,re.M)
    assert bytes.fromhex('e803000003200100') == (1000).to_bytes(4,'little')+bytes((3,32,1,0))
    counts = defaultdict(Counter);section = '';previous = ''
    for line in (folder/'standing-disassembly.stdout').read_text().splitlines():
        found = re.match(r'Disassembly of section (.+):',line)
        if found:section = found.group(1)
        relocation = re.search(r'R_AVR_CALL\s+([^+\s]+)',line)
        if relocation:
            instruction = re.search(r'\b(call|jmp)\s',previous)
            assert instruction,previous
            counts[section][instruction.group(1)+' '+relocation.group(1)] += 1
        previous = line
    result = dict(passed=True,auditSourceSha256=digest(Path(__file__)),outerCommands=9,observedOwnedIdentitiesAbsent=9,
        immutableInputs=10,pinnedInspectionTools=2,objectsExecuted=False,checksRerun=False,
        descriptorConstantConfirmed=True,descriptorConstantBytes='e803000003200100',descriptorByteCount=8,
        disassemblyCoverage='Complete finite_describe instruction/relocation fragment and constant bytes; all R_AVR_CALL relocation records classified by preceding call/jmp mnemonic. No whole-program semantic or stack review claimed.',
        standingStaticCallAndJumpRelocations={name:dict(values) for name,values in counts.items()},
        inspectionSourceSha256=digest(HERE/'run_analysis.py'),resultSha256=digest(HERE/'RESULTS.json'))
    with (HERE/'AUDIT.json').open('x') as target:
        json.dump(result,target,indent=2,sort_keys=True);target.write('\n');target.flush();os.fsync(target.fileno())
    print(json.dumps({name:value for name,value in result.items() if name!='standingStaticCallAndJumpRelocations'},sort_keys=True))


if __name__ == '__main__':main()

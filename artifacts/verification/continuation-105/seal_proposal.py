"""Join retained text-analysis outputs and seal the unimplemented proposal only."""
import collections
import hashlib
import json
import os
from pathlib import Path
import sys

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FOLDER = ROOT/'artifacts/design/standing-endpoint-phase-size'
PINS = {
    'measure.py': '641f50f80605ef7f481d90c278b224767bdf922ea059ebe0010dbc6ac00d44f8',
    'inputs.json': '92ac0f09dc0e4648e08fcce64986560a0b73c1151d0116ea90f70d29925928b9',
    'measurements.json': 'f2d2cac788ed4f00325d2e4c2857e2789595b8bc5469387392e2b61e420765c7',
    'coverage.json': '8517071c2faecb51749adcef55447b101ad9964fb0e971bd5dba19b95a7906cb',
    'PROPOSAL.md': '2d43f61d49026f6ddd5b2b681f87717fbfc62e04913695373fac129e5b08bc06',
    'SEMANTICS.md': '233f59bdf21f62d332d3919b5d798ca78a6d0b42cb473a8dc9264bb726fc8a56',
    'CONTROLS.md': '1fe27748d5f1777d42f51dc63bff132cbce31faa4bf91af5e92a225a7e168a83',
    'ANALYSIS.md': '3c22c34001e5b97d521d739361d83eb4692946b45c09531f1aefd1e4ec43fb5b',
}

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def main():
    assert len(sys.argv) == 1 and not (FOLDER/'index.json').exists()
    for name,pin in PINS.items(): assert digest(FOLDER/name) == pin
    inputs = read(FOLDER/'inputs.json')['files']
    assert len(inputs) == len({row['source'] for row in inputs}) == 20
    assert sum(row['bytes'] for row in inputs) == 2653917
    for row in inputs:
        for path in (FOLDER/row['copy'],ROOT/row['source']):
            assert path.is_file() and not path.is_symlink()
            assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
    m = read(FOLDER/'measurements.json'); c = read(FOLDER/'coverage.json')
    assert m['sections'] == dict(text=39876,data=26,bss=1477,noinit=0)
    assert m['flashBytes'] == m['sections']['text']+m['sections']['data'] == 39902
    assert m['physicalGapBytes'] == 7134 and m['applicationGapBytes'] == 7646
    assert not any(m[key] for key in ('candidateImplemented','expectedSavingsKnown',
        'compilerExecuted','targetExecuted','supportedFit','completeStackProof'))
    sections = sorted(m['allocatedTextSections'],key=lambda row:row['address'])
    assert len(sections) == m['allocatedTextSectionCount'] == 151
    assert sections[0]['address'] == 0
    assert all(a['address']+a['bytes'] == b['address'] for a,b in zip(sections,sections[1:]))
    assert sum(row['bytes'] for row in sections) == 39876
    functions = m['emittedFunctions']; assert len(functions) == 131
    owners = collections.Counter(); direct = collections.Counter()
    assembly_name = 'artifacts/implementation/standing-endpoint-shared-kernel/build/avr/compiler-tmp/ccwk0Cum.ltrans0.ltrans.s'
    raw = (FOLDER/'inputs'/assembly_name).read_bytes().splitlines(keepends=True)
    for row in functions:
        body = b''.join(raw[row['firstLine']-1:row['lastLine']])
        assert hashlib.sha256(body).hexdigest() == row['rangeSha256']
        match = [section for section in sections if section['section'] == row['section']]
        assert len(match) == 1 and match[0]['bytes'] == row['bytes']
        assert row['instructionBytes']+row['tableBytes'] == row['bytes']
        assert sum(row['opcodeBytes'].values()) == row['instructionBytes']
        owners[row['emittedOwner']] += row['bytes']
        direct.update(call['resolved'] for call in row['directCalls'])
    assert dict(owners) == m['emittedOwnerBodyBytes'] and sum(owners.values()) == m['emittedBodyBytes'] == 39322
    assert dict(direct) == m['directCallCounts'] and sum(direct.values()) == m['directCallSites'] == 676
    assert sum(row['bytes'] for row in m['otherTextSections']) == m['otherTextBytes'] == 554
    assert m['emittedBodyBytes']+m['otherTextBytes']+m['sections']['data'] == m['flashBytes']
    assert len(m['retainedRootInlineCopies']) == 10
    assert sum(row['standaloneBodyBytes'] for row in m['retainedRootInlineCopies']) == m['weightedStandaloneSizeOfInlineCopies'] == 224
    assert m['inlineCopySizeIsNotSavingsEstimate'] and m['sourceOwnerIncludesInlinedDescendants']
    assert c['inputsSha256'] == PINS['inputs.json'] and c['manualReadingIsNotUniversalSemanticProof']
    assert len(c['manualAssemblyViews']) == len(c['completeCFilesRead']) == 9
    assert len(c['manualWpaRanges']) == len(c['proposalFilesRead']) == 3
    for row in c['manualAssemblyViews']:
        assert row['source'] == assembly_name
        assert hashlib.sha256(b''.join(raw[row['firstLine']-1:row['lastLine']])).hexdigest() == row['rawRangeSha256']
    files = []
    for path in sorted(FOLDER.rglob('*')):
        assert not path.is_symlink() and '__pycache__' not in path.parts
        if path.is_file():
            before=path.stat(); pin=digest(path); after=path.stat()
            signature=lambda s:(s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            assert signature(before) == signature(after)
            files.append(dict(path=str(path.relative_to(FOLDER)),bytes=before.st_size,sha256=pin))
    assert len(files) == 30 and sum(row['bytes'] for row in files) == 2966935
    result = dict(profile='hms-isolated-evidence-packet/1',status='sealed-unimplemented-source-and-data-proposal',
        sealSourceSha256=digest(Path(__file__)),fileCount=len(files),totalBytes=sum(row['bytes'] for row in files),
        facts=dict(inputFiles=20,allocatedTextSections=151,generatedBodies=131,generatedBodyBytes=39322,
            otherTextBytes=554,chargedFlashBytes=39902,applicationGapBytes=7646,measuredNewSavings=False,
            candidateExecuted=False,compilerExecuted=False,targetExecuted=False),
        completeStackProof=False,targetFitEstablished=False,completeGoalClaimed=False,files=files)
    with (FOLDER/'index.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True); stream.write('\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps(dict(path=str(FOLDER.relative_to(ROOT)),indexSha256=digest(FOLDER/'index.json'),
        files=len(files),bytes=result['totalBytes']),sort_keys=True))

if __name__ == '__main__': main()

"""Verify source-only call-count evidence and seal the proposal, not a candidate."""
import hashlib
import json
import os
from pathlib import Path
import sys

assert not sys.flags.optimize
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FOLDER=ROOT/'artifacts/design/standing-host-selection-reuse'
PINS={'PROPOSAL.md':'27dbc42bc9b1185075766509586e4b76666ccff12c96cd3267051fb0b0629f5a',
 'SOURCE-EVIDENCE.json':'97204231cccff0e7256e196b53e92c30ed374779c46a6f622a3dc99971874bdc',
 'CALL-COUNTS.json':'c0c4ad0c889b0f9aeb7b9373f7e485e832774d0fc458cf60934c8e3cd9bf3e88'}

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    assert len(sys.argv)==1 and not (FOLDER/'index.json').exists()
    for name,pin in PINS.items():assert digest(FOLDER/name)==pin
    evidence=json.loads((FOLDER/'SOURCE-EVIDENCE.json').read_bytes())
    counts=json.loads((FOLDER/'CALL-COUNTS.json').read_bytes())
    sources=evidence['sources'];assert len(sources)==evidence['exactSourceCopies']==17
    assert sum(row['bytes'] for row in sources)==431827
    for row in sources:
        for path in (FOLDER/row['copy'],ROOT/row['source']):
            assert path.is_file() and not path.is_symlink()
            assert path.stat().st_size==row['bytes'] and digest(path)==row['sha256']
        raw=(FOLDER/row['copy']).read_bytes().splitlines(keepends=True)
        assert len(raw)==row['lfLines']
        for span in row['readRanges']:
            assert hashlib.sha256(b''.join(raw[span['startLine']-1:span['endLine']])).hexdigest()==span['sha256']
    assert evidence['sourceOnly'] and not evidence['candidateExecuted'] and not evidence['candidateImplemented']
    assert counts['units']==['parse_installation','parse_topology','_generations','binding_proof']
    assert counts['parse_installation']==[1,4,3,2] and counts['policy_fresh']==[1,5,4,3]
    assert counts['catalog_fresh']==[2,9,7,5]
    assert counts['private_catalog_compile_current']==counts['public_compiler_current_and_proposed']==[5,20,15,10]
    assert counts['private_catalog_compile_proposed']==[1,4,3,2]
    for label in ('current','proposed'):
        selected=[a+b for a,b in zip(counts['catalog_fresh'],counts['private_catalog_compile_'+label])]
        assert counts['selected_'+label]==selected
        assert counts['sixty_four_selected_'+label]==[64*v for v in selected]
        full=[64*a+32*b+32*c for a,b,c in zip(selected,counts['catalog_fresh'],counts['policy_fresh'])]
        assert counts['full_32_loops_'+label]==full
    assert counts['policy_fresh_calls_unchanged']==128 and counts['history_mutation_validations_unchanged']==2176
    assert not any(counts[k] for k in ('speedupEstablished','timingExtrapolated','full128RecordCapacityEstablished'))
    files=[]
    for path in sorted(FOLDER.rglob('*')):
        assert not path.is_symlink() and '__pycache__' not in path.parts
        if path.is_file():files.append(dict(path=str(path.relative_to(FOLDER)),bytes=path.stat().st_size,sha256=digest(path)))
    assert len(files)==20
    result=dict(profile='hms-isolated-evidence-packet/1',status='sealed-source-only-private-compilation-proposal',
        sealSourceSha256=digest(Path(__file__)),fileCount=len(files),totalBytes=sum(r['bytes'] for r in files),
        facts=dict(exactSourceCopies=17,selectedInstallationValidationsCurrent=7,selectedInstallationValidationsProposed=3,
            selectedTopologyValidationsCurrent=29,selectedTopologyValidationsProposed=13,sourceCountModelOnly=True),
        candidateExecuted=False,performanceImprovementEstablished=False,fullCapacityPassed=False,completeGoalClaimed=False,files=files)
    with (FOLDER/'index.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps(dict(files=len(files),bytes=result['totalBytes'],indexSha256=digest(FOLDER/'index.json')),sort_keys=True))

if __name__=='__main__':main()

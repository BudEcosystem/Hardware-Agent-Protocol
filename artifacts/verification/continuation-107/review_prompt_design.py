"""Data-only verification of the reviewed planning handoff proposal."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKET = ROOT / 'artifacts/design/prompt-intent-handoff'

def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def main():
    assert len(sys.argv) == 1 and not sys.flags.optimize
    copies = []
    for line in (PACKET / 'SOURCE_SHA256SUMS').read_text().splitlines():
        pin, name = line.split('  ', 1)
        relative = Path(name)
        assert relative.parts[0] == 'source' and '..' not in relative.parts
        copied = PACKET / relative
        original = ROOT.joinpath(*relative.parts[1:])
        assert copied.is_file() and not copied.is_symlink()
        assert sha(copied) == sha(original) == pin
        copies.append(dict(path=name, bytes=copied.stat().st_size, sha256=pin))
    assert len(copies) == len({r['path'] for r in copies}) == 30
    assert {str(p.relative_to(PACKET)) for p in (PACKET / 'source').rglob('*') if p.is_file()} == {r['path'] for r in copies}
    contract = json.loads((PACKET / 'CONTRACT.json').read_bytes())
    assert contract['status'] == 'proposed-field-contract-not-mounted-or-executed'
    assert len(contract['forbiddenEffects']) == 7
    scope = json.loads((PACKET / 'READ_SCOPE.json').read_bytes())
    assert len(scope['fullFileReads']) == 21
    reviewed = ('README.md', 'CONTRACT.json', 'READ_SCOPE.json', 'SOURCE_SHA256SUMS')
    result = dict(status='verified-source-proposal', sourceCopies=copies,
        rootFullyRead={name:sha(PACKET/name) for name in reviewed},
        rootAdditionalSourceRanges={'hms/pat_io_contracts.py':[[207,300]],
            'hms/pat_io_combined_matrix.py':[[1,88],[120,193]]},
        qualificationCaseCountsSourceDerived=[30,35,37], installedCombinedCeiling=32,
        candidateImported=False, candidateExecuted=False, modelInvoked=False,
        implementationProvided=False, learningEstablished=False, physicalExecution=False,
        interpretation='A proposed durable intent/proposal boundary, separate from qualification and actuation.',
        verificationSourceSha256=sha(Path(__file__)))
    with (HERE/'prompt-design-review.json').open('x') as output:
        json.dump(result, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps(dict(status=result['status'], sourceCopies=len(copies))))

if __name__ == '__main__':
    main()

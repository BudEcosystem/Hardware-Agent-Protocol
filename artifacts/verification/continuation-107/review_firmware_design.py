"""Data-only joins of the reviewed firmware proposal to existing measurements."""
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKET = ROOT/'artifacts/design/standing-endpoint-aggregate-size'
PARENT = ROOT/'artifacts/implementation/standing-endpoint-phase-kernels'

def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def main():
    assert len(sys.argv) == 1 and not sys.flags.optimize
    assert sha(PARENT/'index.json') == 'b80a6ec4119dd822bfa451929e7fba4f7994f9fca27134eb9361c88785f63dd6'
    copies = []
    for line in (PACKET/'inputs.sha256').read_text().splitlines():
        pin, name = line.split('  ', 1)
        relative = Path(name)
        assert relative.parts[0] == 'inputs' and '..' not in relative.parts
        copy = PACKET/relative
        original = ROOT.joinpath(*relative.parts[1:])
        assert copy.is_file() and not copy.is_symlink()
        assert sha(copy) == sha(original) == pin
        copies.append(dict(path=name, bytes=copy.stat().st_size, sha256=pin))
    assert len(copies) == len({row['path'] for row in copies}) == 13
    measurement = json.loads((PARENT/'codegen-measurements.json').read_bytes())
    current = measurement['current']
    assert current['flashBytes'] == 39186 and current['staticBytes'] == 1503
    assert measurement['applicationOverflowBytes'] == 6930 and not measurement['validElf']
    assert json.loads((PACKET/'direct-call-counts.json').read_bytes()) == current['directCallCounts']
    fields = ('name','address','bytes','emittedOwner','firstLine','lastLine','frameLocalBytes','savedRegisterBytes')
    projected = []
    for row in current['emittedFunctions']:
        values = [row[key] for key in fields] + [row['backendFrame']['bytes']]
        projected.append('\t'.join('' if value is None else str(value) for value in values))
    assert len(projected) == 146
    assert (PACKET/'function-inventory.tsv').read_text() == '\n'.join(projected)+'\n'
    plans = (PACKET/'PLANS.md').read_text()
    rows = [int(n) for n in re.findall(r'^\| [a-z_]+ \((\d+)\) \|', plans, re.M)]
    assert len(rows) == 28 and sum(rows) == 88
    assert 88*8 + 38*8 + 20*2 + 42 == 1090
    names = ('README.md','ANALYSIS.md','PROPOSAL.md','PLANS.md','SEMANTICS.md','CONTROLS.md','SOURCE-COVERAGE.md')
    result = dict(status='verified-source-proposal', inputCopies=copies,
        rootFullyRead={name:sha(PACKET/name) for name in names},
        existingEmittedBodies=146, validationPlans=28, validationRows=88,
        proposedCodecRows=38, proposedDescriptorBytes=1090,
        priorFlashBytes=39186, priorStaticBytes=1503, priorApplicationOverflowBytes=6930,
        compilerExecuted=False, candidateImplemented=False, candidateExecuted=False,
        newAssemblyParsed=False, fitEstablished=False, completeStackProof=False,
        savingsForecast=None, verificationSourceSha256=sha(Path(__file__)))
    with (HERE/'firmware-design-review.json').open('x') as output:
        json.dump(result, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps(dict(status=result['status'], inputCopies=13, emittedBodies=146, proposedDescriptorBytes=1090)))

if __name__ == '__main__':
    main()

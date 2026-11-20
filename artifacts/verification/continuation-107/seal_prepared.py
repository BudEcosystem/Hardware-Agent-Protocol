"""Seal the reviewed failed capacity attempt and two source-only proposals."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def main():
    assert len(sys.argv) == 1 and not sys.flags.optimize
    host = ROOT/'artifacts/implementation/standing-host-selection-capacity'
    assert sha(host/'AUDIT.json') == '2b32b2736d366a9e90262ef4c5662379183de062516c4207498fdf7677221034'
    assert sha(host/'audit_retained.py') == 'cb445555e14740987db09ef8077354494fdc4015966863f7775498b7b0494e0a'
    assert sha(host/'RESULTS.md') == 'd1f91968f6ae810a792fee6f8d2657f947a8ab272e5514816f1e1f369175c369'
    assert sha(host/'NEXT.md') == 'f798cd48a68da44ebba1dab30223304da47e8868b03f7b462e07b4243034023e'
    audit = read(host/'AUDIT.json')
    assert audit['passed'] and audit['checks'] == 63046 and audit['completedCases'] == 0
    assert audit['database']['neverHandedOffMutations'] == 110 and audit['database']['preparedMutations'] == 1
    assert not read(host/'selection-capacity-mutation-attempt01/RESULTS.json')['passed']
    source = read(host/'SOURCE-REVIEW.json')
    for row in source['files']:
        assert sha(host/row['path']) == row['sha256']
    for row in read(host/'AUDIT-INPUT-PINS.json')['attempt']['files']:
        assert sha(host/'selection-capacity-mutation-attempt01'/row['path']) == row['sha256']
    packets = [(host, 'failed-execution-retained-audit', sha(host/'AUDIT.json'))]
    for name, review_name, copies_key in (
        ('prompt-intent-handoff', 'prompt-design-review.json', 'sourceCopies'),
        ('standing-endpoint-aggregate-size', 'firmware-design-review.json', 'inputCopies')):
        packet = ROOT/'artifacts/design'/name
        review = read(HERE/review_name)
        assert review['status'] == 'verified-source-proposal'
        for path, pin in review['rootFullyRead'].items():
            assert sha(packet/path) == pin
        for row in review[copies_key]:
            assert (packet/row['path']).stat().st_size == row['bytes'] and sha(packet/row['path']) == row['sha256']
        packets.append((packet, 'source-only-proposal', sha(HERE/review_name)))
    assert all(not (packet/'index.json').exists() for packet, _, _ in packets)
    results = []
    for packet, kind, review_pin in packets:
        files = []
        for path in sorted(packet.rglob('*')):
            assert not path.is_symlink()
            if path.is_file():
                assert '__pycache__' not in path.parts and path.suffix != '.pyc'
                files.append(dict(path=str(path.relative_to(packet)), bytes=path.stat().st_size, sha256=sha(path)))
        result = dict(schema='hms-continuation107-evidence-seal/1', kind=kind,
            fileCount=len(files), totalBytes=sum(row['bytes'] for row in files), files=files,
            sealSourceSha256=sha(Path(__file__)), supportingReviewSha256=review_pin,
            physicalExecution=False, candidateRerun=False)
        with (packet/'index.json').open('x') as output:
            json.dump(result, output, indent=2, sort_keys=True)
            output.write('\n')
        results.append(dict(path=str(packet.relative_to(ROOT)), files=len(files),
            bytes=result['totalBytes'], indexSha256=sha(packet/'index.json')))
    with (HERE/'prepared-seals.json').open('x') as output:
        json.dump(results, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps(results))

if __name__ == '__main__':
    main()

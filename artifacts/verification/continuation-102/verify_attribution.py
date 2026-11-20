"""Independently check retained text and inventories; execute no candidate code."""
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LANE = ROOT/'artifacts/verification/standing-lto-attribution'
INDEX = '85cd88298d252d1a5d51b4d4c286e46e91c5aaef1541f356ebd33cf39ae92a39'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    assert digest(LANE/'index.json') == INDEX
    index = read(LANE/'index.json')
    assert len(index['files']) == 25
    for row in index['files']:
        path = LANE/row['path']
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
    data = read(LANE/'attribution.json')
    for row in data['inputs']:
        path = ROOT/row['path']
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
    build = ROOT/'artifacts/implementation/standing-endpoint-lto/build/avr-attempt-2'
    raw = (build/'compiler-tmp/cc1w4vmK.ltrans0.ltrans.s').read_text().splitlines()
    mapped = (build/'runtime.map').read_text()
    expected = {'hms_standing_poll': (3580,7462), 'hms_standing_handle': (2733,5784),
                'hms_endpoint_poll': (1386,2874), 'hms_endpoint_handle': (2355,4880)}
    rows = []
    for name, (count, size) in expected.items():
        start = raw.index(name+':')
        end = next(i for i in range(start,len(raw)) if re.fullmatch(r'\s*\.size\s+'+name+r',.*',raw[i]))
        body = raw[start:end+1]
        assert (LANE/(name+'.raw.s')).read_text() == '\n'.join(body)+'\n'
        instructions = [line.strip().split(maxsplit=1) for line in body if re.match(r'^\t[a-z][a-z0-9]*\s*',line)]
        byte_count = sum(4 if part[0] in {'call','jmp','lds','sts'} else 2 for part in instructions)
        words = [line for line in body if re.match(r'\s*\.word\s',line)]
        assert all(re.fullmatch(r'\s*\.word gs\(\.L[0-9]+\)',line) for line in words)
        byte_count += 2*len(words)
        section = re.findall(r'^ \.text\.'+name+r'\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)',mapped,re.M)
        assert len(section) == 1 and int(section[0][1],16) == size == byte_count
        assert len(instructions) == count
        if name == 'hms_standing_poll':
            adjustments = sum(bool(re.fullmatch(r'(?:adiw|sbiw) r28,\d+-\d+',line.strip())) for line in body)
            assert adjustments == 448
        rows.append(dict(name=name,instructions=count,bytes=byte_count,tableBytes=2*len(words)))
    assert sum(row['bytes'] for row in rows) == 21000
    finite = read(LANE/'finite-coverage.json')
    ranges = 0
    for item in finite['inputs'].values():
        path = ROOT/item['path']
        assert path.stat().st_size == item['bytes'] and digest(path) == item['sha256']
        assert len(path.read_bytes().splitlines()) == item['lines']
    for group in finite['coverage']:
        lines = (ROOT/finite['inputs'][group['input']]['path']).read_bytes().splitlines(keepends=True)
        for span in group.get('ranges',[]):
            assert 1 <= span['first'] <= span['last'] <= len(lines)
            assert hashlib.sha256(b''.join(lines[span['first']-1:span['last']])).hexdigest() == span['sha256']
            ranges += 1
    assert ranges == 38
    commit = read(LANE/'commit-blocks.json')
    for key in ('demand_instructions','feedback_instructions'):
        assert all(raw[number-1].strip() == instruction for number,instruction in commit[key])
    left = [line for _,line in commit['demand_instructions']]
    right = [line for _,line in commit['feedback_instructions']]
    assert left[:48] == right[:48] and left[48] != right[48]
    assert sum(4 if line.split()[0] in {'call','jmp','lds','sts'} else 2 for line in left[:48]) == 96
    result = dict(status='verified',verificationSourceSha256=digest(Path(__file__)),
        packetIndexSha256=INDEX,packetFiles=25,packetBytes=sum(r['bytes'] for r in index['files']),
        functions=rows,coverageRangesVerified=ranges,standingFrameAddressAdjustmentBytes=896,
        duplicatedObservationPrefixBytes=96,candidateExecuted=False,compilerExecuted=False,
        targetExecuted=False,stackProof=False,fitEstablished=False)
    with (HERE/'attribution-verification.json').open('x') as out:
        json.dump(result,out,indent=2,sort_keys=True);out.write('\n');out.flush();os.fsync(out.fileno())
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':
    main()

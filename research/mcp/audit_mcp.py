#!/usr/bin/env python3
"""Check pinned MCP specification bytes and reader-supplied coverage, locally."""
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'research/mcp'
checks = 0


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(path, expected):
    global checks
    data = (ROOT / path).read_bytes()
    if digest(data) != expected:
        raise ValueError('Hash mismatch: ' + path)
    checks += 1
    return data


def git_hash(kind, data):
    return hashlib.sha1(kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data).hexdigest()


pin = json.loads((BASE / 'pin.json').read_text())
commit = json.loads(verify(pin['metadata_path'], pin['sha256']))
tree = json.loads(verify(pin['tree_metadata_path'], pin['tree_metadata_sha256']))
assert commit['sha'] == pin['commit']
assert commit['commit']['tree']['sha'] == tree['sha'] == pin['tree_sha']
assert not tree['truncated']
entries = {item['path']: item for item in tree['tree']}
children = {}
for item in tree['tree']:
    parent = str(PurePosixPath(item['path']).parent)
    children.setdefault('' if parent == '.' else parent, []).append(item)
for parent, items in children.items():
    ordered = sorted(items, key=lambda item: PurePosixPath(item['path']).name.encode() +
                     (b'/' if item['type'] == 'tree' else b''))
    data = b''.join(item['mode'].lstrip('0').encode() + b' ' + PurePosixPath(item['path']).name.encode() +
                    b'\0' + bytes.fromhex(item['sha']) for item in ordered)
    assert git_hash('tree', data) == (pin['tree_sha'] if parent == '' else entries[parent]['sha'])
records = [json.loads(line) for line in (BASE / 'manifest.jsonl').read_text().splitlines()]
assert len({r['id'] for r in records}) == len(records)
for record in records:
    data = verify(record['raw_path'], record['raw_sha256'])
    assert git_hash('blob', data) == entries[record['repository_path']]['sha']
    assert record['url'] == ('https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/' +
                             pin['commit'] + '/' + record['repository_path'])
reading = json.loads((BASE / 'reading-mcp-full.json').read_text())
chunks = 0
read_lines = 0
for source in reading['sources']:
    data = verify(source['text_path'], source['text_sha256'])
    parts = data.split(b'\n')
    lines = [p + b'\n' for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    assert len(lines) == source['line_count']
    covered = set()
    for chunk in source['coverage_ranges']:
        a, z = chunk['start_line'], chunk['end_line']
        assert 1 <= a <= z <= len(lines)
        assert digest(b''.join(lines[a-1:z])) == chunk['sha256']
        covered.update(range(a, z + 1))
        chunks += 1
    assert (len(covered) == len(lines)) == source['coverage_complete']
    read_lines += len(covered)
result = dict(verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), acquisitions=len(records),
              repository_pins=1, snapshot_files=len(records), reconstructed_metadata_trees=len(children),
              reading_records=len(reading['sources']), full_records=sum(r['coverage_complete'] for r in reading['sources']),
              coverage_chunks=chunks, read_lines=read_lines, hash_checks=checks,
              limitations=['Coverage is reader-attested, not machine proof.',
                           'Selected repository blobs only; metadata reconstruction is not whole-repository reading.',
                           'HTTPS metadata links commit and tree; commit signature was not independently verified.',
                           'Generated JSON schema used for test validation; it was not read in full.'])
result['inputs'] = {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in
                    [BASE / 'manifest.jsonl', BASE / 'pin.json', BASE / 'reading-mcp-full.json', Path(__file__).resolve()]}
(BASE / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))

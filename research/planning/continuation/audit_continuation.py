#!/usr/bin/env python3
"""Check retained research bytes/provenance, not reading or robot conformance."""
from pathlib import Path, PurePosixPath
import datetime
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'research/planning/continuation'
RECEIPT = ROOT / 'research/planning/reading-continuation-full.json'
checks = 0


def require(condition, description):
    if not condition:
        raise ValueError(description)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(path, expected, size=None):
    global checks
    resolved = (ROOT / path).resolve()
    require(resolved.is_relative_to(ROOT), f'Outside root: {path}')
    data = resolved.read_bytes()
    require(digest(data) == expected, f'Hash mismatch: {path}')
    if size is not None:
        require(len(data) == size, f'Byte count mismatch: {path}')
    checks += 1
    return data


def git_hash(kind, data):
    return hashlib.sha1(kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def lf_lines(data):
    parts = data.split(b'\n')
    return [part + b'\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


manifest = [json.loads(line) for line in (BASE / 'manifest.jsonl').read_text().splitlines()]
require(len({item['id'] for item in manifest}) == len(manifest), 'Duplicate acquisition ID')
for item in manifest:
    verify(item['raw_path'], item['sha256'], item['bytes'])
    verify(item['text_path'], item['text_sha256'])

repositories = json.loads((BASE / 'repos.json').read_text())
trees = 0
selected_files = 0
for repo in repositories:
    commit = json.loads(verify(repo['commit_metadata_path'], repo['commit_metadata_sha256']))
    tree = json.loads(verify(repo['tree_metadata_path'], repo['tree_metadata_sha256']))
    require(commit['sha'] == repo['commit'], 'Commit metadata mismatch')
    require(commit['commit']['tree']['sha'] == repo['tree_sha'], 'Commit/tree metadata mismatch')
    require(tree['sha'] == repo['tree_sha'] and not tree.get('truncated'), 'Incomplete tree metadata')
    entries = {entry['path']: entry for entry in tree['tree']}
    require(len(entries) == len(tree['tree']), 'Duplicate tree path')
    children = {}
    for entry in tree['tree']:
        path = PurePosixPath(entry['path'])
        parent = '' if str(path.parent) == '.' else str(path.parent)
        children.setdefault(parent, []).append(entry)
    for parent, items in children.items():
        def order(entry):
            return PurePosixPath(entry['path']).name.encode() + (b'/' if entry['type'] == 'tree' else b'')
        payload = b''.join(entry['mode'].lstrip('0').encode() + b' ' +
                           PurePosixPath(entry['path']).name.encode() + b'\0' + bytes.fromhex(entry['sha'])
                           for entry in sorted(items, key=order))
        expected = repo['tree_sha'] if parent == '' else entries[parent]['sha']
        require(git_hash('tree', payload) == expected, f'Tree reconstruction mismatch: {parent}')
        trees += 1
    for item in repo['files']:
        data = verify(item['path'], item['sha256'], item['bytes'])
        require(git_hash('blob', data) == item['git_blob_sha'], f'Blob mismatch: {item["path"]}')
        require(entries[item['repository_path']]['sha'] == item['git_blob_sha'], 'Blob/tree membership mismatch')
        expected_url = repo['repository'].replace('https://github.com/', 'https://raw.githubusercontent.com/')
        expected_url += '/' + repo['commit'] + '/' + item['repository_path']
        require(item['url'] == expected_url, 'Unpinned source URL')
        selected_files += 1

reading = json.loads(RECEIPT.read_text())
chunks = 0
lines_read = 0
for item in reading['sources']:
    verify(item['raw_path'], item['raw_sha256'])
    data = verify(item['text_path'], item['text_sha256'])
    lines = lf_lines(data)
    require(len(lines) == item['line_count'], f'Line count mismatch: {item["id"]}')
    cursor = 1
    for part in item['coverage_ranges']:
        start, end = part['start_line'], part['end_line']
        require(start == cursor and start <= end <= len(lines), f'Coverage gap/overlap/range: {item["id"]}')
        chunk = b''.join(lines[start - 1:end])
        require(digest(chunk) == part['sha256'] and len(chunk) == part['bytes'], 'Chunk bytes mismatch')
        require(part['status'] == 'read_untruncated', 'Unexpected reading status')
        cursor = end + 1
        chunks += 1
    require(item['coverage_complete'] and cursor == len(lines) + 1, 'Incomplete claimed full reading')
    lines_read += len(lines)

artifacts = json.loads((BASE / 'artifacts.json').read_text())['artifacts']
render_paths = set()
for item in artifacts:
    verify(item['path'], item['sha256'], item['bytes'])
    require(item['path'] not in render_paths, 'Duplicate render')
    render_paths.add(item['path'])
reviewed = {item['path'] for item in artifacts if item['reading_status'] == 'visually_reviewed'}
require(reviewed == {item['path'] for item in reading['figures']}, 'Visual reading overlay mismatch')
for item in reading['figures']:
    verify(item['path'], item['sha256'], item['bytes'])
for item in manifest:
    if 'pdf_page_count' not in item:
        continue
    pages = {part['pdf_page_one_based'] for part in artifacts if part['source_id'] == item['id']}
    require(pages == set(range(1, item['pdf_page_count'] + 1)), 'Missing PDF render')
    record = next(part for part in reading['sources'] if part['id'] == item['id'])
    inspected = {part['pdf_page_one_based'] for part in artifacts
                 if part['source_id'] == item['id'] and part['reading_status'] == 'visually_reviewed'}
    require(inspected == set(record['pdf_pages_visually_inspected_one_based']), 'Reviewed page mismatch')

inputs = [BASE / 'manifest.jsonl', BASE / 'repos.json', BASE / 'artifacts.json', RECEIPT, Path(__file__).resolve()]
out = dict(verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
           acquisitions=len(manifest), repository_pins=len(repositories), snapshot_files=selected_files,
           reconstructed_metadata_trees=trees, reading_records=len(reading['sources']),
           full_records=len(reading['sources']), coverage_chunks=chunks, logical_lines=lines_read,
           page_renders=len(artifacts), reviewed_page_renders=len(reviewed), hash_checks=checks,
           inputs={str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in inputs},
           limitations=['Reader attestations are not machine proof of reading or understanding.',
                        'Retained HTTPS commit metadata links the pinned commit to the tree; commit signatures were not independently verified.',
                        'Only selected repository blobs are retained/read; recursive metadata reconstruction is not whole-repository reading.',
                        'No acquired program executed; no robot, service account or device contacted.'])
(BASE / 'audit.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2))

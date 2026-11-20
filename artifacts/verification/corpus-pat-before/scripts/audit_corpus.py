#!/usr/bin/env python3
"""Verify local research hashes/commit pins; never infer reading or conformance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
checked = 0
unique_files = set()
coverage_chunks = 0


def verify(path, digest):
    global checked
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise ValueError(f'Hash mismatch: {path}')
    checked += 1
    unique_files.add(path.resolve())


def verify_reading_record(item):
    """Verify an overlay's source bytes and any exact LF-based coverage chunks.

    A coverage assertion is reader-supplied evidence, not machine proof of reading.
    """
    global coverage_chunks
    for file_key, hash_key in [('path', 'sha256'), ('raw_path', 'raw_sha256'),
                               ('text_path', 'text_sha256')]:
        if item.get(file_key) and item.get(hash_key):
            verify(ROOT / item[file_key], item[hash_key])
    if item.get('raw_path') and item.get('sha256') and not item.get('raw_sha256'):
        verify(ROOT / item['raw_path'], item['sha256'])
    ranges = item.get('coverage_ranges', [])
    if not ranges:
        intervals = item.get('sequential_read_ranges', item.get('untruncated_read_line_intervals', item.get('read_ranges_inclusive', [])))
        ranges = [{'start_line': a, 'end_line': b} for a, b in intervals]
    source_path = item.get('text_path', item.get('path'))
    if ranges and source_path:
        # splitlines() also splits PDF form feeds and is wrong for sed ranges.
        data = (ROOT / source_path).read_bytes()
        lines = data.split(b'\n')
        lines = [line + b'\n' for line in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
        for key in ('line_count', 'text_line_count', 'logical_lines'):
            if key in item and item[key] != len(lines):
                raise ValueError(f'Line count mismatch: {source_path}')
        covered = set()
        for chunk in ranges:
            start, end = chunk['start_line'], chunk['end_line']
            if not 1 <= start <= end <= len(lines):
                raise ValueError(f'Invalid coverage interval: {source_path}')
            if chunk.get('sha256'):
                actual = hashlib.sha256(b''.join(lines[start - 1:end])).hexdigest()
                if actual != chunk['sha256']:
                    raise ValueError(f'Coverage hash mismatch: {source_path}:{start}-{end}')
                coverage_chunks += 1
            covered.update(range(start, end + 1))
        claims_full = item.get('coverage_complete') or item.get('text_coverage_fraction') == 1.0 or item.get('coverage_gaps') == [] or item.get('reading_status') == 'read_full'
        if claims_full and covered != set(range(1, len(lines) + 1)):
            raise ValueError(f'Incomplete claimed coverage: {source_path}')


sources = []
for lane in ('protocols', 'physical-ai'):
    base = ROOT / 'research' / lane
    data = json.loads((base / 'manifest.json').read_text())
    records = data['sources'] if isinstance(data, dict) else data
    for item in records:
        for file_key, hash_key in [('raw_path', 'sha256'), ('text_path', 'text_sha256')]:
            if item.get(file_key) and item.get(hash_key):
                verify(base / item[file_key], item[hash_key])
    sources.extend(records)
for lane in ('mhs', 'laboratory'):
    for item in map(json.loads, (ROOT / f'research/{lane}/manifest.jsonl').read_text().splitlines()):
        for file_key, hash_key in [('raw_path', 'sha256'), ('text_path', 'text_sha256')]:
            if item.get(file_key) and item.get(hash_key):
                verify(ROOT / item[file_key], item[hash_key])
        sources.append(item)
    for item in json.loads((ROOT / f'research/{lane}/reading-log.json').read_text()):
        verify_reading_record(item)
for lane in ('host-contract', 'planning', 'planning/continuation', 'instrumentation', 'home', 'industrial-opcua', 'mcp', 'wot-architecture', 'deployment/gb10-followup'):
    manifest = ROOT / f'research/{lane}/manifest.jsonl'
    if manifest.exists():
        records = list(map(json.loads, manifest.read_text().splitlines()))
    else:
        records = json.loads(manifest.with_suffix('.json').read_text())['sources']
    for item in records:
        for file_key, hash_key in [('raw_path', 'sha256'), ('text_path', 'text_sha256')]:
            if item.get(file_key) and item.get(hash_key):
                verify(ROOT / item[file_key], item[hash_key])
        sources.append(item)
for item in json.loads((ROOT / 'research/instrumentation/reading-instrumentation.json').read_text())['sources']:
    verify_reading_record(item)
instrument_figures = json.loads((ROOT / 'research/instrumentation/figure-manifest.json').read_text())
for collection in ('pages', 'sheets', 'detail_images'):
    for item in instrument_figures[collection]:
        verify(ROOT / item.get('path', item.get('render_path')), item['sha256'])
for item in instrument_figures['source_coverage']:
    if item.get('all_pdf_pages_reviewed') and set(item['reviewed_pdf_pages']) != set(range(1, item['pdf_page_count'] + 1)):
        raise ValueError(f'Incomplete claimed PDF page coverage: {item["id"]}')
for manifest in sorted((ROOT / 'research/constrained').glob('*/manifest.json*')):
    if manifest.suffix == '.jsonl':
        records = [json.loads(line) for line in manifest.read_text().splitlines()]
    else:
        data = json.loads(manifest.read_text())
        records = data['sources'] if isinstance(data, dict) else data
    for item in records:
        if item.get('raw_path'):
            verify(ROOT / item['raw_path'], item.get('sha256', item.get('raw_sha256')))
        if item.get('text_path'):
            verify(ROOT / item['text_path'], item['text_sha256'])
        sources.append(item)
for item in json.loads((ROOT / 'research/embedded/reading-log.json').read_text())['files']:
    verify_reading_record(item)
for path in sorted((ROOT / 'research').glob('*/reading-*-full.json')):
    data = json.loads(path.read_text())
    for item in data['sources']:
        verify_reading_record(item)
    for item in data.get('figures', []):
        verify(ROOT / item['path'], item['sha256'])
ancillary = json.loads((ROOT / 'research/protocols/wot-artifacts/manifest.json').read_text())
for item in ancillary:
    if item.get('path') and item.get('sha256'):
        verify(ROOT / 'research/protocols/wot-artifacts' / item['path'], item['sha256'])
for item in json.loads((ROOT / 'research/laboratory/figure-manifest.json').read_text()):
    verify(ROOT / item['path'], item['sha256'])
repositories_verified = set()
for lane, name in [('protocols','repositories.json'), ('physical-ai','repos.json'),
                   ('mhs','repo-manifest.json'), ('laboratory','repositories.json'),
                   ('host-contract','repos.json')]:
    base = ROOT / 'research' / lane
    records = json.loads((base / name).read_text())
    for item in records if isinstance(records, list) else [records]:
        path = item.get('checkout_path', item.get('path'))
        repo = ROOT / path if path.startswith('research/') else base / path
        actual = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
        if actual != item['commit']:
            raise ValueError(f'Commit mismatch: {repo}')
        for file in item.get('files', item.get('inspected_files', item.get('files_read', []))):
            verify(repo / file['path'], file['sha256'])
        repositories_verified.add(repo.resolve())
for item in json.loads((ROOT / 'research/embedded/repositories.json').read_text())['repositories']:
    repo = ROOT / item['checkout_path']
    actual = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    if actual != item['commit']:
        raise ValueError(f'Commit mismatch: {repo}')
    repositories_verified.add(repo.resolve())
snapshot_pins = set()
for record in json.loads((ROOT / 'research/planning/repos.json').read_text()):
    entries = []
    for item in record['files']:
        path = ROOT / item['path']
        verify(path, item['sha256'])
        data = path.read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if blob != item['git_blob_sha']:
            raise ValueError(f'Git blob mismatch: {path}')
        entries.append((path.name, b'100644 ' + path.name.encode() + b'\0' + bytes.fromhex(blob)))
    # These two acquired subtrees are flat; retain that explicit assumption.
    tree = b''.join(entry for name, entry in sorted(entries))
    tree_hash = hashlib.sha1(b'tree ' + str(len(tree)).encode() + b'\0' + tree).hexdigest()
    if tree_hash != record['tree_sha']:
        raise ValueError(f'Git subtree mismatch: {record["subdirectory"]}')
    snapshot_pins.add((record['repository'], record['commit']))
# Home snapshots retain recursive GitHub commit/tree metadata, not Git checkouts
# or the flat subtrees above. Run their original local integrity checker freshly;
# its tree/blob checks remain separate from this script's file-hash counters.
home_audit = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(ROOT / 'research/home/audit_home.py')], text=True))
for path, digest in home_audit['inputs'].items():
    verify(ROOT / path, digest)
home_repositories = json.loads((ROOT / 'research/home/repos.json').read_text())
if home_audit['repository_pins'] != len(home_repositories):
    raise ValueError('Home snapshot repository count mismatch')
for record in home_repositories:
    for prefix in ('commit', 'tree'):
        verify(ROOT / record[f'{prefix}_metadata_path'], record[f'{prefix}_metadata_sha256'])
    snapshot_pins.add((record['repository'], record['commit']))
# The continuation uses one recursive selected-file snapshot, not the flat
# planning subtrees above. Its fresh local checker also validates render counts,
# exact chunk byte counts and selected-file membership in the retained Git tree.
continuation_base = ROOT / 'research/planning/continuation'
continuation_audit = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(continuation_base / 'audit_continuation.py')], text=True))
for path, digest in continuation_audit['inputs'].items():
    verify(ROOT / path, digest)
continuation_repositories = json.loads((continuation_base / 'repos.json').read_text())
if continuation_audit['repository_pins'] != len(continuation_repositories):
    raise ValueError('Planning continuation repository count mismatch')
for record in continuation_repositories:
    for prefix in ('commit', 'tree'):
        verify(ROOT / record[f'{prefix}_metadata_path'], record[f'{prefix}_metadata_sha256'])
    for item in record['files']:
        verify(ROOT / item['path'], item['sha256'])
    snapshot_pins.add((record['repository'], record['commit']))
for base in (ROOT / 'research/planning', continuation_base):
    for item in json.loads((base / 'artifacts.json').read_text())['artifacts']:
        verify(ROOT / item['path'], item['sha256'])
# The OPC UA lane is version/build-pinned specification exports, not a Git
# snapshot. Recompute its local audit, including exact complete-section
# boundaries, unread Part4 gaps, and unavailable Part10 figure references.
# Its own counters are nested and not added to this script's overlapping counts.
opcua_base = ROOT / 'research/industrial-opcua'
opcua_audit = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(opcua_base / 'audit_opcua.py')], text=True))
if not opcua_audit['passed'] or opcua_audit['repository_pins'] != 0:
    raise ValueError('Unexpected OPC UA audit result or repository claim')
for item in opcua_audit['metadata_hashes']:
    verify(ROOT / item['path'], item['sha256'])
for item in json.loads((opcua_base / 'figure-manifest.json').read_text())['figures']:
    verify(ROOT / item['path'], item['sha256'])
for item in json.loads((opcua_base / 'metadata/selected-sections.json').read_text()):
    verify(ROOT / item['path'], item['sha256'])
# MCP is a selected-file specification snapshot with a retained recursive Git
# tree. Nested counters overlap this script's source/coverage hashes, so retain
# them separately rather than summing them as distinct evidence.
mcp_base = ROOT / 'research/mcp'
mcp_audit = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(mcp_base / 'audit_mcp.py')], text=True))
for path, digest in mcp_audit['inputs'].items():
    verify(ROOT / path, digest)
mcp_pin = json.loads((mcp_base / 'pin.json').read_text())
verify(ROOT / mcp_pin['metadata_path'], mcp_pin['sha256'])
verify(ROOT / mcp_pin['tree_metadata_path'], mcp_pin['tree_metadata_sha256'])
snapshot_pins.add(('https://github.com/modelcontextprotocol/modelcontextprotocol', mcp_pin['commit']))
# The microscope lane retains exact source copies from four Git checkouts,
# two already present in the older physical-AI lane. Count unique checkout
# paths, preserve failed HTTP attempts, and keep byte/range audit counters
# separate from claims of reading or physical behavior.
microscopy_base = ROOT / 'research/microscopy-controller'
microscopy_audit = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(microscopy_base / 'verify_retained.py')], text=True))
if microscopy_audit['status'] != 'passed' or microscopy_audit['acquiredCodeExecuted']:
    raise ValueError('Unexpected microscopy audit result or execution claim')
for name, digest in microscopy_audit['inputsSha256'].items():
    verify(microscopy_base / name, digest)
verify(ROOT / 'docs/microscope-controller-binding.md', microscopy_audit['bindingDocumentSha256'])
for item in json.loads((microscopy_base / 'manifest.json').read_text())['files']:
    verify(ROOT / item['path'], item['sha256'])
for item in json.loads((microscopy_base / 'acquisition.json').read_text()):
    if item.get('path'):
        verify(ROOT / item['path'], item['sha256'])
    sources.append(dict(item, http_status=item['status'],
                        status='acquired' if item['status'] == 200 else 'failed'))
for item in json.loads((microscopy_base / 'pins.json').read_text())['repositories']:
    repositories_verified.add((ROOT / item['retainedCheckout']).resolve())
# Current LwM2M published text is covered by the generic constrained overlays;
# this nested check also pins HTML figure inventories, their PDF-page mapping,
# separately acquired schemas and the explicitly unavailable Appendix K.
lwm2m_current_base = ROOT / 'research/constrained/lwm2m-current'
lwm2m_current_audit = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(lwm2m_current_base / 'audit_lwm2m_current.py')], text=True))
if not lwm2m_current_audit['passed'] or lwm2m_current_audit['repository_pins'] != 0:
    raise ValueError('Unexpected current LwM2M audit result or repository claim')
for item in lwm2m_current_audit['input_hashes']:
    verify(ROOT / item['path'], item['sha256'])
# The Architecture Recommendation's full-text reading already enters through
# the generic reading glob. Recompute its original offline verifier to check
# extraction fidelity, all tables/figures and the explicitly selected editor
# configuration. Image acquisitions and nested counts remain separate from
# document acquisitions and overlapping aggregate hash/range counts.
wot_architecture_base = ROOT / 'research/wot-architecture'
wot_architecture_summary = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(wot_architecture_base / 'audit_wot_architecture.py')], text=True))
wot_architecture_report = wot_architecture_base / 'audit-result.json'
wot_architecture_audit = json.loads(wot_architecture_report.read_text())
if (not wot_architecture_audit['passed'] or wot_architecture_audit['repository_pins'] != 0 or
        wot_architecture_audit['acquired_code_executed'] or wot_architecture_audit['devices_contacted'] or
        any(wot_architecture_audit.get(key) != value for key, value in wot_architecture_summary.items())):
    raise ValueError('Unexpected WoT Architecture audit result, summary or execution claim')
for item in wot_architecture_audit['input_files']:
    verify(ROOT / item['path'], item['sha256'])
for item in json.loads((wot_architecture_base / 'reading-wot-architecture-full.json').read_text())['selected_sources']:
    verify_reading_record(item)
wot_architecture_report_sha256 = hashlib.sha256(wot_architecture_report.read_bytes()).hexdigest()
# Platform acquisitions already enter through the constrained manifest glob.
# The nested verifier checks selected/full scope and negative metadata cases;
# the aggregate separately counts its exact source/range/figure hashes.
platform_base = ROOT / 'research/constrained/clock-boot-platform'
platform_audit = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(platform_base / 'verify.py')], text=True))
if not platform_audit['ok']:
    raise ValueError('Platform source audit failed')
platform_reading = json.loads((platform_base / 'reading.json').read_text())
verify(platform_base / 'reading.json', platform_audit['reading_sha256'])
for item in platform_reading['sources']:
    verify_reading_record(item)
for item in platform_reading['integrity_files']:
    verify(ROOT / item['path'], item['sha256'])
for item in json.loads((ROOT / platform_reading['figure_manifest_path']).read_text()):
    verify(ROOT / item['path'], item['sha256'])
platform_status = json.loads((platform_base / 'notes/source-status.json').read_text())
sdk_release = next(item for item in platform_status['official_sources'] if item['id'] == 'pico-sdk-latest')
sdk_file_prefix = 'https://raw.githubusercontent.com/raspberrypi/pico-sdk/' + sdk_release['commit'] + '/'
platform_sdk_files = [item for item in platform_reading['sources'] if item['url'].startswith(sdk_file_prefix)]
if len(platform_sdk_files) != 6:
    raise ValueError('Unexpected pinned Pico SDK source-file set')
platform_sdk_file_pin = {'repository_url':'https://github.com/raspberrypi/pico-sdk',
    'commit':sdk_release['commit'], 'file_count':len(platform_sdk_files),
    'scope':'Six exact commit-URL source files, not a checkout or complete repository snapshot; separate from repository/snapshot pin counts.'}
gb10_base = ROOT / 'research/deployment/gb10-followup'
gb10_audit = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(gb10_base / 'verify.py')], text=True))
if not gb10_audit['ok']:
    raise ValueError('GB10 source audit failed')
verify(gb10_base / 'reading.json', gb10_audit['reading_sha256'])
gb10_reading = json.loads((gb10_base / 'reading.json').read_text())
for item in gb10_reading['sources']:
    verify_reading_record(item)
for item in gb10_reading['integrity_files'] + gb10_reading['figures']:
    verify(ROOT / item['path'], item['sha256'])
edhoc_base = ROOT / 'research/constrained/edhoc-full'
edhoc_audit = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(edhoc_base / 'verify.py')], text=True))
if edhoc_audit['status'] != 'pass':
    raise ValueError('EDHOC source audit failed')
edhoc_reading = json.loads((edhoc_base / 'reading.json').read_text())
for item in edhoc_reading['sources']:
    verify_reading_record(item)
for item in edhoc_reading['integrity_files'] + edhoc_reading['figures']:
    verify(ROOT / item['path'], item['sha256'])
# Q-Block acquisitions enter through the constrained manifest glob above.
# Its full TXT reading is distinct from selected PDF/registry-HTML coverage;
# run the original offline verifier to check those boundaries and negative
# cases, then include exact source/range/supporting-file hashes in the aggregate.
# Nested counters overlap these assertions and must not be added to them.
qblock_base = ROOT / 'research/constrained/qblock-full'
qblock_audit = json.loads(subprocess.check_output(
    [sys.executable, '-I', '-B', str(qblock_base / 'verify.py')], text=True))
if qblock_audit['status'] != 'pass':
    raise ValueError('Q-Block source audit failed')
qblock_reading_path = qblock_base / 'reading.json'
qblock_reading_sha256 = hashlib.sha256(qblock_reading_path.read_bytes()).hexdigest()
verify(qblock_reading_path, qblock_reading_sha256)
qblock_reading = json.loads(qblock_reading_path.read_text())
for item in qblock_reading['sources']:
    verify_reading_record(item)
for item in qblock_reading['integrity_files'] + qblock_reading['figures']:
    verify(ROOT / item['path'], item['sha256'])
qblock_audit_sha256 = hashlib.sha256((qblock_base / 'verification.json').read_bytes()).hexdigest()
selected = json.loads((ROOT / 'research/planning/reading-code-selected.json').read_text())
for item in selected['files']:
    verify_reading_record(item)
for notebook in selected['notebooks']:
    path = ROOT / notebook['path']
    verify(path, notebook['sha256'])
    cells = json.loads(path.read_text())['cells']
    if len(cells) != notebook['total_cells']:
        raise ValueError(f'Notebook cell count mismatch: {path}')
    for item in notebook['selected_cells']:
        verify_reading_record(item)
        cell = cells[item['cell_index_zero_based']]
        source = cell['source']
        data = (''.join(source) if isinstance(source, list) else source).encode()
        if cell['cell_type'] != item['cell_type'] or data != (ROOT / item['path']).read_bytes():
            raise ValueError(f'Notebook excerpt mismatch: {item["path"]}')
base = ROOT / 'research/host-ipc'
host_ipc = json.loads((base / 'manifest.json').read_text())
for item in host_ipc['entries']:
    path = base / item['snapshot']
    verify(path, item['sha256'])
    if path.stat().st_size != item['bytes']:
        raise ValueError(f'Host IPC byte count mismatch: {path}')
    sources.append(dict(item, status='acquired'))


def verify_harness_entry(base, item):
    path = base / item['snapshot']
    verify(path, item['sha256'])
    if path.stat().st_size != item['bytes']:
        raise ValueError(f'Harness byte count mismatch: {path}')
    # These manifests retain LF ranges, not per-range hashes. Full snapshots
    # remain distinct from the full/partial reading assertions.
    verify_reading_record({
        'path': str(path.relative_to(ROOT)), 'line_count': item['line_count'],
        'coverage_ranges': [{'start_line': a, 'end_line': b} for a, b in item['read_lines']],
        'coverage_complete': item['reading_status'] == 'full',
    })


def pinned_harness_blob(manifest, path):
    # Read a historical Git object; do not require the adjacent live HEAD to
    # remain at a research pin, or execute any Harness source or Git filters.
    return subprocess.check_output(['git', '-C', manifest['repository'], 'cat-file',
                                    'blob', manifest['commit'] + ':' + path])


harness_base = ROOT / 'research/harness'
harness_original = json.loads((harness_base / 'manifest.json').read_text())
harness_current_base = harness_base / 'current-review'
harness_current = json.loads((harness_current_base / 'manifest.json').read_text())
harness_entries = 0
harness_pins = set()
for base, manifest in [(harness_base, harness_original), (harness_current_base, harness_current)]:
    for item in manifest['entries']:
        verify_harness_entry(base, item)
        if pinned_harness_blob(manifest, item['path']) != (base / item['snapshot']).read_bytes():
            raise ValueError(f'Harness pinned blob mismatch: {item["path"]}')
        harness_entries += 1
    snapshot_pins.add((manifest['repository'], manifest['commit']))
    harness_pins.add((manifest['repository'], manifest['commit']))
if ((harness_current_base / harness_current['original_manifest']).resolve() !=
        (harness_base / 'manifest.json').resolve() or
        harness_current['original_commit'] != harness_original['commit'] or
        harness_current['observed_final_head'] != harness_current['commit']):
    raise ValueError('Harness review provenance mismatch')
original_by_path = {item['path']: item for item in harness_original['entries']}
comparison_paths = [item['path'] for item in harness_current['comparisons']]
if len(comparison_paths) != len(set(comparison_paths)) or set(comparison_paths) != set(original_by_path):
    raise ValueError('Harness original snapshot comparison coverage mismatch')
for item in harness_current['comparisons']:
    original = original_by_path[item['path']]
    path = harness_current_base / item['original_snapshot']
    verify(path, item['sha256'])
    if (path.resolve() != (harness_base / original['snapshot']).resolve() or
            item['original_reading_status'] != original['reading_status'] or
            item['original_read_lines'] != original['read_lines'] or
            item['bytes'] != original['bytes'] or item['line_count'] != original['line_count']):
        raise ValueError(f'Harness retained reading metadata mismatch: {item["path"]}')
    matches = pinned_harness_blob(harness_current, item['path']) == path.read_bytes()
    if matches != item['matches_original_snapshot']:
        raise ValueError(f'Harness comparison mismatch: {item["path"]}')
diff = harness_current['changed_api_review']
verify(harness_current_base / diff['artifact'], diff['sha256'])
git_diff = ['git', '-C', harness_current['repository'], 'diff', '--no-ext-diff', '--no-textconv']
expected_diff = subprocess.check_output(git_diff + [harness_original['commit'],
    harness_current['commit'], '--'] + diff['paths'])
if expected_diff != (harness_current_base / diff['artifact']).read_bytes():
    raise ValueError('Harness retained adjacent API diff mismatch')
changed_paths = subprocess.check_output(git_diff + ['--name-only', harness_original['commit'],
    harness_current['commit'], '--'], text=True).splitlines()
if changed_paths != harness_current['changed_paths_since_original']:
    raise ValueError('Harness changed-path inventory mismatch')
acquired = [s for s in sources if s.get('status',s.get('acquisition_status')) in ('acquired','downloaded')]
print(json.dumps({'source_records':len(sources),'acquired_records':len(acquired),
                  'ancillary_wot_records':len(ancillary),'repository_pins':len(repositories_verified) + len(snapshot_pins),
                  'git_checkout_pins':len(repositories_verified),'snapshot_repository_pins':len(snapshot_pins),
                  'hash_assertions_verified':checked,'unique_files_verified':len(unique_files),
                  'coverage_chunk_hashes_verified':coverage_chunks,
                  'home_snapshot_audit':home_audit,
                  'planning_continuation_audit':continuation_audit,
                  'industrial_opcua_audit':opcua_audit,
                  'mcp_specification_audit':mcp_audit,
                  'microscopy_controller_audit':microscopy_audit,
                  'lwm2m_current_audit':lwm2m_current_audit,
                  'wot_architecture_audit':wot_architecture_audit,
                  'wot_architecture_audit_sha256':wot_architecture_report_sha256,
                  'wot_architecture_figure_acquisition_records':wot_architecture_audit['figure_acquisition_records'],
                  'clock_boot_platform_audit':platform_audit,
                  'clock_boot_platform_sdk_file_pin':platform_sdk_file_pin,
                  'gb10_deployment_audit':gb10_audit,
                  'edhoc_full_audit':edhoc_audit,
                  'qblock_full_audit':qblock_audit,
                  'qblock_full_reading_sha256':qblock_reading_sha256,
                  'qblock_full_audit_sha256':qblock_audit_sha256,
                  'host_ipc_snapshots':len(host_ipc['entries']),
                  'harness_snapshot_files':harness_entries,
                  'harness_historical_commit_pins':len(harness_pins),
                  'harness_comparisons':len(harness_current['comparisons']),
                  'warning':'Acquisition counts include alternate URLs/renditions and a relocation page, not distinct works. Nested audit counters overlap the aggregate counters and must not be summed. Reading overlays preserve reader attestations; hashes do not prove reading or physical conformance.'}, indent=2))

#!/usr/bin/env python3
"""Offline archive/declared-reading verification; no Q-Block or crypto execution."""
from copy import deepcopy
from datetime import datetime, timezone
import csv, hashlib, io, json, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PAGES = [8, 9, 16, 19, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 38, 39, 40, 41]
FULL = {'rfc9177-text', 'rfc9177-metadata', 'rfc9177-errata', 'iana-options',
        'iana-content-formats', 'iana-missing-blocks'}
COUNTS = {'rfc9177-text': 2154, 'rfc9177-pdf': 2192, 'rfc9177-metadata': 43,
          'rfc9177-errata': 58, 'iana-core-status': 2897, 'iana-options': 63,
          'iana-content-formats': 156, 'iana-missing-blocks': 39}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local_path(value):
    relative = Path(value)
    path = (ROOT / relative).resolve()
    require(not relative.is_absolute() and path.is_relative_to(ROOT),
            f'Not repository-relative: {value}')
    return path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_hash(path, expected):
    require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected),
            'Malformed SHA-256')
    require(digest(local_path(path).read_bytes()) == expected, f'Hash mismatch: {path}')


def lf_lines(data):
    parts = data.split(b'\n')
    return [part + b'\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def verify_coverage(row):
    lines = lf_lines(local_path(row['text_path']).read_bytes())
    require(lines and row['line_count'] == len(lines), 'LF line count mismatch')
    require(type(row['coverage_complete']) is bool, 'Invalid complete flag')
    full = row['coverage_complete'] or row['reading_status'] == 'read_full'
    covered = set()
    previous = 0
    for chunk in row['coverage_ranges']:
        start, end = chunk['start_line'], chunk['end_line']
        require(type(start) is int and type(end) is int, 'Invalid range type')
        require(1 <= start <= end <= len(lines), 'Out-of-range coverage')
        require(start > previous, 'Overlapping or unordered coverage')
        require(digest(b''.join(lines[start - 1:end])) == chunk['sha256'],
                'Coverage hash mismatch')
        covered.update(range(start, end + 1))
        previous = end
    require(abs(row['text_coverage_fraction'] - len(covered) / len(lines)) < 1e-12,
            'Incorrect coverage fraction')
    if full:
        require(covered == set(range(1, len(lines) + 1)), 'Incomplete full-reading claim')
        require(row['coverage_complete'] and row['reading_status'] == 'read_full',
                'Full-reading status disagreement')
    return len(row['coverage_ranges'])


def verify_visual(pdf, figures):
    require(pdf['pdf_page_count'] == 41 and pdf['all_pdf_pages_reviewed'] is False and
            pdf['reviewed_pdf_pages'] == PAGES and not pdf['coverage_complete'],
            'PDF scope overclaim or wrong page inventory')
    require([r['pdf_page'] for r in figures] == PAGES, 'Wrong selected visual pages')
    require(all(r['visual_review_status'] == 'reviewed_figures_and_tables' for r in figures),
            'Unreviewed visual evidence')
    labels = [label.split(':', 1)[0] for row in figures for label in row['captions']]
    require(sorted(labels) == sorted([f'Figure {n}' for n in range(1, 21)] +
                                    [f'Table {n}' for n in range(1, 6)]),
            'Incomplete or duplicate visual figure/table inventory')


def expect_rejection(function):
    try:
        function()
    except ValueError:
        return
    raise AssertionError('Negative self-check unexpectedly passed')


def main():
    reading = json.loads((BASE / 'reading.json').read_text())
    manifest = [json.loads(line) for line in (BASE / 'manifest.jsonl').read_text().splitlines()]
    require(reading['schema'] == 'hms-reading-overlay-v1', 'Wrong schema')
    require(len(manifest) == 8 and {r['id'] for r in manifest} == set(COUNTS),
            'Unexpected retrieval inventory')
    checked, hash_assertions, chunks = set(), 0, 0
    for row in manifest:
        require(row['status'] == 'downloaded' and row['retrieved_at'], 'Incomplete acquisition')
        require(row['url'].startswith(('https://www.rfc-editor.org/', 'https://www.iana.org/')),
                'Unexpected primary source')
        require(row['final_url'].startswith(('https://www.rfc-editor.org/',
                    'https://errata.rfc-editor.org/', 'https://www.iana.org/')), 'Unexpected redirect')
        for path_key, hash_key in [('raw_path', 'sha256'), ('text_path', 'text_sha256')]:
            verify_hash(row[path_key], row[hash_key])
            checked.add(row[path_key]); hash_assertions += 1
        require(local_path(row['raw_path']).stat().st_size == row['bytes'], 'Raw size mismatch')
    sources = reading['sources']
    require(len(sources) == 8 and {r['id'] for r in sources} == set(COUNTS),
            'Reading/source inventory mismatch')
    for row in sources:
        acquisition = next(m for m in manifest if m['id'] == row['id'])
        for key in ('raw_path', 'text_path', 'text_sha256', 'url', 'final_url', 'retrieved_at'):
            require(row[key] == acquisition[key], f'Acquisition/reading mismatch: {key}')
        require(row['raw_sha256'] == acquisition['sha256'], 'Raw acquisition mismatch')
        require(row['line_count'] == COUNTS[row['id']], 'Unexpected source line count')
        for path_key, hash_key in [('raw_path', 'raw_sha256'), ('text_path', 'text_sha256')]:
            verify_hash(row[path_key], row[hash_key])
            checked.add(row[path_key]); hash_assertions += 1
        chunks += verify_coverage(row)
        hash_assertions += len(row['coverage_ranges'])
    require({r['id'] for r in sources if r['coverage_complete']} == FULL, 'Wrong full-reading set')
    for row in reading['integrity_files'] + reading['figures']:
        verify_hash(row['path'], row['sha256'])
        checked.add(row['path']); hash_assertions += 1
    require(len({r['path'] for r in reading['integrity_files']}) == len(reading['integrity_files']),
            'Duplicate integrity paths')
    rfc = next(r for r in sources if r['id'] == 'rfc9177-text')
    pdf = next(r for r in sources if r['id'] == 'rfc9177-pdf')
    status = next(r for r in sources if r['id'] == 'iana-core-status')
    text = local_path(rfc['text_path']).read_text()
    for label, count in [('Figure', 20), ('Table', 5)]:
        require(list(map(int, re.findall(rf'^\s*{label} (\d+):', text, re.M))) ==
                list(range(1, count + 1)), f'Wrong {label} inventory')
    verify_visual(pdf, reading['figures'])
    metadata = json.loads((BASE / 'raw/rfc9177-metadata.json').read_text())
    require(metadata['status'] == 'PROPOSED STANDARD' and metadata['pub_date'] == 'March 2022'
            and all(metadata[k] == [] for k in ('updates','updated_by','obsoletes','obsoleted_by')),
            'Metadata snapshot changed')
    require(reading['errata'] == [] and 'No matching errata found.' in
            (BASE / 'text/rfc9177-errata.txt').read_text(), 'Errata snapshot changed')
    require('2026-08-11' in ''.join((BASE/'text/iana-core-status.txt').read_text().splitlines(True)[:32]),
            'IANA snapshot date changed')
    opts = {row['Name']: row['Number'] for row in csv.DictReader(
            io.StringIO((BASE / 'text/iana-options.txt').read_text()))}
    require(opts['Q-Block1'] == '19' and opts['Q-Block2'] == '31' and opts['Request-Tag'] == '292',
            'IANA option allocation mismatch')
    formats = {row['Content Type']: row['ID'] for row in csv.DictReader(
            io.StringIO((BASE / 'text/iana-content-formats.txt').read_text()))}
    require(formats['application/missing-blocks+cbor-seq'] == '272', 'IANA Content-Format mismatch')
    prior_path = 'research/constrained/reading-observe-blockwise-full.json'
    require(reading['prior_selected_reading']['path'] == prior_path, 'Prior receipt path mismatch')
    verify_hash(prior_path, reading['prior_selected_reading']['sha256'])
    hash_assertions += 1; checked.add(prior_path)
    prior = json.loads(local_path(prior_path).read_text())
    old = next(row for row in prior['sources'] if row['id'] == 'q-block-rfc9177')
    require(not old['coverage_complete'] and old['coverage_ranges'][0]['start_line'] == 1 and
            old['coverage_ranges'][0]['end_line'] == 200 and
            old['raw_sha256'] == rfc['raw_sha256'], 'Prior selected relationship changed')
    require(digest(local_path(old['raw_path']).read_bytes()) == rfc['raw_sha256'],
            'Earlier selected acquisition differs')
    hash_assertions += 1; checked.add(old['raw_path'])
    negative_cases = []
    def reject(name, function):
        expect_rejection(function); negative_cases.append(name)
    broken = deepcopy(rfc); broken['coverage_ranges'].pop()
    reject('missing_full_coverage', lambda: verify_coverage(broken))
    wrong = deepcopy(rfc); wrong['coverage_ranges'][0]['sha256'] = '0' * 64
    reject('coverage_hash_mismatch', lambda: verify_coverage(wrong))
    overlap = deepcopy(rfc); overlap['coverage_ranges'].insert(1, deepcopy(overlap['coverage_ranges'][0]))
    reject('overlapping_coverage', lambda: verify_coverage(overlap))
    outside = deepcopy(rfc); outside['coverage_ranges'][-1]['end_line'] += 1
    reject('out_of_range_coverage', lambda: verify_coverage(outside))
    disorder = deepcopy(rfc); disorder['coverage_ranges'].reverse()
    reject('unordered_coverage', lambda: verify_coverage(disorder))
    bad_type = deepcopy(rfc); bad_type['coverage_ranges'][0]['start_line'] = True
    reject('boolean_range_index', lambda: verify_coverage(bad_type))
    full_pdf = deepcopy(pdf); full_pdf['coverage_complete'] = True; full_pdf['reading_status'] = 'read_full'
    reject('false_full_pdf_text', lambda: verify_coverage(full_pdf))
    full_status = deepcopy(status); full_status['coverage_complete'] = True; full_status['reading_status'] = 'read_full'
    reject('false_full_registry_text', lambda: verify_coverage(full_status))
    full_visual = deepcopy(pdf); full_visual['all_pdf_pages_reviewed'] = True
    reject('false_all_pdf_visual', lambda: verify_visual(full_visual, reading['figures']))
    fraction = deepcopy(rfc); fraction['text_coverage_fraction'] = 0.99
    reject('incorrect_coverage_fraction', lambda: verify_coverage(fraction))
    reject('path_escape', lambda: local_path('../outside-root'))
    reject('file_hash_mismatch', lambda: verify_hash(rfc['raw_path'], '0' * 64))
    report = dict(status='pass', checked_at=datetime.now(timezone.utc).isoformat(),
        retrieval_records=len(manifest), successful_acquisitions=8,
        hash_assertions=hash_assertions, unique_files_checked=len(checked),
        full_text_sources=len(FULL), full_text_lf_lines=sum(COUNTS[n] for n in FULL),
        rfc9177_lf_lines=2154, coverage_chunks=chunks, figures=20, tables=5,
        selected_pdf_pages_reviewed=len(PAGES), total_pdf_pages=41,
        negative_self_checks=len(negative_cases), negative_cases=negative_cases,
        scope='Offline archival hashes and declared coverage consistency; no Q-Block, crypto, controller, hardware or conformance execution.')
    (BASE / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

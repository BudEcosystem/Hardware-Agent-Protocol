#!/usr/bin/env python3
"""Offline integrity checks only; execute no publisher code or device commands."""
import copy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
EXPECTED = {
    'hardware-current': (108, 2), 'porting-overview': (40, 0),
    'porting-dependencies': (203, 1), 'porting-cuda': (25, 0),
    'release-notes': (194, 1), 'vllm-advanced': (443, 4),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked_file(path, expected):
    target = ROOT / path
    require(sha(target.read_bytes()) == expected, 'Hash mismatch: ' + path)
    return target


def validate(reading):
    require(reading['no_acquired_code_executed'] is True, 'Unexpected execution claim')
    require(reading['scope'] == 'six complete bounded HTML primary-content pages', 'Scope differs')
    sources = reading['sources']
    require(len(sources) == 6 and {s['id'] for s in sources} == set(EXPECTED), 'Page identities differ')
    assertions, chunks, tables, lines_total = 0, 0, 0, 0
    for source in sources:
        expected_lines, expected_tables = EXPECTED[source['id']]
        checked_file(source['raw_path'], source['raw_sha256']); assertions += 1
        text_path = checked_file(source['text_path'], source['text_sha256']); assertions += 1
        data = text_path.read_bytes()
        pieces = data.split(b'\n')
        lines = [p + b'\n' for p in pieces[:-1]] + ([pieces[-1]] if pieces[-1] else [])
        require(source['line_count'] == len(lines) == expected_lines, 'Line count differs')
        require(source['coverage_complete'] is True, 'Incomplete claimed page')
        covered = []
        for interval in source['coverage_ranges']:
            lo, hi = interval['start_line'], interval['end_line']
            require(1 <= lo <= hi <= len(lines), 'Invalid LF range')
            require(sha(b''.join(lines[lo-1:hi])) == interval['sha256'], 'LF range hash mismatch')
            covered.extend(range(lo, hi+1)); chunks += 1
        require(covered == list(range(1, len(lines)+1)), 'Coverage gap, overlap or order error')
        structure_path = checked_file(source['structure_path'], source['structure_sha256']); assertions += 1
        structure = json.loads(structure_path.read_text())
        require(source['tables_reviewed'] == len(structure['tables']) == expected_tables, 'Table coverage differs')
        tables += expected_tables; lines_total += len(lines)
    require(len(reading['figures']) == 1, 'Figure count differs')
    for figure in reading['figures']:
        checked_file(figure['path'], figure['sha256']); assertions += 1
        require(figure['visually_reviewed'] is True, 'Figure review missing')
    for item in reading['integrity_files']:
        checked_file(item['path'], item['sha256']); assertions += 1
    return {'sources': len(sources), 'complete_bounded_pages': 6,
            'covered_lf_lines': lines_total, 'coverage_chunk_hashes': chunks,
            'tables_reviewed': tables, 'figures_reviewed': 1,
            'file_hash_assertions': assertions}


def negative_checks(reading):
    mutations = []
    bad = copy.deepcopy(reading); bad['sources'][0]['raw_sha256'] = '0'*64; mutations.append(bad)
    bad = copy.deepcopy(reading); bad['sources'][0]['coverage_ranges'] = []; mutations.append(bad)
    bad = copy.deepcopy(reading); bad['sources'][-1]['line_count'] = 1; mutations.append(bad)
    bad = copy.deepcopy(reading); bad['sources'][2]['tables_reviewed'] = 0; mutations.append(bad)
    bad = copy.deepcopy(reading); bad['figures'][0]['visually_reviewed'] = False; mutations.append(bad)
    bad = copy.deepcopy(reading); bad['no_acquired_code_executed'] = False; mutations.append(bad)
    for bad in mutations:
        try:
            validate(bad)
        except ValueError:
            continue
        raise ValueError('Negative metadata mutation was accepted')
    return len(mutations)


def main():
    path = BASE / 'reading.json'
    reading = json.loads(path.read_text())
    summary = validate(reading)
    manifest = [json.loads(line) for line in (BASE/'manifest.jsonl').read_text().splitlines()]
    require(len(manifest) == 6 and all(r['status'] == 'downloaded' for r in manifest), 'Acquisition records differ')
    for acquired, reviewed in zip(manifest, reading['sources']):
        require(acquired['id'] == reviewed['id'], 'Manifest order differs')
        for left, right in [('raw_path','raw_path'), ('sha256','raw_sha256'),
                            ('text_path','text_path'), ('text_sha256','text_sha256')]:
            require(acquired[left] == reviewed[right], 'Acquired/reviewed bytes differ')
    links = 0
    for path in (BASE/'README.md', BASE/'notes/method-and-gaps.md', ROOT/'docs/gb10-deployment-evidence.md'):
        for match in re.finditer(r'\[[^\]\n]*\]\(([^)\n]+)\)', path.read_text()):
            target = urlsplit(match[1])
            if target.scheme or not target.path:
                continue
            require((path.parent/unquote(target.path)).resolve().exists(), 'Missing local link')
            links += 1
    report = {'ok': True, 'reading_sha256': sha((BASE/'reading.json').read_bytes()),
              **summary, 'negative_metadata_checks': negative_checks(reading),
              'local_links_checked': links,
              'scope': 'Offline bytes and declared coverage integrity; not reading comprehension, publisher truth, compatibility or device qualification.'}
    (BASE/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

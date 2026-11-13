#!/usr/bin/env python3
"""Offline integrity audit of retained WoT Architecture evidence; original code only."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'research/wot-architecture'
DOC = ROOT / 'docs/wot-architecture-binding.md'
INPUTS = set()
VERIFIED = set()
CHECKS = 0


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def path(name):
    require(not Path(name).is_absolute(), f'Absolute path: {name}')
    p = (ROOT / name).resolve()
    require(p.is_relative_to(BASE) or p == DOC, f'Outside lane: {name}')
    return p


def read(name):
    p = path(name)
    INPUTS.add(p)
    return p.read_bytes()


def verify(name, digest, size=None):
    global CHECKS
    b = read(name)
    require(sha(b) == digest, f'Hash mismatch: {name}')
    require(size is None or len(b) == size, f'Size mismatch: {name}')
    CHECKS += 1
    VERIFIED.add(path(name))
    return b


def doc(name):
    return json.loads(read(f'research/wot-architecture/{name}'))


def lf_lines(data):
    parts = data.split(b'\n')
    return [part + b'\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


class PublicationParser(HTMLParser):
    """Independently reconstruct text and inventories from archived HTML."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignore = 0
        self.text = []
        self.figures = []
        self.figure = None
        self.caption = None
        self.other_images = []
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.sections = []
        self.heading = None
        self.headings = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style'):
            self.ignore += 1
        if tag == 'section':
            self.sections.append(a.get('id'))
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.heading = {'tag': tag, 'id': a.get('id'),
                            'section_id': self.sections[-1] if self.sections else None,
                            'parts': []}
        if tag == 'figure':
            require(self.figure is None, 'Unexpected nested figure')
            self.figure = {'number': len(self.figures) + 1,
                           'html_id': a.get('id'), 'images': []}
        if tag == 'figcaption':
            self.caption = []
        if tag == 'img':
            item = {'src': a.get('src'), 'alt': a.get('alt')}
            if self.figure is None:
                self.other_images.append(item)
            else:
                self.figure['images'].append(item)
        if tag == 'table':
            require(self.table is None, 'Unexpected nested table')
            self.table = {'number': len(self.tables) + 1,
                          'html_id': a.get('id'), 'rows': []}
        if tag == 'tr' and self.table is not None:
            self.row = []
        if tag in ('th', 'td') and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.ignore or not data.strip():
            return
        item = data.strip()
        self.text.append(item)
        if self.caption is not None:
            self.caption.append(item)
        if self.cell is not None:
            self.cell.append(item)
        if self.heading is not None:
            self.heading['parts'].append(item)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.ignore -= 1
        if tag == 'section':
            self.sections.pop()
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') and self.heading:
            self.heading['text'] = ' '.join(self.heading.pop('parts'))
            self.headings.append(self.heading)
            self.heading = None
        if tag == 'figcaption':
            self.figure['caption'] = ' '.join(self.caption)
            self.caption = None
        if tag == 'figure':
            self.figures.append(self.figure)
            self.figure = None
        if tag in ('th', 'td') and self.cell is not None:
            self.row.append(' '.join(self.cell))
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.table['rows'].append(self.row)
            self.row = None
        if tag == 'table' and self.table is not None:
            self.tables.append(self.table)
            self.table = None

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


def main():
    ledger = doc('integrity-ledger.json')
    names = [r['path'] for r in ledger['files']]
    require(len(names) == len(set(names)), 'Duplicate ledger path')
    expected = {str(p.relative_to(ROOT)) for p in BASE.rglob('*') if p.is_file()
                and p.name not in {'integrity-ledger.json', 'audit_wot_architecture.py',
                                   'audit-result.json'}} | {str(DOC.relative_to(ROOT))}
    require(set(names) == expected, 'Ledger does not cover exact retained lane file set')
    for item in ledger['files']:
        verify(item['path'], item['sha256'], item['bytes'])

    manifest = [json.loads(x) for x in read('research/wot-architecture/manifest.jsonl').splitlines()]
    require(len(manifest) == 6, 'Expected six document acquisitions')
    byid = {r['id']: r for r in manifest}
    require(len(byid) == 6, 'Duplicate source id')
    parsers = {}
    for item in manifest:
        require(item['status'] == 'acquired' and item['http_status'] == 200,
                'Unsuccessful acquisition')
        raw = verify(item['raw_path'], item['sha256'], item['bytes'])
        extracted = verify(item['text_path'], item['text_sha256'], item['text_bytes'])
        parser = PublicationParser()
        parser.feed(raw.decode('utf-8'))
        require(('\n'.join(parser.text) + '\n').encode() == extracted,
                f'HTML text reconstruction mismatch: {item["id"]}')
        require(extracted.count(b'\n') == item['text_lf_lines'], 'Extraction line count drift')
        parsers[item['id']] = parser
    rec = byid['architecture-11-rec']
    require(all(byid[x]['sha256'] == rec['sha256'] for x in
                ['latest-alias', 'latest-11-alias']), 'Current alias/version mismatch')

    receipt = doc('reading-wot-architecture-full.json')
    progress = doc('metadata/read-progress.json')
    counts = receipt['counts']
    require(counts == {'acquisitions': 6, 'full_specifications': 1,
                      'full_text_sources': 3, 'full_text_lines': 8602,
                      'coverage_ranges': 11, 'selected_raw_sources': 1,
                      'selected_raw_lines': 70, 'semantic_figures': 40,
                      'figure_assets': 41, 'table_count': 2,
                      'section_headings': 130}, 'Scope/count drift')
    require({r['id'] for r in receipt['sources']} ==
            {'architecture-11-rec', 'publication-history', 'errata-11'},
            'Unexpected full reading claim')
    ranges_count = total_lines = 0
    for item in receipt['sources']:
        acquired = byid[item['id']]
        require(item['raw_path'] == acquired['raw_path'] and
                item['text_path'] == acquired['text_path'], 'Reading acquisition mismatch')
        verify(item['raw_path'], item['raw_sha256'])
        b = verify(item['text_path'], item['text_sha256'], item['text_bytes'])
        lines = lf_lines(b)
        require(len(lines) == item['line_count'] == item['logical_lines'], 'LF count mismatch')
        require(item['ends_with_newline'] == b.endswith(b'\n'), 'LF termination mismatch')
        cursor = 1
        ranges = []
        for r in item['coverage_ranges']:
            a, z = r['start_line'], r['end_line']
            require(a == cursor and a <= z <= len(lines), 'Incomplete/overlapping reading')
            require(sha(b''.join(lines[a-1:z])) == r['sha256'], 'Reading chunk hash mismatch')
            ranges.append([a, z])
            cursor = z + 1
            ranges_count += 1
        require(cursor == len(lines)+1 and item['coverage_complete'], 'False full text claim')
        require(ranges == item['untruncated_read_line_intervals'] ==
                progress['untruncated_read_ranges'][item['id']], 'Reading interval drift')
        total_lines += len(lines)
    require((ranges_count, total_lines) == (11, 8602), 'Reading totals differ')
    require(len(receipt['selected_sources']) == 1, 'Selected scope drift')
    selected = receipt['selected_sources'][0]
    require(selected['id'] == 'editors-draft' and not selected['coverage_complete'],
            'False complete editor draft claim')
    raw = verify(selected['path'], selected['raw_sha256'])
    require(selected['coverage_ranges'] == [{'start_line': 1, 'end_line': 70,
                'sha256': sha(b''.join(lf_lines(raw)[:70]))}], 'Draft selected chunk mismatch')
    require(b'specStatus: "ED"' in raw and b'shortName: "wot-architecture11"' in raw,
            'Draft status changed')
    require(receipt['unread_text_renditions'][0]['lines'] ==
            byid['editors-draft']['text_lf_lines'] == 5020, 'Unread draft scope mismatch')

    parser = parsers['architecture-11-rec']
    figures = doc('metadata/figure-inventory.json')
    require(len(figures) == len(parser.figures) == 40, 'Semantic figure count mismatch')
    image_count = 0
    source_assets = set()
    for retained, actual in zip(figures, parser.figures):
        for key in ('number', 'html_id', 'caption'):
            require(retained[key] == actual[key], f'Figure metadata drift: {key}')
        require([{'src': i['src'], 'alt': i['alt']} for i in retained['images']] ==
                actual['images'], 'Figure image inventory drift')
        for image in retained['images']:
            require(image['url'] == urljoin(rec['url'], image['src']) and
                    image['http_status'] == 200, 'Wrong figure acquisition')
            verify(image['raw_path'], image['sha256'], image['bytes'])
            source_assets.add(image['raw_path'])
            image_count += 1
    require(image_count == len(source_assets) == 41, 'Missing/repeated semantic asset')
    require(parser.other_images == [{'src': 'https://www.w3.org/StyleSheets/TR/2021/logos/W3C',
                                     'alt': 'W3C'}], 'Unreviewed non-figure semantic image')
    require(doc('metadata/table-inventory.json') == parser.tables and
            [len(t['rows']) for t in parser.tables] == [9, 7], 'Table inventory drift')
    require(doc('metadata/section-inventory.json') == parser.headings and
            len(parser.headings) == 130, 'Section inventory drift')
    require({'changes', 'acknowledgements', 'references', 'normative-references',
             'informative-references'} <= {h['section_id'] for h in parser.headings},
            'Appendix/reference omission')
    for key in ('figure_manifest', 'table_manifest', 'section_manifest'):
        pin = receipt[key]
        verify(pin['path'], pin['sha256'], pin['bytes'])
    reviewed = doc('metadata/figure-reviews.json')
    require(len(reviewed['renders']) == 41 and len(reviewed['contact_sheets']) == 7,
            'Figure review count drift')
    require({r['source_path'] for r in reviewed['renders']} == source_assets,
            'Unreviewed/repeated figure asset')
    for r in reviewed['renders']:
        b = verify(r['path'], r['sha256'], r['bytes'])
        require(b.startswith(b'\x89PNG\r\n\x1a\n'), 'Bad figure render signature')
        verify(r['source_path'], r['source_sha256'])
        require(r['review_note'] and r['reading_status'].startswith('visually_reviewed')
                and r['path'] in progress['figures_visually_reviewed'], 'Missing figure review assertion')
    for r in reviewed['contact_sheets']:
        verify(r['path'], r['sha256'], r['bytes'])
        require(r['path'] in progress['contact_sheets_visually_reviewed'], 'Missing sheet review')
    labels = doc('metadata/svg-labels.json')
    require(len(labels) == 3, 'SVG label scope drift')
    for item in labels:
        root = ET.fromstring(read(item['source_path']))
        foreign = []
        fallback = []
        for element in root.iter():
            kind = element.tag.split('}')[-1]
            require(kind != 'script', 'Unexpected acquired SVG script')
            if kind == 'foreignObject':
                foreign.append(' '.join(x.strip() for x in element.itertext() if x.strip()))
            if kind == 'text':
                fallback.append(''.join(element.itertext()))
        require(foreign == item['foreign_object_labels'] and
                fallback == item['fallback_text_labels'], 'SVG label extraction drift')
    require('%3CmxGraphModel%3E' in labels[2]['foreign_object_labels'][4],
            'Published figure defect disclosure drift')
    status = doc('metadata/version-status.json')
    require(status['current_approved_baseline']['date'] == '2023-12-05' and
            status['current_approved_baseline']['status'] == 'W3C Recommendation' and
            status['aliases_identical_to_versioned_source'], 'Approved baseline drift')
    require(len(status['source_pins']) == 6, 'Missing version source pins')
    for pin in status['source_pins']:
        acquired = byid[pin['id']]
        require(pin['raw_path'] == acquired['raw_path'] and
                pin['raw_sha256'] == acquired['sha256'] and
                pin['text_path'] == acquired['text_path'] and
                pin['text_sha256'] == acquired['text_sha256'], 'Version pin mismatch')
    read(str(Path(__file__).resolve().relative_to(ROOT)))
    hashes = [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p.read_bytes())}
              for p in sorted(INPUTS)]
    result = {
        'passed': True,
        'command': 'python3 -I -B research/wot-architecture/audit_wot_architecture.py',
        'scope': 'Offline byte integrity, independent HTML text reconstruction, complete reader-asserted '
                 'LF coverage for one Recommendation and two status pages, selected draft configuration, '
                 'exact table/heading/semantic-figure inventories, SVG label fidelity and figure-review '
                 'assertions. Does not prove comprehension, normative conformance, interoperability, '
                 'physical safety, complete editor-draft/bibliography/repository review or device execution.',
        'acquisition_records': 6, 'figure_acquisition_records': 41, 'repository_pins': 0,
        'file_hash_checks': CHECKS, 'unique_verified_files': len(VERIFIED),
        'reading_full_text_sources': 3, 'reading_partial_raw_sources': 1,
        'reading_chunk_hashes': 11, 'reading_lines': 8602,
        'selected_raw_chunk_hashes': 1, 'selected_raw_lines': 70,
        'full_specifications': [{'id': 'architecture-11-rec', 'lines': 8405,
                                 'scope': 'Sections 1–12 and appendices A–C, all two tables and 40 figures'}],
        'semantic_figures_visually_reviewed': 40, 'figure_assets_visually_reviewed': 41,
        'svg_fallback_renders_with_complete_embedded_labels': 3,
        'svg_source_defects_disclosed': ['Figure 23 Operational label contains encoded mxGraphModel; '
                                       'supplied fallback labels truncate and can clip. No repair substituted.'],
        'table_count': 2, 'section_heading_count': 130,
        'input_file_count': len(hashes), 'input_files': hashes,
        'acquired_code_executed': False, 'devices_contacted': False,
    }
    output = BASE / 'audit-result.json'
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in {'input_files', 'scope',
                          'full_specifications', 'svg_source_defects_disclosed'}}, indent=2))


if __name__ == '__main__':
    main()

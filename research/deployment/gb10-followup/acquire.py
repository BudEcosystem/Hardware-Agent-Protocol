#!/usr/bin/env python3
"""Acquire six bounded publisher pages; never execute their example commands."""
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
SOURCES = [
    ('hardware-current', 'https://docs.nvidia.com/dgx/dgx-spark/hardware.html'),
    ('porting-overview', 'https://docs.nvidia.com/dgx/dgx-spark-porting-guide/latest/overview.html'),
    ('porting-dependencies', 'https://docs.nvidia.com/dgx/dgx-spark-porting-guide/latest/porting/dependencies.html'),
    ('porting-cuda', 'https://docs.nvidia.com/dgx/dgx-spark-porting-guide/latest/porting/cuda.html'),
    ('release-notes', 'https://docs.nvidia.com/dgx/dgx-spark/release-notes.html'),
    ('vllm-advanced', 'https://build.nvidia.com/spark/vllm/advanced'),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    records = []
    for name, url in SOURCES:
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        request = urllib.request.Request(url, headers={'User-Agent': 'HMS bounded research archive/1'})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                resolved = response.url
                headers = dict(response.headers.items())
            raw_path = BASE / 'raw' / (name + '.html')
            raw_path.write_bytes(raw)
            soup = BeautifulSoup(raw, 'html.parser')
            article = soup.select_one('article.bd-article')
            selector = 'article.bd-article'
            if article is None:
                article = soup.select_one('main')
                selector = 'main'
            if article is not None and not article.get_text(strip=True):
                # React streamed HTML may place the full page outside the main
                # placeholder. Parse retained HTML only; never run its scripts.
                heading = soup.find('h2', string='Choose and run a vLLM recipe on DGX Spark or Station')
                if heading is not None:
                    article = next((p for p in heading.parents
                                    if isinstance(p.get('id'), str) and p['id'].startswith('S:')), None)
                    selector = 'server-streamed page container containing exact advanced-tab h2'
            if article is None:
                raise ValueError('No bounded article/main element')
            if not article.get_text(strip=True):
                raise ValueError('Bounded page extraction is empty')
            for item in article.select('script,style'):
                item.decompose()
            extracted = (article.get_text('\n', strip=True) + '\n').encode()
            text_path = BASE / 'text' / (name + '.txt')
            text_path.write_bytes(extracted)
            table_rows = []
            for index, table in enumerate(article.select('table'), 1):
                table_rows.append({'table': index, 'rows': [
                    [cell.get_text(' ', strip=True) for cell in row.select('th,td')]
                    for row in table.select('tr')]})
            structure = {'selector': selector, 'title': soup.title.get_text() if soup.title else None,
                         'tables': table_rows,
                         'images': [{'src': i.get('src'), 'alt': i.get('alt'), 'srcset': i.get('srcset')}
                                    for i in article.select('img')],
                         'article_links': [{'text': a.get_text(' ', strip=True), 'href': a.get('href')}
                                           for a in article.select('a[href]')]}
            structure_path = BASE / 'notes' / (name + '-structure.json')
            structure_path.write_text(json.dumps(structure, indent=2) + '\n')
            records.append({'id': name, 'url': url, 'resolved_url': resolved, 'retrieved_at': stamp,
                            'status': 'downloaded', 'publisher': 'NVIDIA',
                            'reading_status': 'acquired_not_yet_read',
                            'raw_path': str(raw_path.relative_to(ROOT)), 'sha256': sha(raw),
                            'bytes': len(raw), 'text_path': str(text_path.relative_to(ROOT)),
                            'text_sha256': sha(extracted), 'extraction_selector': selector,
                            'text_line_count': extracted.count(b'\n'),
                            'response_headers': headers,
                            'structure_path': str(structure_path.relative_to(ROOT)),
                            'structure_sha256': sha(structure_path.read_bytes()),
                            'scope': 'One bounded published HTML page; linked pages and full website not included.'})
        except Exception as error:
            records.append({'id': name, 'url': url, 'retrieved_at': stamp, 'status': 'failed',
                            'error': type(error).__name__ + ': ' + str(error)})
        print(json.dumps({key: records[-1][key] for key in ('id', 'status')}))
    (BASE / 'manifest.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in records))


if __name__ == '__main__':
    main()

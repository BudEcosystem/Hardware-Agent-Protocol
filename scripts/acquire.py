#!/usr/bin/env python3
"""Archive a public URL and text extraction; acquisition never implies reading."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

import requests
from bs4 import BeautifulSoup


def acquire(url, root, source_id):
    root = Path(root)
    for directory in ('raw', 'text'):
        (root / directory).mkdir(parents=True, exist_ok=True)
    record = {'id': source_id, 'url': url, 'retrieved_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'reading_status': 'unread'}
    try:
        response = requests.get(url, timeout=60, headers={'User-Agent': 'HMS-Research/0.1 (local research archive)'})
        record.update(http_status=response.status_code, final_url=response.url, content_type=response.headers.get('Content-Type', ''))
        response.raise_for_status()
        data = response.content
        suffix = '.pdf' if data.startswith(b'%PDF') else '.html' if 'html' in record['content_type'] else '.txt'
        raw = root / 'raw' / (source_id + suffix)
        raw.write_bytes(data)
        record.update(raw_path=str(raw), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        extracted = root / 'text' / (source_id + '.txt')
        if suffix == '.pdf':
            subprocess.run(['pdftotext', '-layout', str(raw), str(extracted)], check=True)
            record['extraction'] = 'pdftotext -layout; figures require separate inspection'
        elif suffix == '.html':
            soup = BeautifulSoup(data, 'html.parser')
            for node in soup(['script', 'style', 'nav', 'footer', 'header']):
                node.decompose()
            content = soup.find('main') or soup.find('article') or soup
            extracted.write_text(content.get_text('\n', strip=True))
            record['extraction'] = 'BeautifulSoup main/article/body; raw HTML retained; dynamic content may be absent'
        else:
            extracted.write_text(response.text)
            record['extraction'] = 'response text'
        record.update(text_path=str(extracted), text_sha256=hashlib.sha256(extracted.read_bytes()).hexdigest(), text_chars=len(extracted.read_text()), acquisition_status='downloaded')
    except Exception as error:
        record.update(acquisition_status='failed', error=str(error))
    with (root / 'manifest.jsonl').open('a') as output:
        output.write(json.dumps(record) + '\n')
    print(json.dumps(record))
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('id')
    parser.add_argument('url')
    parser.add_argument('--root', default='research/mhs')
    args = parser.parse_args()
    acquire(args.url, args.root, args.id)

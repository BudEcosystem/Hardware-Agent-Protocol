"""Retain three primary sources without executing acquired code."""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

BASE = Path(__file__).resolve().parent
SOURCES = [
    ('connection', 'https://raw.githubusercontent.com/python/cpython/v3.12.3/Modules/_sqlite/connection.c', '.c'),
    ('cursor', 'https://raw.githubusercontent.com/python/cpython/v3.12.3/Modules/_sqlite/cursor.c', '.c'),
]
(BASE / 'raw').mkdir()


def acquire(item):
    name, url, suffix = item
    request = urllib.request.Request(url, headers={'User-Agent': 'HMS-local-research/1'})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read(1048577)
        assert len(body) <= 1048576
        row = {'id': name, 'url': url, 'finalUrl': response.url, 'status': response.status,
               'headers': dict(response.headers.items()), 'bytes': len(body),
               'sha256': hashlib.sha256(body).hexdigest(), 'path': 'raw/' + name + suffix}
    with (BASE / row['path']).open('xb') as stream:
        stream.write(body)
    return row


with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    rows = list(pool.map(acquire, SOURCES))
with (BASE / 'acquisition.json').open('x') as stream:
    json.dump({'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'sources': rows, 'perResponseLimitBytes': 1048576, 'perResponseTimeoutSeconds': 20,
               'acquiredCodeExecuted': False}, stream, indent=2); stream.write('\n')
print(json.dumps([{'id': r['id'], 'bytes': r['bytes'], 'sha256': r['sha256']} for r in rows]))

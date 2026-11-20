"""Retain official API documentation as data; no acquired source is executed."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

BASE = Path(__file__).resolve().parent / 'research'
BASE.mkdir(mode=0o700, exist_ok=False)
SOURCES = {name: 'https://raw.githubusercontent.com/python/cpython/v3.12.3/Doc/c-api/' + name + '.rst'
           for name in ('exceptions', 'init', 'module', 'sys', 'long')}
SOURCES['pep-0475'] = 'https://raw.githubusercontent.com/python/peps/main/peps/pep-0475.rst'

def acquire(item):
    name, url = item
    with urllib.request.urlopen(url, timeout=25) as response:
        data = response.read(1048577)
        assert len(data) <= 1048576
        final = response.url
    data.decode('utf-8')
    with (BASE / (name + '.rst')).open('xb') as stream:
        stream.write(data)
    return dict(path=name + '.rst', url=url, finalUrl=final, bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(), lfLines=data.count(b'\n'),
                coverage='unread-at-acquisition')

with ThreadPoolExecutor(max_workers=4) as pool:
    rows = list(pool.map(acquire, SOURCES.items()))
with (BASE / 'acquisition.json').open('x') as stream:
    json.dump(dict(sources=rows, acquiredCodeExecuted=False), stream, indent=2)
    stream.write('\n')
print(json.dumps(rows))

"""Acquire three fixed GCC 7.3.0 upstream source files as data only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
FILES = {'gcc.c': 'gcc/gcc.c', 'collect2.c': 'gcc/collect2.c', 'BASE-VER': 'gcc/BASE-VER'}
records = []
for name, source in FILES.items():
    url = 'https://gcc.gnu.org/cgit/gcc/plain/' + source + '?h=releases/gcc-7.3.0'
    with urlopen(Request(url, headers={'User-Agent': 'HMS bounded source review'}), timeout=30) as response:
        data = response.read(2 * 1024 * 1024 + 1)
        if response.status != 200 or len(data) > 2 * 1024 * 1024:
            raise RuntimeError('Unexpected source response')
        if (name == 'BASE-VER' and data.strip() != b'7.3.0') or (name != 'BASE-VER' and not data.startswith(b'/*')):
            raise RuntimeError('Unexpected source content')
        metadata = {'source': source, 'url': url, 'final_url': response.url,
                    'status': response.status, 'headers': dict(response.headers)}
    with (HERE / name).open('xb') as target:
        target.write(data)
    metadata.update(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    records.append(metadata)
with (HERE / 'acquisition.json').open('x') as target:
    json.dump({'schema': 'hms-gcc-plugin-lookup-source-acquisition/1',
               'recorded_at': datetime.now(timezone.utc).isoformat(),
               'files': records, 'compiler_or_acquired_source_executed': False,
               'scope': 'Upstream GCC release tag; not proof of byte-identical downstream AVR build source.'},
              target, indent=2, sort_keys=True)
    target.write('\n')
print(json.dumps([{'path': row['path'], 'bytes': row['bytes'], 'sha256': row['sha256']} for row in records]))

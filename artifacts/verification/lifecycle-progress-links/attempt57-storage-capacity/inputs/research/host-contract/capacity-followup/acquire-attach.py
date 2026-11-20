"""Retain the bounded official ATTACH reference without executing its content."""
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request
from bs4 import BeautifulSoup

base = Path(__file__).resolve().parent
url = 'https://sqlite.org/lang_attach.html'
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
request = urllib.request.Request(url, headers={'User-Agent': 'HMS-research/1.0'})
with urllib.request.urlopen(request, timeout=30) as response:
    body = response.read(2 * 1024 * 1024 + 1)
    assert response.status == 200 and len(body) <= 2 * 1024 * 1024
    final_url, headers = response.url, dict(response.headers)
with (base / 'raw/attach.html').open('xb') as stream:
    stream.write(body)
soup = BeautifulSoup(body, 'html.parser')
visuals = [dict(kind=node.name, source=node.get('src'),
                text=node.get_text(' ', strip=True)[:4096])
           for node in soup.find_all(['svg', 'img'])]
for node in soup.find_all(['script', 'style']):
    node.decompose()
extracted = '\n'.join(line.strip() for line in soup.get_text('\n').splitlines()
                      if line.strip()) + '\n'
with (base / 'text/attach.txt').open('x') as stream:
    stream.write(extracted)
record = dict(id='attach', url=url, finalUrl=final_url, retrievedAt=started,
              status=200, headers=headers, rawPath='raw/attach.html',
              rawBytes=len(body), rawSha256=hashlib.sha256(body).hexdigest(),
              textPath='text/attach.txt', textBytes=len(extracted.encode()),
              textSha256=hashlib.sha256(extracted.encode()).hexdigest(),
              lines=len(extracted.splitlines()), visuals=visuals,
              readingStatus='acquired-not-yet-read', acquiredContentExecuted=False)
with (base / 'metadata/attach.json').open('x') as stream:
    stream.write(json.dumps(record, indent=2) + '\n')
print(json.dumps({key: record[key] for key in ('id', 'rawBytes', 'lines', 'rawSha256')}))

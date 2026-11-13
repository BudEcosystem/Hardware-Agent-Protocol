"""Retain bounded official SQLite documentation; execute no acquired content."""
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
SOURCES = [('limits','https://sqlite.org/limits.html'),
    ('transactions','https://sqlite.org/lang_transaction.html'),
    ('pragmas','https://sqlite.org/pragma.html'),
    ('tempfiles','https://sqlite.org/tempfiles.html'),
    ('dbstat','https://sqlite.org/dbstat.html')]
for directory in ('raw','text','metadata'):
    (BASE / directory).mkdir(exist_ok=True)
rows = []
for name, url in SOURCES:
    request = urllib.request.Request(url, headers={'User-Agent':'HMS-research/1.0'})
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(2*1024*1024 + 1)
        assert response.status == 200 and len(body) <= 2*1024*1024
        final_url = response.url
        headers = dict(response.headers)
    raw = BASE / 'raw' / (name + '.html')
    with raw.open('xb') as stream: stream.write(body)
    soup = BeautifulSoup(body, 'html.parser')
    visuals = [dict(kind=node.name, source=node.get('src'), identifier=node.get('id'),
                    text=node.get_text(' ',strip=True)[:4096]) for node in soup.find_all(['svg','img'])]
    for node in soup.find_all(['script','style']): node.decompose()
    text = '\n'.join(line.strip() for line in soup.get_text('\n').splitlines() if line.strip()) + '\n'
    text_path = BASE / 'text' / (name + '.txt')
    with text_path.open('x') as stream: stream.write(text)
    row = dict(id=name,url=url,finalUrl=final_url,retrievedAt=started,status=200,headers=headers,
        rawPath=raw.relative_to(BASE).as_posix(),rawBytes=len(body),rawSha256=hashlib.sha256(body).hexdigest(),
        textPath=text_path.relative_to(BASE).as_posix(),textBytes=len(text.encode()),
        textSha256=hashlib.sha256(text.encode()).hexdigest(),lines=len(text.splitlines()),visuals=visuals,
        readingStatus='acquired-not-yet-read',acquiredContentExecuted=False)
    with (BASE/'metadata'/(name+'.json')).open('x') as stream: stream.write(json.dumps(row,indent=2)+'\n')
    rows.append(row)
    print(json.dumps({key:row[key] for key in ('id','rawBytes','lines','rawSha256','visuals')}),flush=True)
with (BASE/'acquisition.json').open('x') as stream: stream.write(json.dumps(rows,indent=2)+'\n')

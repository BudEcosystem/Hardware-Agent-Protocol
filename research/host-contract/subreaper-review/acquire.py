"""Retain primary Linux manual pages as data; execute no acquired content."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.request

HERE = Path(__file__).resolve().parent
PAGES = ['PR_SET_CHILD_SUBREAPER.2const', 'PR_GET_CHILD_SUBREAPER.2const', 'prctl.2']


class ManualText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.out = []
        self.sections = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('pre', 'h1', 'h2'):
            self.depth += 1
            self.sections += tag == 'pre'
            self.out.append('\n')

    def handle_endtag(self, tag):
        if tag in ('pre', 'h1', 'h2'):
            assert self.depth > 0
            self.depth -= 1
            self.out.append('\n')

    def handle_data(self, data):
        if self.depth:
            self.out.append(data)


def obtain(page):
    url = 'https://man7.org/linux/man-pages/man2/' + page + '.html'
    request = urllib.request.Request(url, headers={'User-Agent': 'HMS-primary-source-research/1'})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(1024 * 1024 + 1)
        assert response.status == 200 and len(raw) <= 1024 * 1024
        final_url = response.url
        content_type = response.headers.get('Content-Type')
    parser = ManualText()
    parser.feed(raw.decode('utf-8'))
    parser.close()
    assert parser.depth == 0 and parser.sections >= 8
    text = ''.join(parser.out).encode('utf-8')
    paths = [(HERE / 'raw' / (page + '.html'), raw), (HERE / 'text' / (page + '.txt'), text)]
    rows = []
    for path, body in paths:
        with path.open('xb') as stream:
            stream.write(body)
        rows.append(dict(path=str(path.relative_to(HERE)), bytes=len(body),
                         sha256=hashlib.sha256(body).hexdigest()))
    return dict(page=page, url=url, finalUrl=final_url, contentType=content_type,
                retrievedAt=datetime.now(timezone.utc).isoformat(), files=rows,
                extraction='All h1/h2 headings and all preformatted manual blocks in document order; navigation/footer chrome excluded.',
                preformattedBlocks=parser.sections, extractedLfLines=text.count(b'\n'),
                acquiredCodeExecuted=False, readingStatus='unread')


def main():
    assert not (HERE / 'manifest.json').exists()
    for name in ('raw', 'text'):
        (HERE / name).mkdir(exist_ok=False)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(obtain, PAGES))
    with (HERE / 'manifest.json').open('x') as stream:
        json.dump(dict(sources=results, acquiredCodeExecuted=False), stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps([dict(page=r['page'], bytes=r['files'][0]['bytes'], lines=r['extractedLfLines']) for r in results]))


if __name__ == '__main__':
    main()

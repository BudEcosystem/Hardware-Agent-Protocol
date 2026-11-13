"""Acquire two fixed official manual chapters as inert, bounded source data."""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import urllib.request

HERE = Path(__file__).resolve().parent
BASE = 'https://gcc.gnu.org/onlinedocs/gcc-7.3.0/gcc/'
LIMIT = 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Unexpected redirect: ' + newurl)


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('head', 'script', 'style'):
            self.hidden += 1
        if not self.hidden and tag in ('p','div','h1','h2','h3','h4','h5','h6','li','dt','dd','pre','br','hr','tr'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('head', 'script', 'style'):
            self.hidden -= 1
        if not self.hidden and tag in ('p','div','h1','h2','h3','h4','h5','h6','li','dt','dd','pre','tr'):
            self.parts.append('\n')
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def main():
    metadata = {'purpose': 'Official GCC7.3.0 chapter acquisition; no acquired content executed',
        'startedAt': datetime.now(timezone.utc).isoformat(),
        'limits': {'requests': 2, 'redirectsAllowed': 0, 'bodyBytesPerRequest': LIMIT,
                   'socketTimeoutSeconds': 20, 'acceptEncoding': 'identity'},
        'extraction': 'HTMLParser character references decoded; head/script/style excluded; block boundaries and source newlines preserved; horizontal whitespace collapsed; blank lines removed. All body text retained in document order, not a relevance filter.',
        'scriptSha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'sources': []}
    opener = urllib.request.build_opener(NoRedirect())
    for name in ('Optimize-Options', 'Developer-Options'):
        url = BASE + name + '.html'
        request = urllib.request.Request(url, headers={'Accept-Encoding':'identity',
            'User-Agent':'HMS-source-review/1.0'})
        with opener.open(request, timeout=20) as response:
            assert response.status == 200 and response.url == url
            data = response.read(LIMIT + 1)
            assert len(data) <= LIMIT
            headers = dict(response.headers.items())
            assert response.headers.get_content_type() == 'text/html'
            encoding = response.headers.get_content_charset() or 'utf-8'
        parser = Text(); parser.feed(data.decode(encoding)); parser.close()
        assert parser.hidden == 0
        lines = [re.sub(r'[^\S\n]+', ' ', line).strip()
                 for line in ''.join(parser.parts).splitlines()]
        lines = [line for line in lines if line]
        text = ('\n'.join(lines) + '\n').encode('utf-8')
        with (HERE/(name+'.html')).open('xb') as f:
            f.write(data)
        with (HERE/(name+'.txt')).open('xb') as f:
            f.write(text)
        metadata['sources'].append({'url': url, 'finalUrl': url, 'httpStatus':200,
            'acquiredAt':datetime.now(timezone.utc).isoformat(), 'responseHeaders':headers,
            'html':name+'.html', 'htmlBytes':len(data), 'htmlSha256':sha256(data).hexdigest(),
            'text':name+'.txt', 'textBytes':len(text), 'textSha256':sha256(text).hexdigest(),
            'textLines':len(lines), 'encoding':encoding})
    metadata['finishedAt'] = datetime.now(timezone.utc).isoformat()
    with (HERE/'acquisition.json').open('x') as f:
        json.dump(metadata,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps([{'text':s['text'],'lines':s['textLines'],'bytes':s['textBytes']}
                      for s in metadata['sources']]))


if __name__ == '__main__':
    main()

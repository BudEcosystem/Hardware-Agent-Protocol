"""Reproduce the retained prose extraction; acquired scripts are never executed."""
from html.parser import HTMLParser


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        if tag in ('h1', 'h2', 'h3', 'p', 'li', 'pre', 'br', 'tr', 'div'):
            self.out.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip -= 1
        if tag in ('h1', 'h2', 'h3', 'p', 'li', 'pre', 'tr', 'div'):
            self.out.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def extract(body):
    parser = Text()
    parser.feed(body.decode('utf-8'))
    return ('\n'.join(line.strip() for line in ''.join(parser.out).splitlines() if line.strip())+'\n').encode('utf-8')

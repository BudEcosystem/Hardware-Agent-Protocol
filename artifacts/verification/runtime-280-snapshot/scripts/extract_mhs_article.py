#!/usr/bin/env python3
"""Recover text in expanded MHS article panels from archived Next.js Flight data.

Site-specific archive extractor; does not execute embedded JavaScript. It retains
text order inside payload fields but is not a visual/figure/video completeness proof.
"""
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1] / 'research/mhs'
soup = BeautifulSoup((ROOT / 'raw/anthropic-mhs.html').read_bytes(), 'html.parser')
chunks = []
for script in soup.find_all('script'):
    content = script.get_text()
    prefix = 'self.__next_f.push('
    if content.startswith(prefix):
        fields = json.loads(content[len(prefix):-1])
        if len(fields) > 1 and isinstance(fields[1], str):
            chunks.append(fields[1])
flight = ''.join(chunks)
(ROOT / 'text/anthropic-mhs-flight.txt').write_text(flight)
raw = flight.encode()
longs = {}
for match in re.finditer(rb'([0-9a-f]+):T([0-9a-f]+),', raw):
    longs['$' + match[1].decode()] = raw[match.end():match.end() + int(match[2], 16)].decode()
texts = []
for field in re.findall(r'"text":("(?:[^"\\]|\\.)*")', flight):
    value = json.loads(field)
    value = longs.get(value, value)
    if value not in texts:
        texts.append(value)
(ROOT / 'text/anthropic-mhs-complete-content.txt').write_text('\n'.join(texts) + '\n')
print(f'Extracted {len(texts)} unique content fields; inspect reading coverage separately.')

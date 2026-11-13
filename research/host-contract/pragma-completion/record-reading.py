"""Record a completed prose/markup reading; never execute acquired content."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
PRIOR = BASE.parent / 'capacity-followup'
raw = (PRIOR / 'raw/pragmas.html').read_bytes()
body = (PRIOR / 'text/pragmas.txt').read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'af75d7d7ab00c29e6eea98618cb1259a3919c308af60a6173215bf9798706034'
assert hashlib.sha256(body).hexdigest() == 'd0bb67f0235ce56a61f6803cfe38ff9b19f1a9fa82577a48d6b5f25317b3a38e'
assert body.count(b'\n') == 2688
ranges = [[1,230], [231,480], [481,730], [731,980], [981,1230],
          [1231,1480], [1481,1730], [1731,1980], [1981,2105],
          [2106,2230], [2231,2400], [2401,2540], [2541,2688]]
assert [n for a,b in ranges for n in range(a,b+1)] == list(range(1,2689))
svgs = re.findall(rb'<svg\b.*?</svg>', raw, re.S)
assert len(svgs) == 3
folder = BASE / 'diagrams'; folder.mkdir(exist_ok=False)
diagrams = []
for name, wire in zip(('pragma-stmt', 'pragma-value', 'signed-number'), svgs):
    root = ET.fromstring(wire)
    for element in root.iter():
        assert element.tag.rsplit('}', 1)[-1] in {'svg','circle','polygon','path','text'}
        assert all(not key.lower().startswith('on') and not key.endswith('href') for key in element.attrib)
        assert all('url(' not in value.lower() for value in element.attrib.values())
    path = folder / (name + '.svg')
    with path.open('xb') as stream: stream.write(wire + b'\n')
    diagrams.append(dict(path=path.relative_to(BASE).as_posix(), bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        markupAndBranchPathsRead=True, renderedVisualInspection=False))
receipt = dict(sourceUrl='https://sqlite.org/pragma.html',
    retainedRaw='../capacity-followup/raw/pragmas.html', rawSha256=hashlib.sha256(raw).hexdigest(),
    retainedText='../capacity-followup/text/pragmas.txt', textSha256=hashlib.sha256(body).hexdigest(),
    totalLFLines=2688, readRanges=ranges, uniqueLinesRead=2688, proseComplete=True,
    previousSelectedLines=251, newlyCoveredUniqueLines=2437,
    diagrams=diagrams, decorativeBannerExcluded=True, linkedReferencesIncluded=False,
    acquiredContentExecuted=False, runtimeExperimentsPerformed=False,
    widerResearchComplete=False)
with (BASE / 'reading.json').open('x') as stream:
    json.dump(receipt, stream, indent=2); stream.write('\n')
print(json.dumps(dict(proseLines=2688, diagramMarkupRead=3, renderedVisualInspection=False)))

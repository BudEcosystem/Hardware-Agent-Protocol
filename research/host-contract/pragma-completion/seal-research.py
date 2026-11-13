"""Seal the actual retained-page reading and its visual-review evidence."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
assert not (BASE/'index.json').exists()
reading=read(BASE/'reading.json'); visual=read(BASE/'visual-review.json')
assert reading['proseComplete'] and reading['uniqueLinesRead']==reading['totalLFLines']==2688
assert [n for a,b in reading['readRanges'] for n in range(a,b+1)]==list(range(1,2689))
assert sha(BASE/reading['retainedRaw'])==reading['rawSha256']
assert sha(BASE/reading['retainedText'])==reading['textSha256']
assert visual['readingReceiptSha256']==sha(BASE/'reading.json')
assert visual['renderedImagesInspected']==3 and visual['retainedPageProseAndInlineDiagramsComplete']
for row in reading['diagrams']+visual['images']:
    path=BASE/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
files=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file(): files.append(dict(path=path.relative_to(BASE).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
with (BASE/'index.json').open('x') as stream:
    json.dump(dict(scope='Retained SQLite PRAGMA prose and three inline diagrams fully read; wider research remains incomplete',
        proseLFLines=2688,newlyCoveredUniqueLines=2437,inlineDiagramsVisuallyRead=3,
        acquiredCodeExecuted=False,linkedReferencesIncluded=False,files=files),stream,indent=2)
    stream.write('\n')
print(json.dumps(dict(files=len(files),indexSha256=sha(BASE/'index.json'))))

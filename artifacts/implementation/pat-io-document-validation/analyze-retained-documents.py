"""Count exact repeated BLOB validation inputs from a sealed complete capture.

No project import, database opening, execution, timing claim or source mutation.
"""
from collections import OrderedDict
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd()
PREVIOUS = ROOT/'artifacts/implementation/pat-io-service-runs'
BASE = ROOT/'artifacts/implementation/pat-io-document-validation'
INDEX_PIN = '15116241febffbf79fe7d56278f1dcc77ce20c9ad62f38ac3f7ccddca70a4fe1'
DEST = 'attempt07-passed-authority-owned'
MAX_ENTRIES, MAX_BYTES = 64, 128*1024

def sha(data):
    return hashlib.sha256(data).hexdigest()

assert sha((PREVIOUS/'results/index.json').read_bytes()) == INDEX_PIN
indexed = {row['path']:row for row in json.loads((PREVIOUS/'results/index.json').read_bytes())['files']}
read_files = {}

def read(path):
    data = path.read_bytes()
    name = path.relative_to(PREVIOUS/'results').as_posix()
    row = indexed[name]
    assert len(data) == row['bytes'] and sha(data) == row['sha256']
    read_files[name] = row
    return json.loads(data)

folder = PREVIOUS/'results'/DEST
audit = read(folder/'process-audit.json')
assert audit['groupStatus'] == 'captured' and audit['completedCases'] == 30 and audit['states'] == 26
target = read(folder/'attempt/harness/targets.json')['targets'][0]
work = folder/'attempt/scratch'/target.rsplit('.',1)[1]
output = work/'supervisor'/audit['attemptId']/'output'
cases = []
for case in sorted(output.glob('case-*')):
    directory = case/'configuration'
    if not directory.exists():
        continue
    documents = []
    for path in sorted(directory.glob('*.json')):
        document = read(path)
        if document['kind'] == 'snapshot':
            documents.append(document['value'])
    cache = OrderedDict()
    cache_bytes = peak_bytes = peak_entries = hits = misses = input_bytes = repeated_bytes = 0
    for snapshot in documents:
        for table in snapshot['tables']:
            for reference in table['pages']:
                path = directory/reference['path']
                page = read(path)
                row = read_files[path.relative_to(PREVIOUS/'results').as_posix()]
                assert row['bytes'] == reference['bytes'] and row['sha256'] == reference['sha256']
                assert page['kind'] == 'table_page' and page['value']['table'] == table['table']
                for cells in page['value']['rows']:
                    for cell in cells:
                        if cell['type'] != 'blob-utf8':
                            continue
                        value = cell['value'].encode('utf-8')
                        assert 0 < len(value) <= 65536
                        input_bytes += len(value)
                        if value in cache:
                            hits += 1
                            repeated_bytes += len(value)
                            cache.move_to_end(value)
                            continue
                        misses += 1
                        while cache and (len(cache) >= MAX_ENTRIES or cache_bytes+len(value) > MAX_BYTES):
                            old, _ = cache.popitem(last=False)
                            cache_bytes -= len(old)
                        cache[value] = True
                        cache_bytes += len(value)
                        peak_bytes, peak_entries = max(peak_bytes, cache_bytes), max(peak_entries, len(cache))
    cases.append(dict(case=case.name, snapshots=len(documents), validationInputs=hits+misses,
        inputBytes=input_bytes, hypotheticalExactHits=hits, hypotheticalMisses=misses,
        repeatedBytes=repeated_bytes, peakRetainedBytes=peak_bytes, peakEntries=peak_entries))
assert len(cases) == 26
totals = {key:sum(row[key] for row in cases) for key in
          ('snapshots','validationInputs','inputBytes','hypotheticalExactHits','hypotheticalMisses','repeatedBytes')}
report = dict(scope='Exact-byte duplication analysis of a sealed complete finite-I/O capture; not a timing benchmark or an implemented cache.',
    sourceResultsIndexSha256=INDEX_PIN, sourceAttempt=DEST, target=target,
    perEngineProposal=dict(maxEntries=MAX_ENTRIES, maxRetainedBytes=MAX_BYTES),
    totals=totals, cases=cases, sourceFilesChecked=list(read_files.values()),
    databaseOrAuthorityReadsCached=False, acquiredCodeExecuted=False, physicalEffectsPerformed=False,
    causalityOfDeadlineEstablished=False)
path = BASE/'analysis/retained-document-duplication.json'
with path.open('x') as stream:
    stream.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(**totals, cases=len(cases), sourceFilesChecked=len(read_files),
    maximumPerEngineBytes=max(row['peakRetainedBytes'] for row in cases),
    maximumPerEngineEntries=max(row['peakEntries'] for row in cases))))

"""Verify retained finite results and seal this research/documentation checkpoint."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
RESEARCH = ROOT / 'research/host-contract/capacity-followup'
CHECKPOINT = ROOT / 'artifacts/verification/lifecycle-progress-links/attempt57-storage-capacity'

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')

def seal(directory, scope):
    assert not (directory / 'index.json').exists()
    rows = []
    for path in sorted(directory.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():
            rows.append(dict(path=path.relative_to(directory).as_posix(),
                             bytes=path.stat().st_size, sha256=sha(path)))
    write(directory / 'index.json', dict(scope=scope, files=rows))
    return len(rows)

assert not CHECKPOINT.exists()
for folder, expected in (
    ('source01', 'ca772b3097cfcc6c8769652c596770f5824b4384da32818d7c81724360c4d737'),
    ('source02', '04f84c166d8540f3f9ec74bd3efb4b9babdf4f562328dda635b4f5e833f140b7')):
    path = BASE / folder / 'index.json'
    assert sha(path) == expected
    for row in read(path)['files']:
        target = path.parent / row['path']
        assert target.stat().st_size == row['bytes'] and sha(target) == row['sha256']
failed = read(BASE / 'attempts/attempt01/result.json')
passed = read(BASE / 'attempts/attempt02/result.json')
assert failed['status'] == 'failed' and failed['exitCode'] == 1
assert passed['status'] == 'passed' and passed['exitCode'] == 0 and passed['errors'] == []
for name, value in (('attempt01', failed), ('attempt02', passed)):
    assert value['sourcesUnchanged'] and value['scratchRetained'] and value['childState'] == 'exited'
    assert (value['timeoutSeconds'], value['maxSingleFileBytes'], value['maxScratchBytes']) == (30, 1048576, 8388608)
    assert value['maxOutputBytesPerStream'] == 65536
    for row in value['files']:
        path = BASE / 'attempts' / name / 'scratch' / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
observed = read(BASE / 'attempts/attempt02/stdout.log')
assert observed['status'] == 'passed' and len(observed['cases']) == 5
assert observed['files'] == passed['files'] and observed['sqliteVersion'] == '3.45.1'
assert (BASE / 'attempts/attempt02/stderr.log').read_bytes() == b''
assert b'sqlite3.DatabaseError: not authorized' in (BASE / 'attempts/attempt01/stderr.log').read_bytes()
origin = read(BASE / 'source02/origin.json')
assert not origin['productionChanges'] and not origin['boundsChanged'] and not origin['auditRerun']
before = (BASE / 'source01/probe.py').read_text()
after = before.replace("    db.execute('ATTACH DATABASE ? AS bulk', (str(PATHS['bulk.db']),))",
    "    attach_literal = \"'\" + str(PATHS['bulk.db']).replace(\"'\", \"''\") + \"'\"\n    db.execute('ATTACH DATABASE ' + attach_literal + ' AS bulk')")
assert after == (BASE / 'source02/probe.py').read_text()
assert (BASE / 'source01/run.py').read_text().replace('attempts/attempt01', 'attempts/attempt02') == (BASE / 'source02/run.py').read_text()
assert sha(BASE / 'source01/audit-allocation.py') == sha(BASE / 'source02/audit-allocation.py')
audit = read(BASE / 'allocation.json')
assert audit['status'] == 'passed' and audit['originalAndCopyUnchanged']
assert len(audit['ownerLocksHeld']) == 56 and audit['sourceIndexSha256'] == failed['sourceIndexSha256']
assert audit['observation']['compactEvidenceBtreeBytes'] == 15440896
assert audit['observation']['otherBtreeBytes'] == 758784 and audit['observation']['freeBytes'] == 0
previous = ROOT / 'artifacts/implementation/pat-io-definition-build'
assert sha(previous / 'index.json') == 'c38169d02e04a3fbb72a50ea4ccd285683ed79834da2e9d9cd32fe5b10f1fe02'
assert sha(previous / 'implementation01/index.json') == '7a52bf04800bde161cfb778fca0da5cec996468fe03d9944902e73e11c6817cc'
for row in read(previous / 'implementation01/index.json')['files']:
    path = ROOT / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
reading = read(RESEARCH / 'reading.json')
assert len(reading['sources']) == 8 and reading['readLines'] == 2449
for row in reading['sources']:
    meta = read(RESEARCH / 'metadata' / (row['id'] + '.json'))
    assert sha(RESEARCH / meta['rawPath']) == row['rawSha256'] == meta['rawSha256']
    assert sha(RESEARCH / meta['textPath']) == row['textSha256'] == meta['textSha256']
links = read(ROOT / 'artifacts/verification/project-links.json')
assert not links['missing'] and sha(ROOT / 'scripts/check_project_links.py') == links['checker_sha256']
for row in links['files']:
    assert sha(ROOT / row['path']) == row['sha256']
write(BASE / 'RESULTS.json', dict(
    scope='Bounded host-only SQLite capacity research; no production behavior added',
    passingProbeScopes=1, failedProbeScopes=1, passingExperiments=5,
    passingReadOnlyAllocationAudits=1, originalAndCopyUnchangedAtAudit=True,
    retainedOwnerLocksAtAudit=56, sqliteVersion=observed['sqliteVersion'],
    evidenceBtreeBytes=15440896, otherAuthorityBtreeBytes=758784, freePages=0,
    authorityFileBytes=16199680, originalFileCeiling=16777216, headroomBytes=577536,
    successfulScratchBytes=sum(row['bytes'] for row in passed['files']),
    source01IndexSha256=failed['sourceIndexSha256'], source02IndexSha256=passed['sourceIndexSha256'],
    originalFailureRetained=True, originalProductionInputsUnchanged=True,
    acquiredSources=8, readLines=2449, fullMediaReadingClaimed=False,
    productionStorageSeparationImplemented=False, aggregateQuotaEnforced=False,
    physicalCapacityReserved=False, publicQualificationMounted=False,
    physicalEffects=False, acquiredCodeExecuted=False, goalStatus='active'))
research_count = seal(RESEARCH, 'Eight official SQLite pages with bounded acquisition and exact partial/full-text reading receipts; media/PRAGMA gaps retained')
stage_count = seal(BASE, 'Five passing finite host experiments plus one retained guard failure; original authority allocation audit; proposed independent storage profile, not production capacity enforcement')
selected = {
    ROOT / 'README.md', ROOT / 'PROGRESS.md', ROOT / 'docs/control-storage.md',
    ROOT / 'docs/io-driver-hub-control.md', ROOT / 'docs/prompt-to-pat.md',
    ROOT / 'scripts/check_project_links.py', ROOT / 'artifacts/verification/project-links.json',
    ROOT / 'artifacts/verification/lifecycle-progress-links/attempt56-io-definition-build/index.json'}
for folder in (BASE, RESEARCH):
    selected.update(path for path in folder.iterdir() if path.is_file())
selected.update(BASE.glob('source*/index.json'))
copies = []
for source in sorted(selected):
    relative = source.relative_to(ROOT)
    destination = CHECKPOINT / 'inputs' / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    body = source.read_bytes()
    with destination.open('xb') as stream:
        stream.write(body)
    assert destination.read_bytes() == source.read_bytes() == body
    copies.append(dict(source=relative.as_posix(), copy=destination.relative_to(ROOT).as_posix(),
                       bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
write(CHECKPOINT / 'index.json', dict(scope='Storage capacity design and bounded research; full HMS goal remains active',
    stageIndexSha256=sha(BASE / 'index.json'), researchIndexSha256=sha(RESEARCH / 'index.json'),
    stageFiles=stage_count, researchFiles=research_count, passingExperiments=5, failedScopesRetained=1,
    readOnlyAllocationAuditsPassed=1, readLines=2449, productionChanges=False,
    goalStatus='active', markdownFiles=links['project_markdown_files'], localLinks=links['local_links_checked'],
    missing=[], files=copies))
print(json.dumps(dict(stageFiles=stage_count, stageIndexSha256=sha(BASE / 'index.json'),
    researchFiles=research_count, researchIndexSha256=sha(RESEARCH / 'index.json'),
    checkpointFiles=len(copies), checkpointIndexSha256=sha(CHECKPOINT / 'index.json'), goalStatus='active')))

"""Recompute source observations and seal this assessment without runtime effects."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import unquote

import inspect_sources as inspection
from extract import extract

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def inventory(base):
    rows = []
    for path in sorted(base.rglob('*')):
        assert not path.is_symlink(), path
        if path.is_file() and path != base/'index.json':
            rows.append({'path':str(path.relative_to(base)), 'bytes':path.stat().st_size, 'sha256':sha(path)})
    return rows


def main():
    assert not (HERE/'AUDIT.json').exists() and not (HERE/'index.json').exists()
    prior = inspection.PRIOR
    assert sha(prior/'index.json') == inspection.PRIOR_HASH
    prior_rows = inventory(prior)
    assert prior_rows == read(prior/'index.json')['files'] and len(prior_rows) == 857
    assert sha(inspection.BASE) == inspection.BASE_HASH
    baseline = read(inspection.BASE)
    assert baseline['passed'] and baseline['tests'] == 866 and len(baseline['files']) == 244
    assert all(sha(ROOT/r['path']) == r['sha256'] for r in baseline['files'])
    inputs = read(HERE/'inputs.json')['files']
    frozen = HERE/'frozen-inputs'
    assert len(inputs) == 124
    assert {r['path'] for r in inputs} == {str(p.relative_to(ROOT)) for directory in ['hms','hms_qualification']
        for p in (ROOT/directory).rglob('*') if p.suffix in {'.py','.c'} and '__pycache__' not in p.parts}
    modules = []
    for row in inputs:
        assert sha(ROOT/row['path']) == sha(frozen/row['path']) == row['sha256']
        if row['path'].endswith('.py'):
            source = (frozen/row['path']).read_text()
            visitor = inspection.Calls(source); visitor.visit(ast.parse(source))
            modules.append({'path':row['path'], 'fileCallCandidates':visitor.sites,
                            'sqlCallerScopes':sorted(visitor.sql_callers), 'pragmaCalls':visitor.pragmas,
                            'supervisorRootConsumers':visitor.root_consumers})
    assert len(modules) == 123 and modules == read(HERE/'call-inventory.json')['modules']
    review = read(HERE/'site-review.json')
    candidates = [{'path':m['path'],**s} for m in modules for s in m['fileCallCandidates']]
    assert len(candidates) == 156
    assert candidates == [{k:v for k,v in r.items() if k != 'classification'} for r in review['sites']]
    assert dict(Counter(r['classification'] for r in review['sites'])) == review['counts']
    assert review['inventorySha256'] == sha(HERE/'call-inventory.json')
    result = read(HERE/'RESULTS.json')
    assert result['status'] == 'source-contract-reviewed' and not result['publicRuntimeChanged']
    assert result['directSqliteConnections'] == [r for r in candidates if r['target']=='sqlite3.connect']
    assert len(result['directSqliteConnections']) == 5
    observations = read(HERE/'observation-inputs.json')
    for row in observations['files']:
        assert sha(ROOT/row['path']) == sha(frozen/row['frozen']) == row['sha256']
    historical_index = read(frozen/'observation-01-index.json')['files']
    retained = [r for r in historical_index if r['path'].startswith(inspection.PREFIX)]
    assert retained == observations['historicalIndexRows'] and len(retained) == 4266
    assert sum(r['bytes'] for r in retained) == 35502635
    history = read(frozen/'observation-00-RESULTS.json')
    assert history['actualScopePassed'] and history['requestedCases'] == history['caseManifests'] == 30
    assert history['rawFiles'] == len(retained) and history['rawBytes'] == sum(r['bytes'] for r in retained)
    assert history['producerImageFiles'] == result['historicalProducerImageFiles'] == 267
    assert history['vaultImportObservation']['originalOutputClosure']['fileCount'] == result['historicalOutputFiles'] == 3936
    for group in result['historicalLayout']:
        prefix = inspection.PREFIX+group['domainAtTimeOfRun']+'/'
        rows = [r for r in retained if r['path'].startswith(prefix)]
        names = [r['path'][len(prefix):] for r in rows]
        assert group['regularFiles'] == len(rows) and group['logicalBytes'] == sum(r['bytes'] for r in rows)
        assert group['inferredNonRootDirectories'] == len({str(q) for n in names for q in Path(n).parents if str(q)!='.'})
        assert group['maxRelativeDepth'] == max(len(Path(n).parts) for n in names)
        assert group['maxComponentBytes'] == max(len(part.encode()) for n in names for part in Path(n).parts)
    launch = read(frozen/'original-launch.json')
    assert result['historicalOriginalLimits'] == launch['request']['limits']
    assert result['historicalGroupLimits'] == launch['request']['groupLimits']
    assert [r['bytes'] for r in result['nameIncompatibilities']] == [69,86,92,83,94]
    assert all(len(r['name']) == r['bytes'] and not r['acceptedByCurrentFlatNameRule'] and
               re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}',r['name']) is None for r in result['nameIncompatibilities'])
    reading = read(HERE/'reading.json')['files']
    full = [r for r in reading if r['fullFileReviewed'] and not r['path'].startswith('artifacts/')]
    assert len(full) == 14 and sum(r['lfLines'] for r in full) == 2329
    for row in reading:
        path = ROOT/row['path']; body = path.read_bytes()
        assert sha(path) == row['sha256'] and body.count(b'\n') == row['lfLines']
        assert all(1 <= a <= b <= len(body.splitlines()) for a,b in row['reviewedRanges'])
        if row['fullFileReviewed']:
            assert row['reviewedRanges'] == [[1,len(body.splitlines())]]
    acquisition = read(HERE/'sources/acquisition.json')
    assert acquisition['url'] == 'https://sqlite.org/tempfiles.html' and acquisition['status'] == 200
    for suffix in ['html','txt']:
        path = HERE/'sources'/('sqlite-tempfiles.'+suffix)
        assert sha(path) == acquisition[suffix]['sha256'] and path.stat().st_size == acquisition[suffix]['bytes']
    assert extract((HERE/'sources/sqlite-tempfiles.html').read_bytes()) == (HERE/'sources/sqlite-tempfiles.txt').read_bytes()
    assert acquisition['txt']['lfLines'] == 489
    docs = [ROOT/n for n in ['README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md']]
    docs += sorted(HERE.glob('*.md'))
    links = 0
    for doc in docs:
        for target in re.findall(r'\]\(([^)]+)\)',doc.read_text()):
            if '://' in target or target.startswith(('#','mailto:')):
                continue
            target=unquote(target.split('#',1)[0].split(' "',1)[0].strip('<>'))
            if target:
                links += 1
                path=(doc.parent/target).resolve()
                assert path.exists() or path in {HERE/'AUDIT.json',HERE/'index.json'},(doc,target)
    for path in HERE.rglob('*.py'):
        ast.parse(path.read_text())
    # This audit imports only the original AST scanner and text extractor, not HMS.
    import sys
    assert not any(n=='hms' or n.startswith(('hms.','hms_qualification')) for n in sys.modules)
    assert all(sha(ROOT/r['path']) == r['sha256'] for r in baseline['files'])
    audit = {'schema':'hms.service-storage-contract-audit/1','auditedUnix':time.time(),
             'reviewer':'primary agent only','priorIndexSha256':inspection.PRIOR_HASH,'priorFilesExact':857,
             'runtimeFilesExact':244,'previousPublicTestsPassed':866,'publicSuiteRerun':False,
             'pythonModulesParsed':123,'sourceFilesFrozen':124,'reviewedCallCandidates':156,
             'directSqliteConnections':5,'historicalIndexRows':4266,'historicalLogicalBytes':35502635,
             'fullCurrentSourceFilesRead':14,'fullCurrentSourceLfLinesRead':2329,'fullArticleRenderedLfLinesRead':489,
             'textExtractionReproduced':True,'databasesOpened':0,'newWorkerRuns':0,'runtimeImported':False,
             'publicRuntimeChanged':False,'filesystemInterfaceImplemented':False,'serviceStorageQualified':False,
             'backedControlCapacity':False,'localLinksChecked':links,'missingLinks':[],
             'documents':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in docs]}
    save(HERE/'AUDIT.json',audit)
    rows=inventory(HERE)
    save(HERE/'index.json',{'schema':'hms.exact-file-index/1','files':rows})
    assert rows==inventory(HERE)
    print(json.dumps({'indexSha256':sha(HERE/'index.json'),'indexedFiles':len(rows),'runtimeFilesExact':244,
                      'reviewedCallCandidates':156,'localLinksChecked':links},sort_keys=True))


if __name__ == '__main__':
    main()

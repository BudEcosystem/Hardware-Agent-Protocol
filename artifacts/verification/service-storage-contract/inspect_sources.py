"""Static current-source inventory; never imports HMS or opens a database."""
import ast
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
BASE_HASH = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
PRIOR = ROOT/'artifacts/verification/chunk-block-read-regressions'
PRIOR_HASH = '5edec9412acc78f47ab0a490b3edc509be31ba56278315235aaf0d65c6307c7a'
HIST = ROOT/'artifacts/implementation/pat-statement-cache'
PREFIX = 'artifacts/implementation/pat-statement-cache/harness01/attempts/attempt01-actual/scratch/test_actual_original_matrix_catalog_admission_and_cold_history/'
FILE_CALLS = {'open','mkdir','makedirs','write','write_bytes','write_text','pwrite','fsync','fdatasync',
              'truncate','ftruncate','rename','replace','unlink','remove','rmdir','rmtree','chmod',
              'fchmod','chown','fchown','link','symlink','copy','copyfile','copytree','copy2','flock',
              'memfd_create','bind','connect','mkstemp','mkdtemp','TemporaryFile','NamedTemporaryFile',
              'mmap','fallocate','posix_fallocate'}


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


class Calls(ast.NodeVisitor):
    def __init__(self, source):
        self.source = source
        self.stack = []
        self.sites = []
        self.sql_callers = set()
        self.pragmas = []
        self.root_consumers = []

    def visit_ClassDef(self, node):
        self.stack.append(node.name); self.generic_visit(node); self.stack.pop()

    def visit_FunctionDef(self, node):
        self.stack.append(node.name); self.generic_visit(node); self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        target = ast.unparse(node.func)
        leaf = target.rsplit('.', 1)[-1]
        owner = '.'.join(self.stack) or '<module>'
        if leaf in FILE_CALLS:
            self.sites.append({'line': node.lineno, 'endLine': node.end_lineno, 'owner': owner,
                               'target': target, 'expression': ast.get_source_segment(self.source, node)})
        if leaf in {'execute','executemany','executescript'}:
            self.sql_callers.add(owner)
        if any(isinstance(n, ast.Constant) and isinstance(n.value, str) and 'PRAGMA ' in n.value.upper()
               for n in node.args):
            self.pragmas.append({'line': node.lineno, 'owner': owner, 'expression': ast.unparse(node)})
        self.generic_visit(node)

    def visit_Attribute(self, node):
        value = ast.unparse(node)
        if value in {'ledger.root','ledger.fd','self.ledger.root','self.ledger.fd','supervisor_service.ledger.fd'}:
            self.root_consumers.append({'line': node.lineno, 'owner': '.'.join(self.stack), 'expression': value})
        self.generic_visit(node)


def main():
    assert sha(BASE) == BASE_HASH and sha(PRIOR/'index.json') == PRIOR_HASH
    runtime = read(BASE)
    assert len(runtime['files']) == 244
    assert all(sha(ROOT/r['path']) == r['sha256'] for r in runtime['files'])
    assert all(sha(PRIOR/r['path']) == r['sha256'] for r in read(PRIOR/'index.json')['files'])
    frozen = HERE/'frozen-inputs'
    frozen.mkdir()
    paths = sorted(p for directory in ('hms','hms_qualification') for p in (ROOT/directory).rglob('*')
                   if p.suffix in {'.py','.c'} and '__pycache__' not in p.parts)
    known = {r['path']:r['sha256'] for r in runtime['files']}
    inventory = []
    modules = []
    for source in paths:
        relative = str(source.relative_to(ROOT))
        assert relative in known and sha(source) == known[relative], relative
        dest = frozen/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
        inventory.append({'path': relative, 'bytes': dest.stat().st_size, 'sha256': sha(dest),
                          'lfLines': dest.read_bytes().count(b'\n')})
        if source.suffix == '.py':
            text = dest.read_text(); tree = ast.parse(text); visitor = Calls(text); visitor.visit(tree)
            modules.append({'path': relative, 'fileCallCandidates': visitor.sites,
                            'sqlCallerScopes': sorted(visitor.sql_callers), 'pragmaCalls': visitor.pragmas,
                            'supervisorRootConsumers': visitor.root_consumers})
    save(HERE/'inputs.json', {'schema':'hms.service-storage-inputs/1', 'runtimeReceiptSha256':BASE_HASH,
                            'priorStageIndexSha256':PRIOR_HASH, 'files':inventory})
    save(HERE/'call-inventory.json', {'schema':'hms.service-storage-call-inventory/1', 'modules':modules,
                                    'scope':'Static syntax candidates, not alias resolution or native syscall coverage.'})
    connections = [{'path':m['path'], **s} for m in modules for s in m['fileCallCandidates'] if s['target']=='sqlite3.connect']
    expected = {'hms/journal.py','hms/simulator.py','hms/synthetic_io_board.py',
                'hms_qualification/supervisor/attempt_ledger.py','hms_qualification/evidence_vault/connection.py'}
    assert len(connections) == 5 and {r['path'] for r in connections} == expected
    # Use only immutable historical JSON/index bytes. Never open retained databases.
    historical = read(HIST/'RESULTS.json'); old_index = read(HIST/'index.json')
    assert historical['actualScopePassed'] and historical['requestedCases'] == historical['caseManifests'] == 30
    retained = [r for r in old_index['files'] if r['path'].startswith(PREFIX)]
    assert len(retained) == historical['rawFiles'] == 4266
    assert sum(r['bytes'] for r in retained) == historical['rawBytes'] == 35502635
    proof_inputs = [HIST/'RESULTS.json', HIST/'index.json',
                    ROOT/'artifacts/implementation/runtime-qualification-package/inspection01.json',
                    ROOT/'artifacts/implementation/chunk-store-capacity/chunk_store.py']
    history_sources = []
    for index, source in enumerate(proof_inputs):
        dest = frozen/f'observation-{index:02d}-{source.name}'
        dest.write_bytes(source.read_bytes())
        history_sources.append({'path':str(source.relative_to(ROOT)), 'frozen':dest.name, 'sha256':sha(dest)})
    input_rows = [r for r in retained if r['path'].endswith('/input.json') and '/supervisor/' in r['path']]
    assert len(input_rows) == 1
    input_row = input_rows[0]
    assert sha(ROOT/input_row['path']) == input_row['sha256']
    launch = read(ROOT/input_row['path'])
    (frozen/'original-launch.json').write_bytes((ROOT/input_row['path']).read_bytes())
    history_sources.append({'path':input_row['path'], 'frozen':'original-launch.json', 'sha256':input_row['sha256']})
    save(HERE/'observation-inputs.json', {'files':history_sources, 'historicalIndexRows':retained,
                                       'databasesOpened':0, 'workerRerun':False})
    observed = []
    for group in ['runtime','supervisor','vault']:
        rows = [r for r in retained if r['path'].startswith(PREFIX+group+'/')]
        names = [r['path'][len(PREFIX+group+'/'):] for r in rows]
        directories = {str(parent) for name in names for parent in Path(name).parents if str(parent) != '.'}
        observed.append({'domainAtTimeOfRun':group,'regularFiles':len(rows),'logicalBytes':sum(r['bytes'] for r in rows),
                         'inferredNonRootDirectories':len(directories),
                         'maxComponentBytes':max(len(part.encode()) for name in names for part in Path(name).parts),
                         'maxRelativeDepth':max(len(Path(name).parts) for name in names)})
    adapter = (ROOT/'artifacts/implementation/chunk-store-capacity/chunk_store.py').read_text()
    assert "MAX_INODES = 16" in adapter and "MAX_HANDLES = 64" in adapter
    pattern = r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}'
    assert repr(pattern) in adapter
    samples = ['code-'+'0'*64,'synthetic-io-board-'+'0'*64+'.db',
               'synthetic-io-board-'+'0'*64+'.db.owner','simulated-plant-'+'0'*64+'.db',
               'synthetic-io-board-'+'0'*64+'.db-journal']
    incompatibilities = [{'name':s,'bytes':len(s),'acceptedByCurrentFlatNameRule':re.fullmatch(pattern,s) is not None} for s in samples]
    assert all(not r['acceptedByCurrentFlatNameRule'] for r in incompatibilities)
    result = {'schema':'hms.service-storage-assessment/1', 'status':'source-contract-reviewed',
              'pythonModulesParsed':len(modules),'sourceFilesFrozen':len(inventory),
              'fileCallCandidates':sum(len(m['fileCallCandidates']) for m in modules),
              'directSqliteConnections':connections,'historicalLayout':observed,
              'historicalOriginalLimits':launch['request']['limits'],
              'historicalGroupLimits':launch['request']['groupLimits'],
              'nameIncompatibilities':incompatibilities, 'currentFlatInodeLimit':16,
              'historicalProducerImageFiles':historical['producerImageFiles'],
              'historicalOutputFiles':historical['vaultImportObservation']['originalOutputClosure']['fileCount'],
              'runtimeFilesExact':244,'previousPublicTestsPassed':866,'databasesOpened':0,
              'runtimeImported':False,'newWorkerRuns':0,'publicRuntimeChanged':False,
              'filesystemInterfaceImplemented':False,'serviceStorageQualified':False,
              'hardQuotaEnforced':False,'backedControlCapacity':False}
    assert all(sha(ROOT/r['path']) == sha(frozen/r['path']) == r['sha256'] for r in inventory)
    assert all(sha(ROOT/r['path']) == r['sha256'] for r in runtime['files'])
    save(HERE/'RESULTS.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in {'directSqliteConnections','historicalOriginalLimits','historicalGroupLimits','nameIncompatibilities'}},sort_keys=True))


if __name__ == '__main__':
    main()

"""Freeze the actual-run fixture and adapt the previously reviewed actual runner."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
SOURCE=BASE/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-definition-build'
TEMPLATE=OLD/'harness02'
HARNESS=BASE/'harness01'
METHOD='test_actual_original_matrix_import_and_cold_vault_history'
TARGET='test_vault_original_run.VaultOriginalRunTests.'+METHOD
OLD_METHOD='test_actual_original_matrix_catalog_execution_and_historical_replay'
OLD_TARGET='test_io_recorded_catalog_process.RecordedIoCatalogProcessTests.'+OLD_METHOD
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream: stream.write(body if type(body) is bytes else body.encode())
def dump(path,value): write(path,json.dumps(value,indent=2)+'\n')

assert sha(OLD/'index.json')=='c38169d02e04a3fbb72a50ea4ccd285683ed79834da2e9d9cd32fe5b10f1fe02'
original_index=next(row for row in read(OLD/'index.json')['files'] if row['path']=='harness02/index.json')
assert sha(TEMPLATE/'index.json')==original_index['sha256']
for row in read(TEMPLATE/'index.json')['files']:
    path=TEMPLATE/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
baseline=read(SOURCE/'baseline-inputs.json')['files']; assert len(baseline)==285
for row in baseline:
    path=SOURCE/'project'/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
project=sorted(p for p in (SOURCE/'project').rglob('*') if p.is_file()); assert len(project)==286
for path in project:
    assert not path.is_symlink()
    if path.suffix=='.py': ast.parse(path.read_bytes(),filename=str(path))
assert sha(OLD/'implementation01/index.json')=='7a52bf04800bde161cfb778fca0da5cec996468fe03d9944902e73e11c6817cc'
legacy_files=[]
for row in read(OLD/'implementation01/index.json')['files']:
    path=ROOT/row['path']
    if not path.is_relative_to(OLD/'implementation01/project'): continue
    relative=path.relative_to(OLD/'implementation01/project')
    assert sha(path)==sha(SOURCE/'project'/relative)==row['sha256']; legacy_files.append(relative.as_posix())
assert len(legacy_files)==275
write(SOURCE/'README.md','# Actual original-run verification source\n\nAll 285 inherited files remain unchanged. One test adds a fresh complete 30-case worker, the real archive reader/reducer, authority-vault import, exact replay, configuration drift and cold vault reopening. All 275 files from the prior actual compact-catalog source also remain exact. Full runtime/session reopening and catalog integration remain required later; this scope does not claim them.\n')
dump(SOURCE/'source-review.json',dict(review='Primary-agent source and execution-bound review',
    productionChanged=False,inheritedFilesUnchanged=285,priorActualSourceFilesUnchanged=275,
    addedTest=TARGET,actualWorkerCount=1,workerMaxWallMs=60000,outerMaxSeconds=180,
    maxParentSqliteOpens=6,plannedSqliteOpens=5,maxSingleFileBytes=16777216,
    maxScratchBytes=268435456,maxVaultBytes=15728640,snapshotMaxMs=5000,
    initialArchiveAndReducerSubstituted=False,checkpointInstrumentationOnly=True,
    replayTrapsAppliedAfterActualImport=True,coldVaultReopen=True,
    coldRuntimeAndSupervisorReopen=False,sessionDriftTested=False,catalogIntegrated=False,
    sourceApplicationInvocations=0,physicalEffects=False,
    reviewLimit='Helpers unavailable until the recorded usage reset; no helper requested'))
files=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(SOURCE.rglob('*')) if p.is_file()]
assert len(files)==289
dump(SOURCE/'index.json',dict(scope='Unchanged authority/vault production with one actual original-run fixture',files=files))
HARNESS.mkdir()
borrowed=[]
for filename in ('run_attempt.py','attempt_child.py'):
    source=TEMPLATE/filename; original=source.read_text(); body=original
    body=body.replace(OLD_TARGET,TARGET).replace(OLD_METHOD,METHOD)
    if filename=='run_attempt.py':
        body=body.replace('7a52bf04800bde161cfb778fca0da5cec996468fe03d9944902e73e11c6817cc',sha(SOURCE/'index.json'))
        body=body.replace('artifacts/implementation/pat-io-definition-build/implementation01/','artifacts/implementation/pat-vault-original-run/implementation01/')
        body=re.sub(r'\b275\b','286',body); body=re.sub(r'\b278\b','289',body)
        body=body.replace("prefix='hms-io-definition-build-'","prefix='hms-vault-original-run-'")
    else:
        needle="valid=(path==work/'supervisor'/'attempts.db' or (path.parent==work/'runtime' and"
        assert body.count(needle)==1
        body=body.replace(needle,"valid=(path==work/'vault'/'evidence.db' or path==work/'supervisor'/'attempts.db' or (path.parent==work/'runtime' and")
        body=body.replace('Only exact authority/runtime/supervisor databases may open','Only exact authority/runtime/supervisor/vault databases may open')
        body=body.replace("or name == 'recorded_io'", "or name == 'evidence_vault' or name.startswith('evidence_vault.') or name == 'evidence_authority' or name.startswith('evidence_authority.') or name == 'recorded_io'")
    ast.parse(body)
    write(HARNESS/filename,body); write(HARNESS/'references'/filename,original)
    write(HARNESS/(filename+'.patch'),''.join(difflib.unified_diff(original.splitlines(True),body.splitlines(True),fromfile='prior-actual/'+filename,tofile='vault-actual/'+filename)))
    borrowed.append(dict(source=source.relative_to(ROOT).as_posix(),copy='references/'+filename,bytes=source.stat().st_size,sha256=sha(source)))
source=TEMPLATE/'references/approved-external-roots.json'
write(HARNESS/'references/approved-external-roots.json',source.read_bytes())
borrowed.append(dict(source=source.relative_to(ROOT).as_posix(),copy='references/approved-external-roots.json',bytes=source.stat().st_size,sha256=sha(source)))
dump(HARNESS/'borrowed-inputs.json',borrowed)
dump(HARNESS/'targets.json',dict(testCount=1,targets=[TARGET]))
write(HARNESS/'README.md','# Actual original-run scope\n\n[Source](../implementation01/README.md), [bounds](SCOPE.md), [target](targets.json). The parent-release flag records source review within the already authorized host simulation scope.\n')
write(HARNESS/'SCOPE.md','# Exact actual-run boundary\n\nOne fresh complete 30-case worker and real semantic reduction feed the authority-owned independent evidence vault. The test covers original import, exact replay, configuration drift and cold vault reopening. It does not exercise a new PAT application, catalog promotion, full runtime/supervisor reopen or endpoint-session drift; those remain explicit next gates.\n\nKeep the original actual-run limits: 180-second child wait, 60-second worker, six parent SQLite opens (five planned), 16 MiB single file, 256 MiB scratch, 8,192 files and 8 MiB log. Vault cap stays 15 MiB; snapshot stays five seconds. One declared vault database path is added to the closed path set. The runner retains original scratch plus exact copies after actual supervisor-owner and writer-lease quiescence checks. No reset, substituted original lease identity, replacement key, reduced case matrix or widened time/storage bound.\n\nOnly the owned original worker entry can launch; no network, physical endpoint, MCU, inference or service executes. Initial archive/reducer implementations are unchanged. Post-import traps reject worker/archive/reducer/planning reuse. Audit hooks remain cooperative guardrails, not OS isolation.\n')
files=[dict(path=p.relative_to(HARNESS).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(HARNESS.rglob('*')) if p.is_file()]
dump(HARNESS/'index.json',dict(scope='One actual original 30-case import and cold-vault history; wider system incomplete',files=files))
print(json.dumps(dict(sourceFiles=286,sourceIndexSha256=sha(SOURCE/'index.json'),harnessIndexSha256=sha(HARNESS/'index.json'),priorActualFilesUnchanged=275)))

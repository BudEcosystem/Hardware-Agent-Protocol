"""Reverify all immutable inputs and retained attempts, then seal this incomplete qualification stage."""
import ast, copy, hashlib, json, shutil, stat
from pathlib import Path
ROOT=Path.cwd(); B=ROOT/'artifacts/implementation/pat-io-execution-handoff'; R=B/'results'
OLD=ROOT/'artifacts/implementation/pat-io-document-validation'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt50-io-execution-handoff'
PINS={'implementation01':'f53286e08e528fd764893afc6f6765128c388a349ef536c2f22b17bc521f6035',
      'implementation02':'52590e9723805e43f76ad50c94d306d4d6a45c031e00b5fff2b6572c38ee4b90'}
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    with p.open('x') as f:f.write(json.dumps(v,indent=2)+'\n')
def verify(p,row):assert not p.is_symlink() and p.is_file() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
def inventory(folder):
    rows=[]
    for p in folder.rglob('*'):
        assert not p.is_symlink()
        if p.is_file():rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return sorted(rows,key=lambda row:row['path'])
def identity(p):
    s=p.lstat();assert stat.S_ISDIR(s.st_mode)
    return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
assert not (R/'index.json').exists() and not D.exists()
assert sha(OLD/'implementation01/index.json')=='31118f7405fcce5f4828bf4d256faea21e61b6d5bae470632376d9c8c484c4c0'
assert sha(OLD/'results/index.json')=='a4e2629f76a0df2e341edcf038502337f6305dac05fcf9b0de5a9d35de360d0c'
entries=[(OLD/'implementation01',True)]
for name,pin in PINS.items():
    assert sha(B/name/'index.json')==pin;entries.append((B/name,True))
for n in range(1,31):
    h=B/('harness%02d'%n); assert read(h/'review.json')['sourceIndexSha256']==PINS['implementation02' if n>=26 else 'implementation01']
    entries.append((h,False))
counts={}
for folder,rooted in entries:
    rows=read(folder/'index.json')['files']
    for row in rows:verify((ROOT if rooted else folder)/row['path'],row)
    counts[folder.relative_to(ROOT).as_posix()]=len(rows)
baseline=read(B/'implementation01/baseline-inputs.json')['inheritedProjectInputs'];changed=[]
for row in baseline:
    relative=(ROOT/row['path']).relative_to(OLD/'implementation01/project')
    if sha(B/'implementation01/project'/relative)!=row['sha256']:changed.append(relative.as_posix())
assert len(baseline)==248 and changed==['supervisor/attempt_ledger.py','supervisor/supervisor_contracts.py']
for row in read(B/'implementation02/baseline-inputs.json')['inheritedProjectInputs']:
    relative=(ROOT/row['path']).relative_to(B/'implementation01/project');verify(B/'implementation02/project'/relative,row)
old_tree=ast.parse((OLD/'implementation01/project/supervisor/attempt_ledger.py').read_bytes())
new_tree=ast.parse((B/'implementation01/project/supervisor/attempt_ledger.py').read_bytes())
constants={n.targets[0].id:n.value for n in new_tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in {'ATTEMPT_SQL','INDEX_SQL'}}
cls=next(n for n in new_tree.body if isinstance(n,ast.ClassDef) and n.name=='AttemptLedger')
hooks={n.name:n.body for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in {'_create_metadata','_check_metadata'}}
class Expand(ast.NodeTransformer):
    def visit_Expr(self,n):
        if isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and n.value.func.attr in hooks:return copy.deepcopy(hooks[n.value.func.attr])
        return self.generic_visit(n)
    def visit_Name(self,n):return copy.deepcopy(constants[n.id]) if n.id in constants and isinstance(n.ctx,ast.Load) else n
new_tree.body=[n for n in new_tree.body if not (isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in constants)]
cls.body=[n for n in cls.body if not (isinstance(n,ast.FunctionDef) and n.name in hooks)]
assert ast.dump(old_tree,include_attributes=False)==ast.dump(Expand().visit(new_tree),include_attributes=False)
analysis=read(B/'RESULTS.json');assert analysis['goalStatus']=='active' and analysis['attemptedScopes']==30 and analysis['selectedDistinctMethods']==349
assert analysis['newPassingControlMethods']==50 and not analysis['actualHandoffWorkerPassed'] and not analysis['regressionComplete']
originals={};passed=set();complete=set();incomplete=set()
for item in analysis['attempts']:
    folder=R/item['destination']; A=folder/'attempt'; proof=read(folder/'proof.json'); result=read(A/'result.json'); H=B/proof['harness'];review=read(H/'review.json')
    assert proof['status']==result['status']==item['status'] and proof['counts']==result['counts']==item['counts']
    assert result['childState']=='exited' and not Path('/proc',str(result['pid'])).exists()
    assert proof['harnessIndexSha256']==sha(H/'index.json') and proof['sourceIndexSha256']==review['sourceIndexSha256']
    targets=read(H/'targets.json')['targets'];assert item['targets']==targets
    for label,folder_root,count in [('inputs',A/'project',review.get('projectInputCount',252)),('frozen',ROOT,review.get('frozenPreparationInputCount',255)),('harness',A/'harness',6)]:
        rows=read(A/(label+'-before.json'));assert rows==read(A/(label+'-after.json')) and len(rows)==count
        for row in rows:verify(folder_root/row['path'],row)
    external=read(A/'external-before.json');assert external==read(A/'external-after.json') and len(external['files'])==159
    for row in external['files']:verify(Path(row['resolvedPath']),row)
    if result['status']=='timed_out':
        assert result['counts'] is None and proof['fullChildReceiptAvailable'] is False and not (A/'test-return.json').exists();incomplete.update(targets)
    else:
        assert result['errors']==result['childErrors']==[]
        actual=read(A/'actual-tests.json');assert actual['loaded']==actual['executed']==targets and actual['exactSelection'];complete.update(targets)
        origins=read(A/'imports.json');assert origins['summary']['allOriginsMatched'] and origins['violations']==origins['prohibitedAttempts']==[]
        for row in origins['records']:
            if 'sha256' in row:assert sha(Path(row['origin']))==row['sha256']
        for label in ('compiler','driver'):assert read(A/(label+'-before.json'))==read(A/(label+'-after.json'))
        assert len(read(A/'sqlite-connections.json'))==proof['sqliteConnections']
        if result['status']=='passed':passed.update(targets)
    raw=Path(proof['rawScratch']['path']);assert identity(raw)==proof['rawScratch'] and identity(raw.parent)==read(A/'raw-scratch-before.json')['parent']
    rows=inventory(raw);assert rows==inventory(A/'scratch')==read(A/'scratch-index.json') and len(rows)==proof['rawScratchFiles']
    assert sum(row['bytes'] for row in rows)==proof['rawScratchBytes']<=review['scratchBytesCeiling']
    original=H/'attempts'/proof['attempt'];rows=inventory(original);assert rows==inventory(A) and len(rows)==proof['attemptFilesAcquired']
    originals[item['destination']]=len(rows)
    assert read(folder/'storage-audit.json')['databaseBytesUnchanged']
    if 'processAudit' in item:
        value=read(folder/item['processAudit']);assert value['ledgerUnchanged'] and not value['qualificationPassed']
        quiet=read(A/'writer-quiescence.json');assert quiet['ownerQuiescent'] and len(quiet['records'])==1
        assert quiet['records'][0].get('writerQuiescent') or quiet['records'][0].get('launchIntentAbsent')
        if value.get('codeImageExactClosure'):assert value['codeImageFiles']==262 and value['runtimeFiles']==157
    if review.get('selectionKind')=='history':
        value=read(folder/'history-audit.json');assert value['allDatabasesUnchanged'] and value['originalValidHandoffs']==2 and not value['actualWorkerExecuted']
assert len(passed)==analysis['distinctPassingMethods'] and len(complete)==analysis['completedReceiptMethods'] and len(incomplete)==analysis['incompleteSelectionMethods']
links=read(ROOT/'artifacts/verification/project-links.json');assert links['missing']==[] and links['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in links['files']:assert sha(ROOT/row['path'])==row['sha256']
rows=inventory(R);write(R/'index.json',dict(scope='Durable handoff controls, all original process attempts and retained incomplete compatibility selection. Full HMS goal active.',files=rows))
counts[R.relative_to(ROOT).as_posix()]=len(rows);entries.append((R,False))
D.mkdir();names=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
    'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
names.extend(p.relative_to(ROOT).as_posix() for p in sorted(B.iterdir()) if p.is_file() and p.suffix in ('.md','.py','.json','.patch','.log'))
names.extend((folder/'index.json').relative_to(ROOT).as_posix() for folder,_ in entries)
assert len(names)==len(set(names));copies=[]
for name in names:
    source=ROOT/name;dest=D/'inputs'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    row=dict(source=name,copy=dest.relative_to(ROOT).as_posix(),bytes=source.stat().st_size,sha256=sha(source));verify(dest,row);copies.append(row)
write(D/'index.json',dict(scope='Durable supervisor identity and handoff with retained deadline failures; prompt-to-PAT and full device/driver/hub goal remain active.',
    selectedDistinctMethods=349,completedReceiptMethods=len(complete),distinctPassingMethods=len(passed),incompleteSelectionMethods=len(incomplete),
    newPassingControls=50,actualHandoffWorkerPassed=False,regressionComplete=False,publicServiceMounted=False,historicalFailuresPreserved=True,
    markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],
    originalAttemptFilesReverified=originals,artifactEntriesReverified=counts,reportFileHashesVerified=len(links['files']),files=copies))
print(json.dumps(dict(resultsFiles=len(rows),resultsIndexSha256=sha(R/'index.json'),documentIndexSha256=sha(D/'index.json'),
    documentCopies=len(copies),artifactEntriesReverified=sum(counts.values()),markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'])))

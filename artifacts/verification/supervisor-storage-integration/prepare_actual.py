"""Prepare the original complete actual scope; this does not release or run it."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
OLD=ROOT/'artifacts/implementation/pat-statement-cache/harness01'
SOURCE=ROOT/'artifacts/implementation/supervisor-storage-bindings/implementation01'
NEW=BASE/'harness01'
PIN='ffcace54bb02211d47e2f69febfb2f7f1566d6ee6dcb8264a3f10ecef5a8534f'
OLD_PIN='7ecd42fec5cef9374573ae8b3d0747060bdc8c4cd8ca552e9c3de4d64a2ec23e'
HPIN='74204ea2477aa497bfce9a6c667455b4ec5fb622f49c07663a7c87b3c583d933'
TARGET='test_storage_actual.SplitVaultCatalogProcessTests.test_actual_original_matrix_catalog_admission_and_cold_history'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as stream:stream.write(v if type(v) is bytes else (v if type(v) is str else json.dumps(v,indent=2)+'\n').encode())
assert sha(OLD/'index.json')==HPIN and sha(SOURCE/'index.json')==PIN
for index,prefix in ((OLD/'index.json',OLD),(SOURCE/'index.json',ROOT)):
    for row in read(index)['files']:
        p=prefix/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
assert not NEW.exists();NEW.mkdir()
diff=[]
before=(OLD/'run_attempt.py').read_text();after=before.replace(OLD_PIN,PIN)
after=after.replace('artifacts/implementation/pat-statement-cache/implementation01','artifacts/implementation/supervisor-storage-bindings/implementation01')
for old,new in [('!= 313','!= 312'),("'frozenPreparationInputCount': 313","'frozenPreparationInputCount': 312"),
    ("'projectInputCount': 304","'projectInputCount': 309"),('!= 304','!= 309'),('exactly 304 files','exactly 309 files'),
    ('test_vault_catalog_process.VaultCatalogProcessTests.test_actual_original_matrix_catalog_admission_and_cold_history',TARGET)]:
    assert old in after;after=after.replace(old,new)
after=after.replace("root = scratch / PROCESS_METHOD / 'supervisor'", "root = scratch / PROCESS_METHOD / 'supervisor-control'\n    bulk = scratch / PROCESS_METHOD / 'supervisor-bulk'")
after=after.replace("fd=os.open(root/identifier/'writer.lease'", "fd=os.open(bulk/identifier/'writer.lease'")
old="            records=db.execute('SELECT id,record FROM qs_attempts LIMIT 2').fetchall()"
new=old+"\n            binding_meta=db.execute('SELECT version,binding FROM qs_meta LIMIT 2').fetchall()\n            if len(binding_meta)!=1 or binding_meta[0][0]!=3 or type(binding_meta[0][1]) is not bytes or len(binding_meta[0][1])>16384:raise RuntimeError('Invalid split storage metadata')\n            binding=json.loads(binding_meta[0][1])"
assert after.count(old)==1;after=after.replace(old,new)
old="        if row(ledger,'attempts.db')!=before:raise RuntimeError('Read-only ledger changed')"
new=old+"\n        proof['storageBinding']=hold_storage_binding(binding,root,bulk,held)"
assert after.count(old)==1;after=after.replace(old,new)
helper='''def hold_storage_binding(binding,control,bulk,held):
    """Check original bound objects while the control owner remains locked."""
    if set(binding)!={'profile','bindingId','control','bulk','bulkOwner','bulkManifest','manifestSha256'} or binding['profile']!='hms.supervisor.storage-split/0.1':raise RuntimeError('Invalid storage binding')
    if not re.fullmatch(r'[0-9a-f]{32}',binding['bindingId']):raise RuntimeError('Invalid binding id')
    for name,path in [('control',control),('bulk',bulk)]:
        info=path.lstat()
        expected=dict(path=str(path),uid=os.getuid(),device=str(info.st_dev),inode=str(info.st_ino))
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.getuid() or binding[name]!=expected:raise RuntimeError('Original storage root changed')
    for name,key in [('bulk.owner','bulkOwner'),('storage.json','bulkManifest')]:
        path=bulk/name;fd=os.open(path,(os.O_RDWR if name=='bulk.owner' else os.O_RDONLY)|os.O_NOFOLLOW|os.O_CLOEXEC)
        held.append(fd);info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600 or binding[key]!=dict(device=str(info.st_dev),inode=str(info.st_ino)):raise RuntimeError('Storage marker identity changed')
        if name=='bulk.owner':
            if info.st_size!=0:raise RuntimeError('Bulk owner content')
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        else:
            if not 0<info.st_size<=16384:raise RuntimeError('Storage marker size')
            body=os.pread(fd,16385,0)
            expected=json.dumps({k:binding[k] for k in ('profile','bindingId','control','bulk')},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
            if body!=expected or hashlib.sha256(body).hexdigest()!=binding['manifestSha256']:raise RuntimeError('Storage marker bytes changed')
    return dict(bindingId=binding['bindingId'],control=binding['control'],bulk=binding['bulk'],bulkOwnerHeld=True,manifestExact=True)


'''
after=after.replace('def main():',helper+'def main():')
ast.parse(after);write(NEW/'run_attempt.py',after)
diff+=list(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='original/run_attempt.py',tofile='split/run_attempt.py'))
before=(OLD/'attempt_child.py').read_text();after=before
after=after.replace("/ 'test_actual_original_matrix_catalog_admission_and_cold_history' / 'supervisor'", "/ 'test_actual_original_matrix_catalog_admission_and_cold_history' / 'supervisor-bulk'")
after=after.replace('root_scan = path == expected',"root_scan = path in (expected,expected.with_name('supervisor-control'))")
after=after.replace("work/'supervisor'/'attempts.db'","work/'supervisor-control'/'attempts.db'")
after=after.replace('MAX_ORIGINS = 8192','MAX_ORIGINS = 8192\nimport resource\nresource.setrlimit(resource.RLIMIT_FSIZE,(MAX_FILE,MAX_FILE))')
ast.parse(after);write(NEW/'attempt_child.py',after)
diff+=list(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='original/attempt_child.py',tofile='split/attempt_child.py'))
write(NEW/'targets.json',dict(testCount=1,targets=[TARGET]))
write(NEW/'references/approved-external-roots.json',(OLD/'references/approved-external-roots.json').read_bytes())
write(NEW/'borrowed-inputs.json',[dict(source=str((OLD/name).relative_to(ROOT)),bytes=(OLD/name).stat().st_size,sha256=sha(OLD/name)) for name in ('run_attempt.py','attempt_child.py','targets.json','SCOPE.md','references/approved-external-roots.json')])
write(NEW/'SCOPE.md','''# One complete original qualification with split supervisor storage

The inherited actual test body is exact apart from previously frozen computed
identity literals. Its setup binds private control and bulk roots instead of one
legacy supervisor root. There is one qualification worker, all thirty cases,
the real reducer, vault publication, catalog promotion, one simulated application,
drift refusal and cold vault/bridge history. Six parent SQLite opens, the original
60-second worker / 180-second parent, 16 MiB file / 256 MiB scratch and 15 MiB vault
bounds remain. The child explicitly installs the declared 16 MiB inherited file
limit. Source/dependency, native image, exact root/attempt scans, process ownership
and inherited lease checks remain. Read-only acquisition also checks the new
binding's root, owner and manifest identities. No worker case database is reopened.

Only run after all 71 distinct controls have complete passing receipts. The
earlier batched control profile remains failed; its changed diagnostic batching
does not change this complete integration scope. No retry, replacement application
key, physical execution, public mounting or capacity-reservation claim follows.
''')
write(NEW/'adaptation.patch',''.join(diff))
write(NEW/'PREPARATION.json',dict(reviewer='primary-agent',independentReview=False,sourceIndexSha256=PIN,
    templateIndexSha256=HPIN,target=TARGET,cases=30,semanticOracleSubstitution=False,workerMaxMs=60000,parentMaxSeconds=180,
    parentSqliteOpens=6,fileLimitBytes=16777216,scratchLimitBytes=268435456,publicRuntimeChanged=False,
    actualLaunchReleased=False,awaitsAllDistinctControls=71))
files=[dict(path=p.relative_to(NEW).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(NEW.rglob('*')) if p.is_file()]
write(NEW/'index.json',dict(files=files));print(json.dumps(dict(indexSha256=sha(NEW/'index.json'),files=len(files),released=False)))

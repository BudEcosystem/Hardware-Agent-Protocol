"""Reuse the exact native/accounting child with only source-selection changes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
SOURCE=BASE/'implementation01';HARNESS=BASE/'harness01'
TEMPLATE=ROOT/'artifacts/verification/pat-native-worker-accounting/harness01'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body if type(body)is bytes else body.encode())
def dump(path,value):put(path,json.dumps(value,indent=2)+'\n')
assert not HARNESS.exists()
assert sha(SOURCE/'index.json')=='387d33e2992d2862b1c21902b8de09195a56b569f52c3c3e04b84ce09b2d8849'
assert sha(TEMPLATE/'index.json')=='34bfe3567be9944a079d8c9809b62227e0967a59875c85a8bc84a6de53651b9a'
for folder,prefix in ((SOURCE,ROOT),(TEMPLATE,TEMPLATE)):
    for row in read(folder/'index.json')['files']:
        path=prefix/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
controls=read(BASE/'contract-controls.json')
assert controls['status']=='passed' and controls['testsRun']==9 and controls['deniedEvents']==[]
assert controls['runnerSha256']==sha(BASE/'run_contract_controls.py') and controls['sourceIndexSha256']==sha(SOURCE/'index.json')
borrowed=[]
for name in ('run_attempt.py','attempt_child.py','targets.json','references/approved-external-roots.json'):
    source=TEMPLATE/name;old=source.read_text();new=old
    reference='references/original-'+source.name
    put(HARNESS/reference,source.read_bytes())
    borrowed.append(dict(source=str(source.relative_to(ROOT)),copy=reference,bytes=source.stat().st_size,sha256=sha(source)))
    if name=='run_attempt.py':
        changes=[('255b919194d150572c7b7876d941fb2e7d5866e36cdc119e91608da4b85ddc18',sha(SOURCE/'index.json'),1),
            ('artifacts/implementation/pat-native-supervisor/implementation02','artifacts/implementation/pat-integer-canonical/implementation01',2),
            ("prefix='hms-native-worker-accounting-'","prefix='hms-integer-canonical-actual-'",1)]
        for old_value,new_value,count in changes:
            assert new.count(old_value)==count;new=new.replace(old_value,new_value)
        put(HARNESS/'run_attempt.py.patch',''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='original-native-accounting',tofile='canonical-candidate')))
    if name.endswith('.py'):ast.parse(new)
    put(HARNESS/name,new)
assert sha(HARNESS/'attempt_child.py')==sha(TEMPLATE/'attempt_child.py')
dump(HARNESS/'borrowed-inputs.json',borrowed)
put(HARNESS/'README.md','# Original complete canonical-candidate trial\n\n[Scope](SCOPE.md). The native guard and accounting child are byte-identical to the preceding controlled diagnostic.\n')
put(HARNESS/'SCOPE.md','# Original full integration scope\n\nThe one-module canonicalization candidate runs the unchanged complete thirty-case authority-vault worker/import/cold-history test, except its independently derived consumer pin. The exact preceding native guard and original-process accounting observer remain in the child. No extra wait, poll, signal, effect, retry or case selection is introduced.\n\nBounds remain: 60-second worker, 180-second parent, six parent SQLite opens, 16 MiB file, 256 MiB retained scratch, 8192 files, 8 MiB log, five-second held snapshot and 15 MiB vault. No physical endpoint, MCU, inference, live service or acquired controller runs. Interrupted case databases must not be opened/recovered. Partial evidence is not promotion authority.\n\nAccounting is observational: global pressure is not process attribution, peak RSS is not additive, and a single trial is not a matched deployment-performance experiment. Cooperative audit hooks are not an OS sandbox.\n')
dump(HARNESS/'review.json',dict(reviewer='primary-agent',independentReview=False,sourceIndexSha256=sha(SOURCE/'index.json'),
    templateIndexSha256=sha(TEMPLATE/'index.json'),childByteIdentical=True,nativeGuardAndObserverUnchanged=True,
    previousObserverControls=15,previousCompositionControls=6,currentPublicContractTests=9,pureDifferentialCases=1668,
    currentContractControlsSha256=sha(BASE/'contract-controls.json'),caseMatrix=30,workerMaxWallMs=60000,parentMaxSeconds=180,
    addedWaits=0,addedSignals=0,pidBasedCounterReads=0,actualScopeNotYetExecuted=True))
rows=[]
for path in sorted(HARNESS.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():rows.append(dict(path=str(path.relative_to(HARNESS)),bytes=path.stat().st_size,sha256=sha(path)))
dump(HARNESS/'index.json',dict(scope='Exact native/accounting child with one-module source candidate under original complete scope',files=rows))
print(json.dumps(dict(files=len(rows),harnessIndexSha256=sha(HARNESS/'index.json'),childUnchanged=True)))

"""Original copied-source test harness. Invoke only after parent's explicit release."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import _sqlite3

parser = argparse.ArgumentParser()
parser.add_argument('attempt')
parser.add_argument('--parent-released', action='store_true')
parser.add_argument('--source-snapshot', choices=['01','02'])
parser.add_argument('targets', nargs='*')
args = parser.parse_args()
if not args.parent_released:
    raise SystemExit('No execution: parent shared-freeze release must be explicit.')
if not args.attempt.replace('-','').replace('_','').isalnum():
    raise SystemExit('Invalid unique attempt name')
stage = Path(__file__).resolve().parent
attempt = stage/'attempts'/args.attempt
attempt.mkdir(parents=True, exist_ok=False)
(attempt/'run_attempt.py').write_bytes(Path(__file__).read_bytes())
tree = attempt/'project'; shutil.copytree(stage/'project',tree)
if args.source_snapshot:
    frozen = stage/'review-inputs'/args.source_snapshot
    source_rows = json.loads((frozen/'manifest.json').read_text())['files']
    for row in source_rows:
        if not row['path'].startswith('hms/'):
            continue  # Use the later regression test against the actual old source.
        source = frozen/'project'/row['path']; body = source.read_bytes()
        if hashlib.sha256(body).hexdigest() != row['sha256']:
            raise SystemExit('Frozen source snapshot changed')
        (tree/row['path']).write_bytes(body)


def files(directory):
    return [{'path':str(path.relative_to(directory)),'bytes':path.stat().st_size,
             'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(directory.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts]


def external_inputs():
    rows = []
    for package in ('jsonschema','referencing','jsonschema-specifications','attrs','rpds-py'):
        distribution = importlib.metadata.distribution(package)
        for item in sorted(distribution.files or [],key=str):
            if item.is_absolute() or '..' in item.parts or '__pycache__' in item.parts:
                continue
            path = Path(distribution.locate_file(item))
            if path.is_file():
                body = path.read_bytes()
                rows.append({'package':package,'version':distribution.version,'path':str(item),
                    'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
    for label,path in [('python',Path(sys.executable)),('sqlite-extension',Path(_sqlite3.__file__))]:
        rows.append({'runtime':label,'path':str(path),'bytes':path.stat().st_size,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return rows


before = files(tree); external_before = external_inputs()
(attempt/'inputs-before.json').write_text(json.dumps(before,indent=2)+'\n')
(attempt/'external-before.json').write_text(json.dumps(external_before,indent=2)+'\n')
(attempt/'evidence').mkdir(mode=0o700); (attempt/'scratch').mkdir(mode=0o700)
targets = args.targets or ['test_io_lifecycle']
script = '''import hashlib,json,os,pathlib,sys,unittest
sys.dont_write_bytecode=True
def network_veto(event,args):
    if event.startswith('socket.'):raise RuntimeError('Lifecycle proof forbids network use')
sys.addaudithook(network_veto)
import test_io_lifecycle as lifecycle
import test_io_synthetic_provider as ordinary
root=pathlib.Path(os.environ['EXPECTED_PROJECT']).resolve()
import hms.journal
assert pathlib.Path(hms.journal.__file__).resolve().is_relative_to(root)
out=pathlib.Path(os.environ['ATTEMPT_DIRECTORY'])
lifecycle.EVIDENCE_DIRECTORY=out/'evidence'/'lifecycle';lifecycle.EVIDENCE_DIRECTORY.mkdir()
ordinary.EVIDENCE_DIRECTORY=out/'evidence'/'ordinary';ordinary.EVIDENCE_DIRECTORY.mkdir()
tests=unittest.defaultTestLoader.loadTestsFromNames(json.loads(os.environ['TEST_TARGETS']))
result=unittest.TextTestRunner(verbosity=2).run(tests)
imports=[]
for name,module in sorted(sys.modules.items()):
    path=getattr(module,'__file__',None)
    if path and (name=='hms' or name.startswith('hms.') or name.startswith('test_io_')):
        path=pathlib.Path(path).resolve();assert path.is_relative_to(root),(name,str(path))
        imports.append({'module':name,'path':str(path.relative_to(root)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(out/'imports.json').write_text(json.dumps(imports,indent=2)+'\\n')
report={'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
    'skips':len(result.skipped),'expectedFailures':len(result.expectedFailures),'unexpectedSuccesses':len(result.unexpectedSuccesses)}
(out/'test-return.json').write_text(json.dumps(report,indent=2)+'\\n')
raise SystemExit(0 if result.wasSuccessful() and not result.skipped and not result.expectedFailures else 1)
'''
(attempt/'test-script.py').write_text(script)
environment = dict(os.environ,PYTHONDONTWRITEBYTECODE='1',
    PYTHONPATH=os.pathsep.join((str(tree),str(tree/'tests'))),
    EXPECTED_PROJECT=str(tree),ATTEMPT_DIRECTORY=str(attempt),TMPDIR=str(attempt/'scratch'),TEST_TARGETS=json.dumps(targets))
started = time.monotonic()
with (attempt/'output.log').open('wb') as log:
    process = subprocess.run([sys.executable,'-B',str(attempt/'test-script.py')],cwd=tree,env=environment,
        stdout=log,stderr=subprocess.STDOUT)
elapsed = time.monotonic()-started
after = files(tree); external_after = external_inputs()
(attempt/'inputs-after.json').write_text(json.dumps(after,indent=2)+'\n')
(attempt/'external-after.json').write_text(json.dumps(external_after,indent=2)+'\n')
evidence = files(attempt/'evidence')
(attempt/'evidence-index.json').write_text(json.dumps(evidence,indent=2)+'\n')
counts = json.loads((attempt/'test-return.json').read_text()) if (attempt/'test-return.json').exists() else None
result = {'profile':'hms.lifecycle-staged-attempt/1','attempt':args.attempt,'sourceSnapshot':args.source_snapshot,
    'targets':targets,'exitCode':process.returncode,'elapsedSeconds':elapsed,'counts':counts,
    'inputCount':len(before),'inputsUnchanged':before==after,'externalInputCount':len(external_before),
    'externalInputsUnchanged':external_before==external_after,'evidenceFiles':len(evidence),
    'runnerSha256':hashlib.sha256((attempt/'run_attempt.py').read_bytes()).hexdigest(),
    'runnerUnchanged':Path(__file__).read_bytes()==(attempt/'run_attempt.py').read_bytes(),
    'scope':'Original controlled-clock SQLite lifecycle/ordinary-provider code in exact copies; no acquired programs, native endpoints, OS driver actions, neural models or hardware.',
    'limits':['No physical or native-clock availability proof; no autonomous stop latency or hard SQLite bound.',
        'Selected external distribution/Python/_sqlite3 pins are not a complete standard-library/shared-library/OS/kernel closure.',
        'Lifecycle public result profile and stock/public mounting remain unsupported.']}
(attempt/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(process.returncode or (0 if before==after and external_before==external_after and result['runnerUnchanged'] else 2))

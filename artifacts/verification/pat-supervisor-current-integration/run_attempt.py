"""Copy-only proof harness; test execution uses this attempt's original source tree."""
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

stage=Path(__file__).resolve().parent
attempt=stage/'attempts'/sys.argv[1]
attempt.mkdir(parents=True,exist_ok=False)
(attempt/'run_attempt.py').write_bytes(Path(__file__).read_bytes())
tree=attempt/'tree';tree.mkdir()
for name in ('src','tests'):shutil.copytree(stage/name,tree/name)
shutil.copytree(stage/'baseline/current',tree/'current')
def manifest():
    return [{'path':str(p.relative_to(tree)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(tree.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
before=manifest();(attempt/'inputs-before.json').write_text(json.dumps(before,indent=2)+'\n')
def external_inputs():
    rows=[]
    for package in ('jsonschema','referencing','jsonschema-specifications','attrs','rpds-py'):
        distribution=importlib.metadata.distribution(package)
        for item in sorted(distribution.files or [],key=str):
            if item.is_absolute() or '..' in item.parts or '__pycache__' in item.parts:continue
            source=Path(distribution.locate_file(item))
            if source.is_file():
                body=source.read_bytes();rows.append({'package':package,'version':distribution.version,
                    'path':str(item),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
    for label,path in [('python',Path(sys.executable)),('sqlite-extension',Path(_sqlite3.__file__))]:
        rows.append({'runtime':label,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return rows
external_before=external_inputs()
(attempt/'external-before.json').write_text(json.dumps(external_before,indent=2)+'\n')
script='''import json, os, pathlib, shutil, sys, unittest
sys.dont_write_bytecode=True
import test_supervisor as suite
targets=json.loads(os.environ['TEST_TARGETS'])
tests=unittest.defaultTestLoader.loadTestsFromNames(targets) if targets else unittest.defaultTestLoader.loadTestsFromModule(suite)
result=unittest.TextTestRunner(verbosity=2).run(tests)
output=pathlib.Path(os.environ['RETAIN_OUTPUT']);output.mkdir()
report=suite.LAST_REPORT
report['testsRun']=result.testsRun;report['failures']=len(result.failures);report['errors']=len(result.errors);report['skips']=len(result.skipped)
for i, root in enumerate(suite.ROOTS):
    shutil.copytree(root,output/('case-%02d'%i),symlinks=True)
report['retainedRoots']=[{'original':str(r),'retained':'case-%02d'%i} for i,r in enumerate(suite.ROOTS)]
(output/'report.json').write_text(json.dumps(report,indent=2)+'\\n')
raise SystemExit(0 if result.wasSuccessful() else 1)
'''
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=os.pathsep.join(str(tree/p) for p in ('current','src','tests')),
         EXPECTED_HMS_ROOT=str(tree/'current'), RETAIN_OUTPUT=str(attempt/'output'),
         RETAIN_SETUP=str(attempt/'trusted-setup'),TEST_TARGETS=json.dumps(sys.argv[2:]))
started=time.time()
with (attempt/'output.log').open('wb') as log:
    process=subprocess.run([sys.executable,'-B','-c',script],cwd=tree,env=env,stdout=log,stderr=subprocess.STDOUT)
after=manifest();(attempt/'inputs-after.json').write_text(json.dumps(after,indent=2)+'\n')
external_after=external_inputs()
(attempt/'external-after.json').write_text(json.dumps(external_after,indent=2)+'\n')
result={'profile':'hms.staged-supervisor-attempt/0.1','exitCode':process.returncode,'elapsedSeconds':time.time()-started,
        'inputsUnchanged':before==after,'inputCount':len(before),'cwd':str(tree),'targets':sys.argv[2:],'command':[sys.executable,'-B','-c','retained script below'],
        'externalInputsUnchanged':external_before==external_after,'externalInputCount':len(external_before),
        'runnerSha256':hashlib.sha256((attempt/'run_attempt.py').read_bytes()).hexdigest(),
        'pythonExecutableSha256':hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),'script':script}
(attempt/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(process.returncode or (0 if before==after and external_before==external_after else 2))

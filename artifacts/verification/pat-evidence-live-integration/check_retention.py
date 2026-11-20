"""Failure-injection check for the proof runner only; no Runtime/worker."""
import ast, hashlib, json, shutil, tempfile
from pathlib import Path
from unittest import mock

base=Path(__file__).resolve().parent
source=(base/'run.py').read_text()
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='retain_worker_output')
namespace={'shutil':shutil,'json':json}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(base/'run.py'),'exec'),namespace)
retain=namespace['retain_worker_output']
checks=[]
for phase in ('copy_failure','report_failure','success'):
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); scratch=root/'original';scratch.mkdir()
        (scratch/'sentinel').write_bytes(b'exact original evidence')
        destination=root/'retained';destination.mkdir()
        if phase=='copy_failure':
            with mock.patch.object(shutil,'copytree',side_effect=OSError('injected copy failure')):
                try: retain(scratch,destination,{'test':True})
                except OSError: pass
                else: raise AssertionError('expected failure')
        elif phase=='report_failure':
            with mock.patch.object(Path,'write_text',side_effect=OSError('injected report failure')):
                try: retain(scratch,destination,{'test':True})
                except OSError: pass
                else: raise AssertionError('expected failure')
        else:
            retain(scratch,destination,{'test':True})
        if phase=='success':
            assert not scratch.exists()
            assert (destination/'worker-output/sentinel').read_bytes()==b'exact original evidence'
            assert json.loads((destination/'worker-report.json').read_text())=={'test':True}
        else:
            assert (scratch/'sentinel').read_bytes()==b'exact original evidence'
        checks.append({'phase':phase,'passed':True})
report={'profile':'hms-proof-runner-retention-check/0.1','scope':'Three original runner-only failure/success checks; no qualification evidence or Runtime execution.',
        'checks':checks,'runnerSha256':hashlib.sha256(source.encode()).hexdigest(),'checkerSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
with (base/'retention-check.json').open('x') as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))

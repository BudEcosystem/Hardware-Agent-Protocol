"""Combined pure-service integration and existing PAT regressions; original local simulation only."""
from pathlib import Path
import datetime, hashlib, io, json, sys, time, unittest
ROOT=Path.cwd()
BASE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tests'),str(ROOT)]
from scripts.check_runtime import input_paths, compiler_identity
paths=input_paths(ROOT)
rows=[]
for p in paths:
    data=p.read_bytes(); relative=p.relative_to(ROOT); target=BASE/'sources'/relative
    target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
    rows.append({'path':str(relative),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
(BASE/'inputs-before.json').write_text(json.dumps(rows,indent=2)+'\n')
identity=compiler_identity()
(BASE/'compiler-before.json').write_text(json.dumps(identity,indent=2)+'\n')
names=['test_pat_compiler','test_pat_catalog','test_pat_catalog_review','test_pat_execution','test_pat_bindings','test_pat_simulation_contracts','test_pat_environment']
suite=unittest.defaultTestLoader.loadTestsFromNames(names)
started=time.monotonic()
with (BASE/'tests.log').open('w') as output:
    result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
after=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in input_paths(ROOT)]
(BASE/'inputs-after.json').write_text(json.dumps(after,indent=2)+'\n')
after_identity=compiler_identity()
(BASE/'compiler-after.json').write_text(json.dumps(after_identity,indent=2)+'\n')
record={'schema':'hms-pat-service-pure-integration/1','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'command':'python3 -B artifacts/verification/pat-service-pure-integration/run.py','modules':names,
 'scope':'37 newly integrated pure checks and89 existing PAT checks; existing suites run original local simulations. No qualification worker, hardware, model or acquired program execution.',
 'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
 'seconds':time.monotonic()-started,'inputCount':len(rows),'inputsStable':rows==after,'compilerIdentityStable':identity==after_identity,
 'failureDetails':[{'test':str(t),'detail':d} for t,d in result.failures], 'errorDetails':[{'test':str(t),'detail':d} for t,d in result.errors],
 'passed':result.wasSuccessful() and not result.skipped and rows==after and identity==after_identity,
 'runnerSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(BASE/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k not in ['failureDetails','errorDetails','modules']}))
raise SystemExit(0 if record['passed'] else 1)

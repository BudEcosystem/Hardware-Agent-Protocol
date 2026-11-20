import cProfile,hashlib,json,pstats,time
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'src'),str(root/'baseline/producer')]
import evidence_reducer as e
from hms.contracts import canonical
source=e.read_retained_attempt(root/'retained/case-04')
cap=json.loads(source['files'][0]['body'])['value']
trust={'profile':e.TRUST_PROFILE,'deployment':cap['evaluationEnvironment']['deployment'],'runId':'profile:historical',
 'evaluator':{'evaluatorId':'sim:retained-fan','implementationDigest':'sha256:'+hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest(),
 'policyDigest':cap['identities']['policyDigest'],'requiredChecks':[{'id':k,'category':c} for k,c in e.CHECKS],'evidenceProfile':e.PROFILE},'input':cap}
profile=cProfile.Profile();start=time.monotonic();profile.enable()
reduced=e.reduce_attempt(trust,source['result'],source['files'])
profile.disable();elapsed=time.monotonic()-start
out=root/'profiling';profile.dump_stats(out/'reducer.prof')
with (out/'cumulative.txt').open('w') as stream:pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(70)
with (out/'self.txt').open('w') as stream:pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('tottime').print_stats(50)
(out/'result.json').write_text(json.dumps({'scope':'Original frozen full semantic reduction only; actual retained case04; no Runtime/worker execution.','sourceSha256':hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest(),'secondsWithProfiler':elapsed,'groupDigest':reduced['groupDigest'],'documents':len(reduced['documents'])},indent=2)+'\n')
print((out/'result.json').read_text());print((out/'cumulative.txt').read_text())

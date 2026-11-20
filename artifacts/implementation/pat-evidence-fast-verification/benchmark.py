"""Same frozen copied tree, actual historical evidence, no Runtime or worker."""
import hashlib,json,sqlite3,sys,time
from pathlib import Path
attempt=Path(sys.argv[1]).resolve();tree=attempt/'tree'
status=json.loads((attempt/'result.json').read_bytes())
assert status['exitCode']==0 and status['inputsStable'] is True
sys.path[:0]=[str(tree/'tests'),str(tree/'src'),str(tree/'baseline/producer')]
import test_fast_evidence as fixture
import evidence_reducer as e
import fast_evidence as f
import hms.contracts
from hms.journal import Context
assert Path(hms.contracts.__file__).resolve().is_relative_to(tree/'baseline/producer')
folder=attempt/'benchmark';folder.mkdir(exist_ok=False)
rows=[]
for case in ('case-04','case-01'):
 trust,source=fixture.sample(case);memo=f.ValidatedReducerMemo()
 start=time.monotonic();bundle=memo.warm(trust,source['result'],source['files']);warm=time.monotonic()-start
 db=sqlite3.connect(folder/(case+'.sqlite'))
 try:
  full=e.EvidenceStore(db,trust);start=time.monotonic();result=full.import_bundle(bundle);imported=time.monotonic()-start
  receipt=fixture.receipt(trust,result);ctx=Context('benchmark-reader',trust['deployment'])
  fast=f.FastEvidenceStore(db,trust,memo=memo);cold=f.FastEvidenceStore(db,trust,memo=f.ValidatedReducerMemo())
  def measure(store):
   db.execute('BEGIN');db.set_authorizer(fixture.guard)
   try:
    start=time.monotonic()
    try:ok=store.verify_evidence(ctx,receipt);reason=None
    except e.EvidenceError as error:ok=False;reason=error.code
    return {'seconds':time.monotonic()-start,'verified':ok,'reason':reason}
   finally:db.set_authorizer(None);db.rollback()
  before=memo.usage();changes=db.total_changes
  reference=measure(full);hot=[measure(fast) for _ in range(3)];miss=measure(cold)
  assert reference['verified'] is True and all(item['verified'] is True for item in hot)
  assert miss['reason']=='PAT_EVIDENCE_CACHE_COLD' and memo.usage()==before and db.total_changes==changes
  manifest=json.loads(bundle['documents'][bundle['groupDigest']])
  rows.append({'case':case,'cases':len(manifest['cases']),'groupDigest':bundle['groupDigest'],
    'documents':len(bundle['documents']),'logicalBytes':manifest['closureBytes'],'warmSeconds':warm,
    'importSeconds':imported,'fullVerification':reference,'hotVerification':hot,'coldVerification':miss,
    'memo':before,'dbChangesDuringVerification':db.total_changes-changes})
  (folder/(case+'-trust.json')).write_bytes(e.canonical(trust));(folder/(case+'-receipt-projection.json')).write_bytes(e.canonical(receipt))
 finally:db.close()
report={'profile':'hms.staged-memo-measurement/0.1','scope':'Two actual historical worker outputs; same read-only SQLite guard for full/hot/cold verification; no Runtime/worker execution or current qualification.',
 'validationIdentity':f.validation_identity(),'imports':{'memo':f.__file__,'reducer':e.__file__,'contracts':hms.contracts.__file__},'results':rows}
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

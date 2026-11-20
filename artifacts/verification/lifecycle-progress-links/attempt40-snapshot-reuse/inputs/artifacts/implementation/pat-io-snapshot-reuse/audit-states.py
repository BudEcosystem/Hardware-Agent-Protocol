"""Read exact terminated acquired synthetic states; never reopen a Runtime."""
import hashlib,json,sqlite3,sys
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-snapshot-reuse'
name=sys.argv[1];folder=B/'results'/name;proof=json.loads((folder/'proof.json').read_bytes())
assert proof['status']in{'passed','failed'}
result=json.loads((folder/'attempt/result.json').read_bytes())
assert result['childState']=='exited' and not Path('/proc'/Path(str(result['pid']))).exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for group_file in sorted((folder/'attempt/scratch').rglob('group/result.json')):
 group=json.loads(group_file.read_bytes());matrix=json.loads((group_file.parent/'matrix.json').read_bytes())
 states=[]
 for d in sorted(group_file.parent.glob('case-*/state')):
  index=int(d.parent.name[5:]);assert 0<=index<len(matrix['cases'])
  authority=d/'authority.db';boards=list(d.glob('synthetic-io-board-*.db'));assert len(boards)==1
  assert not list(d.glob('*-wal')) and not list(d.glob('*-journal'))
  pins={p.name:sha(p)for p in (authority,*boards)}
  db=sqlite3.connect(authority.as_uri()+'?mode=ro&immutable=1',uri=True)
  try:
   operations=[list(r)for r in db.execute('SELECT state,count(*) FROM operations GROUP BY state ORDER BY state')]
   claims=db.execute('SELECT count(*) FROM claims').fetchone()[0]
   parents=[list(r)for r in db.execute('SELECT state,count(*) FROM pr_procedures GROUP BY state ORDER BY state')]
  finally:db.close()
  db=sqlite3.connect(boards[0].as_uri()+'?mode=ro&immutable=1',uri=True)
  try:
   receipts=[list(r)for r in db.execute('SELECT state,count(*) FROM io_receipts GROUP BY state ORDER BY state')]
   effects=list(db.execute('SELECT sum(activations),sum(completed),sum(canceled) FROM io_effects').fetchone())
   owners=db.execute('SELECT count(*) FROM io_owners').fetchone()[0]
  finally:db.close()
  assert pins=={p.name:sha(p)for p in (authority,*boards)}
  case=matrix['cases'][index]
  states.append(dict(caseIndex=index,caseId=case['caseId'],scenario=case.get('definition',{}).get('scenario','candidate'),
   operations=operations,claims=claims,parents=parents,receipts=receipts,effects=effects,owners=owners,databasePins=pins))
 rows.append(dict(groupStatus=group['status'],groupError=group['error'],completedCases=len(group['cases']),
  activeCaseId=group['accounting']['activeCaseId'],states=states))
out=dict(scope='Read-only closed synthetic state observations; no independent complete-history or qualification conclusion.',
 attempt=name,groups=rows,sourceDatabasesUnchanged=True)
with (folder/'state-audit.json').open('x')as f:f.write(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(attempt=name,groups=len(rows),states=sum(len(r['states'])for r in rows),active=[r['states'][-1]for r in rows if r['states']]),indent=2))

"""Split the exact timed-out75 selection; preserve all original execution bounds."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
R=Path.cwd();B=R/'artifacts/implementation/pat-io-clock-history';O=B/'harness11'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
assert sha(O/'index.json')=='89ba088508914ae7eece886821dd3dc72c8b16dbc10a628834ca9e3a1cd79f8f'
for row in read(O/'index.json')['files']:
 p=O/row['path'];assert p.stat().st_size==row['bytes']and sha(p)==row['sha256']
all_targets=read(O/'targets.json')['targets'];selected=[]
for number,module,count in [('13','configuration_history',48),('14','observation_history',27)]:
 H=B/('harness'+number);H.mkdir();(H/'references').mkdir();borrowed=[]
 for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(R).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed)
 targets=[t for t in all_targets if t.startswith('test_pat_io_'+module+'.')];assert len(targets)==count;selected+=targets
 write(H/'targets.json',dict(testCount=count,targets=targets))
 for item in ['run_attempt.py','attempt_child.py']:
  before=(O/item).read_text();after=before.replace('ClockHistory75','ClockHistory'+str(count)).replace('clock75','clock'+str(count))
  after=after.replace('!= 75','!= '+str(count)).replace('== 75','== '+str(count)).replace("'expectedTests': 75","'expectedTests': "+str(count))
  if item=='run_attempt.py':
   a=after.index("                sum(name.startswith('test_pat_io_configuration_history.")
   z=after.index(":\n            raise ValueError('Closed",a)
   after=after[:a]+"                sum(name.startswith('test_pat_io_"+module+".') for name in targets['targets']) != "+str(count)+')'+after[z:]
  ast.parse(after);(H/item).write_text(after);(H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(R).as_posix(),tofile=(H/item).relative_to(R).as_posix())))
 for item in ['README.md','SCOPE.md']:(H/item).write_text((O/item).read_text().replace('75 exact',str(count)+' exact'))
 review=read(O/'review.json');review.update(tests=count,targetSha256=sha(H/'targets.json'),reviewed=review['reviewed']+['Split only the exact75 target set after its retained180-second timeout. Source03, all test assertions and every acquisition/execution bound unchanged.'])
 write(H/'review.json',review)
 rows=[dict(path=p.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(H.rglob('*'))if p.is_file()]
 write(H/'index.json',dict(scope='Frozen smaller exact selection after timeout; original bounds retained.',files=rows));print(H.name,sha(H/'index.json'),sha(H/'targets.json'))
assert sorted(selected)==all_targets and len(set(selected))==75

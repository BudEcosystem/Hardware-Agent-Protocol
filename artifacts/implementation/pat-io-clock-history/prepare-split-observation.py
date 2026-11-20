"""Divide unchanged27 observation methods into interleaved14 and13 selections."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
R=Path.cwd();B=R/'artifacts/implementation/pat-io-clock-history';O=B/'harness14'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
assert sha(O/'index.json')=='c00d8e9493e0215252fa0b7fe844ed92b263c4cd5963dbcaa8d6e947e62d3885'
for row in read(O/'index.json')['files']:
 p=O/row['path'];assert p.stat().st_size==row['bytes']and sha(p)==row['sha256']
all_targets=read(O/'targets.json')['targets'];selected=[]
for number,start,count in [('15',0,14),('16',1,13)]:
 H=B/('harness'+number);H.mkdir();(H/'references').mkdir();borrowed=[]
 for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=O/item;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(R).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed)
 targets=all_targets[start::2];assert len(targets)==count;selected+=targets;write(H/'targets.json',dict(testCount=count,targets=targets))
 for item in ['run_attempt.py','attempt_child.py']:
  before=(O/item).read_text();after=before.replace('ClockHistory27','ClockHistory'+str(count)).replace('clock27','clock'+str(count)).replace('!= 27','!= '+str(count)).replace('== 27','== '+str(count)).replace("'expectedTests': 27","'expectedTests': "+str(count))
  ast.parse(after);(H/item).write_text(after);(H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/item).relative_to(R).as_posix(),tofile=(H/item).relative_to(R).as_posix())))
 for item in ['README.md','SCOPE.md']:(H/item).write_text((O/item).read_text().replace('27 exact',str(count)+' exact'))
 review=read(O/'review.json');review.update(tests=count,targetSha256=sha(H/'targets.json'),reviewed=review['reviewed']+['The observation-only27 selection also timed out. Interleave its exact unchanged methods into14 and13; no source, test assertion or bound changes.'])
 write(H/'review.json',review)
 rows=[dict(path=p.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(H.rglob('*'))if p.is_file()]
 write(H/'index.json',dict(scope='Smaller exact observation selection after retained timeout; original boundaries unchanged.',files=rows));print(H.name,sha(H/'index.json'),sha(H/'targets.json'))
assert sorted(selected)==all_targets and len(set(selected))==27

"""Seal all retained attempts, reviewed sources and reconciled project documents."""
import hashlib,json,shutil,stat
from pathlib import Path
ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-clock-history';OUT=BASE/'results'
DOCS=ROOT/'artifacts/verification/lifecycle-progress-links/attempt26-io-clock-history201'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,row):assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
folders=['attempt01-failed33','attempt02-failed33','attempt03-passed33','attempt04-passed73','attempt05-timeout75','attempt06-passed20','attempt07-passed48','attempt08-timeout27','attempt09-passed14','attempt10-passed13']
methods=[];expected_result_files=1
for folder,count in zip(folders,[33,33,33,73,75,20,48,27,14,13]):
 proof=read(OUT/folder/'proof.json');expected_result_files+=proof['attemptFilesAcquired']+2
 assert proof['rawScratchFiles']==proof['rawScratchBytes']==0
 if folder in {'attempt05-timeout75','attempt08-timeout27'}:
  assert proof['expectedTests']==count and proof['status']=='timed_out'and proof['counts']is None and proof['completeActualOriginEvidence']is False
  continue
 assert proof['counts']['testsRun']==count and proof['attemptFilesAcquired']==8056 and proof['sqliteConnections']==0
 if folder in {'attempt01-failed33','attempt02-failed33'}:
  assert proof['status']=='failed'and(proof['counts']['errors'],proof['counts']['failures'])==(2,1)
 else:
  assert proof['status']=='passed'and proof['counts']['errors']==proof['counts']['failures']==0
  methods+=read(BASE/proof['harness']/'targets.json')['targets']
assert len(methods)==len(set(methods))==201
rows=[]
for p in sorted(OUT.rglob('*')):
 assert not p.is_symlink()
 if p.is_dir():continue
 assert stat.S_ISREG(p.stat().st_mode)
 rows.append(dict(path=p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==expected_result_files,len(rows)
write(OUT/'index.json',dict(scope='Two semantic failures and two timeouts preserved;201 distinct tests pass in33+73+48+14+13+20 bounded pure runs. No full qualification or physical evidence.',files=rows))
sourcepins=['6fddf44b03d4910da1848f594a015f43d0df6b80d5d6cdbc0e7602c69d4d6d6b','c33c4ce245f95cf087201ffa7eedd5290a554f69aa5c2ad8301b5998d591a01e','f98de6d5d3c76335cb74032da5641750a21d6de37af8004f2738f0797aba5ff9']
harnesspins=['e965e3df5317b2c999ed0511b07b9ed1bc756c4eb217b37f249df7e4b3272179','b37ebb0c597fa9041935314af932fa88c2db092a5adc4d34442974faa313fa8e','4affca049614429875c8d6f193426424b6494bced4835b340ca9ef7598606a05','bc0af67a902a161e82b0b1ad2209c67d670efcdb2b98809531b066444280fb1f',
'2a96043e428e1779edf10701d68aeb1bf8e280b226d66e48176cf88c06216728','6804817a208183c9f168339d57fa5ab01ec8a5b37e7f1cce71a5d28686e9ec22','9d212b446610f2d462d4e08614cedec7997bd172cfad688c4eef50fbf605cb60','7fbe6b964a675198464fcbb0c4b6c5d9199a58dedcf433c2f2acc35037ce0d3f',
'5247016ccd4f26b233c0d46162b774d65bf1918ba5959575bac1350d0edcd2ec','e3821e99e485fa385eea7da2d0dc650f0ecaaa3155758cd2b0fb2dde678e6a6a','89ba088508914ae7eece886821dd3dc72c8b16dbc10a628834ca9e3a1cd79f8f','9fb7bf2001a07f62c5a363b0f48bc73d860eaba050ca00eb0ce5af0259980051','c2cc11b0a27908d4947a1b34e50dee56f6d8542d588203aea9897502a0e12cc5','c00d8e9493e0215252fa0b7fe844ed92b263c4cd5963dbcaa8d6e947e62d3885','bccbd18403fce3955fb9df3e1b8ac84f659764c4a8b7de6b070d2652fbf2e46a','2a88472bdfdce977042c89d46f833aa266ac22620b3bfdbe26200b0ec840a34f']
entries=[(BASE/f'implementation{i:02}',p,True)for i,p in enumerate(sourcepins,1)]+[(BASE/f'harness{i:02}',p,False)for i,p in enumerate(harnesspins,1)]+[(OUT,sha(OUT/'index.json'),False)]
counts={}
for folder,pin,rooted in entries:
 assert sha(folder/'index.json')==pin;rows=read(folder/'index.json')['files']
 for row in rows:verify((ROOT if rooted else folder)/row['path'],row)
 counts[folder.relative_to(ROOT).as_posix()]=len(rows)
assert sum(counts.values())==3*8025+16*12+expected_result_files,sum(counts.values())
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[]and report['project_markdown_files']==321
assert report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']
DOCS.mkdir()
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py','artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [(BASE/p).relative_to(ROOT).as_posix()for p in ['DESIGN.md','edit-components.py','prepare.py','prepare02.py','prepare03.py','prepare-split.py','prepare-split-observation.py','acquire-timeout27.py','acquire-timeout.py','acquire.py','reconcile-docs.py','finish-stage.py','receipt-key-correction.patch','start-exclusion-release-correction.patch','preparation-diagnostics/finish-stage.rejected.py']]
sources += [(f/'index.json').relative_to(ROOT).as_posix()for f,_,_ in entries]
copies=[]
for name in sources:
 p=ROOT/name;q=DOCS/'inputs'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
 row=dict(source=name,copy=q.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p));verify(q,row);copies.append(row)
write(DOCS/'index.json',dict(scope='201 distinct pure tests pass;6 exact clock expected responses checked;2 semantic failures and2 timeouts retained. Full matrix/current qualification and original goal remain incomplete.',
 markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],reportFileHashesVerified=len(report['files']),artifactEntriesReverified=counts,files=copies))
print(json.dumps(dict(results=dict(indexSha256=sha(OUT/'index.json'),files=expected_result_files),documents=dict(indexSha256=sha(DOCS/'index.json'),copies=len(copies),artifactEntriesVerified=sum(counts.values()),markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked']))))

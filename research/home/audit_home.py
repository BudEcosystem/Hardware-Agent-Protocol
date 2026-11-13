#!/usr/bin/env python3
"""Verify this retained corpus's integrity; never infer reading or conformance."""
from pathlib import Path, PurePosixPath
import hashlib, json, datetime
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'research/home'
checks=0

def digest(data): return hashlib.sha256(data).hexdigest()
def verify(path,expected):
 global checks
 data=(ROOT/path).read_bytes();assert digest(data)==expected,path;checks+=1;return data

def git_hash(kind,data): return hashlib.sha1(kind.encode()+b' '+str(len(data)).encode()+b'\0'+data).hexdigest()

def lf_lines(data):
 p=data.split(b'\n');return [x+b'\n' for x in p[:-1]]+([p[-1]] if p[-1] else [])

manifest=[json.loads(x) for x in (BASE/'manifest.jsonl').read_text().splitlines()]
assert len({x['id'] for x in manifest})==len(manifest)
for r in manifest:
 verify(r['raw_path'],r['sha256']);verify(r['text_path'],r['text_sha256'])

repositories=json.loads((BASE/'repos.json').read_text());tree_count=0;file_count=0
for r in repositories:
 commit=json.loads(verify(r['commit_metadata_path'],r['commit_metadata_sha256']))
 tree=json.loads(verify(r['tree_metadata_path'],r['tree_metadata_sha256']))
 assert commit['sha']==r['commit'] and commit['commit']['tree']['sha']==r['tree_sha']
 assert tree['sha']==r['tree_sha'] and not tree.get('truncated')
 entries={x['path']:x for x in tree['tree']}
 # Reconstruct each tree from all retained metadata entries, including the root.
 # Blob contents outside the selected files are neither acquired nor claimed read.
 children={}
 for x in tree['tree']:
  p=PurePosixPath(x['path']);parent='' if str(p.parent)=='.' else str(p.parent)
  children.setdefault(parent,[]).append(x)
 for parent,items in children.items():
  def order(x):return PurePosixPath(x['path']).name.encode()+ (b'/' if x['type']=='tree' else b'')
  payload=b''.join(x['mode'].lstrip('0').encode()+b' '+PurePosixPath(x['path']).name.encode()+b'\0'+bytes.fromhex(x['sha']) for x in sorted(items,key=order))
  expected=r['tree_sha'] if parent=='' else entries[parent]['sha']
  assert git_hash('tree',payload)==expected,(r['id'],parent);tree_count+=1
 for f in r['files']:
  data=verify(f['path'],f['sha256']);assert git_hash('blob',data)==f['git_blob_sha'],f['path']
  assert entries[f['repository_path']]['sha']==f['git_blob_sha']
  assert f['url']==r['repository'].replace('https://github.com/','https://raw.githubusercontent.com/')+'/'+r['commit']+'/'+f['repository_path']
  file_count+=1

reading=json.loads((BASE/'reading-home-full.json').read_text());chunk_count=0
for r in reading['sources']:
 verify(r['raw_path'],r['raw_sha256']);data=verify(r['text_path'],r['text_sha256']);lines=lf_lines(data);assert len(lines)==r['line_count'];covered=set()
 for c in r['coverage_ranges']:
  a,z=c['start_line'],c['end_line'];assert 1<=a<=z<=len(lines);assert digest(b''.join(lines[a-1:z]))==c['sha256'];covered.update(range(a,z+1));chunk_count+=1
 assert (covered==set(range(1,len(lines)+1)))==r['coverage_complete'],r['id']
 assert (r['reading_status']=='read_full')==r['coverage_complete']
out=dict(verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),acquisitions=len(manifest),repository_pins=len(repositories),snapshot_files=file_count,reconstructed_metadata_trees=tree_count,reading_records=len(reading['sources']),full_records=sum(x['coverage_complete'] for x in reading['sources']),selected_records=sum(not x['coverage_complete'] for x in reading['sources']),coverage_chunks=chunk_count,hash_checks=checks,warning='Local hashes and Git tree/blob identities verify retained bytes and stated provenance. GitHub HTTPS metadata links commits to trees; commit signatures were not independently validated. Reading coverage is reader-attested, not machine proof. No acquired source program or hardware interface was executed.')
out['inputs']={str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in [BASE/'manifest.jsonl',BASE/'repos.json',BASE/'reading-home-full.json',Path(__file__).resolve()]}
(BASE/'audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

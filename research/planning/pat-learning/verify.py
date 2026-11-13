#!/usr/bin/env python3
"""Offline integrity/declared-coverage check. Never imports or executes archived code."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib, json, re
from pathlib import Path
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
COMMIT='55e45a880755d0c8c66ca7fb5fe7962ac8974f89'
PAGES=[1,2,3,4,5,6,7,8,9,19,21,30,32,34,38,39,41,42]
REPO_PATHS=['README.md','voyager/voyager.py','voyager/agents/skill.py','voyager/agents/action.py','voyager/agents/critic.py','voyager/agents/curriculum.py','voyager/prompts/skill.txt','voyager/prompts/action_template.txt','voyager/prompts/critic.txt','voyager/prompts/curriculum_task_decomposition.txt','voyager/env/bridge.py','voyager/env/mineflayer/index.js','voyager/env/mineflayer/lib/skillLoader.js']
REPO_IDS={'repo-'+p.replace('/','--').replace('.','-') for p in REPO_PATHS}
FULL=REPO_IDS|{'voyager-arxiv-v2','voyager-project-retry'}
SELECTED={'voyager-arxiv-status':[(1,71)],'voyager-commit':[(1,48)],'voyager-tree':[(1,24)],'queue-lrll-status':[(1,85)],'queue-autoskill-status':[(1,85)],'queue-skillpp-status':[(1,85)]}
FAILED={'voyager-project':503,'voyager-publisher-record':429,'voyager-publisher':403}
def require(ok,message):
    if not ok:raise ValueError(message)
def digest(data):return hashlib.sha256(data).hexdigest()
def local(value):
    p=Path(value);absolute=(ROOT/p).resolve()
    require(not p.is_absolute() and absolute.is_relative_to(BASE),'Path outside owned lane')
    return absolute
def lf_lines(data):
    parts=data.split(b'\n')
    return [p+b'\n' for p in parts[:-1]]+([parts[-1]] if parts[-1] else [])
def checkhash(path,sha):
    require(isinstance(sha,str) and re.fullmatch('[0-9a-f]{64}',sha),'Malformed SHA-256')
    require(digest(local(path).read_bytes())==sha,'Hash mismatch: '+path)
def coverage(row):
    lines=lf_lines(local(row['text_path']).read_bytes())
    require(row['line_count']==len(lines),'LF count mismatch')
    require(type(row['coverage_complete']) is bool,'Bad complete flag')
    previous=0;seen=set()
    for c in row['coverage_ranges']:
        a,b=c['start_line'],c['end_line']
        require(type(a) is int and type(b) is int,'Bad range type')
        require(1<=a<=b<=len(lines) and a>previous,'Out of range, overlap, or disorder')
        require(digest(b''.join(lines[a-1:b]))==c['sha256'],'Bad coverage hash')
        seen.update(range(a,b+1));previous=b
    require(abs(row['text_coverage_fraction']-len(seen)/len(lines))<1e-12,'Bad coverage fraction')
    full=seen==set(range(1,len(lines)+1))
    require(row['coverage_complete']==full,'Incorrect full coverage claim')
    require((row['reading_status']=='read_full')==full,'Incorrect full status')
    return len(row['coverage_ranges']),len(seen)
def visual(sources,figures):
    pdf=next(s for s in sources if s['id']=='voyager-arxiv-v2')
    require(pdf['pdf_page_count']==42 and pdf['reviewed_pdf_pages']==PAGES and pdf['all_pdf_pages_reviewed'] is False,'Incorrect PDF visual scope')
    require([f['pdf_page'] for f in figures]==PAGES,'Incorrect figure page inventory')
    require(all(f['visual_review_status']=='reviewed_figures_tables_or_selected_code' for f in figures),'Unreviewed figure')
    labels=[x for f in figures for x in f['labels'] if x.startswith(('Figure','Table'))]
    expected=[f'Figure {n}' for n in range(1,11)]+[f'Figure A.{n}' for n in range(1,5)]+['Table 1','Table 2']+[f'Table A.{n}' for n in range(1,5)]
    require(sorted(labels)==sorted(expected),'Missing or duplicate figure/table')
def pincheck(pin):
    require(pin['commit']==COMMIT and pin['repository']=='https://github.com/MineDojo/Voyager','Wrong repository pin')
    tree=json.loads((BASE/'raw/voyager-tree.json').read_text())
    require(tree['sha']==COMMIT and not tree['truncated'],'Wrong/incomplete tree')
    entries={e['path']:e for e in tree['tree']}
    require({f['repository_path'] for f in pin['files']}==set(REPO_PATHS) and len(pin['files'])==13,'Wrong selected files')
    for f in pin['files']:
        b=local(f['path']).read_bytes(); blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        require(blob==f['git_blob_sha1']==entries[f['repository_path']]['sha'],'Git blob mismatch')
        require(len(b)==f['bytes']==entries[f['repository_path']]['size'],'Git size mismatch')
        checkhash(f['path'],f['sha256'])
def queuecheck(queue):
    require({q['arxiv_id'] for q in queue['papers']}=={'2406.18746','2603.01145','2611.00544'},'Queue mismatch')
    require(all(q['paper_read'] is False and q['implementation_read'] is False and q['status']=='metadata_only_selected' for q in queue['papers']),'Queue falsely promoted to paper read')
def main():
    manifest=[json.loads(l) for l in (BASE/'manifest.jsonl').read_text().splitlines()]
    reading=json.loads((BASE/'reading.json').read_text());pin=json.loads((BASE/'repository-pin.json').read_text());queue=json.loads((BASE/'queue.json').read_text())
    require(len(manifest)==24 and len({m['id'] for m in manifest})==24,'Acquisition inventory mismatch')
    acquired={m['id']:m for m in manifest if m['status']=='downloaded'}
    require(set(acquired)==FULL|set(SELECTED),'Acquired source inventory mismatch')
    failures={m['id']:m for m in manifest if m['status']=='failed'}
    require(set(failures)==set(FAILED),'Failure inventory mismatch')
    for k,v in FAILED.items():require(failures[k]['http_status']==v and failures[k].get('error'),'Failure record changed')
    hashes=0;files=set();chunks=0;lines_read=0
    for m in acquired.values():
        require(m['url'].startswith(('https://arxiv.org/','https://voyager.minedojo.org/','https://api.github.com/repos/MineDojo/Voyager/','https://raw.githubusercontent.com/MineDojo/Voyager/')),'Unexpected source')
        require(m['retrieved_at'] and m['source_version'] and m['http_status']==200,'Incomplete acquisition metadata')
        for pk,hk in [('raw_path','sha256'),('text_path','text_sha256')]:
            checkhash(m[pk],m[hk]);hashes+=1;files.add(m[pk])
        require(local(m['raw_path']).stat().st_size==m['bytes'],'Acquired size mismatch')
    require(reading['schema']=='hms-reading-overlay-v1','Wrong reading schema')
    sources=reading['sources'];require(len(sources)==21 and {s['id'] for s in sources}==set(acquired),'Reading inventory mismatch')
    for s in sources:
        m=acquired[s['id']]
        for k in ('url','final_url','retrieved_at','source_version','raw_path','text_path','text_sha256'):require(s[k]==m[k],'Manifest/reading mismatch '+k)
        require(s['raw_sha256']==m['sha256'],'Wrong source hash')
        c,n=coverage(s);chunks+=c;lines_read+=n;hashes+=c
        if s['id'] in SELECTED:
            require([(c['start_line'],c['end_line']) for c in s['coverage_ranges']]==SELECTED[s['id']],'Selected scope changed')
    require({s['id'] for s in sources if s['coverage_complete']}==FULL,'Full-reading set mismatch')
    require(next(s for s in sources if s['id']=='voyager-arxiv-v2')['line_count']==2553,'Paper line count changed')
    for r in reading['integrity_files']+reading['figures']:
        checkhash(r['path'],r['sha256']);hashes+=1;files.add(r['path'])
    require(len({r['path'] for r in reading['integrity_files']})==len(reading['integrity_files']),'Duplicate integrity file')
    visual(sources,reading['figures']);pincheck(pin);queuecheck(queue);hashes+=13
    require(reading['publisher_full_read'] is False and reading['broader_review_complete'] is False,'Unsupported completion claim')
    negatives=[]
    def reject(name,fn):
        try:fn()
        except ValueError:negatives.append(name);return
        raise AssertionError('Negative check passed: '+name)
    paper=next(s for s in sources if s['id']=='voyager-arxiv-v2')
    broken=deepcopy(paper);broken['coverage_ranges'].pop();reject('missing_full_tail',lambda:coverage(broken))
    bad=deepcopy(paper);bad['coverage_ranges'][0]['sha256']='0'*64;reject('coverage_hash',lambda:coverage(bad))
    overlap=deepcopy(paper);overlap['coverage_ranges'].insert(1,deepcopy(overlap['coverage_ranges'][0]));reject('overlap',lambda:coverage(overlap))
    outside=deepcopy(paper);outside['coverage_ranges'][-1]['end_line']+=1;reject('out_of_bounds',lambda:coverage(outside))
    disorder=deepcopy(paper);disorder['coverage_ranges'].reverse();reject('unordered',lambda:coverage(disorder))
    index=deepcopy(paper);index['coverage_ranges'][0]['start_line']=True;reject('boolean_index',lambda:coverage(index))
    fraction=deepcopy(paper);fraction['text_coverage_fraction']=0.5;reject('fraction',lambda:coverage(fraction))
    partial=deepcopy(next(s for s in sources if s['id']=='queue-lrll-status'));partial['coverage_complete']=True;partial['reading_status']='read_full';reject('metadata_false_full',lambda:coverage(partial))
    missing=deepcopy(reading['figures']);missing.pop();reject('missing_visual_page',lambda:visual(sources,missing))
    allpages=deepcopy(sources);next(s for s in allpages if s['id']=='voyager-arxiv-v2')['all_pdf_pages_reviewed']=True;reject('all_pages_overclaim',lambda:visual(allpages,reading['figures']))
    badpin=deepcopy(pin);badpin['files'][0]['git_blob_sha1']='0'*40;reject('git_blob',lambda:pincheck(badpin))
    badqueue=deepcopy(queue);badqueue['papers'][0]['paper_read']=True;reject('queue_paper_read',lambda:queuecheck(badqueue))
    reject('path_escape',lambda:local('../outside'))
    result={'schema':'hms-pat-learning-verification-v1','verified_at':datetime.now(timezone.utc).isoformat(),'status':'pass','manifest_sha256':digest((BASE/'manifest.jsonl').read_bytes()),'reading_sha256':digest((BASE/'reading.json').read_bytes()),'acquisition_records':24,'acquired_sources':21,'failed_attempts':3,'fully_read_sources':len(FULL),'selected_sources':len(SELECTED),'coverage_chunks':chunks,'lf_lines_read':lines_read,'selected_repository_files':13,'reviewed_pdf_pages':PAGES,'figure_count':14,'table_count':6,'hash_assertions':hashes,'distinct_files_checked':len(files),'negative_checks':negatives,'execution_scope':'Original offline archive validator only; no acquired research code, dependency, model, controller, simulator, firmware or hardware execution','limits':'Integrity and declared scope only; reading attestation is not independently provable by hashes. Publisher final paper and queued papers remain unread; broader review open.'}
    (BASE/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

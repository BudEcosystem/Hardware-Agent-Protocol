#!/usr/bin/env python3
"""Offline archive/declared-coverage verifier. Never imports or executes acquired code."""
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
COMMIT='25097958485a91450c3a15e5ba9023936180db4b'
FULL={'lrll-v2','lrll-publisher','lrll-project','author-homepage','website-README-md','website-index-html','website-prompts-py'}
SELECTED={'lrll-status':[(1,85)],'author-repositories':[(1,12)],'lrll-project-commit':[(1,48)],'lrll-institution-record':[(1,110)],'lrll-project-tree':[(1,45)]}
FAILED={'lrll-supplement-attempt':404,'lrll-code-link-attempt':404,'lrll-publisher-attempt':403}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def digest(data):return hashlib.sha256(data).hexdigest()
def local(value):
    p=Path(value);a=(ROOT/p).resolve();require(not p.is_absolute() and a.is_relative_to(BASE),'Path outside owned lane');return a
def lf_lines(data):
    x=data.split(b'\n');return [v+b'\n' for v in x[:-1]]+([x[-1]] if x[-1] else [])
def checkhash(path,sha):
    require(isinstance(sha,str) and re.fullmatch('[0-9a-f]{64}',sha),'Malformed SHA-256');require(digest(local(path).read_bytes())==sha,'Hash mismatch '+path)
def coverage(row):
    ls=lf_lines(local(row['text_path']).read_bytes());require(row['line_count']==len(ls),'LF count mismatch');require(type(row['coverage_complete']) is bool,'Bad complete type')
    seen=set();last=0
    for c in row['coverage_ranges']:
        a,z=c['start_line'],c['end_line'];require(type(a) is int and type(z) is int,'Bad range type');require(1<=a<=z<=len(ls) and a>last,'Range overlap/order/bounds')
        require(digest(b''.join(ls[a-1:z]))==c['sha256'],'Coverage hash mismatch');seen.update(range(a,z+1));last=z
    full=seen==set(range(1,len(ls)+1));require(row['coverage_complete']==full,'False coverage claim');require((row['reading_status']=='read_full')==full,'False reading status');require(abs(row['text_coverage_fraction']-len(seen)/len(ls))<1e-12,'Wrong coverage fraction')
    return len(row['coverage_ranges']),len(seen)
def visual(sources,figs):
    require(len(figs)==17,'Missing visual page')
    for ident,n in [('lrll-v2',8),('lrll-publisher',9)]:
        s=next(s for s in sources if s['id']==ident);fs=[f for f in figs if f['source_id']==ident]
        require(s['pdf_page_count']==n and s['reviewed_pdf_pages']==list(range(1,n+1)) and s['all_pdf_pages_reviewed'] is True,'False PDF scope')
        require([f['pdf_page'] for f in fs]==list(range(1,n+1)),'Wrong visual page inventory')
        require(all(f['visual_review_status']=='reviewed_full_page' and f['source_pdf_sha256']==s['raw_sha256'] for f in fs),'Unreviewed or wrong-source visual')
        labels=[l for f in fs for l in f['labels'] if l.startswith(('Figure','Table'))]
        require(sorted(labels)==sorted(['Figure 1','Figure 2','Figure 3','Figure 4','Table I','Table II']),'Missing/duplicate figure/table')
def scope(reading,pin,provenance):
    require(reading['publisher_full_read'] is True and reading['supplement_full_read'] is False and reading['implementation_complete'] is False and reading['broader_review_complete'] is False,'Unsupported completeness claim')
    require(pin['whole_repository_read'] is False and pin['core_orchestration_files_read']==0 and pin['prompt_source_files_read']==1,'Prompt-only source promoted to full implementation')
    require(provenance['identity']['arxiv']=='2406.18746v2' and provenance['identity']['doi']=='10.1109/ICRA57147.2024.10611448','Wrong paper identity')
    require(provenance['paper_scope']['appendices_in_acquired_papers']==0 and provenance['paper_scope']['supplement_read'] is False,'Unsupported appendix/supplement claim')
def pincheck(pin):
    require(pin['commit']==COMMIT and pin['repository']=='https://github.com/gtziafas/LRLL_project','Wrong pin')
    tree=json.loads((BASE/'raw/lrll-project-tree.json').read_text());commit=json.loads((BASE/'raw/lrll-project-commit.json').read_text());require(tree['sha']==COMMIT and tree['truncated'] is False and commit['sha']==COMMIT and pin['tree_sha']==commit['commit']['tree']['sha'],'Wrong/incomplete tree')
    entries={e['path']:e for e in tree['tree']};require({f['repository_path'] for f in pin['files']}=={'README.md','index.html','prompts.py'} and len(pin['files'])==3,'Wrong selected files')
    for f in pin['files']:
        b=local(f['path']).read_bytes();blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest();require(blob==f['git_blob_sha1']==entries[f['repository_path']]['sha'],'Git blob mismatch');require(len(b)==f['bytes']==entries[f['repository_path']]['size'],'Git size mismatch');checkhash(f['path'],f['sha256'])
    require((BASE/'repository/website-index-html.html').read_bytes()==(BASE/'raw/lrll-project.html').read_bytes(),'Project live snapshot differs from pinned HTML')
def projections():
    rs=json.loads((BASE/'raw/author-repositories.json').read_text());require(len(rs)==38,'Discovery count changed')
    expected='\n'.join(json.dumps({k:r[k] for k in ('full_name','description','html_url','homepage','fork')},ensure_ascii=False) for r in rs)+'\n'
    require((BASE/'notes/author-repository-inventory.txt').read_text()==expected,'Wrong author projection')
    tree=json.loads((BASE/'raw/lrll-project-tree.json').read_text());require((BASE/'notes/project-tree-inventory.txt').read_text()=='\n'.join(e['path'] for e in tree['tree'])+'\n','Wrong tree projection')
def comparison():
    d=json.loads((BASE/'notes/paper-comparison.json').read_text());a=(BASE/'text/lrll-v2-reading-order.txt').read_text();b=(BASE/'text/lrll-publisher-reading-order.txt').read_text().split('\f',1)[1]
    for pattern in d['removed_patterns']:a=re.sub(pattern,'',a,flags=re.M);b=re.sub(pattern,'',b,flags=re.M)
    ac,bc=Counter(a.split()),Counter(b.split());require(d['equivalence_claim'] is False,'Unjustified version equivalence');require(dict(ac-bc)==d['arxiv_only_tokens'] and dict(bc-ac)==d['publisher_only_tokens'],'Comparison mismatch');require(sum(ac.values())==d['arxiv_token_count']==7403 and sum(bc.values())==d['publisher_token_count']==7403,'Comparison token count')
def main():
    manifest=[json.loads(x) for x in (BASE/'manifest.jsonl').read_text().splitlines()];reading=json.loads((BASE/'reading.json').read_text());pin=json.loads((BASE/'repository-pin.json').read_text());provenance=json.loads((BASE/'provenance.json').read_text())
    require(len(manifest)==15 and len({m['id'] for m in manifest})==15,'Wrong acquisition inventory');acquired={m['id']:m for m in manifest if m['status']=='downloaded'};require(set(acquired)==FULL|set(SELECTED),'Wrong acquired inventory')
    failed={m['id']:m for m in manifest if m['status']=='failed'};require(set(failed)==set(FAILED),'Wrong failure inventory')
    for k,v in FAILED.items():require(failed[k]['http_status']==v and failed[k].get('error'),'Missing failed attempt')
    hashes=0;files=set();chunks=0;source_lines=0;additional_lines=0
    for m in acquired.values():
        require(m['http_status']==200 and m['retrieved_at'] and m['source_version'],'Missing provenance');require(m['url'].startswith(('https://arxiv.org/','https://gtziafas.github.io/','https://api.github.com/users/gtziafas/','https://api.github.com/repos/gtziafas/LRLL_project/','https://raw.githubusercontent.com/gtziafas/LRLL_project/','https://research.rug.nl/','https://pure.rug.nl/')),'Unexpected source')
        for pk,hk in [('raw_path','sha256'),('text_path','text_sha256')]:checkhash(m[pk],m[hk]);hashes+=1;files.add(m[pk])
        require(local(m['raw_path']).stat().st_size==m['bytes'],'Acquired size mismatch')
    sources=reading['sources'];require(reading['schema']=='hms-reading-overlay-v1' and len(sources)==12 and {s['id'] for s in sources}==set(acquired),'Wrong reading inventory')
    for s in sources:
        m=acquired[s['id']]
        for k in ('url','final_url','retrieved_at','source_version','raw_path','text_path','text_sha256'):require(s[k]==m[k],'Manifest/reading mismatch')
        require(s['raw_sha256']==m['sha256'],'Wrong source hash');c,n=coverage(s);chunks+=c;source_lines+=n;hashes+=c
        if s['id'] in SELECTED:require([(r['start_line'],r['end_line']) for r in s['coverage_ranges']]==SELECTED[s['id']],'Changed selected scope')
    require({s['id'] for s in sources if s['coverage_complete']}==FULL,'Wrong full-reading inventory')
    for ident,n in [('lrll-v2',529),('lrll-publisher',622),('website-prompts-py',248)]:require(next(s for s in sources if s['id']==ident)['line_count']==n,'Wrong paper/prompt length')
    for row in reading['integrity_files']+reading['figures']:
        checkhash(row['path'],row['sha256']);hashes+=1;files.add(row['path'])
        if row.get('coverage_ranges'):c,n=coverage(row);chunks+=c;additional_lines+=n;hashes+=c
    require(len(reading['integrity_files'])==16 and len({r['path'] for r in reading['integrity_files']})==16,'Wrong integrity inventory')
    visual(sources,reading['figures']);scope(reading,pin,provenance);pincheck(pin);projections();comparison();hashes+=3
    negatives=[]
    def reject(name,fn):
        try:fn()
        except ValueError:negatives.append(name);return
        raise AssertionError('Negative fixture accepted: '+name)
    paper=next(s for s in sources if s['id']=='lrll-v2')
    bad=deepcopy(paper);bad['coverage_ranges'].pop();reject('missing_full_tail',lambda:coverage(bad))
    bad=deepcopy(paper);bad['coverage_ranges'][0]['sha256']='0'*64;reject('bad_coverage_hash',lambda:coverage(bad))
    bad=deepcopy(paper);bad['coverage_ranges'].insert(1,deepcopy(bad['coverage_ranges'][0]));reject('overlap',lambda:coverage(bad))
    bad=deepcopy(paper);bad['coverage_ranges'].reverse();reject('unordered',lambda:coverage(bad))
    bad=deepcopy(paper);bad['coverage_ranges'][-1]['end_line']+=1;reject('out_of_bounds',lambda:coverage(bad))
    bad=deepcopy(paper);bad['coverage_ranges'][0]['start_line']=True;reject('boolean_index',lambda:coverage(bad))
    bad=deepcopy(paper);bad['text_coverage_fraction']=.5;reject('bad_fraction',lambda:coverage(bad))
    bad=deepcopy(next(s for s in sources if s['id']=='lrll-status'));bad['coverage_complete']=True;bad['reading_status']='read_full';reject('metadata_false_full',lambda:coverage(bad))
    figs=deepcopy(reading['figures']);figs.pop();reject('missing_visual_page',lambda:visual(sources,figs))
    figs=deepcopy(reading['figures']);figs[0]['source_pdf_sha256']='0'*64;reject('wrong_visual_source',lambda:visual(sources,figs))
    figs=deepcopy(reading['figures']);figs[0]['labels']=[];reject('missing_figure_label',lambda:visual(sources,figs))
    bp=deepcopy(pin);bp['files'][0]['git_blob_sha1']='0'*40;reject('git_blob',lambda:pincheck(bp))
    bp=deepcopy(pin);bp['whole_repository_read']=True;reject('full_repository_overclaim',lambda:scope(reading,bp,provenance))
    br=deepcopy(reading);br['supplement_full_read']=True;reject('supplement_overclaim',lambda:scope(br,pin,provenance))
    br=deepcopy(reading);br['implementation_complete']=True;reject('implementation_overclaim',lambda:scope(br,pin,provenance))
    br=deepcopy(reading);br['broader_review_complete']=True;reject('literature_overclaim',lambda:scope(br,pin,provenance))
    prov=deepcopy(provenance);prov['identity']['arxiv']='2305.16291';reject('wrong_paper_identity',lambda:scope(reading,pin,prov))
    reject('path_escape',lambda:local('../outside'))
    result={'schema':'hms-lrll-full-verification-v1','status':'pass','verified_at':datetime.now(timezone.utc).isoformat(),'manifest_sha256':digest((BASE/'manifest.jsonl').read_bytes()),'reading_sha256':digest((BASE/'reading.json').read_bytes()),'acquisition_records':15,'acquired_sources':12,'failed_attempts':3,'fully_read_sources':7,'selected_sources':5,'source_lf_lines_read':source_lines,'additional_full_html_and_projected_inventory_lf_lines':additional_lines,'lf_lines_read':source_lines+additional_lines,'coverage_chunks':chunks,'selected_repository_files':3,'prompt_source_files':1,'core_orchestration_files':0,'reviewed_pdf_pages':{'arxiv':8,'publisher_with_cover':9},'distinct_numbered_figures':4,'distinct_numbered_tables':2,'hash_assertions':hashes,'distinct_files_checked':len(files),'negative_checks':negatives,'execution_scope':provenance['execution_scope'],'limits':'Hashes verify retained integrity and scope consistency, not proof of human/model reading or scientific reproduction. Separate supplement and core implementation remain unavailable; broader review open.'}
    (BASE/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

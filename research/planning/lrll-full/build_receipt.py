#!/usr/bin/env python3
"""Construct this lane's reading attestation from already reviewed, retained bytes.

Original archive utility only. Does not acquire, import, or execute research code.
Coverage intervals below record actual reading; this script cannot prove reading.
"""
import hashlib,json
from pathlib import Path
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
COMMIT='25097958485a91450c3a15e5ba9023936180db4b'
def sha(data):return hashlib.sha256(data).hexdigest()
def rel(p):return str(p.relative_to(ROOT))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def lines(data):
    x=data.split(b'\n');return [y+b'\n' for y in x[:-1]]+([x[-1]] if x[-1] else [])
def coverage(p,ranges):
    ls=lines(p.read_bytes());count=sum(z-a+1 for a,z in ranges);full=count==len(ls)
    return {'text_path':rel(p),'text_sha256':sha(p.read_bytes()),'line_count':len(ls),'coverage_ranges':[{'start_line':a,'end_line':z,'sha256':sha(b''.join(ls[a-1:z]))} for a,z in ranges],'coverage_complete':full,'text_coverage_fraction':count/len(ls),'reading_status':'read_full' if full else 'read_selected'}
def main():
    manifest=[json.loads(x) for x in (BASE/'manifest.jsonl').read_text().splitlines()]
    acquired={m['id']:m for m in manifest if m['status']=='downloaded'}
    tree=json.loads((BASE/'raw/lrll-project-tree.json').read_text())
    entries={e['path']:e for e in tree['tree']}
    repo=[]
    for path in ['README.md','index.html','prompts.py']:
        m=acquired['website-'+path.replace('.','-')]
        repo.append({'repository_path':path,'path':m['raw_path'],'sha256':m['sha256'],'bytes':m['bytes'],'git_blob_sha1':entries[path]['sha'],'scope':'complete prompt artifact' if path=='prompts.py' else 'complete website file'})
    write(BASE/'repository-pin.json',{'repository':'https://github.com/gtziafas/LRLL_project','commit':COMMIT,'tree_sha':json.loads((BASE/'raw/lrll-project-commit.json').read_text())['commit']['tree']['sha'],'repository_role':'official project website with one prompt artifact; not identified full research implementation','whole_repository_read':False,'core_orchestration_files_read':0,'prompt_source_files_read':1,'files':repo})
    repos=json.loads((BASE/'raw/author-repositories.json').read_text())
    (BASE/'notes/author-repository-inventory.txt').write_text('\n'.join(json.dumps({k:r[k] for k in ('full_name','description','html_url','homepage','fork')},ensure_ascii=False) for r in repos)+'\n')
    (BASE/'notes/project-tree-inventory.txt').write_text('\n'.join(e['path'] for e in tree['tree'])+'\n')
    write(BASE/'provenance.json',{'schema':'hms-lrll-provenance-v1','identity':{'title':'Lifelong Robot Library Learning: Bootstrapping Composable and Generalizable Skills for Embodied Control with Language Models','authors':['Georgios Tziafas','Hamidreza Kasaei'],'arxiv':'2406.18746v2','arxiv_revision_date':'2024-07-15','doi':'10.1109/ICRA57147.2024.10611448','publication':'ICRA 2024, pages 515–522'},'primary_discovery':['https://arxiv.org/abs/2406.18746','https://gtziafas.github.io/LRLL_project/','https://research.rug.nl/en/publications/lifelong-robot-library-learning-bootstrapping-composable-and-gene/','https://api.github.com/users/gtziafas/repos?per_page=100&sort=full_name'],'paper_scope':{'arxiv_pages':8,'publisher_pdf_pages':9,'publisher_body_pages':8,'publisher_extra':'Institutional cover','appendices_in_acquired_papers':0,'supplement_read':False,'unique_numbered_figures':4,'unique_numbered_tables':2,'all_acquired_pdf_pages_visually_reviewed':True,'manuscript_publisher_byte_equivalence':False,'comparison':'notes/paper-comparison.json; token diagnostic ignores order, not an equivalence proof'},'repository_scope':{'commit':COMMIT,'selected_complete_files':3,'prompt_source_files':1,'core_orchestration_files':0,'whole_repository_read':False,'implementation_complete':False,'discovery_limit':'38 public author-account repository entries projected to name/description/homepage; only relevant project tree and three selected files examined. Does not prove absence of another implementation.'},'gaps':[{'id':'lrll-supplement-attempt','status':404,'meaning':'Official project linked supplementary PDF unavailable; not read'},{'id':'lrll-code-link-attempt','status':404,'meaning':'Official project Code href is YOUR REPO HERE placeholder; no core implementation inferred'},{'id':'lrll-publisher-attempt','status':403,'meaning':'Institution-linked files endpoint rejected; ordinary public pure.rug.nl repository endpoint later succeeded'}],'empty_acquisition':'Author homepage HTTP 200 response contains only one LF; no biographical or implementation evidence','license_context':'arXiv status links CC BY 4.0; website says CC BY-SA 4.0; publisher institutional cover identifies Taverne and retained copyright. Website notice is not relabeled as publisher license.','execution_scope':'Only original acquisition, extraction, rendering, comparison and archive validation utilities; no acquired source imports, execution, compilation, model, simulator, controller, MCU or hardware','broader_review_complete':False})
    selected={'lrll-status':[(1,85)],'author-repositories':[(1,12)],'lrll-project-commit':[(1,48)],'lrll-institution-record':[(1,110)],'lrll-project-tree':[(1,45)]}
    chunks={'lrll-v2':[(1,235),(236,420),(421,529)],'lrll-publisher':[(1,210),(211,420),(421,622)]}
    sources=[]
    for m in acquired.values():
        p=ROOT/m['text_path']; ranges=selected.get(m['id'],chunks.get(m['id'],[(1,len(lines(p.read_bytes())))]))
        s={k:m[k] for k in ['id','url','final_url','retrieved_at','source_version','raw_path']};s['raw_sha256']=m['sha256'];s.update(coverage(p,ranges))
        s['source_kind']='selected_prompt_source' if m['id']=='website-prompts-py' else 'primary_research_or_metadata'
        s['note']='Coverage applies to retained LF extraction only. Acquisition of unmarked remainder is not reading.'
        if m['id']=='website-index-html':s['note']='Full visible text; complete raw HTML reading is separately recorded under integrity_files.'
        if m['id']=='author-homepage':s['note']='One LF only. Full byte reading of an empty response gives no substantive homepage evidence.'
        if m['id'] in chunks:
            n=8 if m['id']=='lrll-v2' else 9;s.update(pdf_page_count=n,all_pdf_pages_reviewed=True,reviewed_pdf_pages=list(range(1,n+1)),appendices_present=0)
            s['note']='Full LF text including final form feed and all references; every PDF page visually reviewed. Publisher PDF includes institutional cover. Unavailable separate supplement not read.'
        sources.append(s)
    integrity=[]
    names=['README.md','acquire.py','build_receipt.py','verify.py','manifest.jsonl','repository-pin.json','provenance.json','notes/critique.md','notes/figures.md','notes/paper-comparison.json','notes/paper-comparison-initial.json','text/lrll-v2-reading-order.txt','text/lrll-publisher-reading-order.txt','notes/author-repository-inventory.txt','notes/project-tree-inventory.txt','repository/website-index-html.html']
    for name in names:
        p=BASE/name;r={'path':rel(p),'sha256':sha(p.read_bytes())}
        if name in ['notes/author-repository-inventory.txt','notes/project-tree-inventory.txt','repository/website-index-html.html']:
            r.update(coverage(p,[(1,len(lines(p.read_bytes())))]));r['note']='Full projected inventory or complete selected raw HTML, separately reviewed; not full source JSON or asset dependency audit.'
        integrity.append(r)
    figs=[]
    arxiv_labels={1:['Figure 1'],3:['Figure 2','Unnumbered retrieval equation'],5:['Table I','Table II'],6:['Figure 3','Figure 4']}
    for ident,n,offset in [('lrll-v2',8,0),('lrll-publisher',9,1)]:
        for page in range(1,n+1):
            p=BASE/f'figures/{ident}-page-{page:02d}.png';figs.append({'source_id':ident,'pdf_page':page,'path':rel(p),'sha256':sha(p.read_bytes()),'source_pdf_sha256':acquired[ident]['sha256'],'labels':arxiv_labels.get(page-offset,[]),'visual_review_status':'reviewed_full_page','note':'Figure/table count deduplicates the two versions; all PDF pages viewed.'})
    write(BASE/'reading.json',{'schema':'hms-reading-overlay-v1','review_date':'2026-11-07','scope':'Full arXiv v2 and institution-hosted publisher paper; all PDF pages visual; three complete selected website/prompt files. Selected metadata and projected discovery inventories. No full core implementation/dependency audit.','publisher_full_read':True,'supplement_full_read':False,'implementation_complete':False,'broader_review_complete':False,'sources':sources,'integrity_files':integrity,'figures':figs})
if __name__=='__main__':main()

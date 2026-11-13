#!/usr/bin/env python3
"""Encode already-performed reading; acquisition is not a reading claim."""
import hashlib,json
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
def sha(b):return hashlib.sha256(b).hexdigest()
def lf(b):
 p=b.split(b'\n');return [x+b'\n' for x in p[:-1]]+([p[-1]] if p[-1] else [])
def write(name,value):(BASE/name).write_text(json.dumps(value,indent=2)+'\n')
manifest=[json.loads(l) for l in (BASE/'manifest.jsonl').read_text().splitlines()]
commit='55e45a880755d0c8c66ca7fb5fe7962ac8974f89';tree={e['path']:e for e in json.loads((BASE/'raw/voyager-tree.json').read_text())['tree']}
pin={'schema':'hms-selected-repository-pin-v1','repository':'https://github.com/MineDojo/Voyager','commit':commit,'commit_date':'2023-07-27T07:35:42Z','whole_repository_read':False,'dependencies_read':False,'code_executed':False,'files':[]}
for m in manifest:
 if m['id'].startswith('repo-'):
  p=m['url'].split(commit+'/')[1];pin['files'].append({'repository_path':p,'path':m['raw_path'],'sha256':m['sha256'],'bytes':m['bytes'],'git_blob_sha1':tree[p]['sha'],'read_full_file':True})
write('repository-pin.json',pin)
write('queue.json',{'scope':'Selected official abstract/status metadata only; no full papers, figures, appendices, or implementations read. These records are research leads, not validated results.','papers':[{'arxiv_id':i,'url':'https://arxiv.org/abs/'+i,'title':title,'observed_version':version,'status':'metadata_only_selected','paper_read':False,'implementation_read':False,'question_for_full_reading':q} for i,title,version,q in [('2406.18746','Lifelong Robot Library Learning: Bootstrapping Composable and Generalizable Skills for Embodied Control with Language Models','v2, 2024-07-15','How are experiences abstracted/promoted and what inference remains during reuse?'),('2603.01145','AutoSkill: Experience-Driven Lifelong Learning via Skill Self-Evolution','v2, 2026-03-05','Distinguish injected guidance for future LLM calls from executable, bounded, inference-free procedures.'),('2611.00544','Skill++: Towards Lifelong Agents via Routing-Aware Skill Refinement','v1, submitted 2026-10-31','Study routing interference, body/metadata mismatch and abstention; abstract explicitly concerns LLM routers, not deterministic selection.')]]})
selected={'voyager-arxiv-status':[(1,71)],'voyager-commit':[(1,48)],'voyager-tree':[(1,24)],'queue-lrll-status':[(1,85)],'queue-autoskill-status':[(1,85)],'queue-skillpp-status':[(1,85)]}
paper_ranges=[(1,330),(331,700),(701,1080),(1081,1460),(1461,1850),(1851,2240),(2241,2553)]
reading={'schema':'hms-reading-overlay-v1','review_date':'2026-11-07','scope':'Complete arXiv v2 LF text and selected visual corroboration; complete official project visible text; thirteen complete selected source files; selected metadata only. No full repository or dependency audit.','publisher_full_read':False,'broader_review_complete':False,'sources':[],'figures':[],'integrity_files':[]}
for m in manifest:
 if m['status']!='downloaded':continue
 lines=lf((ROOT/m['text_path']).read_bytes()); n=len(lines)
 ranges=paper_ranges if m['id']=='voyager-arxiv-v2' else selected.get(m['id'],[(1,n)])
 full=m['id'] not in selected
 s={k:m[k] for k in ('id','url','final_url','retrieved_at','source_version','raw_path','text_path','text_sha256')}
 s.update(raw_sha256=m['sha256'],source_kind='selected_repository_file' if m['id'].startswith('repo-') else 'primary_research_or_metadata',line_count=n,coverage_ranges=[{'start_line':a,'end_line':b,'sha256':sha(b''.join(lines[a-1:b]))} for a,b in ranges],coverage_complete=full,text_coverage_fraction=sum(b-a+1 for a,b in ranges)/n,reading_status='read_full' if full else 'read_selected',note='Full selected source only; not its links/dependencies.' if full else 'Selected metadata coverage; acquisition of remainder does not imply reading. Queued papers themselves are not acquired or read.')
 if m['id']=='voyager-arxiv-v2':s.update(pdf_page_count=42,all_pdf_pages_reviewed=False,reviewed_pdf_pages=[1,2,3,4,5,6,7,8,9,19,21,30,32,34,38,39,41,42],note='Full LF text including final form-feed line, references and both appendices; all numbered figures/tables visually corroborated on selected pages. No publisher-final claim.')
 reading['sources'].append(s)
labels={1:['Figure 1'],2:['Figure 2'],3:['Figure 3'],4:['Figure 4'],5:['Figure 5'],6:['Figure 6'],7:['Table 1','Figure 7'],8:['Table 2','Figure 8'],9:['Figure 9','Figure 10'],19:['Pseudocode 1'],21:['Table A.1'],30:['Prompt 4 loop prohibition'],32:['Skill example 1 stale local choice'],34:['Skill example 5 unbounded retries'],38:['Table A.2'],39:['Table A.3','Figure A.1'],41:['Figure A.2'],42:['Figure A.3','Table A.4','Figure A.4']}
for p,l in labels.items():
 f=BASE/f'figures/arxiv-v2-page-{p:02}.png';reading['figures'].append({'path':str(f.relative_to(ROOT)),'sha256':sha(f.read_bytes()),'source_id':'voyager-arxiv-v2','pdf_page':p,'labels':l,'visual_review_status':'reviewed_figures_tables_or_selected_code','render_command':f'pdftoppm -f {p} -l {p} -singlefile -scale-to 1600 -png raw/voyager-arxiv-v2.pdf figures/arxiv-v2-page-{p:02}'})
for name in ['README.md','manifest.jsonl','acquire.py','build_reading.py','verify.py','repository-pin.json','queue.json','notes/critique.md','notes/figures.md']:
 p=BASE/name;reading['integrity_files'].append({'path':str(p.relative_to(ROOT)),'sha256':sha(p.read_bytes())})
write('reading.json',reading)
print('Full sources',sum(s['coverage_complete'] for s in reading['sources']),'Full LF',sum(s['line_count'] for s in reading['sources'] if s['coverage_complete']))

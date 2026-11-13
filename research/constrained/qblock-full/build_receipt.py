#!/usr/bin/env python3
"""Record already completed bounded reading; does not itself constitute reading."""
from datetime import datetime, timezone
import hashlib,json,re,subprocess,sys
from pathlib import Path
import bs4,requests
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
def sha(b): return hashlib.sha256(b).hexdigest()
def rel(p): return str(p.relative_to(ROOT))
def lf_lines(b):
 p=b.split(b'\n')
 return [x+b'\n' for x in p[:-1]]+([p[-1]] if p[-1] else [])
def write(name,data):
 (BASE/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
manifest=[json.loads(s) for s in (BASE/'manifest.jsonl').read_text().splitlines()]
ranges={'rfc9177-text':[(1,270),(271,550),(551,830),(831,1110),(1111,1390),(1391,1670),(1671,1940),(1941,2154)],
 'rfc9177-metadata':[(1,43)],'rfc9177-errata':[(1,58)],'iana-options':[(1,63)],
 'iana-content-formats':[(1,156)],'iana-missing-blocks':[(1,39)],'iana-core-status':[(1,32)],'rfc9177-pdf':[]}
notes={
 'rfc9177-text':'Full LF-bounded reading of the published RFC, all 20 figures, five tables, references, Appendices A/B, acknowledgments and addresses; target works of references not implied read.',
 'rfc9177-pdf':'Complete PDF acquired and text extracted for inventory; selected figure/table pages visually inspected. No full PDF text read or all-pages visual review claim. Complete RFC semantic reading is recorded against the official TXT.',
 'rfc9177-metadata':'Complete current official metadata JSON read via pretty-printed text; metadata does not replace the independent errata query.',
 'rfc9177-errata':'Complete all-status official errata search text read, including no matching errata result; original URL redirects to official errata site.',
 'iana-core-status':'Entire broad registry acquired; only first 32 LF lines read for identity and update date. Relevant allocations independently fully read in the two CSV snapshots. Other registry sections and linked references not claimed read.',
 'iana-options':'Entire official CoAP Option Numbers CSV read, including Q-Block1 19, Q-Block2 31 and relevant associated options; referenced specifications not implied read.',
 'iana-content-formats':'Entire official CoAP Content-Formats CSV read, including application/missing-blocks+cbor-seq 272; referenced specifications not implied read.',
 'iana-missing-blocks':'Complete official media registration read, including CBOR Sequence encoding, usage and RFC reference.'}
source_kinds={'rfc9177-text':'published_rfc','rfc9177-pdf':'published_rfc_pdf','rfc9177-metadata':'official_metadata','rfc9177-errata':'official_errata','iana-core-status':'official_registry','iana-options':'official_registry','iana-content-formats':'official_registry','iana-missing-blocks':'official_media_registration'}
textlines=lf_lines((BASE/'text/rfc9177-text.txt').read_bytes())
text=[line.decode('utf-8').rstrip('\r\n') for line in textlines]
items=[]
for i,line in enumerate(text):
 m=re.match(r'^\s*(Figure|Table) (\d+):\s*(.*)',line)
 if m:
  continuation=[]; j=i+1
  while j<len(text) and text[j].strip(): continuation.append(text[j].strip());j+=1
  items.append(dict(kind=m[1],number=int(m[2]),caption=f'{m[1]} {m[2]}: '+ ' '.join([m[3]]+continuation),start_line=i+1,end_line=j))
sections=[dict(line=i+1,title=line) for i,line in enumerate(text) if re.match(r'^(?:\d+(?:\.\d+)*\. |Appendix [AB]\.|Acknowledgments$|Authors\x27 Addresses$)',line)]
write('notes/content-inventory.json',dict(source_text=rel(BASE/'text/rfc9177-text.txt'),lf_lines=len(textlines),sections=sections,figures_tables=items,appendices=['A','B'],coverage='Complete TXT; all figure/table bodies included in full ranges.'))
observations={
'Table 1':'Verified options 19/31, critical and unsafe flags, Q-Block2 repeatable flag, uint length 0–3 and no default.',
'Table 2':'Verified both Q-Block options marked E and U; Inner and Outer scopes are independent.',
'Figure 1':'Verified nonempty missing-number group CDDL; the surrounding text clarifies CBOR Sequence without an array wrapper.',
'Table 3':'Verified defaults 10, 4, 2 s, 2–3 s, 4 s, 247–248 s, 247 s and formula context.',
'Figure 2':'Four NON request blocks carry one Request-Tag and separate tokens; final response follows receipt of all four.',
'Figure 3':'After ten request payloads, 2.31 enables the eleventh; final 2.04 follows the complete body.',
'Figure 4':'Loss arrows remove blocks 1/9 and next-set block 10; later block 11 reveals missing previous-set data.',
'Figure 5':'Missing 1/9 requested together; later missing 10 recovered after final-number block already arrived; final response then occurs.',
'Figure 6':'Retry wait markers grow 1/2/4/8/16 times NON_RECEIVE_TIMEOUT, ending in partial-body release.',
'Figure 7':'All original notification blocks share token, ETag and Observe; the next representation changes ETag/Observe.',
'Figure 8':'Continue uses a new request token but subsequent notification remains on original token with Observe.',
'Figure 9':'Two lost blocks requested together; recovery responses use recovery token and omit Observe; one block requires another attempt.',
'Figure 10':'M=1 at block 2 requests remaining set, then block 10 Continue resumes original notification token/Observe.',
'Figure 11':'FETCH request body has one Request-Tag; returned/observed response bodies have separate ETags and original response token.',
'Figure 12':'Both directions exceed MAX_PAYLOADS; response Continue retains token 0xaa across response sets.',
'Figure 13':'Two FETCH request blocks lost before wait; remaining blocks alone do not complete request body.',
'Figure 14':'Server recovery fills missing request blocks before response transmission; response block loss remains independently recoverable.',
'Figure 15':'Response recovery FETCH carries tag without original body; recovery tokens differ from original observation token.',
'Table 4':'Verified IANA option assignments Q-Block1 19 and Q-Block2 31.',
'Table 5':'Verified Content-Format 272 for missing-blocks CBOR sequence, no content encoding.',
'Figure 16':'NSTART=3 gates CON sends; empty ACKs differ from final 2.04.',
'Figure 17':'Lost CON requests retry with original MID/token and exponential backoff; failure remains possible.',
'Figure 18':'CON notifications individually ACKed; NSTART and lost-response retries visible; no physical completion semantics.',
'Figure 19':'Reliable request has no UDP MID/type/ACK; only final method result follows request body.',
'Figure 20':'Reliable Observe response bodies carry distinct ETags; no UDP per-message acknowledgments.'}
by_label={f"{x['kind']} {x['number']}":x for x in items}
page_text=(BASE/'text/rfc9177-pdf.txt').read_text().split('\f')
figures=[]
for p,page in enumerate(page_text,1):
 labels=re.findall(r'\b((?:Figure|Table) \d+):',page)
 if labels:
  image=BASE/'figures'/f'rfc9177-page-{p:02}.png'
  figures.append(dict(path=rel(image),sha256=sha(image.read_bytes()),source_id='rfc9177-pdf',pdf_page=p,
   captions=[by_label[label]['caption'] for label in labels],visual_review_status='reviewed_figures_and_tables',
   render_method='pdftoppm -f PAGE -l PAGE -scale-to 1400 -png -singlefile',
   scope='Selected PDF page containing specified figures/tables, visually inspected; not all-PDF review.',
   observations=[observations[label] for label in labels]))
write('notes/figure-inventory.json',figures)
pages=[f['pdf_page'] for f in figures]
sources=[]
for m in manifest:
 ident=m['id']; lines=lf_lines((ROOT/m['text_path']).read_bytes()); covered=ranges[ident]
 count=sum(b-a+1 for a,b in covered); complete=count==len(lines)
 s={k:m[k] for k in ('id','url','final_url','retrieved_at','source_version','raw_path','text_path','text_sha256')}
 s.update(source_kind=source_kinds[ident],raw_sha256=m['sha256'],line_count=len(lines),
  coverage_ranges=[dict(start_line=a,end_line=b,sha256=sha(b''.join(lines[a-1:b]))) for a,b in covered],
  coverage_complete=complete,text_coverage_fraction=count/len(lines),
  reading_status='read_full' if complete else ('acquired_pdf_selected_visual_review' if ident=='rfc9177-pdf' else 'read_selected_sections'),note=notes[ident])
 if ident=='rfc9177-pdf': s.update(pdf_page_count=41,all_pdf_pages_reviewed=False,reviewed_pdf_pages=pages)
 sources.append(s)
write('notes/read-session.json',dict(review_date='2026-11-06',recorded_at=datetime.now(timezone.utc).isoformat(),
 method='Agent read rendered LF-numbered text chunks through shell output, then separately inspected rendered PDF image pages. Receipt assembled after reading, not inferred from acquisition, extraction, grep or hashing.',
 source_ranges=ranges,visual_pages=pages,full_rfc=True,all_pdf_pages=False,
 statement='All listed full-source text ranges and selected registry range were displayed and read without output truncation. Separate exploratory search output truncation is not counted as coverage.',
 limitations='Declared reading and consistency evidence, not a proof of comprehension or protocol implementation.'))
write('notes/access-observations.json',dict(observations=[
 'Official-primary web search and page open used for discovery/current status; web-tool opening www.rfc-editor.org/errata/rfc9177 returned Internal Error.',
 'Direct HTTPS acquisition of that errata URL succeeded with a redirect to errata.rfc-editor.org/search/?rfc_number=9177&presentation=records; archived all-status result says no matching errata.',
 'One web-tool cached CoRE view reported 2026-06-15 while the archived fresh direct HTML reports 2026-08-11. Allocation claims use retained CSV bytes, not cached search metadata.',
 'The preexisting selected RFC TXT and new full-review TXT have identical SHA-256. Prior reading claim remains 1–200 only.'
 ],acquisition_manifest='research/constrained/qblock-full/manifest.jsonl'))
tooling=dict(python=sys.version.split()[0],requests=requests.__version__,beautifulsoup=bs4.__version__,
 pdftotext=subprocess.run(['pdftotext','-v'],text=True,capture_output=True,check=True).stderr.splitlines()[0],
 pdftoppm=subprocess.run(['pdftoppm','-v'],text=True,capture_output=True,check=True).stderr.splitlines()[0],
 policy='Research acquisition/extraction/rendering only; no source-provided programs, controllers or cryptographic/protocol endpoints executed.')
write('notes/tooling.json',tooling)
prior=ROOT/'research/constrained/reading-observe-blockwise-full.json'
integrity=[BASE/x for x in ('manifest.jsonl','README.md','acquire.py','render.py','verify.py','build_receipt.py',
 'notes/full-review.md','notes/content-inventory.json','notes/figure-inventory.json','notes/read-session.json','notes/access-observations.json','notes/tooling.json')]+[ROOT/'docs/qblock-binding.md']
reading=dict(schema='hms-reading-overlay-v1',review_date='2026-11-06',
 scope='Complete RFC 9177 TXT, metadata, errata, two relevant IANA CSV registries and media registration. Selected broad-registry status lines and selected PDF figure/table visual corroboration; no implied full reading of referenced works or all PDF pages.',
 sources=sources,integrity_files=[dict(path=rel(p),sha256=sha(p.read_bytes())) for p in integrity],figures=figures,
 errata=[],metadata_status='PROPOSED STANDARD',iana_core_snapshot_last_updated='2026-08-11',
 allocations={'Q-Block1':19,'Q-Block2':31,'application/missing-blocks+cbor-seq':272},
 prior_selected_reading=dict(path=rel(prior),sha256=sha(prior.read_bytes()),source_id='q-block-rfc9177',range=[1,200],coverage_complete=False,relation='Same RFC bytes; prior selected coverage preserved without rewriting.'),
 qualification='Archival full-reading overlay and proposed HMS binding only; no protocol, cryptographic, MCU, physical or conformance execution. Broader literature goal remains open.')
write('reading.json',reading)
print(json.dumps(dict(sources=len(sources),full_text_sources=sum(s['coverage_complete'] for s in sources),coverage_chunks=sum(len(s['coverage_ranges']) for s in sources),visual_pages=len(figures),integrity_files=len(integrity)),indent=2))

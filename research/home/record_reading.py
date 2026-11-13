#!/usr/bin/env python3
"""Record reader-attested exact LF intervals actually displayed during this review.
This does not establish reading automatically and must not be used to invent coverage.
"""
import json,hashlib,pathlib,datetime
base=pathlib.Path('research/home')
records=[json.loads(x) for x in (base/'manifest.jsonl').read_text().splitlines()]
# Only these larger files were displayed in multiple chunks; small full files were cat-read.
ranges={
 'ha-contributors:src/content/docs/core/internals/websocket-api.md':[(1,280),(281,525)],
 'ha-core:homeassistant/components/websocket_api/commands.py':[(1,300),(301,582)],
 'ha-core:homeassistant/components/api/__init__.py':[(1,300),(301,553)],
 'ha-js-websocket:lib/connection.ts':[(1,260),(261,616)],
 'esphome:esphome/components/api/api.proto':[(1,410),(411,820),(821,1230),(1231,1660),(1661,2070),(2071,2490),(2491,2890),(2891,3129)],
 'esphome:esphome/components/api/api_connection.cpp':[(490,565),(680,760),(1860,1965),(2140,2375),(2440,2485)],
 'esphome:esphome/components/api/api_server.cpp':[(1,350),(351,640),(641,903)],
 'esphome:esphome/components/api/api_frame_helper_noise.cpp':[(1,310),(311,608)],
 'esphome-docs:src/content/docs/components/api.mdx':[(1,260),(261,530),(531,800),(801,1000)],
 'esphome:esphome/components/api/api_connection.h':[(280,355),(680,750),(830,891)],
}
partial={
 'ha-core:homeassistant/components/websocket_api/commands.py':'Setup/registration, events, call_service, get_states, subscribe_entities and no-await snapshot handoff; remainder unread.',
 'esphome:esphome/components/api/api_connection.cpp':'Selected native cover/switch/sensor state and command handlers, hello/authentication, service requests/responses, key changes and buffering entry points. The rest of this large file remains unread.',
 'esphome:esphome/components/api/api_connection.h':'Selected state subscription/initial iterator, authentication-state accessor, DeferredBatch deduplication and immediate/batch decision helpers. Remainder unread.'
}
sources=[]
for r in records:
 if r['id'].startswith('published-'):continue
 data=pathlib.Path(r['text_path']).read_bytes();parts=data.split(b'\n');lines=[x+b'\n' for x in parts[:-1]]+([parts[-1]] if parts[-1] else [])
 intervals=ranges.get(r['id'],[(1,len(lines))]);covered=set();chunks=[]
 for a,z in intervals:
  assert 1<=a<=z<=len(lines),(r['id'],a,z,len(lines))
  chunks.append(dict(start_line=a,end_line=z,sha256=hashlib.sha256(b''.join(lines[a-1:z])).hexdigest()));covered.update(range(a,z+1))
 full=covered==set(range(1,len(lines)+1));assert full==(r['id'] not in partial),r['id']
 s=dict(id=r['id'],url=r['url'],raw_path=r['raw_path'],raw_sha256=r['sha256'],text_path=r['text_path'],text_sha256=r['text_sha256'],line_count=len(lines),coverage_ranges=chunks,coverage_complete=full,reading_status='read_full' if full else 'read_selected',reading_scope=partial.get(r['id'],'Complete retained text/source file, including examples, comments and inline tables. No claim to read linked documents or the entire repository.'))
 if r.get('commit'):s.update(repository=r['repository'],commit=r['commit'],repository_path=r['repository_path'],git_blob_sha=r['git_blob_sha'])
 s['visual_scope']='Text/source only; embedded image pixels, browser-generated MDX components and linked references not separately inspected.' if ('docs' in r.get('repository_path','') or r['id']=='ha-state-object') else 'Source text; no acquired program execution, generated-code expansion or runtime test.'
 sources.append(s)
out=dict(method='Actual untruncated LF-addressed sequential reads or complete cat displays. Chunk hashes attest retained byte intervals; they do not mechanically prove comprehension. Raw acquisition records remain initially unread; this overlay supplies reading scope.',reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),sources=sources,figures=[])
(base/'reading-home-full.json').write_text(json.dumps(out,indent=2)+'\n')
print({'sources':len(sources),'full':sum(x['coverage_complete'] for x in sources),'selected':sum(not x['coverage_complete'] for x in sources),'coverage_chunks':sum(len(x['coverage_ranges']) for x in sources),'full_text_lines':sum(x['line_count'] for x in sources if x['coverage_complete'])})

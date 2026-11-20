#!/usr/bin/env python3
"""Offline independent-clock review integrity checks; no build or execution."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]

def need(ok,msg):
    if not ok: raise ValueError(msg)
def local(value):
    rel=Path(value); p=(ROOT/rel).resolve()
    need(not rel.is_absolute() and p.is_relative_to(ROOT),'Path escape')
    return p
def digest(data): return hashlib.sha256(data).hexdigest()
def verify_row(row,path_key='path'):
    p=local(row[path_key]); need(digest(p.read_bytes())==row['sha256'],'Hash mismatch: '+row[path_key])
    if 'bytes' in row: need(p.stat().st_size==row['bytes'],'Byte count mismatch')
def lf(data):
    p=data.split(b'\n');return [s+b'\n' for s in p[:-1]]+([p[-1]] if p[-1] else [])
def coverage(row):
    lines=lf(local(row['snapshot_path']).read_bytes());need(row['lf_lines']==len(lines),'LF count mismatch')
    last=0
    for r in row['coverage_ranges']:
        need(type(r['start_line']) is int and type(r['end_line']) is int,'Bad range type')
        need(r['start_line']==last+1 and r['start_line']<=r['end_line']<=len(lines),'Incomplete/overlapping range')
        need(digest(b''.join(lines[r['start_line']-1:r['end_line']]))==r['sha256'],'Coverage hash mismatch')
        last=r['end_line']
    need(last==len(lines) and row['coverage_complete'] is True,'False complete coverage')
def rejected(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('Negative self-check accepted')
def main():
    review=json.loads((BASE/'review.json').read_text()); checked=set();assertions=0
    index=json.loads((BASE/'input-snapshots.json').read_text())
    for row in index['files']:
        verify_row(row,'snapshot_path');checked.add(row['snapshot_path']);assertions+=1
    need(len(index['files'])==42,'Unexpected frozen inventory')
    receipt=next(r for r in index['files'] if r['original_path']=='artifacts/verification/avr-clock/review.json')
    need(receipt['sha256']==index['producer_receipt_sha256']==review['producer_receipt_sha256'],'Producer receipt pin mismatch')
    producer=json.loads(local(receipt['snapshot_path']).read_text())
    for row in producer['files']+producer['outputs']:
        snap=next(x for x in index['files'] if x['original_path']==row['path'])
        need(row['sha256']==snap['sha256'],'Producer closure mismatch')
    for row in review['files']:
        verify_row(row);checked.add(row['path']);assertions+=1
    for row in review['reviewed_sources']:
        coverage(row)
        need(digest(local(row['original_path']).read_bytes())==row['sha256'],'Live reviewed source changed')
        checked.add(row['original_path']);assertions+=1
    result=json.loads((BASE/'results.json').read_text())
    need(result['passed'] and all(not result[k] for k in ('target_executed','emulator_executed','hardware_contacted','acquired_research_code_executed')),'Execution/scope mismatch')
    need(len(result['baselines'])==2 and result['source_mutations_rejected']==12,'Missing host campaign')
    for b in result['baselines']:
        r=b['result'];need(r['timeline_cases']==131920 and r['conversion_cases']==8192056 and r['sequence_steps']==100000 and r['outside_contract_aliases']==5,'Coverage campaign mismatch')
    need(len(result['source_mutations'])==12 and all(m['rejected'] and m['exit_code']==11 for m in result['source_mutations']),'Mutation failure not a test assertion')
    for row in result['inputs']+[result['command_log']]+[x['binary'] for x in result['baselines']]+[v[k] for v in result['source_mutations'] for k in ('source','binary')]:
        verify_row(row);checked.add(row['path']);assertions+=1
    need(sum(x['lf_lines'] for x in review['reviewed_sources'])==986,'Unexpected reviewed source count')
    wrong=deepcopy(review['reviewed_sources'][0]);wrong['coverage_ranges'].pop()
    rejected(lambda:coverage(wrong))
    wrong_hash=dict(review['files'][0],sha256='0'*64);rejected(lambda:verify_row(wrong_hash))
    rejected(lambda:local('../outside-root'))
    output=dict(passed=True,checked_at=datetime.now(timezone.utc).isoformat(),hash_assertions=assertions,
        unique_files=len(checked),frozen_snapshot_files=42,full_reviewed_source_lines=986,
        negative_self_checks=3,scope='Offline historical snapshot/receipt integrity and current reviewed code identity, not a proof of comprehension, timing or hardware qualification.')
    (BASE/'verification.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))
if __name__=='__main__':main()

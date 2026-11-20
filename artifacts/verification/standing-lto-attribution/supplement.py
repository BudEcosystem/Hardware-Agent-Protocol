#!/usr/bin/env python3
"""Reproduce supplementary comparisons using retained assembler text only."""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BUILD=ROOT/'artifacts/implementation/standing-endpoint-lto/build/avr-attempt-2'
FINAL=BUILD/'compiler-tmp/cc1w4vmK.ltrans0.ltrans.s'
FAT=BUILD/'standing.s'

def unit(lines,name):
    first=lines.index(name+':')
    last=next(i for i in range(first,len(lines)) if re.match(r'\s*\.size\s+'+name+r',',lines[i]))
    return first,last,lines[first:last+1]

def normalized(body):
    labels={}
    def replace(match):
        if match[0] not in labels:labels[match[0]]='LABEL'+str(len(labels))
        return labels[match[0]]
    return [re.sub(r'\.L\d+',replace,line.strip()) for line in body
            if re.match(r'^\t[a-z][a-z0-9]*\s*',line) or re.match(r'^\s*\.word\s',line)]

def main():
    final=FINAL.read_text().splitlines();fat=FAT.read_text().splitlines()
    report={'scope':'Exact retained text comparisons; no binary execution or predicted savings',
            'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (FINAL,FAT)}}
    comparisons=[]
    for name in ('hms_standing_poll','hms_standing_handle'):
        a,b,body=unit(final,name);c,d,other=unit(fat,name)
        comparisons.append({'name':name,'ltrans_lines':[a+1,b+1],'fat_lines':[c+1,d+1],
            'instructions_plus_words_equal_after_local_label_renumber':normalized(body)==normalized(other),
            'frame_adjust_instructions':sum(bool(re.match(r'\s*(?:adiw|sbiw) r28,\d+-\d+$',line)) for line in body)})
    report['fat_comparisons']=comparisons
    report['duplicate_readers']=[{'names':[left,right],'instructions_equal_after_local_label_renumber':
        normalized(unit(final,left)[2])==normalized(unit(final,right)[2])} for left,right in [('read64','get64'),('read32','get32')]]
    commit=json.loads((HERE/'commit-blocks.json').read_text());left=commit['demand_instructions'];right=commit['feedback_instructions']
    count=0
    for a,b in zip(left,right):
        if a[1]!=b[1]:break
        count+=1
    report['commit_duplicate_prefix']={'instructions':count,'bytes':sum(4 if row[1].split()[0] in ('call','jmp','lds','sts') else 2 for row in left[:count]),
        'demand_raw_lines':[left[0][0],left[count-1][0]],'feedback_raw_lines':[right[0][0],right[count-1][0]]}
    with (HERE/'supplement.json').open('x') as out:json.dump(report,out,indent=2,sort_keys=True);out.write('\n')

if __name__=='__main__':main()

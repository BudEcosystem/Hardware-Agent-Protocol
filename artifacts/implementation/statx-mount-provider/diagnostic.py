"""Nested cost attribution; all original ownership and durability work executes."""
import functools
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

import candidate as hierarchy
from native import Native

HERE=Path(__file__).resolve().parent
WORK=Path.cwd()
MODE=sys.argv[1]
assert MODE in ('coarse','nested')
KW=dict(block_source=HERE/'fixed_block.py',library=HERE/'hierarchical-store.so',
        library_hash='7049dc14940b0f686f5cbe682e85f70944a8074936786e7f962c6ee29ed321de')
IDENTITY='92929292929292929292929292929292'
EXPECTED={}
STEPS=[]

def save(name,value):
    with (WORK/name).open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

class Tracer:
    def __init__(self):self.phase='setup';self.stack=[];self.totals={}

    def call(self,label,action,*args,**kwargs):
        key=self.phase+'/'+label
        frame=[0,0];start_wall=time.perf_counter_ns();start_cpu=time.process_time_ns();self.stack.append(frame)
        try:return action(*args,**kwargs)
        finally:
            elapsed_cpu=time.process_time_ns()-start_cpu;elapsed_wall=time.perf_counter_ns()-start_wall
            assert self.stack.pop() is frame
            row=self.totals.setdefault(key,dict(calls=0,wallNs=0,cpuNs=0,selfWallNs=0,selfCpuNs=0))
            row['calls']+=1;row['wallNs']+=elapsed_wall;row['cpuNs']+=elapsed_cpu
            # Rounding at nested clock boundaries is represented, never hidden.
            row['selfWallNs']+=elapsed_wall-frame[0];row['selfCpuNs']+=elapsed_cpu-frame[1]
            if self.stack:self.stack[-1][0]+=elapsed_wall;self.stack[-1][1]+=elapsed_cpu

    def wrap(self,label,action):
        @functools.wraps(action)
        def wrapped(*args,**kwargs):
            name=label(args,kwargs) if callable(label) else label
            return self.call(name,action,*args,**kwargs)
        return wrapped

TRACE=Tracer()

class OSProxy:
    def __init__(self,original):
        self.original=original
        for name in ['fstat','stat','listdir','pread','pwrite','fsync','getpid','getuid','open','close','posix_fallocate']:
            setattr(self,name,TRACE.wrap('os.'+name,getattr(original,name)))
    def __getattr__(self,name):return getattr(self.original,name)

def install_nested():
    original_loader=hierarchy._block_module
    def loader(path,wanted):
        module=original_loader(path,wanted)
        module.os=OSProxy(module.os)
        module._host=TRACE.wrap('provider.mount_check',module._host)
        module.create_image=TRACE.wrap('provider.create_image',module.create_image)
        original=module.FixedBlockImage
        methods={name:TRACE.wrap('provider.'+name,getattr(original,name))
                 for name in ['__init__','_verify','_perform','read','write','erase','sync','close']}
        module.FixedBlockImage=type('ObservedFixedBlockImage',(original,),methods)
        return module
    hierarchy._block_module=loader
    Native.call=TRACE.wrap(lambda args,kw:'native.'+args[1],Native.call)

def delta(after,before):return {name:after[name]-before[name] for name in after}

def operation(label,action,*args,store=None,**kwargs):
    prior=dict(store.native.counts) if store is not None else None
    before_wall=time.perf_counter_ns();before_cpu=time.process_time_ns()
    result=TRACE.call('logical.'+label,action,*args,**kwargs)
    row=dict(phase=TRACE.phase,operation=label,wallNs=time.perf_counter_ns()-before_wall,
             cpuNs=time.process_time_ns()-before_cpu)
    if prior is not None:row['callbacks']=delta(store.native.counts,prior)
    STEPS.append(row);return result

def body(number,size):return bytes((number+i)%251 for i in range(size))

def expected_namespace(store):
    actual={};directories=set();pending=['']
    while pending:
        parent=pending.pop()
        for entry in operation('listdir',store.listdir,parent,store=store):
            path=parent+'/'+entry['name'] if parent else entry['name']
            if entry['kind']=='dir':directories.add(path);pending.append(path)
            else:actual[path]=entry['size']
    assert directories=={'devices','drivers','hub','qualification'}|{
        root+'/group'+str(group) for root in ['devices','drivers','hub','qualification'] for group in range(4)}
    assert actual=={name:len(value) for name,value in EXPECTED.items()}
    for name,value in EXPECTED.items():
        handle=operation('open_read',store.open,name,writable=False,store=store)
        observed=operation('pread',store.pread,handle,len(value),0,store=store)
        assert observed==value
        operation('close_handle',store.close_handle,handle,store=store)

def main():
    os.umask(0o077);started=time.monotonic()
    if MODE=='nested':install_nested()
    TRACE.phase='fresh'
    store=operation('create_store',hierarchy.HierarchicalStore.create,WORK/'image',IDENTITY,chunks=8,**KW)
    save('anchor.json',store.anchor)
    TRACE.phase='directories'
    roots=['devices','drivers','hub','qualification']
    for root in roots:
        operation('mkdir',store.mkdir,root,store=store)
        for group in range(4):operation('mkdir',store.mkdir,root+'/group'+str(group),store=store)
    TRACE.phase='files'
    for number in range(40):
        size=[0,128,4096,8193,65536][number%5]
        name=f'{roots[number%4]}/group{(number//4)%4}/{number:04d}-'+hashlib.sha256(str(number).encode()).hexdigest()+'.json'
        value=body(number,size);EXPECTED[name]=value
        handle=operation('open_create',store.open,name,create=True,exclusive=True,store=store)
        assert operation('pwrite',store.pwrite,handle,value,0,store=store)==len(value)
        operation('close_handle',store.close_handle,handle,store=store)
    TRACE.phase='warm_read'
    expected_namespace(store)
    TRACE.phase='close'
    operation('close_store',store.close,store=store)
    first=dict(store.native.counts)
    TRACE.phase='cold_open'
    store=operation('reopen_store',hierarchy.HierarchicalStore.reopen,WORK/'image',json.loads((WORK/'anchor.json').read_text()),**KW)
    TRACE.phase='cold_read'
    expected_namespace(store)
    TRACE.phase='cold_close'
    operation('close_store',store.close,store=store)
    cold=dict(store.native.counts)
    assert not TRACE.stack and store.native.fault is None
    expected=[dict(path=name,bytes=len(value),sha256=hashlib.sha256(value).hexdigest()) for name,value in sorted(EXPECTED.items())]
    backing={p.name:digest(p) for p in sorted((WORK/'image').iterdir())}
    usage=resource.getrusage(resource.RUSAGE_SELF)
    report=dict(status='passed',mode=MODE,directories=20,files=40,payloadBytes=sum(len(v) for v in EXPECTED.values()),
        expectedFiles=expected,firstOwnerCallbacks=first,coldOwnerCallbacks=cold,backingHashes=backing,
        spans=TRACE.totals,steps=STEPS,elapsedSeconds=time.monotonic()-started,cpuSeconds=usage.ru_utime+usage.ru_stime,
        peakRSSKiB=usage.ru_maxrss,fullWorkflowQualified=False,checksDisabled=False,fsyncDisabled=False)
    save('diagnostic.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['spans','steps','expectedFiles','backingHashes']},sort_keys=True),flush=True)

if __name__=='__main__':main()

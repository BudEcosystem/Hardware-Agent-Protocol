"""Bounded observational wrappers over an unchanged original workload."""
import functools
import json
import os
from pathlib import Path
import resource
import sys
import time

HERE=Path(__file__).resolve().parent
WORK=Path.cwd()
MODE=sys.argv[1]
assert MODE in ('screen','replay_write')
PHASES=('creation','directories','file_io','readback','close')
PUBLIC=('mkdir','open','pwrite','pread','close_handle','accounting','close','listdir','info')
META=('_new_inode','_initialize_inode','_save_super','_save_inode','_publish','_inventory','_recover_inventory')
PROVIDER=('__init__','_verify','read','write','erase','sync','close')
NATIVE=('hm_format','hm_mount','hm_stat','hm_list','hm_entries','hm_mkdir','hm_remove','hm_sync','hm_used')
PATH_KINDS=('super','state','chunk','entry','other')
LABELS=(tuple('logical.'+n for n in ('create','reopen',*PUBLIC))+
        tuple('hierarchy.'+n for n in META)+
        ('native.owner','native.dispose')+tuple('native.'+n for n in NATIVE)+
        tuple('native.'+n+'.'+k for n in ('hm_read','hm_write','hm_rename') for k in PATH_KINDS)+
        tuple('provider.'+n for n in PROVIDER)+
        ('provider.create_image','provider.mount_admit','provider.mount_current')+
        tuple('os.'+n for n in ('pread','pwrite','fsync','posix_fallocate')))
assert len(LABELS)==len(set(LABELS)) and len(LABELS)<128


def path_kind(path):
    if type(path) is not bytes:return 'other'
    if path in (b'super',b'super.tmp'):return 'super'
    if path.endswith((b'/state',b'/state.tmp')):return 'state'
    leaf=path.rsplit(b'/',1)[-1]
    if len(leaf)==9 and leaf.startswith(b'c') and all(c in b'0123456789abcdef' for c in leaf[1:]):return 'chunk'
    if path.startswith(b'pending/') or b'/entries/' in path:return 'entry'
    return 'other'


def native_label(args,kwargs):
    name=args[1]
    if name in ('hm_read','hm_write','hm_rename'):
        return 'native.'+name+'.'+path_kind(args[2])
    return 'native.'+name


class Tracker:
    def __init__(self):
        self.labels={name:i for i,name in enumerate(LABELS)}
        self.rows=[[[0]*6 for unused in LABELS] for unused in PHASES]
        self.stack=[];self.phase=0;self.phase_source=None;self.store=None;self.owner=0
        self.started=time.monotonic_ns();self.last_snapshot=0;self.sequence=0
        self.root_started=0;self.root_completed=0;self.current=None
        self.errors=[];self.enabled=True;self.bytes_written=0
        self.observer_cpu=0;self.observer_wall=0;self.observer_calls=0;self.observer_drops=0
        self.stream=(WORK/'attribution.jsonl').open('xb')
        self.snapshot('initial',force=True)

    def note_error(self,error):
        self.enabled=False
        if len(self.errors)<8:self.errors.append(type(error).__name__+': '+str(error)[:256])

    def select_phase(self,label):
        if self.phase_source is not None:
            phase=self.phase_source()
            self.phase=(0 if phase in ('setup','fresh') else 1 if phase=='directories' else
                        3 if phase in ('warm_read','cold_open','cold_read') else
                        4 if phase in ('close','cold_close') else 2)
        elif label in ('logical.create','logical.reopen'):self.phase=0
        elif label=='logical.mkdir':self.phase=1
        elif label in ('logical.accounting','logical.close'):self.phase=4
        else:self.phase=2

    def snapshot(self,event,force=False):
        now=time.monotonic_ns()
        if not force and now-self.last_snapshot<1_000_000_000:return
        before_cpu=time.process_time_ns();before_wall=time.monotonic_ns()
        self.last_snapshot=now
        try:
            native=getattr(self.store,'native',None)
            value=dict(schema='hms.storage-attribution/0.1',sequence=self.sequence,
                event=event,elapsedNs=now-self.started,phases=PHASES,labels=LABELS,
                rowFields=('calls','raised','cpuNs','wallNs','selfCpuNs','selfWallNs'),
                rows=[[p,n,*row] for p,phase in enumerate(self.rows) for n,row in enumerate(phase) if row[0]],
                rootStarted=self.root_started,rootCompleted=self.root_completed,current=self.current,
                ownerSequence=self.owner,callbacks=None if native is None else dict(native.counts),errors=list(self.errors),
                observer=dict(calls=self.observer_calls,cpuNs=self.observer_cpu,wallNs=self.observer_wall,
                    dropped=self.observer_drops,bytesWritten=self.bytes_written),
                stackDepth=len(self.stack),nativeInternalFunctionsMeasured=False)
            wire=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
            if len(wire)>65536 or self.bytes_written+len(wire)>12*1024**2:
                self.observer_drops+=1;return
            self.stream.write(wire);self.stream.flush();os.fsync(self.stream.fileno())
            self.bytes_written+=len(wire);self.sequence+=1
        except BaseException as error:self.note_error(error)
        finally:
            self.observer_calls+=1
            self.observer_cpu+=time.process_time_ns()-before_cpu
            self.observer_wall+=time.monotonic_ns()-before_wall

    def enter(self,label,args,boundary):
        if boundary and not self.stack:
            self.select_phase(label);self.root_started+=1
            self.current=dict(operation=label,ordinal=self.root_started)
            if label in ('logical.mkdir','logical.open') and len(args)>1 and type(args[1]) is str:
                self.current['path']=args[1]
            if label=='logical.pwrite' and len(args)>3:
                self.current.update(bytes=len(args[2]),offset=args[3])
            self.snapshot('before')
        assert len(self.stack)<64
        frame=[self.phase,self.labels[label],time.process_time_ns(),time.monotonic_ns(),0,0,boundary]
        self.stack.append(frame);return frame

    def leave(self,frame,raised):
        cpu=time.process_time_ns()-frame[2];wall=time.monotonic_ns()-frame[3]
        assert self.stack.pop() is frame
        row=self.rows[frame[0]][frame[1]]
        for index,value in enumerate((1,int(raised),cpu,wall,cpu-frame[4],wall-frame[5])):row[index]+=value
        if self.stack:self.stack[-1][4]+=cpu;self.stack[-1][5]+=wall
        elif frame[6]:
            self.root_completed+=1;self.current['raised']=raised
            self.snapshot('after')

    def wrap(self,label,action,*,boundary=False):
        @functools.wraps(action)
        def wrapped(*args,**kwargs):
            if not self.enabled:return action(*args,**kwargs)
            try:frame=self.enter(label(args,kwargs) if callable(label) else label,args,boundary)
            except BaseException as error:
                self.note_error(error);return action(*args,**kwargs)
            try:result=action(*args,**kwargs)
            except BaseException:
                try:self.leave(frame,True)
                except BaseException as error:self.note_error(error)
                raise
            else:
                try:self.leave(frame,False)
                except BaseException as error:self.note_error(error)
                return result
        return wrapped

    def finish(self):
        self.snapshot('final',force=True);self.stream.close()
        return dict(calls=self.observer_calls,cpuNs=self.observer_cpu,wallNs=self.observer_wall,
            dropped=self.observer_drops,bytesWritten=self.bytes_written,errors=self.errors,
            residualStackDepth=len(self.stack),nativeInternalFunctionsMeasured=False)


def install(trace):
    import hierarchical_store as implementation
    from candidate import HierarchicalStore as Store
    from native import Native
    original_loader=implementation._block_module
    class OSProxy:
        def __init__(self,original):
            self.original=original
            for name in ('pread','pwrite','fsync','posix_fallocate'):
                setattr(self,name,trace.wrap('os.'+name,getattr(original,name)))
        def __getattr__(self,name):return getattr(self.original,name)
    def loader(path,wanted):
        module=original_loader(path,wanted)
        module.os=OSProxy(module.os)
        module._host=trace.wrap('provider.mount_admit',module._host)
        module._host_current=trace.wrap('provider.mount_current',module._host_current)
        module.create_image=trace.wrap('provider.create_image',module.create_image)
        original=module.FixedBlockImage
        methods={name:trace.wrap('provider.'+name,getattr(original,name)) for name in PROVIDER}
        module.FixedBlockImage=type('ObservedFixedBlockImage',(original,),methods)
        return module
    implementation._block_module=loader
    for name in ('create','reopen'):
        action=getattr(Store,name).__func__
        setattr(Store,name,classmethod(trace.wrap('logical.'+name,action,boundary=True)))
    for name in PUBLIC:setattr(Store,name,trace.wrap('logical.'+name,getattr(Store,name),boundary=True))
    for name in META:setattr(Store,name,trace.wrap('hierarchy.'+name,getattr(Store,name)))
    original_init=Store.__init__
    @functools.wraps(original_init)
    def init(self,*args,**kwargs):
        trace.store=self;trace.owner+=1
        return original_init(self,*args,**kwargs)
    Store.__init__=init
    Native.__init__=trace.wrap('native.owner',Native.__init__)
    Native.call=trace.wrap(native_label,Native.call)
    Native.dispose=trace.wrap('native.dispose',Native.dispose)


def save(name,value):
    with (WORK/name).open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def main():
    os.umask(0o077)
    trace=Tracker();install(trace);started=time.monotonic()
    original_error=None
    try:
        if MODE=='screen':
            sys.argv[1]='coarse'
            import diagnostic
            trace.phase_source=lambda:diagnostic.TRACE.phase
            diagnostic.main()
        else:
            import controls
            controls.replay_write()
            usage=resource.getrusage(resource.RUSAGE_SELF)
            result=dict(scope=MODE,status='passed',checks=controls.CHECKS,details=controls.DETAILS,
                elapsedSeconds=time.monotonic()-started,cpuSeconds=usage.ru_utime+usage.ru_stime,
                peakRSSKiB=usage.ru_maxrss)
            save('checks.json',result);print(json.dumps(result,sort_keys=True),flush=True)
    except BaseException as error:
        original_error=error
        raise
    finally:
        try:
            observer=trace.finish();save('observer.json',observer)
            if original_error is None:
                assert not observer['errors'] and not observer['dropped'] and not observer['residualStackDepth']
        except BaseException as observer_error:
            if original_error is None:raise
            try:sys.stderr.write('observer finalization also failed: '+type(observer_error).__name__+'\n')
            except BaseException:pass


if __name__=='__main__':main()

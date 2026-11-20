"""Bounded compact-wire controls; original cases remain in controls.py unchanged."""
import base64
import copy
import hashlib
import json
import os
import resource
import sys
import time
from unittest.mock import patch

import controls as base
import hierarchical_store as implementation
from candidate import HierarchicalStore as Store
from hierarchical_store import CHUNK, MAX_FILE, MAP_BYTES, StorageError, _pack, _unpack
from native import Native

check,refused,create,reopen,finish=base.check,base.refused,base.create,base.reopen,base.finish
readall,clone,image_hashes,save=base.readall,base.clone,base.image_hashes,base.save


def file_inode(size,bits=()):
    bitmap=bytearray(MAP_BYTES)
    for number in bits:bitmap[number//8]|=1<<(number%8)
    return dict(id=17,kind='file',size=size,chunks=base64.b64encode(bitmap).decode('ascii'))


def codec():
    owner=Store.__new__(Store)
    sizes=[0,1,CHUNK-1,CHUNK,CHUNK+1,7*CHUNK,8*CHUNK,8*CHUNK+1,9*CHUNK,MAX_FILE-1,MAX_FILE]
    lengths=[0,1,1,1,1,1,1,2,2,512,512]
    for size,length in zip(sizes,lengths):
        count=(size+CHUNK-1)//CHUNK;inode=file_inode(size,sorted({0,count-1}) if count else ())
        before=copy.deepcopy(inode);raw=owner._encode_inode(inode);disk=_unpack(raw)
        check(f'encode size {size} preserves caller full map',inode==before and len(base64.b64decode(inode['chunks']))==512)
        check(f'encode size {size} exact independent length',len(base64.b64decode(disk['chunks']))==length)
        check(f'decode size {size} restores full memory map',owner._valid_inode(raw,17)==before)
    for size,wire,bits in [(0,'',()),(1,'AQ==',(0,)),(7*CHUNK,'QQ==',(0,6)),(8*CHUNK,'gQ==',(0,7)),(9*CHUNK,'AQE=',(0,8))]:
        disk=dict(id=17,kind='file',size=size,chunks=wire)
        check(f'independent wire vector {size}',owner._valid_inode(_pack(disk),17)==file_inode(size,bits))
    for index,size in enumerate([-1,MAX_FILE+1,True,'1',1.0,None]):
        inode=file_inode(0);inode['size']=size;inode['chunks']='INVALID'
        refused(f'invalid size {index} rejected before disk bitmap',StorageError,lambda:owner._valid_inode(_pack(inode),17),'INVALID_INODE')
        with patch.object(owner,'_bitmap',side_effect=AssertionError('bitmap evaluated before size')):
            refused(f'invalid size {index} rejected before memory bitmap',StorageError,lambda:owner._encode_inode(inode),'INVALID_INODE')
    invalid=[('missing byte',1,''),('extra byte',1,'AQA='),('old fixed map',1,file_inode(1,(0,))['chunks']),
             ('empty file extra byte',0,'AA=='),('alphabet',1,'!!=='),('unicode',1,'éé=='),
             ('nonstring',1,None),('noncanonical pad bits',1,'AR=='),('extra padding',1,'AQ==='),
             ('newline',1,'AQ==\n'),('short two-byte map',9*CHUNK,'AQ==')]
    for name,size,wire in invalid:
        refused(name+' refuses with valid envelope',StorageError,
                lambda:owner._valid_inode(_pack(dict(id=17,kind='file',size=size,chunks=wire)),17),'INVALID_CHUNK_MAP')
    for size,wire in [(1,'Ag=='),(7*CHUNK,'gA=='),(9*CHUNK,'AAI=')]:
        refused(f'nonzero retained-byte tail at {size}',StorageError,
                lambda:owner._valid_inode(_pack(dict(id=17,kind='file',size=size,chunks=wire)),17),'CHUNK_OUTSIDE_FILE')
    for name,inode in [('discarded tail',file_inode(1,(8,))),('retained tail',file_inode(1,(1,))),('empty tail',file_inode(0,(4095,)))]:
        before=copy.deepcopy(inode)
        refused(name+' cannot serialize',StorageError,lambda:owner._encode_inode(inode),'CHUNK_OUTSIDE_FILE')
        check(name+' refusal leaves caller exact',inode==before)
    for name,wire in [('short memory map','AQ=='),('noncanonical memory map',file_inode(1,(0,))['chunks'][:-2]+'B=')]:
        inode=dict(id=17,kind='file',size=1,chunks=wire)
        refused(name+' cannot serialize',StorageError,lambda:owner._encode_inode(inode),'INVALID_CHUNK_MAP')
    directory=dict(id=17,kind='dir')
    check('directory wire unchanged',owner._encode_inode(directory)==_pack(directory))
    check('directory schema unchanged',owner._valid_inode(_pack(directory),17)==directory)
    refused('directory rejects bitmap key',StorageError,lambda:owner._valid_inode(_pack(dict(directory,chunks='')),17),'INVALID_INODE')
    raw=_pack(dict(id=17,kind='file',size=1,chunks='AQ=='))
    envelope=json.loads(raw);envelope['sha256']='0'*64
    refused('checksum remains strict',StorageError,lambda:owner._valid_inode(json.dumps(envelope,sort_keys=True,separators=(',',':')).encode(),17),'INVALID_METADATA')
    refused('envelope canonical bytes remain strict',StorageError,lambda:owner._valid_inode(raw+b'\n',17),'INVALID_METADATA')


def wire_state(owner,handle):
    inode=owner.inodes[owner.info(handle)['id']]
    raw=owner.native.read(owner._directory(inode['id'])+'/state')
    assert len(base64.b64decode(inode['chunks']))==512
    return raw,_unpack(raw)


def edges():
    s=create();a=s.open('transitions',create=True);b=s.open('transitions')
    raw,disk=wire_state(s,a);check('empty file uses empty disk map',disk['chunks']=='')
    expected=b''
    for count in [1,7,8,9]:
        target=count*CHUNK;payload=bytes([count])*(target-len(expected));offset=len(expected)
        s.pwrite(a,payload,offset);expected+=payload
        raw,disk=wire_state(s,a)
        check(f'{count} chunks disk map length',len(base64.b64decode(disk['chunks']))==({1:1,7:1,8:1,9:2}[count]))
        check(f'{count} chunks shared-handle exact body',readall(s,b)==expected)
    for size in [8*CHUNK,7*CHUNK-3,1,0]:
        s.truncate(b,size);expected=expected[:size]
        check(f'shrink to {size} exact shared body',readall(s,a)==expected)
        raw,disk=wire_state(s,a)
        check(f'shrink to {size} exact disk map length',len(base64.b64decode(disk['chunks']))==(0 if size==0 else 1))
    s.pwrite(a,b'Q'*100,0);s.truncate(a,3);s.truncate(b,9*CHUNK+1)
    expected=b'QQQ'+b'\0'*(9*CHUNK-2)
    check('partial tail zeroed through sparse 7 8 9 growth',readall(s,a)==expected)
    s.pwrite(b,b'Z',8*CHUNK);expected=expected[:8*CHUNK]+b'Z'+expected[8*CHUNK+1:]
    check('sparse bit beyond byte boundary survives overwrite',readall(s,a)==expected)
    maximum=s.open('maximum',create=True);small_raw,_=wire_state(s,maximum)
    s.truncate(maximum,MAX_FILE);s.pwrite(maximum,b'!',MAX_FILE-1)
    large_raw,disk=wire_state(s,maximum)
    check('maximum sparse size has exact 512-byte disk map',len(base64.b64decode(disk['chunks']))==512)
    check('metadata crosses 512-byte inline size threshold',len(small_raw)<=512<len(large_raw))
    check('maximum sparse boundary bytes exact',s.pread(maximum,1,0)==b'\0' and s.pread(maximum,1,MAX_FILE-1)==b'!')
    s.truncate(maximum,CHUNK);shrunk_raw,shrunk=wire_state(s,maximum)
    check('maximum shrink returns metadata below inline threshold',len(shrunk_raw)<=512 and len(base64.b64decode(shrunk['chunks']))==1)
    check('maximum shrink removes former last payload',readall(s,maximum)==b'\0'*CHUNK)
    s.truncate(maximum,MAX_FILE)
    check('maximum regrowth does not expose removed last byte',s.pread(maximum,1,MAX_FILE-1)==b'\0')
    s.pwrite(maximum,b'!',MAX_FILE-1)
    wanted=dict(transitions=expected,maximum=b'\0'*(MAX_FILE-1)+b'!')
    base.DETAILS['expectedFiles']={n:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in wanted.items()}
    finish(s);s=reopen()
    for name,body in wanted.items():
        handle=s.open(name,writable=False)
        check(name+' cold complete body exact',readall(s,handle)==body)
    finish(s)


def corruption():
    for name,wire,message in [('wrong-length',file_inode(1,(0,))['chunks'],'INVALID_CHUNK_MAP'),
                              ('noncanonical','AR==','INVALID_CHUNK_MAP'),('tail-bit','Ag==','CHUNK_OUTSIDE_FILE')]:
        s=create(name);h=s.open('kept',create=True);s.pwrite(h,b'A',0);identity=s.info(h)['id']
        directory=s._directory(identity);disk=dict(id=identity,kind='file',size=1,chunks=wire)
        s.native.write(directory+'/state',_pack(disk))
        s.native.write(directory+'/state.tmp',b'KEEP STAGED INODE');s.native.write('super.tmp',b'KEEP STAGED SUPER')
        s.dispose();before=image_hashes(name);observed=[]
        class Observed(Native):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);observed.append(self)
        with patch.object(implementation,'Native',Observed),patch.object(Store,'_recover_inventory',side_effect=AssertionError('recovery on corrupt bitmap')) as recovery:
            refused(name+' cold mount refuses deep bitmap validation',StorageError,lambda:reopen(name),message)
            check(name+' refused before recovery',not recovery.called)
        check(name+' no mutation callbacks',len(observed)==1 and all(observed[0].counts[k]==0 for k in ['programCalls','erases','syncs']))
        check(name+' all image bytes preserved',image_hashes(name)==before)
        save(name+'-refusal.json',dict(backingHashes=before,callbacks=observed[0].counts,error=message,
                                      corruptDiskInode=disk,validEnvelopeChecksum=True,recoveryInvoked=False))


class Cut(RuntimeError):pass


def interruption():
    for phase in ['state-staged','state-renamed','partial-overwrite','shrink-cleanup']:
        s=create(phase);h=s.open('data',create=True);held=s.open('data')
        initial=b'A' if phase.startswith('state-') else b'A'*(2*CHUNK if phase=='partial-overwrite' else 9*CHUNK)
        s.pwrite(h,initial,0);identity=s.info(h)['id'];directory=s._directory(identity)
        write=s.native.write;call=s.native.call;cut=[]
        if phase=='state-staged':
            def hooked(path,data):
                value=write(path,data)
                if path==directory+'/state.tmp':cut.append(path);raise Cut(phase)
                return value
            s.native.write=hooked;action=lambda:s.pwrite(h,b'Z',8*CHUNK);wanted=initial
        elif phase=='state-renamed':
            def hooked(name,*args,**kwargs):
                value=call(name,*args,**kwargs)
                if name=='hm_rename' and args[0]==(directory+'/state.tmp').encode():cut.append(name);raise Cut(phase)
                return value
            s.native.call=hooked;action=lambda:s.pwrite(h,b'Z',8*CHUNK);wanted=b'A'+b'\0'*(8*CHUNK-1)+b'Z'
        elif phase=='partial-overwrite':
            def hooked(path,data):
                if path==directory+'/c00000001':cut.append(path);raise Cut(phase)
                return write(path,data)
            s.native.write=hooked;action=lambda:s.pwrite(h,b'X'*16,CHUNK-6)
            wanted=initial[:CHUNK-6]+b'X'*6+initial[CHUNK:]
        else:
            def hooked(name,*args,**kwargs):
                if name=='hm_remove' and args[0].startswith((directory+'/c').encode()):cut.append(name);raise Cut(phase)
                return call(name,*args,**kwargs)
            s.native.call=hooked;action=lambda:s.truncate(h,7*CHUNK-3);wanted=initial[:7*CHUNK-3]
        refused(phase+' owner interrupted',Cut,action,phase)
        check(phase+' checkpoint reached once',len(cut)==1)
        check(phase+' owner poisoned',s.poisoned)
        refused(phase+' second held handle also refuses',StorageError,lambda:s.pread(held,1,0),'POISONED')
        refused(phase+' retry prohibited',StorageError,lambda:s.pwrite(h,b'?',0),'POISONED')
        s.dispose();before=image_hashes(phase);clone(phase,phase+'-recovered');r=reopen(phase+'-recovered')
        f=r.open('data');check(phase+' cold committed body exact',readall(r,f)==wanted)
        inode=r.inodes[r.info(f)['id']];items={n for n,k,z in r.native.entries(directory,4099)}
        wanted_names={'state'}|{f'c{n:08x}' for n in r._present(inode)}
        check(phase+' recovery removes only unreferenced physical state',items==wanted_names)
        original_committed=wanted
        if phase=='shrink-cleanup':
            r.truncate(f,9*CHUNK);wanted+=b'\0'*(9*CHUNK-len(wanted))
            check('shrink then sparse regrow hides old bytes',readall(r,f)==wanted)
        finish(r)
        check(phase+' original failed image untouched',image_hashes(phase)==before)
        save(phase+'-expected.json',dict(originalBackingHashes=before,originalCommittedFile=dict(bytes=len(original_committed),sha256=hashlib.sha256(original_committed).hexdigest()),
             recoveredFile=dict(bytes=len(wanted),sha256=hashlib.sha256(wanted).hexdigest()),
             cut=phase,physicalPowerLoss=False,multiChunkWriteAtomic=False))


if __name__=='__main__':
    os.umask(0o077);started=time.monotonic();scope=sys.argv[1]
    {'codec':codec,'edges':edges,'corruption':corruption,'interruption':interruption}[scope]()
    assert len(base.CHECKS)==len(set(base.CHECKS))
    usage=resource.getrusage(resource.RUSAGE_SELF)
    result=dict(scope=scope,status='passed',checks=base.CHECKS,details=base.DETAILS,
                elapsedSeconds=time.monotonic()-started,cpuSeconds=usage.ru_utime+usage.ru_stime,peakRSSKiB=usage.ru_maxrss)
    save('checks.json',result);print(json.dumps(result,sort_keys=True),flush=True)

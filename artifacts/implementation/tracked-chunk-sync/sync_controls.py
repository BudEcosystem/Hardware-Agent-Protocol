"""Real-file synchronization traces, modeled acknowledgements and named faults."""
import errno
import json
import os
from pathlib import Path
import random
from unittest.mock import patch

import fixed_block as bd
import sync_identity as helper

WORK=Path.cwd()
CHECKS=[]
DETAILS={}


def check(name, value):
    assert value, name
    CHECKS.append(name)


def refuse(name, action, kind, match=''):
    try:action()
    except kind as error:check(name, match in str(error))
    else:raise AssertionError(name+': accepted')


def make(name, chunks=1):
    identity=__import__('hashlib').sha256(name.encode()).hexdigest()[:32]
    anchor=bd.create_image(WORK/name,identity,chunks)
    with (WORK/(name+'-anchor.json')).open('x') as stream:json.dump(anchor,stream,sort_keys=True);stream.write('\n')
    return identity,anchor


def owner(name, identity, anchor):
    return bd.FixedBlockImage(WORK/name,identity,len(anchor['files']),expected_objects=anchor['objects'])


def trace_sync(image):
    reverse={fd:int(name[6:]) for name,fd in image._fds.items() if name.startswith('chunk-')}
    events=[];sync=bd.os.fsync;wait=bd._wait_file
    def full(fd):events.append(['fsync',reverse[fd]]);return sync(fd)
    def clean(fd):events.append(['wait',reverse[fd]]);return wait(fd)
    with patch.object(bd.os,'fsync',full),patch.object(bd,'_wait_file',clean):image.sync()
    return events


def main():
    os.umask(0o077)
    library=os.environ['HMS_SYNC_LIBRARY'];wanted=os.environ['HMS_SYNC_LIBRARY_SHA256']
    refuse('wrong helper identity refuses',lambda:helper.Probe(library,'0'*64),helper.SyncError,'LIBRARY_IDENTITY')
    probe=helper.Probe(library,wanted)
    for value in [-1,True,2**31,'7']:
        refuse('invalid descriptor '+repr(value),lambda value=value:probe.wait(value),helper.SyncError,'INVALID_SYNC_DESCRIPTOR')
    fd=os.open(WORK,os.O_RDONLY|os.O_DIRECTORY);os.close(fd)
    refuse('closed descriptor reports EBADF',lambda:probe.wait(fd),helper.SyncError,'ERRNO_9')
    identity,anchor=make('main',3);image=owner('main',identity,anchor)
    try:
        check('new owner conservatively requires every chunk',image._pending_sync==7)
        check('initial sync fsyncs every chunk with chunk zero last',trace_sync(image)==[['fsync',1],['fsync',2],['fsync',0]])
        check('only complete sync clears pending bits',image._pending_sync==0)
        check('clean sync observes other-file errors and retains final fsync',trace_sync(image)==[['wait',1],['wait',2],['fsync',0]])
        image.read(4096,0,0);image.write(8192,0,b'')
        check('empty operations do not create synchronization obligations',image._pending_sync==0)
        with patch.object(bd.os,'pwrite') as writer:
            refuse('invalid write does not execute',lambda:image.write(8192,1,b'A'*16),bd.ImageError,'INVALID_RANGE')
            check('invalid range leaves state and backing alone',not writer.called and image._pending_sync==0 and not image._poisoned)
        image.read(8192,0,16)
        check('payload read is tracked for possible access metadata',image._pending_sync==4)
        check('read-touched chunk receives full fsync',trace_sync(image)==[['wait',1],['fsync',2],['fsync',0]])
        image.write(4096,0,b'A'*16)
        check('write marks its own chunk',image._pending_sync==2)
        check('write-touched chunk receives full fsync',trace_sync(image)==[['fsync',1],['wait',2],['fsync',0]])
        image.erase(8192)
        check('erase uses tracked write path',image._pending_sync==4)
        image.sync()
        real=bd.os.pwrite;seen=[]
        def short(fd,data,offset):
            seen.append(image._pending_sync)
            return real(fd,data[:7],offset)
        with patch.object(bd.os,'pwrite',short):image.write(8192,32,b'B'*32)
        check('bit set before every positive short write',seen==[4]*5)
        image.sync()
        real_read=bd.os.pread;seen=[]
        def read(fd,size,offset):
            if fd==image._fds['chunk-01']:seen.append(image._pending_sync)
            return real_read(fd,size,offset)
        with patch.object(bd.os,'pread',read):image.read(4096,0,16)
        check('read bit set before underlying payload read',seen==[2])
        image.sync()
        # An independent event model: only a successful real fsync advances
        # the durable generation; wait calls never do. This models ordering,
        # not physical power loss or the truthfulness of storage hardware.
        fds={image._fds[f'chunk-{i:02d}'] for i in range(3)}
        versions={fd:0 for fd in fds};durable=dict(versions);barriers=0
        real_write=bd.os.pwrite;real_sync=bd.os.fsync;real_wait=bd._wait_file
        counts=dict(writes=0,fsyncs=0,waits=0)
        def modeled_write(fd,data,offset):
            amount=real_write(fd,data,offset)
            if fd in fds and amount>0:versions[fd]+=1;counts['writes']+=1
            return amount
        def modeled_sync(fd):
            value=real_sync(fd)
            if fd in fds:durable[fd]=versions[fd];counts['fsyncs']+=1
            return value
        def modeled_wait(fd):
            counts['waits']+=1
            return real_wait(fd)
        rng=random.Random(94)
        with patch.object(bd.os,'pwrite',modeled_write),patch.object(bd.os,'fsync',modeled_sync),patch.object(bd,'_wait_file',modeled_wait):
            for step in range(120):
                chunk=rng.randrange(3);kind=step%5;block=chunk*4096+1
                if kind==0:image.write(block,0,bytes([step])*16)
                elif kind==1:image.read(block,0,16)
                elif kind==2:image.erase(block)
                else:
                    image.sync();barriers+=1
                    assert versions==durable,'acknowledged generation was not fsynced'
            image.sync();barriers+=1;assert versions==durable
        check('all modeled acknowledged generations crossed successful real fsync',barriers==49 and counts['writes']==48)
        check('model exercised both full sync and untouched-file wait',counts['waits']>0 and counts['fsyncs']>0)
        DETAILS['acknowledgementModel']=dict(steps=120,barriers=barriers,**counts,physicalPowerLoss=False)
    finally:image.close()
    image=owner('main',identity,anchor)
    try:
        check('cold owner forgets old in-memory clean state',image._pending_sync==7)
        check('cold first barrier still fsyncs every chunk',trace_sync(image)==[['fsync',1],['fsync',2],['fsync',0]])
        image.read(4096,0,16)
        with patch.object(bd.os,'fsync') as sync,patch.object(bd,'_wait_file') as wait:
            image.close()
            check('close does not settle pending writes or reads',not sync.called and not wait.called and image._pending_sync==2)
    finally:image.close()

    identity,anchor=make('failed-fsync',3);image=owner('failed-fsync',identity,anchor)
    real=bd.os.fsync;events=[]
    def fail_later(fd):
        events.append(fd)
        if fd==image._fds['chunk-02']:raise OSError(errno.EIO,'injected later fsync')
        return real(fd)
    try:
        with patch.object(bd.os,'fsync',fail_later):
            refuse('later fsync failure is propagated',image.sync,OSError,'injected later')
        check('partial sync does not clear any pending bits',image._pending_sync==7 and image._poisoned and events==[image._fds['chunk-01'],image._fds['chunk-02']])
        refuse('failed sync cannot be retried by poisoned owner',image.sync,bd.ImageError,'POISONED')
    finally:image.close()

    identity,anchor=make('failed-wait',3);image=owner('failed-wait',identity,anchor)
    image.sync();image.write(4096,0,b'W'*16);real=bd.os.fsync;events=[]
    def full(fd):events.append(['fsync',fd]);return real(fd)
    def fail_wait(fd):events.append(['wait',fd]);raise helper.SyncError('SYNC_WAIT_ERRNO_5')
    try:
        with patch.object(bd.os,'fsync',full),patch.object(bd.sync_identity,'wait',fail_wait):
            refuse('untouched-file deferred error refuses barrier',image.sync,bd.ImageError,'SYNC_WAIT_ERRNO_5')
        check('wait failure after earlier fsync retains all obligations',image._pending_sync==2 and image._poisoned and events==[['fsync',image._fds['chunk-01']],['wait',image._fds['chunk-02']]])
        refuse('deferred error poisons further writes',lambda:image.write(0,0,b'X'*16),bd.ImageError,'POISONED')
    finally:image.close()

    identity,anchor=make('failed-clean-barrier');image=owner('failed-clean-barrier',identity,anchor);image.sync()
    try:
        with patch.object(bd.os,'fsync',side_effect=OSError(errno.EIO,'injected clean barrier')):
            refuse('clean barrier still observes fsync failure',image.sync,OSError,'injected clean')
        check('clean barrier error poisons owner',image._poisoned)
    finally:image.close()

    identity,anchor=make('failed-partial-write');image=owner('failed-partial-write',identity,anchor);image.sync()
    real=bd.os.pwrite;calls=0
    def partial(fd,data,offset):
        nonlocal calls
        calls+=1;assert image._pending_sync==1
        if calls==1:return real(fd,data[:7],offset)
        raise OSError(errno.EIO,'injected after seven bytes')
    try:
        with patch.object(bd.os,'pwrite',partial):
            refuse('partial write failure retains uncertainty',lambda:image.write(0,0,b'P'*16),OSError,'seven bytes')
        check('partial write bit survives failure',image._pending_sync==1 and image._poisoned)
    finally:image.close()
    with (WORK/'failed-partial-write/chunk-00').open('rb') as stream:body=stream.read(16)
    check('partial physical fixture retained without rollback',body==b'P'*7+b'\xff'*9)

    identity,anchor=make('failed-interrupt');image=owner('failed-interrupt',identity,anchor);image.sync()
    try:
        with patch.object(bd.os,'pwrite',side_effect=KeyboardInterrupt):
            refuse('interrupt is propagated',lambda:image.write(0,0,b'I'*16),KeyboardInterrupt)
        check('interrupt leaves obligation and poison',image._pending_sync==1 and image._poisoned)
    finally:image.close()

    identity,anchor=make('failed-admission');before=len(os.listdir('/proc/self/fd'))
    with patch.object(bd.sync_identity,'wait',side_effect=helper.SyncError('SYNC_WAIT_ERRNO_38')):
        refuse('unavailable kernel operation refuses admission',lambda:owner('failed-admission',identity,anchor),bd.ImageError,'ERRNO_38')
    check('failed admission releases its descriptors',len(os.listdir('/proc/self/fd'))==before)
    result=dict(status='passed',checks=CHECKS,details=DETAILS,physicalPowerLossTested=False,
                failedImagesReopened=False,failedImagesRepaired=False)
    with (WORK/'checks.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps(result,sort_keys=True),flush=True)


if __name__=='__main__':main()

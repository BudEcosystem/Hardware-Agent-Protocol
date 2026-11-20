"""Explicit profile admission and refusal before recovery on owned fixtures."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from candidate import HierarchicalStore as Store
import hierarchical_store as implementation
from native import Native

HERE=Path(__file__).resolve().parent
WORK=Path.cwd()
KW=dict(block_source=HERE/'fixed_block.py',library=os.environ['HMS_LIBRARY'],library_hash=os.environ['HMS_LIBRARY_SHA256'])
CHECKS=[]


def check(name,value):
    assert value,name
    CHECKS.append(name)


def hashes(path):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()}


def refused(name,action,match):
    try:action()
    except implementation.StorageError as error:check(name,match in str(error))
    else:raise AssertionError(name+': accepted')


def main():
    os.umask(0o077)
    store=Store.create(WORK/'good','95959595959595959595959595959595',chunks=1,**KW)
    anchor=store.anchor
    (WORK/'good-anchor.json').write_text(json.dumps(anchor,sort_keys=True)+'\n')
    handle=store.open('kept',create=True);store.pwrite(handle,b'PAT',0);store.close_handle(handle);store.close()
    before=hashes(WORK/'good');old=dict(anchor,storeProfile='hms.hierarchical-chunk-store.inline512/0.1')
    with patch.object(implementation,'Native',side_effect=AssertionError('native opened before profile check')) as native:
        refused('old anchor profile refuses',lambda:Store.reopen(WORK/'good',old,**KW),'STORAGE_PROFILE')
        check('anchor refusal does not instantiate native filesystem',not native.called)
    check('anchor refusal leaves backing bytes exact',hashes(WORK/'good')==before)
    store=Store.reopen(WORK/'good',anchor,**KW)
    handle=store.open('kept',writable=False)
    check('new profile cold read keeps complete payload',store.pread(handle,3,0)==b'PAT')
    store.close_handle(handle);store.close()

    store=Store.create(WORK/'wrong-super','96969696969696969696969696969696',chunks=1,**KW)
    anchor=store.anchor
    (WORK/'wrong-super-anchor.json').write_text(json.dumps(anchor,sort_keys=True)+'\n')
    changed=dict(store.super,profile='hms.hierarchical-chunk-store.inline512/0.1')
    store.native.write('super',implementation._pack(changed))
    store.native.write('super.tmp',b'RETAIN ON REFUSAL')
    store.dispose();before=hashes(WORK/'wrong-super');observed=[]
    class Observed(Native):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);observed.append(self)
    with patch.object(implementation,'Native',Observed),patch.object(Store,'_recover_inventory',side_effect=AssertionError('recovery on wrong profile')) as recovery:
        refused('old on-disk profile refuses',lambda:Store.reopen(WORK/'wrong-super',anchor,**KW),'INVALID_SUPERBLOCK')
        check('on-disk refusal occurs before inventory recovery',not recovery.called)
    check('refused native mount made no mutation callbacks',len(observed)==1 and all(observed[0].counts[k]==0 for k in ['programCalls','erases','syncs']))
    check('refused profile and cleanup candidate remain byte exact',hashes(WORK/'wrong-super')==before)
    result=dict(status='passed',checks=CHECKS,wrongSuperBackingHashes=before,
                refusedOwnerCallbacks=observed[0].counts,recoveryInvoked=False)
    with (WORK/'checks.json').open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps(result,sort_keys=True),flush=True)


if __name__=='__main__':main()

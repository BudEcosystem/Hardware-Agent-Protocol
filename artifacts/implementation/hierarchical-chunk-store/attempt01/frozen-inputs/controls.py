"""Finite behavioral scopes, real bounded images, no unchanged retry."""
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

from hierarchical_store import HierarchicalStore as Store, Reject, StorageError, NativeError
from hierarchical_store import CHUNK, MAX_FILE, _pack

HERE=Path(__file__).resolve().parent
WORK=Path.cwd()
KW=dict(block_source=HERE/'fixed_block.py',library=os.environ['HMS_LIBRARY'],
        library_hash=os.environ['HMS_LIBRARY_SHA256'])
CHECKS=[]
DETAILS={}

def save(name,value):
    with (WORK/name).open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def check(name,value):
    if not value:raise AssertionError(name)
    CHECKS.append(name)

def refused(name,error,action,match):
    try:action()
    except error as exc:check(name,match in str(exc))
    else:raise AssertionError(name+': accepted')

def create(name='image',chunks=1):
    store=Store.create(WORK/name,hashlib.sha256(name.encode()).hexdigest()[:32],chunks=chunks,**KW)
    save(name+'-anchor.json',store.anchor)
    return store

def reopen(name='image',cls=Store):
    return cls.reopen(WORK/name,json.loads((WORK/(name+'-anchor.json')).read_text()),**KW)

def readall(store,handle):
    return b''.join(store.pread(handle,min(65536,store.info(handle)['size']-pos),pos)
                    for pos in range(0,store.info(handle)['size'],65536))

def finish(store):
    for handle in list(store.handles):store.close_handle(handle)
    store.close()

def image_hashes(name):
    return {p.name:digest(p) for p in sorted((WORK/name).iterdir())}

def clone(name,target):
    # Fresh private provider objects; exact old image bytes, distinct host anchors.
    import fixed_block
    old=json.loads((WORK/(name+'-anchor.json')).read_text())
    anchor=fixed_block.create_image(WORK/target,old['identity'],old['storeChunks'])
    anchor.update(storeProfile=old['storeProfile'],storeChunks=old['storeChunks'])
    for source in sorted((WORK/name).glob('chunk-*')):
        with source.open('rb') as src,(WORK/target/source.name).open('r+b') as dst:
            while data:=src.read(65536):dst.write(data)
            dst.flush();os.fsync(dst.fileno())
        assert digest(source)==digest(WORK/target/source.name)
    save(target+'-anchor.json',anchor)
    save(target+'-lineage.json',dict(source=name,sourceHashes=image_hashes(name),targetHashes=image_hashes(target)))

def hierarchy():
    s=create();s.mkdir('lab');s.mkdir('lab/stage');d=s.open('lab/stage',directory=True)
    f=s.open('position',create=True,exclusive=True,dir_handle=d);s.pwrite(f,b'12.5 um',0)
    check('descriptor-relative file lookup',s.stat('position',dir_handle=d)['id']==s.info(f)['id'])
    s.rename('lab','experiment')
    check('directory handle survives ancestor rename',s.listdir(dir_handle=d)[0]['name']=='position')
    g=s.open('position',dir_handle=d)
    check('relative reopen after ancestor rename reads exact bytes',readall(s,g)==b'12.5 um')
    check('complete path points to stable inode',s.stat('experiment/stage/position')['id']==s.info(f)['id'])
    unicode_name='é'*127+'a';u=s.open(unicode_name,create=True,dir_handle=d);s.close_handle(u)
    check('255-byte UTF-8 component survives listing',unicode_name in [e['name'] for e in s.listdir(dir_handle=d)])
    s.chmod('experiment',0o700);s.chmod('experiment/stage/position',0o600)
    refused('nonempty directory removal refused',Reject,lambda:s.rmdir('experiment'),'NOT_EMPTY')
    refused('directory cannot be read as file',Reject,lambda:s.pread(d,1,0),'IS_DIRECTORY')
    identity=s.info(d)['id'];finish(s);s=reopen()
    check('cold hierarchy and IDs retained',s.stat('experiment/stage')['id']==identity)
    f=s.open('experiment/stage/position');check('cold nested body exact',readall(s,f)==b'12.5 um')
    finish(s)

def data():
    s=create();a=s.open('data',create=True);b=s.open('data')
    expected=bytearray(bytes(range(256))*32);s.pwrite(a,bytes(expected),0)
    check('existing second handle sees committed data',readall(s,b)==expected)
    s.pwrite(b,b'X'*16,4090);expected[4090:4106]=b'X'*16
    check('cross-chunk overwrite visible through first handle',readall(s,a)==expected)
    s.truncate(a,4100);expected=expected[:4100]
    check('shrink updates all handles',readall(s,b)==expected)
    s.truncate(b,9000);expected.extend(b'\0'*(9000-len(expected)))
    check('regrowth hides truncated tail bytes',readall(s,a)==expected)
    s.pwrite(a,b'Z',12000);expected.extend(b'\0'*(12000-len(expected))+b'Z')
    check('sparse extension exact',readall(s,b)==expected)
    counts=dict(s.native.counts)
    check('empty write at limit does not extend',s.pwrite(a,b'',MAX_FILE)==0 and s.info(a)['size']==12001)
    check('empty write issues no callbacks',s.native.counts==counts)
    check('read past EOF empty',s.pread(b,1,13000)==b'')
    DETAILS['expectedSha256']=hashlib.sha256(expected).hexdigest();finish(s);s=reopen()
    a=s.open('data');check('cold whole body exact',readall(s,a)==expected);finish(s)

def namespace():
    s=create();s.mkdir('left');s.mkdir('right');s.mkdir('left/tree');s.mkdir('right/empty')
    held=s.open('left/tree',directory=True);old=s.open('right/empty',directory=True)
    f=s.open('left/tree/data',create=True);s.pwrite(f,b'SOURCE',0)
    s.rename('left/tree','right/empty')
    check('moved directory preserves identity',s.stat('right/empty')['id']==s.info(held)['id'])
    check('replaced held directory is unlinked',s.info(old)['links']==0)
    check('replaced held directory remains listable',s.listdir(dir_handle=old)==[])
    refused('unlinked directory rejects creation',Reject,lambda:s.open('lost',create=True,dir_handle=old),'UNLINKED_DIRECTORY')
    check('held moved directory resolves its subtree',s.stat('data',dir_handle=held)['id']==s.info(f)['id'])
    refused('move directory into its subtree refused',Reject,lambda:s.rename('right','right/empty/cycle'),'DIRECTORY_CYCLE')
    t=s.open('right/target',create=True);s.pwrite(t,b'TARGET',0);old_id=s.info(t)['id']
    s.rename('right/empty/data','right/target')
    check('replacement keeps old handle body',readall(s,t)==b'TARGET' and s.info(t)['links']==0)
    check('new target resolves source',s.stat('right/target')['id']==s.info(f)['id'])
    s.unlink('right/target');n=s.open('right/target',create=True);s.pwrite(n,b'NEW',0);s.pwrite(f,b'O',0)
    check('open unlinked file retains independent mutable body',readall(s,f)==b'OOURCE' and readall(s,n)==b'NEW')
    s.close_handle(t);check('last replaced-file handle reclaims inode',old_id not in s.inodes)
    s.rmdir('right/empty');check('held removed directory list remains empty',s.listdir(dir_handle=held)==[])
    DETAILS['accounting']=s.accounting();finish(s);s=reopen()
    check('cold complete namespace after replacements',[(x['name'],x['kind']) for x in s.listdir('right')]==[('target','file')])
    n=s.open('right/target');check('cold recreated body exact',readall(s,n)==b'NEW');finish(s)

def bounds():
    s=create();f=s.open('f',create=True);ro=s.open('f',writable=False)
    checks=[('absolute path',lambda:s.open('/x',create=True),'INVALID_NAME'),
        ('dot component',lambda:s.mkdir('a/../b'),'INVALID_NAME'),
        ('empty component',lambda:s.mkdir('a//b'),'INVALID_NAME'),
        ('NUL component',lambda:s.mkdir('a\0b'),'INVALID_NAME'),
        ('oversize UTF-8 name',lambda:s.mkdir('é'*128),'NAME_LIMIT'),
        ('path limit',lambda:s.mkdir('/'.join(['x'*255]*17)),'PATH_LIMIT'),
        ('depth limit',lambda:s.mkdir('/'.join(['x']*33)),'DEPTH_LIMIT'),
        ('bool flags',lambda:s.open('f',create=1),'INVALID_FLAGS'),
        ('unsupported mode',lambda:s.chmod('f',0o644),'UNSUPPORTED_MODE'),
        ('file offset limit',lambda:s.pwrite(f,b'Z',MAX_FILE),'FILE_LIMIT'),
        ('transfer cap',lambda:s.pwrite(f,b'Z'*65537,0),'INVALID_DATA'),
        ('negative truncate',lambda:s.truncate(f,-1),'INVALID_RANGE'),
        ('readonly mutation',lambda:s.pwrite(ro,b'Z',0),'READ_ONLY'),
        ('root removal',lambda:s.rmdir(''),'ROOT_OPERATION')]
    before=dict(s.native.counts)
    for name,action,message in checks:refused(name,Reject,action,message)
    check('invalid requests perform no provider I/O',s.native.counts==before)
    handles=[s.open('f') for unused in range(62)];before=dict(s.native.counts)
    refused('65th live handle refused',Reject,lambda:s.open('f'),'HANDLE_LIMIT')
    check('handle cap has no I/O',s.native.counts==before)
    for h in handles:s.close_handle(h)
    s.close_handle(ro);refused('stale handle refused',Reject,lambda:s.info(ro),'BAD_HANDLE')
    parent=None
    for unused in range(16):
        s.mkdir('x'*255,dir_handle=parent);child=s.open('x'*255,directory=True,dir_handle=parent)
        if parent is not None:s.close_handle(parent)
        parent=child
    check('exact 4095-byte full path admitted',s.info(parent)['kind']=='dir')
    before=dict(s.native.counts)
    refused('handle-relative global path bound',Reject,lambda:s.mkdir('z',dir_handle=parent),'PATH_LIMIT')
    check('relative path bound no I/O',s.native.counts==before)
    s.mkdir('branch');s.mkdir('branch/'+'y'*255)
    target='/'.join(['x'*255]*15+['z'])
    before=dict(s.native.counts)
    refused('subtree rename global path bound',Reject,lambda:s.rename('branch',target),'PATH_LIMIT')
    check('subtree refusal preserves namespace without I/O',s.native.counts==before and s.stat('branch')['kind']=='dir')
    DETAILS['unmaterializedLimit']='8192 inode admission cap not exhaustively allocated in this one-chunk scope'
    finish(s);s=reopen();check('maximum path survives cold inventory',s.stat('/'.join(['x'*255]*16))['kind']=='dir');finish(s)

class Cut(RuntimeError):pass

def recovery():
    for phase in ['identity_reserved','inode_durable','entry_staged','entry_published']:
        name=phase;s=create(name);s.mkdir('kept')
        def checkpoint(current,value):
            if current==phase:
                save(name+'-checkpoint.json',dict(phase=current,value=value));raise Cut(phase)
        s._checkpoint=checkpoint
        refused(phase+' stops owner',Cut,lambda:s.open('kept/new',create=True),phase)
        check(phase+' poisons owner',s.poisoned);s.dispose();before=image_hashes(name)
        clone(name,name+'-recovered');r=reopen(name+'-recovered')
        expected=['new'] if phase=='entry_published' else []
        check(phase+' recovery exact visibility',[e['name'] for e in r.listdir('kept')]==expected)
        check(phase+' only linked inodes retained',len(r.inodes)==len(r.parents)==2+len(expected))
        check(phase+' pending entries reclaimed',r.native.entries('pending',8192)==[])
        finish(r);check(phase+' original untouched',image_hashes(name)==before)

def corruption():
    s=create();s.mkdir('dir');f=s.open('dir/data',create=True);s.pwrite(f,b'A'*4096,0)
    identity=s.info(f)['id'];s.native.write('super.tmp',b'partial staged state')
    s.native.remove(s._path(s.inodes[identity],0));s.dispose();before=image_hashes('image')
    refused('missing committed chunk refuses cold mount',StorageError,lambda:reopen(),'MISSING_REFERENCED_CHUNK')
    check('corrupt mount performs no image mutation',image_hashes('image')==before)
    save('corrupt-image-hashes.json',before)
    s=create('graph');f=s.open('data',create=True)
    s.native.write(s._entry_path(1,'alias'),_pack(dict(id=s.info(f)['id'],kind='file')))
    s.native.write('super.tmp',b'uncommitted');s.dispose();before=image_hashes('graph')
    refused('duplicate inode reference refuses cold mount',StorageError,lambda:reopen('graph'),'INVALID_TREE_LINK')
    check('invalid graph refused before staged cleanup',image_hashes('graph')==before)

def orphan_recovery():
    s=create();live=s.open('live',create=True);s.pwrite(live,b'LIVE',0)
    gone=s.open('gone',create=True);s.pwrite(gone,b'GONE',0);s.mkdir('empty');directory=s.open('empty',directory=True)
    dead_ids=[s.info(gone)['id'],s.info(directory)['id']]
    s.unlink('gone');s.rmdir('empty');s.sync()
    save('owner-before-dispose.json',dict(dead=dead_ids,accounting=s.accounting()))
    s.dispose();before=image_hashes('image');clone('image','recovered');r=reopen('recovered')
    check('ownerless file and directory removed',all(i not in r.inodes for i in dead_ids))
    check('ownerless backing objects reclaimed',all(r.native.stat(r._directory(i)) is None for i in dead_ids))
    check('only live linked file and root remain',len(r.inodes)==2 and [x['name'] for x in r.listdir()]==['live'])
    live=r.open('live');check('linked file survives owner disposal',readall(r,live)==b'LIVE');finish(r)
    check('original unlinked objects remain preserved',image_hashes('image')==before)

def owner_loss():
    s=create();f=s.open('data',create=True);s.pwrite(f,b'A'*4096,0)
    image=WORK/'image';os.rename(image/'owner',image/'owner-original')
    with (image/'owner').open('xb') as out:out.write((s.anchor['identity']+'\n').encode());out.flush();os.fsync(out.fileno())
    os.chmod(image/'owner',0o600);before=image_hashes('image')
    refused('owner pathname replacement refuses I/O',StorageError,lambda:s.sync(),'LITTLEFS_-5')
    check('owner loss poisons logical owner',s.poisoned)
    refused('poisoned owner rejects later reads',StorageError,lambda:s.pread(f,1,0),'POISONED')
    s.dispose();check('owner-loss refusal preserves raw backing',image_hashes('image')==before)

def fault():
    s=create();f=s.open('data',create=True);s.pwrite(f,b'A'*4096,0)
    def inject(kind):
        if kind=='program':raise OSError('injected program callback failure')
    s.native.inject=inject
    refused('callback failure refuses overwrite',NativeError,lambda:s.pwrite(f,b'B',0),'LITTLEFS_-5')
    check('callback failure retained',s.native.fault is not None and 'injected' in s.native.fault)
    check('uncertain error poisons owner',s.poisoned)
    refused('poisoned owner cannot retry write',StorageError,lambda:s.pwrite(f,b'B',0),'POISONED')
    s.dispose();save('failed-image-hashes.json',image_hashes('image'))

def dataset():
    value=json.loads((HERE/'dataset.json').read_text())
    assert len(value['files'])==4270 and sum(row['bytes'] for row in value['files'])==35508922
    return value

def replay_write():
    value=dataset();root=Path(value['sourceRoot']);s=create(chunks=8)
    with (WORK/'progress.jsonl').open('x') as log:
        for path in value['directories']:s.mkdir(path)
        log.write(json.dumps(dict(directoriesComplete=len(value['directories'])))+'\n');log.flush();os.fsync(log.fileno())
        for row in value['files']:
            body=(root/row['path']).read_bytes()
            assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256']
            h=s.open(row['path'],create=True,exclusive=True)
            for offset in range(0,len(body),65536):s.pwrite(h,body[offset:offset+65536],offset)
            s.close_handle(h)
            log.write(json.dumps(row,sort_keys=True)+'\n');log.flush();os.fsync(log.fileno())
    check('all original workflow files written',len(value['files'])==4270)
    check('complete original namespace count',len(s.inodes)==1+len(value['directories'])+len(value['files']))
    DETAILS['accounting']=s.accounting();DETAILS['callbacks']=dict(s.native.counts);finish(s)

def replay_read():
    value=dataset();writer=Path(os.environ['HMS_REPLAY_WRITER'])
    anchor=json.loads((writer/'image-anchor.json').read_text());before={p.name:digest(p) for p in (writer/'image').iterdir()}
    s=Store.reopen(writer/'image',anchor,**KW)
    directories=set();files={};pending=['']
    while pending:
        parent=pending.pop()
        for row in s.listdir(parent):
            path=parent+'/'+row['name'] if parent else row['name']
            if row['kind']=='dir':directories.add(path);pending.append(path)
            else:files[path]=row
    check('cold directory set exact',directories==set(value['directories']))
    check('cold file set exact',set(files)=={row['path'] for row in value['files']})
    for row in value['files']:
        h=s.open(row['path'],writable=False);body=readall(s,h);s.close_handle(h)
        if len(body)!=row['bytes'] or hashlib.sha256(body).hexdigest()!=row['sha256']:raise AssertionError(row['path'])
    check('all 4270 full bodies and sizes exact',len(files)==4270)
    DETAILS['accounting']=s.accounting();DETAILS['callbacks']=dict(s.native.counts);finish(s)
    check('clean cold reader leaves backing exact',{p.name:digest(p) for p in (writer/'image').iterdir()}==before)

if __name__=='__main__':
    os.umask(0o077);started=time.monotonic();scope=sys.argv[1]
    scopes={f.__name__:f for f in [hierarchy,data,namespace,bounds,recovery,corruption,orphan_recovery,owner_loss,fault,replay_write,replay_read]}
    scopes[scope]()
    usage=resource.getrusage(resource.RUSAGE_SELF)
    result=dict(scope=scope,status='passed',checks=CHECKS,details=DETAILS,elapsedSeconds=time.monotonic()-started,
                cpuSeconds=usage.ru_utime+usage.ru_stime,peakRSSKiB=usage.ru_maxrss)
    save('checks.json',result);print(json.dumps(result,sort_keys=True),flush=True)

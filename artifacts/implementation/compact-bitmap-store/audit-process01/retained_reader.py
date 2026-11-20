"""Independent logical reconstruction with strictly read-only backing descriptors."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

HERE=Path(os.environ['HMS_AUDIT_STAGE'])
ROOT=HERE.parents[2]
ATTEMPT=HERE/'attempt01'
FROZEN=ATTEMPT/'frozen-inputs'
sys.path.insert(0,str(FROZEN))
from native import Native

def read(path):return json.loads(path.read_text())
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def canonical(body):return json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
def unpack(raw):
    envelope=json.loads(raw);assert set(envelope)=={'body','sha256'}
    assert canonical(envelope)==raw and hashlib.sha256(canonical(envelope['body'])).hexdigest()==envelope['sha256']
    return envelope['body']

class ReadOnlyImage:
    def __init__(self,path,anchor_path,*,replaced_owner=False):
        self.root=path;self.anchor=read(anchor_path);self.fds={};self.before={};self.named={}
        self.block_count=self.anchor['storeChunks']*4096
        expected={'owner','manifest'}|{f'chunk-{i:02d}' for i in range(self.anchor['storeChunks'])}
        if replaced_owner:expected.add('owner-original')
        assert path.resolve(strict=True)==path and {p.name for p in path.iterdir()}==expected
        try:
            for name in ['.']+sorted(expected):
                flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC
                if name=='.':flags|=os.O_DIRECTORY
                fd=os.open(path/name,flags);self.fds[name]=fd;fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                info=os.fstat(fd);named=(path/name).stat(follow_symlinks=False)
                assert (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino)
                self.named[name]=(info.st_dev,info.st_ino)
                anchor_name='owner' if name=='owner-original' else name
                if replaced_owner and name=='owner':assert list(self.named[name])!=self.anchor['objects']['owner']
                else:assert list(self.named[name])==self.anchor['objects'][anchor_name]
                assert info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==(0o700 if name=='.' else 0o600)
                if name!='.':
                    assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_blocks*512>=info.st_size
                    if name.startswith('chunk-'):assert info.st_size==16*1024**2
                    self.before[name]=digest(path/name)
            owner='owner-original' if replaced_owner else 'owner'
            assert os.pread(self.fds[owner],34,0)==(self.anchor['identity']+'\n').encode()
            assert hashlib.sha256(os.pread(self.fds['manifest'],4096,0)).hexdigest()==self.anchor['manifestSha256']
        except BaseException:self.close();raise

    def read(self,block,offset,size):
        assert 0<=block<self.block_count and 0<=offset<=4096 and 0<=size<=4096-offset
        assert offset%16==size%16==0
        absolute=block*4096+offset;chunk,position=divmod(absolute,16*1024**2)
        value=os.pread(self.fds[f'chunk-{chunk:02d}'],size,position);assert len(value)==size;return value
    def write(self,*args):raise AssertionError('AUDIT_WRITE_FORBIDDEN')
    def erase(self,*args):raise AssertionError('AUDIT_ERASE_FORBIDDEN')
    def sync(self):raise AssertionError('AUDIT_SYNC_FORBIDDEN')
    def stable(self):
        for name,identity in self.named.items():
            info=(self.root/name).stat(follow_symlinks=False);assert (info.st_dev,info.st_ino)==identity
        assert {p.name for p in self.root.iterdir()}==set(self.before)
        assert all(digest(self.root/name)==wanted for name,wanted in self.before.items())
    def close(self):
        for fd in self.fds.values():os.close(fd)
        self.fds.clear()

def inspect(path,anchor,library_hash,*,replaced_owner=False,
            expected_profile='hms.hierarchical-chunk-store.compact-bitmap/0.1',library_path=None,
            bitmap_encoding='compact'):
    assert expected_profile=={'compact':'hms.hierarchical-chunk-store.compact-bitmap/0.1',
                             'fixed512':'hms.hierarchical-chunk-store.inline512/0.1'}[bitmap_encoding]
    image=ReadOnlyImage(path,anchor,replaced_owner=replaced_owner);native=None
    try:
        native=Native(image,ATTEMPT/'hierarchical-store.so' if library_path is None else library_path,library_hash);native.call('hm_mount')
        superblock=unpack(native.read('super'));assert superblock['identity']==image.anchor['identity']
        assert superblock['profile']==expected_profile and superblock['root']==1
        nodes={};physical={}
        for bucket,kind,size in native.entries('objects',256):
            assert kind==2 and size==0
            for name,kind,size in native.entries('objects/'+bucket,8192):
                assert kind==2 and size==0
                identity=int(name[1:],16);directory='objects/'+bucket+'/'+name
                assert identity%256==int(bucket[1:],16) and identity not in nodes and 1<=identity<superblock['next']
                items={n:(k,s) for n,k,s in native.entries(directory,4099)};physical[identity]=items
                if 'state' not in items:continue
                inode=unpack(native.read(directory+'/state'));assert inode['id']==identity
                children={};payload=None;missing=[]
                if inode['kind']=='dir':
                    for n,k,z in native.entries(directory+'/entries',8192):
                        assert k==1;children[n]=unpack(native.read(directory+'/entries/'+n))['id']
                else:
                    assert inode['kind']=='file' and type(inode['size']) is int and 0<=inode['size']<=16*1024**2
                    count=(inode['size']+4095)//4096
                    length=(count+7)//8 if bitmap_encoding=='compact' else 512
                    wire=inode['chunks'];assert type(wire) is str and len(wire)==4*((length+2)//3)
                    bits=base64.b64decode(wire,validate=True)
                    assert len(bits)==length and base64.b64encode(bits).decode('ascii')==wire
                    if count%8:assert not bits[(count-1)//8]>>(count%8)
                    if bitmap_encoding=='fixed512':assert not any(bits[(count+7)//8:])
                    bits+=b'\0'*(512-len(bits))
                    # Normalize for semantic comparison only after strict wire validation.
                    inode=dict(inode,chunks=base64.b64encode(bits).decode('ascii'))
                    body=bytearray(inode['size'])
                    for number in range(4096):
                        if not bits[number//8]&(1<<(number%8)):continue
                        assert number*4096<inode['size'];chunk_name=f'c{number:08x}'
                        if chunk_name not in items:missing.append(number);continue
                        raw=native.read(directory+'/'+chunk_name);assert len(raw)==4096
                        amount=min(4096,inode['size']-number*4096);body[number*4096:number*4096+amount]=raw[:amount]
                    payload=bytes(body)
                nodes[identity]=dict(metadata=inode,children=children,payload=payload,missing=missing)
        directories=set();files={};seen={};duplicates=[];pending=[('',1)]
        while pending:
            name,identity=pending.pop();assert identity in nodes
            if identity in seen:duplicates.append(dict(path=name,first=seen[identity],inode=identity));continue
            seen[identity]=name;node=nodes[identity]
            if node['metadata']['kind']=='dir':
                if name:directories.add(name)
                pending.extend(((name+'/' if name else '')+n,i) for n,i in node['children'].items())
            else:files[name]=node
        assert native.fault is None and all(native.counts[k]==0 for k in ['programCalls','erases','syncs'])
        result=dict(directories=directories,files=files,nodes=nodes,physical=physical,duplicates=duplicates,
            unlinked=set(nodes)-set(seen),pending=[n for n,k,s in native.entries('pending',8192)],
            root={n:(k,s) for n,k,s in native.entries('/',5)},backingHashes=image.before,callbacks=dict(native.counts))
        image.stable();return result
    finally:
        if native is not None:native.dispose()
        image.close()

def bodies(observed):
    assert not observed['duplicates'] and all(not row['missing'] for row in observed['files'].values())
    return {name:row['payload'] for name,row in observed['files'].items()}


def inspect_corrupt_inode(path,anchor,library_hash,expected_disk_inode):
    """Read exact intentionally malformed state without invoking any adapter/recovery."""
    image=ReadOnlyImage(path,anchor);native=None
    try:
        native=Native(image,ATTEMPT/'hierarchical-store.so',library_hash);native.call('hm_mount')
        superblock=unpack(native.read('super'))
        assert superblock['profile']=='hms.hierarchical-chunk-store.compact-bitmap/0.1'
        assert superblock['identity']==image.anchor['identity']
        identity=expected_disk_inode['id'];directory=f'objects/b{identity%256:02x}/i{identity:016x}'
        raw=native.read(directory+'/state');assert unpack(raw)==expected_disk_inode
        assert native.read(directory+'/state.tmp')==b'KEEP STAGED INODE'
        assert native.read('super.tmp')==b'KEEP STAGED SUPER'
        assert native.read(directory+'/c00000000')==b'A'+b'\0'*4095
        assert native.fault is None and all(native.counts[k]==0 for k in ['programCalls','erases','syncs'])
        result=dict(diskInode=expected_disk_inode,stateSha256=hashlib.sha256(raw).hexdigest(),
                    backingHashes=image.before,callbacks=dict(native.counts),recoveryInvoked=False)
        image.stable();return result
    finally:
        if native is not None:native.dispose()
        image.close()

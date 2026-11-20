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
            expected_profile='hms.hierarchical-chunk-store.inline512/0.1',library_path=None):
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
                    assert inode['kind']=='file' and 0<=inode['size']<=16*1024**2
                    bits=base64.b64decode(inode['chunks'],validate=True);assert len(bits)==512
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

def main():
    report=read(ATTEMPT/'RESULTS.json');inputs=read(ATTEMPT/'inputs.json')
    assert report['inputsStable'] and sum(v['checks'] for k,v in report['scopes'].items() if not k.startswith('replay_'))==96
    for row in inputs['files']:assert digest(ROOT/row['path'])==digest(FROZEN/row['frozen'])==row['sha256']
    assert digest(FROZEN/'dataset.json')==inputs['datasetSha256']
    assert digest(ATTEMPT/'hierarchical-store.so')==report['librarySha256']
    processes=[]
    for path in sorted(ATTEMPT.glob('*/started.json')):
        start=read(path);end=read(path.with_name('result.json'))
        assert end['reaped'] and not Path('/proc',str(start['pid'])).exists()
        processes.append(dict(scope=path.parent.name,pid=start['pid'],**end))
    for scope,row in report['scopes'].items():
        work=ATTEMPT/scope;checks=read(work/'checks.json')
        assert read(work/'stdout.txt')==checks and digest(work/'checks.json')==row['receiptSha256']
        assert checks['status']=='passed' and len(checks['checks'])==row['checks']
        assert read(work/'result.json')['returnCode']==0
    images={}
    for anchor in sorted(ATTEMPT.glob('*/*-anchor.json')):
        path=anchor.with_name(anchor.name.removesuffix('-anchor.json'))
        if not path.is_dir():continue
        name=str(path.relative_to(ATTEMPT))
        images[name]=inspect(path,anchor,report['librarySha256'],replaced_owner=name=='owner_loss/image')
    expected=bytearray(bytes(range(256))*32);expected[4090:4106]=b'X'*16
    expected=expected[:4100]+b'\0'*(12000-4100)+b'Z'
    assert bodies(images['data/image'])=={'data':bytes(expected)}
    assert bodies(images['hierarchy/image'])=={'experiment/stage/position':b'12.5 um','experiment/stage/'+'é'*127+'a':b''}
    assert images['hierarchy/image']['directories']=={'experiment','experiment/stage'}
    assert bodies(images['namespace/image'])=={'right/target':b'NEW'}
    assert images['namespace/image']['directories']=={'left','right'}
    assert bodies(images['bounds/image'])=={'f':b''}
    assert '/'.join(['x'*255]*16) in images['bounds/image']['directories']
    for phase in ['identity_reserved','inode_durable','entry_staged','entry_published']:
        original=images['recovery/'+phase];recovered=images['recovery/'+phase+'-recovered']
        wanted={'kept/new':b''} if phase=='entry_published' else {}
        assert bodies(original)==bodies(recovered)==wanted
        assert original['directories']==recovered['directories']=={'kept'}
        assert not recovered['unlinked'] and not recovered['pending']
        lineage=read(ATTEMPT/'recovery'/(phase+'-recovered-lineage.json'))
        assert original['backingHashes']==lineage['sourceHashes']==lineage['targetHashes']
        assert read(ATTEMPT/'recovery'/(phase+'-checkpoint.json'))['phase']==phase
    old=images['orphan_recovery/image'];new=images['orphan_recovery/recovered']
    assert bodies(old)==bodies(new)=={'live':b'LIVE'} and len(old['unlinked'])==2 and not new['unlinked']
    assert len(new['nodes'])==2
    assert old['backingHashes']==read(ATTEMPT/'orphan_recovery/recovered-lineage.json')['sourceHashes']
    corrupt=images['corruption/image'];assert corrupt['files']['dir/data']['missing']==[0] and 'super.tmp' in corrupt['root']
    assert corrupt['backingHashes']==read(ATTEMPT/'corruption/corrupt-image-hashes.json')
    graph=images['corruption/graph'];assert len(graph['duplicates'])==1 and 'super.tmp' in graph['root']
    assert bodies(images['owner_loss/image'])=={'data':b'A'*4096}
    fault=images['fault/image'];assert bodies(fault)['data'] in (b'A'*4096,b'B'+b'A'*4095)
    assert fault['backingHashes']==read(ATTEMPT/'fault/failed-image-hashes.json')
    dataset=read(FROZEN/'dataset.json');replay=None
    if 'replay_write/image' in images:
        observed=images['replay_write/image'];source=Path(dataset['sourceRoot'])
        raw=(ATTEMPT/'replay_write/progress.jsonl').read_bytes();lines=raw.splitlines(keepends=True)
        rows=[];tail=b''
        for index,line in enumerate(lines):
            if not line.endswith(b'\n'):assert index==len(lines)-1;tail=line;break
            rows.append(json.loads(line))
        directories_complete=bool(rows and 'directoriesComplete' in rows[0])
        if directories_complete:assert rows.pop(0)['directoriesComplete']==len(dataset['directories'])
        assert rows==dataset['files'][:len(rows)]
        actual=bodies(observed);wanted={r['path']:r for r in rows}
        assert set(wanted)<=set(actual)
        for name,row in wanted.items():assert len(actual[name])==row['bytes'] and hashlib.sha256(actual[name]).hexdigest()==row['sha256']
        extra=set(actual)-set(wanted)
        assert len(extra)<=1 and (not extra or extra=={dataset['files'][len(rows)]['path']})
        for name in extra:
            full=(source/name).read_bytes();assert full[:len(actual[name])]==actual[name]
        if directories_complete:assert observed['directories']==set(dataset['directories'])
        else:assert observed['directories']<=set(dataset['directories'])
        complete='replay_write' in report['scopes']
        if complete:assert len(rows)==4270 and not extra and not tail
        else:assert not (ATTEMPT/'replay_read').exists()
        replay=dict(completeWriterReceipt=complete,completedFileBodiesVerified=len(rows),completeBodyBytes=sum(r['bytes'] for r in rows),
            directoriesVerified=len(observed['directories']),extraPublishedFiles=[dict(path=n,committedBytes=len(actual[n])) for n in sorted(extra)],
            unlinkedInodes=sorted(observed['unlinked']),incompletePhysicalInodes=sorted(set(observed['physical'])-set(observed['nodes'])),
            pendingEntries=observed['pending'],partialProgressTailBytes=len(tail),dependentColdReaderRun=(ATTEMPT/'replay_read').exists())
    runtime=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(runtime)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    runtime_rows=read(runtime)['files'];assert len(runtime_rows)==244 and all(digest(ROOT/r['path'])==r['sha256'] for r in runtime_rows)
    result=dict(status='verified',semanticChecks=96,imagesReadOnly=len(images),processes=processes,replay=replay,publicInputsExact=244,
        recoveryInvoked=False,allBackingBytesUnchanged=True,physicalPowerLossTested=False,serviceStorageQualified=False,
        images=[dict(path=name,files=len(value['files']),directories=len(value['directories']),unlinkedInodes=sorted(value['unlinked']),
                     incompletePhysicalInodes=sorted(set(value['physical'])-set(value['nodes'])),pendingEntries=value['pending'],
                     backingHashes=value['backingHashes'],callbacks=value['callbacks']) for name,value in images.items()])
    with (HERE/'EVIDENCE-AUDIT.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('images','processes')},sort_keys=True),flush=True)

if __name__=='__main__':main()

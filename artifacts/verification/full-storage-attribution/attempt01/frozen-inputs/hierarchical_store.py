"""Private hierarchical inode adapter; not a mounted POSIX/SQLite provider."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading

from chunk_store_base import ChunkStore, Reject, StorageError, NativeError
from chunk_store_base import _guard, _integer, _canonical, _block_module
from chunk_store_base import CHUNK, MAX_FILE, MAX_HANDLES, MAX_TRANSFER, MAP_BYTES, INTERNAL_MAX
from native import Native

PROFILE='hms.hierarchical-chunk-store.inline512/0.1'
MAX_INODES=8192
MAX_DEPTH=32
MAX_PATH=4095
MAX_NAME=255


def _name(value):
    if type(value) is not str or value in ('','.','..') or '/' in value or '\0' in value:
        raise Reject('INVALID_NAME')
    try:wire=value.encode('utf-8')
    except UnicodeError as error:raise Reject('INVALID_NAME') from error
    if len(wire)>MAX_NAME:raise Reject('NAME_LIMIT')
    return value


def _parts(value):
    if type(value) is not str:raise Reject('INVALID_PATH')
    try:wire=value.encode('utf-8')
    except UnicodeError as error:raise Reject('INVALID_PATH') from error
    if len(wire)>MAX_PATH:raise Reject('PATH_LIMIT')
    if value=='':return []
    parts=value.split('/')
    if len(parts)>MAX_DEPTH:raise Reject('DEPTH_LIMIT')
    return [_name(part) for part in parts]


def _pack(body):
    return _canonical(dict(body=body,sha256=hashlib.sha256(_canonical(body)).hexdigest()))


def _unpack(wire):
    try:
        value=json.loads(wire)
        if type(value) is not dict or set(value)!={'body','sha256'} or _pack(value['body'])!=wire:
            raise ValueError('canonical metadata/checksum')
        if type(value['body']) is not dict:raise ValueError('metadata body')
        return value['body']
    except (ValueError,KeyError,TypeError,RecursionError) as error:
        raise StorageError('INVALID_METADATA') from error


class HierarchicalStore(ChunkStore):
    @classmethod
    def create(cls,path,identity,*,block_source,library,library_hash,chunks=1):
        module=_block_module(Path(block_source),cls.BLOCK_HASH)
        anchor=module.create_image(path,identity,chunks)
        anchor.update(storeProfile=PROFILE,storeChunks=chunks)
        return cls(path,anchor,module,library,library_hash,fresh=True)

    @classmethod
    def reopen(cls,path,anchor,*,block_source,library,library_hash):
        module=_block_module(Path(block_source),cls.BLOCK_HASH)
        return cls(path,anchor,module,library,library_hash,fresh=False)

    def __init__(self,path,anchor,module,library,library_hash,*,fresh):
        if type(anchor) is not dict or anchor.get('storeProfile')!=PROFILE:
            raise StorageError('STORAGE_PROFILE')
        chunks=anchor.get('storeChunks')
        if type(chunks) is not int or not 1<=chunks<=8 or anchor.get('capacityBytes')!=chunks*16*1024*1024:
            raise StorageError('STORAGE_GEOMETRY')
        self.pid=os.getpid();self.lock=threading.RLock()
        self.closed=self.poisoned=False
        self.handles={};self.session=secrets.token_hex(16);self.next_handle=1
        self.anchor=json.loads(json.dumps(anchor));self.inodes={};self.links={};self.parents={}
        self.native=None
        self.image=module.FixedBlockImage(path,anchor['identity'],chunks,expected_objects=anchor['objects'])
        try:
            self.native=Native(self.image,library,library_hash)
            if fresh:self.native.call('hm_format')
            self.native.call('hm_mount')
            if fresh:
                self.super=dict(profile=PROFILE,identity=anchor['identity'],root=1,next=2)
                self.native.call('hm_mkdir',b'objects');self.native.call('hm_mkdir',b'pending')
                self._initialize_inode(1,'dir');self.parents[1]=None
                self._save_super()
            else:
                self.super=_unpack(self.native.read('super'))
                if (set(self.super)!={'profile','identity','root','next'} or self.super['profile']!=PROFILE or
                    self.super['identity']!=anchor['identity'] or type(self.super['root']) is not int or self.super['root']!=1 or
                    type(self.super['next']) is not int or not 2<=self.super['next']<2**64):
                    raise StorageError('INVALID_SUPERBLOCK')
                inventory=self._inventory()
                self._recover_inventory(inventory)
        except BaseException:
            self.dispose();raise

    def _checkpoint(self,phase,value):
        """Research hook; no effect in the candidate."""

    @staticmethod
    def _directory(identity):
        return f'objects/b{identity%256:02x}/i{identity:016x}'

    def _save_super(self):
        self.native.write('super.tmp',_pack(self.super))
        self.native.call('hm_rename',b'super.tmp',b'super')

    def _save_inode(self,inode):
        path=self._directory(inode['id'])
        self.native.write(path+'/state.tmp',_pack(inode))
        self.native.call('hm_rename',(path+'/state.tmp').encode(),(path+'/state').encode())

    def _initialize_inode(self,identity,kind):
        directory=self._directory(identity);bucket=directory.rsplit('/',1)[0]
        if self.native.stat(bucket) is None:self.native.call('hm_mkdir',bucket.encode())
        self.native.call('hm_mkdir',directory.encode())
        inode=dict(id=identity,kind=kind)
        if kind=='file':inode.update(size=0,chunks=base64.b64encode(b'\0'*MAP_BYTES).decode('ascii'))
        else:self.native.call('hm_mkdir',(directory+'/entries').encode())
        self._save_inode(inode);self.inodes[identity]=inode
        if kind=='dir':self.links[identity]={}
        return inode

    def _new_inode(self,kind):
        if len(self.inodes)>=MAX_INODES or self.super['next']>=2**64-1:raise Reject('INODE_LIMIT')
        identity=self.super['next'];self.super['next']+=1
        self._save_super();self._checkpoint('identity_reserved',identity)
        inode=self._initialize_inode(identity,kind)
        self._checkpoint('inode_durable',identity)
        return inode

    def _entry_path(self,parent,name):
        return self._directory(parent)+'/entries/'+name

    def _publish(self,parent,name,inode):
        staged=f'pending/p{inode["id"]:016x}'
        self.native.write(staged,_pack(dict(id=inode['id'],kind=inode['kind'])))
        self._checkpoint('entry_staged',inode['id'])
        self.native.call('hm_rename',staged.encode(),self._entry_path(parent,name).encode())
        self._checkpoint('entry_published',inode['id'])
        self.links[parent][name]=inode['id'];self.parents[inode['id']]=(parent,name)

    def _valid_inode(self,raw,identity):
        inode=_unpack(raw)
        if type(inode.get('id')) is not int or inode['id']!=identity or inode.get('kind') not in ('file','dir'):
            raise StorageError('INVALID_INODE')
        if inode['kind']=='dir':
            if set(inode)!={'id','kind'}:raise StorageError('INVALID_INODE')
        else:
            if set(inode)!={'id','kind','size','chunks'}:raise StorageError('INVALID_INODE')
            try:_integer(inode['size'],MAX_FILE)
            except Reject as error:raise StorageError('INVALID_INODE') from error
            if any(n*CHUNK>=inode['size'] for n in self._present(inode)):
                raise StorageError('CHUNK_OUTSIDE_FILE')
        return inode

    def _inventory(self):
        root={name:(kind,size) for name,kind,size in self.native.entries('/',5)}
        if not {'super','objects','pending'}<=set(root) or set(root)-{'super','super.tmp','objects','pending'}:
            raise StorageError('ROOT_CLOSURE')
        if root['objects']!=(2,0) or root['pending']!=(2,0):raise StorageError('ROOT_TYPES')
        for name in ('super','super.tmp'):
            if name in root and (root[name][0]!=1 or not 0<=root[name][1]<=INTERNAL_MAX):raise StorageError('SUPERBLOCK_SIZE')
        staged=self.native.entries('pending',MAX_INODES)
        for name,kind,size in staged:
            if (re.fullmatch(r'p[0-9a-f]{16}',name) is None or kind!=1 or not 0<=size<=INTERNAL_MAX or
                not 1<int(name[1:],16)<self.super['next']):raise StorageError('PENDING_ENTRY')
        nodes={}
        for bucket,kind,size in self.native.entries('objects',256):
            if re.fullmatch(r'b[0-9a-f]{2}',bucket) is None or (kind,size)!=(2,0):raise StorageError('INODE_BUCKET')
            for name,kind,size in self.native.entries('objects/'+bucket,MAX_INODES):
                if re.fullmatch(r'i[0-9a-f]{16}',name) is None or (kind,size)!=(2,0):raise StorageError('INODE_DIRECTORY')
                identity=int(name[1:],16)
                if not 1<=identity<self.super['next'] or identity%256!=int(bucket[1:],16) or identity in nodes:raise StorageError('INODE_IDENTITY')
                if len(nodes)>=MAX_INODES:raise StorageError('INODE_LIMIT')
                path=self._directory(identity);entries=self.native.entries(path,MAX_FILE//CHUNK+3)
                items={n:(k,s) for n,k,s in entries};inode=None;chunks={}
                for item,k,s in entries:
                    if item in ('state','state.tmp'):
                        if k!=1 or not 0<=s<=INTERNAL_MAX:raise StorageError('INODE_METADATA_SIZE')
                    elif item=='entries':
                        if (k,s)!=(2,0):raise StorageError('ENTRY_DIRECTORY')
                    elif re.fullmatch(r'c[0-9a-f]{8}',item) is not None:
                        number=int(item[1:],16)
                        if number>=MAX_FILE//CHUNK or k!=1 or not 0<=s<=CHUNK:raise StorageError('INVALID_CHUNK')
                        chunks[number]=s
                    else:raise StorageError('UNKNOWN_INODE_OBJECT')
                if 'state' in items:inode=self._valid_inode(self.native.read(path+'/state'),identity)
                if chunks and 'entries' in items:raise StorageError('MIXED_INODE_CONTENTS')
                children={}
                if 'entries' in items:
                    for entry,k,s in self.native.entries(path+'/entries',MAX_INODES):
                        try:_name(entry)
                        except Reject as error:raise StorageError('INVALID_ENTRY_NAME') from error
                        if k!=1 or not 0<s<=INTERNAL_MAX:raise StorageError('INVALID_ENTRY')
                        link=_unpack(self.native.read(path+'/entries/'+entry))
                        if (set(link)!={'id','kind'} or type(link['id']) is not int or
                            not 1<link['id']<self.super['next'] or link['kind'] not in ('file','dir')):
                            raise StorageError('INVALID_ENTRY')
                        children[entry]=link
                if inode is not None:
                    if inode['kind']=='dir':
                        if chunks or 'entries' not in items:raise StorageError('DIRECTORY_CONTENTS')
                    else:
                        if 'entries' in items:raise StorageError('FILE_CONTENTS')
                        if any(chunks.get(n)!=CHUNK for n in self._present(inode)):raise StorageError('MISSING_REFERENCED_CHUNK')
                nodes[identity]=dict(inode=inode,items=items,chunks=chunks,children=children)
        self.inodes={};self.links={};self.parents={1:None}
        pending=[(1,0,0)]
        while pending:
            identity,depth,path_bytes=pending.pop()
            if depth>MAX_DEPTH or path_bytes>MAX_PATH or identity not in nodes or nodes[identity]['inode'] is None:raise StorageError('INVALID_TREE')
            node=nodes[identity];inode=node['inode'];self.inodes[identity]=inode
            if inode['kind']=='dir':
                self.links[identity]={}
                for name,link in node['children'].items():
                    child=link['id']
                    if child in self.parents or child not in nodes or nodes[child]['inode'] is None or nodes[child]['inode']['kind']!=link['kind']:
                        raise StorageError('INVALID_TREE_LINK')
                    self.parents[child]=(identity,name);self.links[identity][name]=child
                    pending.append((child,depth+1,path_bytes+(1 if depth else 0)+len(name.encode('utf-8'))))
        if self.inodes.get(1,{}).get('kind')!='dir':raise StorageError('INVALID_ROOT_INODE')
        for identity,node in nodes.items():
            if identity not in self.parents and node['children']:raise StorageError('UNREACHABLE_NONEMPTY_DIRECTORY')
        self._checkpoint('inventory_validated',len(nodes))
        return dict(root=root,staged=staged,nodes=nodes)

    def _recover_inventory(self,inventory):
        # Entire graph, inode bodies and object closure have been checked above.
        if 'super.tmp' in inventory['root']:self.native.remove('super.tmp')
        for name,unused_kind,unused_size in inventory['staged']:self.native.remove('pending/'+name)
        for identity,node in inventory['nodes'].items():
            path=self._directory(identity)
            if identity not in self.parents:
                self._reclaim_native(identity,node['items']);continue
            if 'state.tmp' in node['items']:self.native.remove(path+'/state.tmp')
            inode=self.inodes[identity]
            if inode['kind']=='file':
                for number in node['chunks']:
                    if number not in self._present(inode):self.native.remove(self._path(inode,number))

    def _reclaim_native(self,identity,items=None):
        path=self._directory(identity)
        if items is None:items={n:(k,s) for n,k,s in self.native.entries(path,MAX_FILE//CHUNK+3)}
        # Removing state first makes interrupted reclamation distinguishable
        # from a live inode whose referenced data vanished.
        for name in ('state.tmp','state'):
            if name in items:self.native.remove(path+'/'+name)
        for name in items:
            if name not in ('state','state.tmp'):self.native.remove(path+'/'+name)
        self.native.remove(path)

    def _drop_inode(self,inode):
        self._reclaim_native(inode['id'])
        self.inodes.pop(inode['id']);self.links.pop(inode['id'],None)

    def _handle(self,handle,*,writable=False,kind=None):
        if type(handle) is not tuple or len(handle)!=2 or type(handle[0]) is not str or type(handle[1]) is not int or handle not in self.handles:
            raise Reject('BAD_HANDLE')
        identity,can_write=self.handles[handle]
        if writable and not can_write:raise Reject('READ_ONLY')
        inode=self.inodes[identity]
        if kind is not None and inode['kind']!=kind:raise Reject('NOT_DIRECTORY' if kind=='dir' else 'IS_DIRECTORY')
        return inode

    def _fd(self,handle,writable=False):
        return self._handle(handle,writable=writable,kind='file')

    def _base(self,handle):
        identity=1 if handle is None else self._handle(handle,kind='dir')['id']
        if identity not in self.parents:raise Reject('UNLINKED_DIRECTORY')
        return identity

    def _resolve_parts(self,parts,base):
        identity=base
        for part in parts:
            if self.inodes[identity]['kind']!='dir':raise Reject('NOT_DIRECTORY')
            if part not in self.links[identity]:raise Reject('NOT_FOUND')
            identity=self.links[identity][part]
        return identity

    def _parent(self,path,handle=None):
        parts=_parts(path)
        if not parts:raise Reject('ROOT_OPERATION')
        parent=self._resolve_parts(parts[:-1],self._base(handle))
        if self.inodes[parent]['kind']!='dir':raise Reject('NOT_DIRECTORY')
        # Absolute depth stays bounded even when traversal starts at a handle.
        depth,size=self._location(parent)
        if depth+1>MAX_DEPTH:raise Reject('DEPTH_LIMIT')
        if size+(1 if depth else 0)+len(parts[-1].encode('utf-8'))>MAX_PATH:raise Reject('PATH_LIMIT')
        return parent,parts[-1]

    def _location(self,identity):
        names=[]
        while identity!=1:
            identity,name=self.parents[identity];names.append(name)
        return len(names),len('/'.join(names).encode('utf-8'))

    def _info(self,inode):
        return dict(id=inode['id'],kind=inode['kind'],size=inode.get('size',0),
            links=1 if inode['id'] in self.parents else 0,mode=0o600 if inode['kind']=='file' else 0o700)

    @_guard
    def open(self,path,*,create=False,exclusive=False,writable=True,directory=False,dir_handle=None):
        if any(type(v) is not bool for v in (create,exclusive,writable,directory)):raise Reject('INVALID_FLAGS')
        if len(self.handles)>=MAX_HANDLES or self.next_handle>=2**64:raise Reject('HANDLE_LIMIT')
        parts=_parts(path);base=self._base(dir_handle)
        if not parts:
            if create or not directory:raise Reject('ROOT_OPERATION')
            inode=self.inodes[base]
        else:
            parent,name=self._parent(path,dir_handle);identity=self.links[parent].get(name)
            if identity is None:
                if not create:raise Reject('NOT_FOUND')
                if directory:raise Reject('USE_MKDIR')
                inode=self._new_inode('file');self._publish(parent,name,inode)
            else:
                if create and exclusive:raise Reject('EXISTS')
                inode=self.inodes[identity]
        if directory!=(inode['kind']=='dir'):raise Reject('NOT_DIRECTORY' if directory else 'IS_DIRECTORY')
        handle=(self.session,self.next_handle);self.next_handle+=1
        self.handles[handle]=(inode['id'],writable);return handle

    @_guard
    def mkdir(self,path,*,dir_handle=None):
        parent,name=self._parent(path,dir_handle)
        if name in self.links[parent]:raise Reject('EXISTS')
        inode=self._new_inode('dir');self._publish(parent,name,inode)
        return self._info(inode)

    @_guard
    def stat(self,path,*,dir_handle=None):
        return self._info(self.inodes[self._resolve_parts(_parts(path),self._base(dir_handle))])

    @_guard
    def info(self,handle):return self._info(self._handle(handle))

    @_guard
    def listdir(self,path='',*,dir_handle=None):
        parts=_parts(path)
        # An unlinked directory is necessarily empty, but its held identity is
        # still readable. It cannot become a base for creating unreachable files.
        if not parts and dir_handle is not None:identity=self._handle(dir_handle,kind='dir')['id']
        else:identity=self._resolve_parts(parts,self._base(dir_handle))
        if self.inodes[identity]['kind']!='dir':raise Reject('NOT_DIRECTORY')
        return [dict(name=name,**self._info(self.inodes[child])) for name,child in sorted(self.links[identity].items())]

    @_guard
    def rename(self,source,target,*,source_dir=None,target_dir=None):
        left,name=self._parent(source,source_dir);right,new_name=self._parent(target,target_dir)
        if name not in self.links[left]:raise Reject('NOT_FOUND')
        identity=self.links[left][name];inode=self.inodes[identity]
        prior_id=self.links[right].get(new_name)
        if prior_id==identity:return
        if prior_id is not None:
            prior=self.inodes[prior_id]
            if prior['kind']!=inode['kind']:raise Reject('TYPE_MISMATCH')
            if prior['kind']=='dir' and self.links[prior_id]:raise Reject('NOT_EMPTY')
        if inode['kind']=='dir':
            at=right
            while True:
                if at==identity:raise Reject('DIRECTORY_CYCLE')
                if at==1:break
                at=self.parents[at][0]
            # A moved subtree must still fit global depth AND UTF-8 path bounds.
            depth,size=self._location(right)
            pending=[(identity,depth+1,size+(1 if depth else 0)+len(new_name.encode('utf-8')))]
            while pending:
                child,depth,size=pending.pop()
                if depth>MAX_DEPTH:raise Reject('DEPTH_LIMIT')
                if size>MAX_PATH:raise Reject('PATH_LIMIT')
                if self.inodes[child]['kind']=='dir':
                    pending.extend((value,depth+1,size+1+len(name.encode('utf-8'))) for name,value in self.links[child].items())
        self.native.call('hm_rename',self._entry_path(left,name).encode(),self._entry_path(right,new_name).encode())
        self._checkpoint('rename_published',dict(source=identity,replaced=prior_id))
        del self.links[left][name];self.links[right][new_name]=identity;self.parents[identity]=(right,new_name)
        if prior_id is not None:
            self.parents.pop(prior_id)
            if not self._referenced(self.inodes[prior_id]):self._drop_inode(self.inodes[prior_id])

    def _unlink(self,path,handle,kind):
        parent,name=self._parent(path,handle)
        if name not in self.links[parent]:raise Reject('NOT_FOUND')
        identity=self.links[parent][name];inode=self.inodes[identity]
        if inode['kind']!=kind:raise Reject('IS_DIRECTORY' if kind=='file' else 'NOT_DIRECTORY')
        if kind=='dir' and self.links[identity]:raise Reject('NOT_EMPTY')
        self.native.remove(self._entry_path(parent,name));self._checkpoint('unlink_published',identity)
        del self.links[parent][name];self.parents.pop(identity)
        if not self._referenced(inode):self._drop_inode(inode)

    @_guard
    def unlink(self,path,*,dir_handle=None):self._unlink(path,dir_handle,'file')

    @_guard
    def rmdir(self,path,*,dir_handle=None):self._unlink(path,dir_handle,'dir')

    @_guard
    def close_handle(self,handle):
        inode=self._handle(handle);del self.handles[handle]
        if inode['id'] not in self.parents and not self._referenced(inode):self._drop_inode(inode)

    @_guard
    def chmod(self,path,mode,*,dir_handle=None):
        inode=self.inodes[self._resolve_parts(_parts(path),self._base(dir_handle))]
        if type(mode) is not int or mode!=(0o600 if inode['kind']=='file' else 0o700):raise Reject('UNSUPPORTED_MODE')

    @_guard
    def accounting(self):
        return dict(uniqueReachableBlocks=self.native.call('hm_used'),blockBytes=CHUNK,
            backingBytes=self.image.block_count*CHUNK,logicalBytes=sum(i.get('size',0) for i in self.inodes.values()),
            inodes=len(self.inodes),linkedInodes=len(self.parents),handles=len(self.handles),reservedContinuationBytes=0)

    @_guard
    def pwrite(self, handle, data, offset):
        inode = self._fd(handle, True)
        if type(data) is not bytes or len(data) > MAX_TRANSFER:
            raise Reject('INVALID_DATA')
        _integer(offset, MAX_FILE)
        if offset+len(data) > MAX_FILE:
            raise Reject('FILE_LIMIT')
        if not data:
            return 0
        stop = offset+len(data)
        if stop > inode['size']:
            self._zero_tail(inode)
        done = 0
        bitmap = bytearray(self._bitmap(inode))
        prior_map = bytes(bitmap)
        while done < len(data):
            number, within = divmod(offset+done, CHUNK)
            amount = min(len(data)-done, CHUNK-within)
            chunk = bytearray(self._chunk(inode, number))
            chunk[within:within+amount] = data[done:done+amount]
            self.native.write(self._path(inode, number), bytes(chunk))
            bitmap[number//8] |= 1 << (number%8)
            done += amount
        if stop > inode['size'] or bytes(bitmap) != prior_map:
            inode['size'] = max(inode['size'], stop)
            inode['chunks'] = base64.b64encode(bitmap).decode('ascii')
            self._save_inode(inode)
        return len(data)

    @_guard
    def truncate(self, handle, size):
        inode = self._fd(handle, True)
        _integer(size, MAX_FILE)
        old = inode['size']
        if old == size:
            return
        if size > old:
            self._zero_tail(inode)
        inode['size'] = size
        if size < old:
            bitmap = bytearray(self._bitmap(inode))
            for number in range((size+CHUNK-1)//CHUNK, MAX_FILE//CHUNK):
                bitmap[number//8] &= ~(1 << (number%8))
            inode['chunks'] = base64.b64encode(bitmap).decode('ascii')
        self._save_inode(inode)
        if size < old:
            directory = self._directory(inode['id'])
            for name in self.native.list(directory, MAX_FILE//CHUNK+2):
                if name in ('state','state.tmp'):continue
                if int(name[1:], 16)*CHUNK >= size:
                    self.native.remove(f'{directory}/{name}')


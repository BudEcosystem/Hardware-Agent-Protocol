#!/usr/bin/env python3
"""Restore already-pinned host tools as data; execute no acquired code.

Parent reviews before invoking. A fresh private directory and receipt preserve
each restoration. No download, installation, PATH mutation, compiler invocation,
target execution, port, or emulator occurs here.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import resource
import signal
import tarfile
import tempfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
ARCHIVE=REPO/'research/constrained/avr/raw/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2'
SHA='bd8c37f6952a2130ac9ee32c53f6a660feb79bee8353c8e289eb60fdcefed91e'
EXPECTED_ARCHIVE_BYTES=37630618

def require(test,message):
    if not test:raise RuntimeError(message)

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def stop(signum,_frame):
    raise RuntimeError('Restoration bound/interruption signal '+str(signum))

def safe_name(name):
    path=PurePosixPath(name)
    require(not path.is_absolute() and path.parts and path.parts[0]=='avr' and '..' not in path.parts,
            'Unsafe archive path: '+name)
    require(path.as_posix()==name.rstrip('/'),'Noncanonical archive path: '+name)
    return path.as_posix()

def main():
    resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024**2,32*1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    for signum in (signal.SIGALRM,signal.SIGTERM):signal.signal(signum,stop)
    signal.alarm(90)
    require(ARCHIVE.stat().st_size==EXPECTED_ARCHIVE_BYTES and digest(ARCHIVE)==SHA,'Pinned archive differs')
    parent=HERE/'toolchains';parent.mkdir(mode=0o700,exist_ok=True)
    destination=Path(tempfile.mkdtemp(prefix='avr-gcc-7.3.0-',dir=parent))
    receipt=destination/'restoration.json'
    report={'schema':'hms-private-toolchain-restoration/1','recorded_at':datetime.now(timezone.utc).isoformat(),
            'script_sha256':digest(Path(__file__)),'archive':str(ARCHIVE),'archive_sha256':SHA,
            'archive_bytes':EXPECTED_ARCHIVE_BYTES,'destination':str(destination),'completed':False,
            'acquired_code_executed':False,'target_executed':False,
            'limits':{'cpu_seconds':60,'wall_seconds':90,'address_bytes':512*1024**2,
                      'file_bytes':32*1024**2,'payload_bytes':256*1024**2,'members':3000,
                      'open_files':64,'core_bytes':0}}
    try:
        members={};hashes={};links={};total=0
        with tarfile.open(ARCHIVE,'r|bz2') as source:
            for member in source:
                name=safe_name(member.name)
                require(name not in members,'Duplicate archive path: '+name)
                require(member.isdir() or member.isfile() or member.issym() or member.islnk(),'Unexpected member type')
                require(0<=member.size<=32*1024**2,'Member extent exceeds bound')
                total+=member.size;members[name]=member
                require(len(members)<=3000 and total<=256*1024**2,'Archive expansion exceeds bound')
                if member.isfile():
                    with source.extractfile(member) as data:hashes[name]=hashlib.file_digest(data,'sha256').hexdigest()
                elif member.issym() or member.islnk():
                    require(not PurePosixPath(member.linkname).is_absolute(),'Absolute link target')
                    target=member.linkname if member.islnk() else posixpath.join(posixpath.dirname(name),member.linkname)
                    links[name]=safe_name(posixpath.normpath(target))
        # No extraction traverses a link as a directory. Every link target must
        # resolve to an archived regular file, with cycles rejected.
        for name in members:
            for ancestor in PurePosixPath(name).parents:
                if str(ancestor)=='.':continue
                require(str(ancestor) in members and members[str(ancestor)].isdir(),'Missing/non-directory ancestor')
        unresolved=dict(links)
        for _ in range(len(unresolved)+1):
            resolved={name:hashes[target] for name,target in unresolved.items() if target in hashes}
            if not resolved:break
            hashes.update(resolved)
            for name in resolved:del unresolved[name]
        require(not unresolved,'Unresolved/cyclic archive links')
        report['member_count']=len(members);report['declared_payload_bytes']=total
        report['regular_or_link_hashes']=hashes;report['links']=links
        # Reopen only after all names/types/extents/links are validated. The
        # standard data filter additionally refuses traversal and unsafe modes.
        with tarfile.open(ARCHIVE,'r:bz2') as source:
            source.extractall(destination,members=list(members.values()),filter='data')
        require(digest(ARCHIVE)==SHA,'Archive changed during restoration')
        actual=set()
        for path in destination.rglob('*'):
            name=path.relative_to(destination).as_posix();actual.add(name)
            require(name in members,'Unexpected extracted path: '+name)
            require(path.resolve().is_relative_to(destination.resolve()),'Extracted path escapes destination')
            member=members[name]
            if member.isdir():require(path.is_dir() and not path.is_symlink(),'Directory differs')
            else:
                require(path.is_file() and digest(path)==hashes[name],'Restored file differs: '+name)
                if member.issym():require(path.is_symlink() and os.readlink(path)==member.linkname,'Symbolic link differs')
                else:require(not path.is_symlink(),'Unexpected symbolic link')
        require(actual==set(members),'Restored member set differs')
        binary=destination/'avr/bin'
        for name in ('avr-gcc','avr-as','avr-ld','avr-size','avr-nm','avr-objdump'):
            require((binary/name).is_file() and os.access(binary/name,os.X_OK),'Host tool lacks executable mode')
        report['toolchain_bin']=str(binary);report['completed']=True
    except BaseException as exc:
        report['error']=str(exc);raise
    finally:
        signal.alarm(0);receipt.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'receipt':str(receipt),'toolchain_bin':report['toolchain_bin'],
                      'completed':True,'acquired_code_executed':False}))

if __name__=='__main__':main()

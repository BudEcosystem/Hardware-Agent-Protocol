"""Protected pre-release inputs and bounded output-file closure; no effects."""
import hashlib
import os
import re
import stat

from hms.contracts import canonical
from hms.pat_io_run_bundle import parse_io_run_bundle
from hms_qualification.supervisor.supervisor_contracts import require, read_file, write_file, document, request_digest, same


def directory(parent, name, *, create=False):
    require(type(name) is str and re.fullmatch(r'[A-Za-z0-9_-]+',name), 'QUALIFICATION_UNSAFE_FILE')
    if create: os.mkdir(name,0o700,dir_fd=parent); os.fsync(parent)
    fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    try:
        info=os.fstat(fd)
        require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'QUALIFICATION_UNSAFE_FILE')
        return fd
    except BaseException: os.close(fd); raise


def _names(fd, maximum):
    names=[]
    with os.scandir(fd) as entries:
        for entry in entries:
            require(len(names)<maximum,'QUALIFICATION_FILE_LIMIT')
            names.append(entry.name)
    return sorted(names)


def check_bundle(request, bundle):
    require(bundle['header']==canonical(request['bundleHeader']) and bundle['bundleDigest']==request['bundleDigest'],
        'QUALIFICATION_INPUT_ASSOCIATION')
    return parse_io_run_bundle(bundle['header'],bundle['documents'],expected_context=request['context'],
        expected_bundle_digest=request['bundleDigest'])


def retain_bundle(parent, request, bundle):
    check_bundle(request,bundle)
    root=directory(parent,'bundle',create=True)
    try:
        write_file(root,'header.json',bundle['header'])
        for part in ('inputs','cases'):
            child=directory(root,part,create=True)
            try:
                for row in request['bundleHeader']['manifest']:
                    prefix,name=row['path'].split('/')
                    if prefix==part: write_file(child,name,bundle['documents'][row['path']])
            finally: os.close(child)
        os.fsync(root)
    finally: os.close(root)
    os.fsync(parent)
    # Read exact protected bytes before a launch-intent transition may commit.
    return load_bundle(parent,request)


def load_bundle(parent, request):
    root=directory(parent,'bundle')
    try:
        require(_names(root,4)==['cases','header.json','inputs'],'QUALIFICATION_INPUT_CLOSURE')
        header=read_file(root,'header.json'); documents={}
        for part in ('inputs','cases'):
            child=directory(root,part)
            try:
                expected=[row['path'].split('/')[1] for row in request['bundleHeader']['manifest']
                    if row['path'].split('/')[0]==part]
                require(_names(child,40)==sorted(expected),'QUALIFICATION_INPUT_CLOSURE')
                for name in expected:
                    require(re.fullmatch(r'[a-z0-9_-]+\.json',name),'QUALIFICATION_INPUT_CLOSURE')
                    documents[part+'/'+name]=read_file(child,name)
            finally: os.close(child)
        value=dict(header=header,documents=documents,bundleDigest=request['bundleDigest'])
        check_bundle(request,value)
        return value
    finally: os.close(root)


def launch_input(request, identifier):
    require(type(identifier) is str and re.fullmatch(r'[0-9a-f]{32}',identifier),'QUALIFICATION_INPUT_ASSOCIATION')
    return dict(profile='hms.pat.io-supervisor-launch/0.1',attemptId=identifier,request=request)


def output_integrity(parent, request, returned, identifier):
    """Inventory every retained file under output after writer quiescence.

This verifies transport and exact source/input/result association, not case
semantics, filesystem allocation, wall timing or physical effects.
"""
    require(type(returned) is dict and set(returned)=={'profile','attemptId','requestDigest','bundleDigest','groupResultDigest','status'},
        'QUALIFICATION_RESULT_ASSOCIATION')
    require(returned['profile']=='hms.pat.io-supervisor-return/0.1' and returned['attemptId']==identifier and
        returned['requestDigest']==request_digest(request) and returned['bundleDigest']==request['bundleDigest'],
        'QUALIFICATION_RESULT_ASSOCIATION')
    bundle=load_bundle(parent,request); parsed=check_bundle(request,bundle)
    output=directory(parent,'output'); count=total=entries=0
    chain=hashlib.sha256(b'HMS-PAT-IO-OUTPUT-CLOSURE-v0.1\0')
    try:
        result_bytes=read_file(output,'result.json'); result=document(result_bytes)
        require(returned['groupResultDigest']=='sha256:'+hashlib.sha256(result_bytes).hexdigest() and
            returned['status']==result['status'] and returned['status'] in ('captured','failed'), 'QUALIFICATION_RESULT_ASSOCIATION')
        require(result['profile']=='hms.pat.io-group-capture/0.1' and
            result['matrixDigest']==request['bundleHeader']['matrixDigest'] and
            result['artifactDigest']==parsed['expected_inputs']['matrix']['artifactDigest'] and
            same(result['identities'],request['implementation']), 'QUALIFICATION_RESULT_ASSOCIATION')
        for key,value in parsed['expected_inputs'].items():
            require(read_file(output,key+'.json')==canonical(value),'QUALIFICATION_RESULT_ASSOCIATION')
        def walk(fd,prefix,depth):
            nonlocal count,total,entries
            require(depth<=10,'QUALIFICATION_EVIDENCE_INVALID')
            for name in _names(fd,request['limits']['maxFilesPerAttempt']):
                entries+=1
                require(entries<=request['limits']['maxFilesPerAttempt'],'QUALIFICATION_FILE_LIMIT')
                require(re.fullmatch(r'[A-Za-z0-9_.-]+',name) and name not in ('.','..'),'QUALIFICATION_EVIDENCE_INVALID')
                path=prefix+name; require(len(path)<=256,'QUALIFICATION_EVIDENCE_INVALID')
                info=os.stat(name,dir_fd=fd,follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child=directory(fd,name)
                    try: walk(child,path+'/',depth+1)
                    finally: os.close(child)
                else:
                    require(count<request['limits']['maxFilesPerAttempt'],'QUALIFICATION_FILE_LIMIT')
                    remaining=request['groupLimits']['maxDerivedBytes']-total
                    body=read_file(fd,name,maximum=min(16*1024*1024,remaining,65536 if name.endswith('.json') else 16*1024*1024))
                    count+=1; total+=len(body)
                    chain.update(canonical(dict(path=path,bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))+b'\n')
        walk(output,'',0)
        return dict(fileCount=count,bytes=total,orderedDigest='sha256:'+chain.hexdigest())
    finally: os.close(output)

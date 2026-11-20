"""Preserve a failed-scope oversize DB as bounded chunks; never repair it.

No project imports, runtime, worker, SQL writes or recovery are executed. This
diagnostic copy does not change the original16MiB-file retention failure.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat

ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-bound-import'
ATTEMPT=BASE/'harness02/attempts/attempt01-real-import'
OUT=BASE/'forensic01'; OUT.mkdir()
MAX_FILE=16*1024*1024; MAX_TOTAL=256*1024*1024; CHUNK=8*1024*1024
OVERSIZE=17591296
def read(path):return json.loads(path.read_bytes())
def write(path,value):
    with path.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
def digest_file(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):value.update(block)
    return value.hexdigest()
def canonical(value):
    def check(item):
        if type(item) is dict:
            assert all(type(key) is str and key.isascii() for key in item)
            for child in item.values():check(child)
        elif type(item) is list:
            for child in item:check(child)
        else:assert type(item) in (str,int,bool,type(None)) and (type(item) is not int or abs(item)<=2**53-1)
    check(value)
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(body):return 'sha256:'+hashlib.sha256(body).hexdigest()
def hashed(domain,value):return sha(domain+b'\0'+canonical(value))
result=read(ATTEMPT/'result.json')
assert result['status']=='failed' and not result['currentPass'] and result['childState']=='exited' and result['exitCode']==0
assert result['counts']==dict(testsRun=1,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert len(result['errors'])==1 and result['errors'][0]['phase']=='scratch-retention'
raw=Path(result['scratchPath']); work=raw/'test_real_bound_worker_import_and_historical_replay'
root_info=raw.lstat(); saved=read(ATTEMPT/'raw-scratch-before.json')['identity']
assert not raw.is_symlink() and stat.S_ISDIR(root_info.st_mode)
assert (root_info.st_dev,root_info.st_ino,root_info.st_uid,stat.S_IMODE(root_info.st_mode))==(saved['device'],saved['inode'],saved['uid'],saved['mode'])
held=[];locks=[]
try:
    paths=sorted(raw.rglob('*'));assert len(paths)<=8192
    for path in paths:
        assert not path.is_symlink()
        if path.is_dir():continue
        info=path.lstat();assert stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
        if path.name.endswith('.owner') or path.name in ('supervisor.owner','writer.lease'):
            fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK);held.append(fd);actual=os.fstat(fd)
            assert actual.st_nlink==1 and stat.S_IMODE(actual.st_mode)==0o600 and actual.st_size==0
            assert (info.st_dev,info.st_ino)==(actual.st_dev,actual.st_ino)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            locks.append(dict(path=path.relative_to(raw).as_posix(),device=str(info.st_dev),inode=str(info.st_ino)))
    ledger=work/'supervisor/attempts.db'; before_ledger=digest_file(ledger)
    db=sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        rows=db.execute('SELECT request,record,return_bytes FROM qs_attempts LIMIT 2').fetchall();assert len(rows)==1
        request=json.loads(rows[0][0]); record=json.loads(rows[0][1]); returned=rows[0][2]
        authority=db.execute('SELECT authority FROM qs_meta').fetchone()[0]
    finally:db.close()
    assert digest_file(ledger)==before_ledger and record['state']=='archived' and record['archive']['transportComplete']
    writer=next(row for row in locks if row['path'].endswith('/'+record['attemptId']+'/writer.lease'))
    assert record['lease']=={key:writer[key] for key in ('device','inode')}
    inventory=[];total=0
    for path in paths:
        if not path.is_file():continue
        relative=path.relative_to(raw).as_posix();size=path.stat().st_size;total+=size
        assert len(inventory)<8192 and total<=MAX_TOTAL
        before=path.stat(); expected=digest_file(path)
        entry=dict(path=relative,bytes=size,sha256=expected)
        if size>MAX_FILE:
            assert path==work/'runtime/authority.db' and size==OVERSIZE
            pieces=[];whole=hashlib.sha256()
            with path.open('rb') as stream:
                offset=0
                while True:
                    body=stream.read(CHUNK)
                    if not body:break
                    dest=OUT/'chunks'/('authority-%02d.bin'%len(pieces));dest.parent.mkdir(exist_ok=True)
                    with dest.open('xb') as output:output.write(body)
                    whole.update(body)
                    pieces.append(dict(path=dest.relative_to(OUT).as_posix(),offset=offset,bytes=len(body),sha256=hashlib.sha256(body).hexdigest()));offset+=len(body)
            assert whole.hexdigest()==expected and offset==size
            entry['chunks']=pieces;entry['originalSingleFileLimitExceeded']=True
        else:
            dest=OUT/'raw'/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
            assert digest_file(dest)==expected and dest.stat().st_size==size
            entry['copy']=dest.relative_to(OUT).as_posix()
        after=path.stat();assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
        assert digest_file(path)==expected;inventory.append(entry)
    authority_path=work/'runtime/authority.db'; authority_before=digest_file(authority_path)
    db=sqlite3.connect(authority_path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        receipt_rows=db.execute('SELECT receipt FROM ioei_runs LIMIT 2').fetchall();assert len(receipt_rows)==1
        receipt=json.loads(receipt_rows[0][0]);external=read(work/'actual-import-receipt.json')
        assert receipt==external['receipt'] and hashed(b'HMS-PAT-IO-IMPORTED-RECEIPT-v0.1',receipt)==external['receiptDigest']
        meta=db.execute('SELECT typeof(path),length(CAST(path AS BLOB)),typeof(digest),length(CAST(digest AS BLOB)),typeof(body),length(body) FROM ioei_documents LIMIT 8321').fetchall()
        assert 1<=len(meta)<=8320
        assert all(t=='text' and 1<=p<=288 and dt=='text' and d==71 and bt=='blob' and 0<=n<=MAX_FILE for t,p,dt,d,bt,n in meta)
        assert sum(row[5] for row in meta)<=24*1024*1024
        files={};unique={};duplicates=0
        for name,expected,body in db.execute('SELECT path,digest,body FROM ioei_documents ORDER BY path'):
            assert sha(body)==expected and name not in files;files[name]=body
            if expected in unique:assert unique[expected]==body;duplicates+=1
            else:unique[expected]=body
        chain=hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0')
        for name,body in sorted(files.items()):chain.update(canonical(dict(path=name,bytes=len(body),sha256=sha(body)))+b'\n')
        assert receipt['closure']==dict(documents=len(files),bytes=sum(map(len,files.values())),digest='sha256:'+chain.hexdigest())
        assert sha(files['evaluation.json'])==receipt['evaluationDigest'] and json.loads(files['evaluation.json'])==external['evaluation']
        evaluation=external['evaluation'];anchor=evaluation['anchor'];assert anchor==receipt['anchor']
        reservation=json.loads(db.execute('SELECT receipt FROM iosr_runs WHERE sequence=1').fetchone()[0])
        handoff=json.loads(db.execute('SELECT receipt FROM iose_handoffs WHERE sequence=1').fetchone()[0])
        assert files['original/control/reservation.json']==canonical(reservation)
        assert files['original/control/handoff.json']==canonical(handoff)
        assert files['original/control/request.json']==canonical(request)
        assert files['original/control/attempt.json']==canonical(record)
        assert files['original/control/return.json']==returned
        assert anchor['reservationDigest']==hashed(b'HMS-PAT-IO-SERVICE-RUN-RESERVATION-v0.1',reservation)
        assert anchor['handoffDigest']==hashed(b'HMS-PAT-IO-SERVICE-HANDOFF-v0.1',handoff)
        assert anchor['supervisorAuthorityId']==authority==handoff['supervisorAuthorityId']
        assert anchor['attemptId']==record['attemptId']==handoff['attemptId']
        producer=work/'supervisor'/record['attemptId'];output={name[len('original/output/'):]:body for name,body in files.items() if name.startswith('original/output/')}
        originals={path.relative_to(producer/'output').as_posix():path for path in (producer/'output').rglob('*') if path.is_file()}
        assert set(output)==set(originals)
        for name,body in output.items():assert originals[name].read_bytes()==body
        for name,body in files.items():
            if name.startswith('original/bundle/'):assert (producer/'bundle'/name[len('original/bundle/'):]).read_bytes()==body
        assert len(json.loads(files['inspection/summary.json'])['cases'])==30
        assert evaluation['inspectedCases']==30 and evaluation['unresolvedEffects']==0 and not evaluation['physicalObjectiveVerified']
        config_rows=db.execute('SELECT receipt FROM iosc_revisions ORDER BY sequence').fetchall() if 'iosc_revisions' in {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} else []
        page_size=db.execute('PRAGMA page_size').fetchone()[0];pages=db.execute('PRAGMA page_count').fetchone()[0]
        counts=dict(importRows=len(receipt_rows),documents=len(files),documentBytes=sum(map(len,files.values())),
            uniqueBodies=len(unique),duplicateReferences=duplicates,uniqueBodyBytes=sum(map(len,unique.values())),
            potentialExactDeduplicationBytes=sum(map(len,files.values()))-sum(map(len,unique.values())),
            databaseBytes=authority_path.stat().st_size,databasePages=pages,pageSize=page_size)
        assert counts['databaseBytes']==pages*page_size
    finally:db.close()
    assert digest_file(authority_path)==authority_before
    write(OUT/'raw-manifest.json',dict(originalScratch=saved,originalFileLimit=MAX_FILE,chunkLimit=CHUNK,
        originalTotalLimit=MAX_TOTAL,originalScopeStatus='failed',scopeReclassified=False,files=inventory,totalBytes=total))
    write(OUT/'audit.json',dict(originalScopeStatus='failed',failurePreserved=True,originalOversizeBytes=OVERSIZE,
        originalFileLimit=MAX_FILE,excessBytes=OVERSIZE-MAX_FILE,allOriginalBytesUnchanged=True,
        allStoredEvidenceBodiesMatched=True,allOriginalProducerOutputsMatched=True,
        completeMatrixCases=30,unresolvedEffects=0,realOriginalAuthorityHandoffAttemptJoined=True,
        supervisorAuthorityId=authority,attemptId=record['attemptId'],receiptDigest=external['receiptDigest'],
        historicalReplay=read(work/'bound-import-replay-checks.json'),locksHeld=locks,
        storage=counts,qualificationScopePassed=False,physicalObjectiveVerified=False,
        collection='Source-free forensic copy in bounded chunks; not a corrected harness pass.'))
    print(json.dumps(dict(rawFiles=len(inventory),rawBytes=total,storage=counts,originalStatus='failed',forensicAuditPassed=True)))
finally:
    for fd in held:os.close(fd)

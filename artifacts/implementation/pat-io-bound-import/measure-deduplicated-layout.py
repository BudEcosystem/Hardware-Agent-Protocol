"""Measure a fresh in-memory layout; never mutate the retained authority.

This is a sizing model, not an implemented store, migration or passing scope.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

BASE=Path('artifacts/implementation/pat-io-bound-import')
manifest=json.loads((BASE/'forensic01/raw-manifest.json').read_bytes())
entry=next(row for row in manifest['files'] if row['path'].endswith('/runtime/authority.db'))
source=Path(manifest['originalScratch']['path'])/entry['path']
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert source.stat().st_size==17591296==entry['bytes'] and digest(source)==entry['sha256']
owner=os.open(str(source)+'.owner',os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK)
try:
    info=os.fstat(owner);assert stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and info.st_size==0
    fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    original=sqlite3.connect(source.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    model=sqlite3.connect(':memory:')
    try:
        page_size=original.execute('PRAGMA page_size').fetchone()[0];assert page_size==1024
        meta=original.execute('SELECT typeof(sequence),typeof(path),length(CAST(path AS BLOB)),typeof(digest),length(CAST(digest AS BLOB)),typeof(body),length(body) FROM ioei_documents LIMIT 8321').fetchall()
        assert len(meta)==4011 and all(a=='integer' and b=='text' and 1<=c<=288 and d=='text' and e==71 and f=='blob' and 0<=g<=16*1024*1024 for a,b,c,d,e,f,g in meta)
        assert sum(row[-1] for row in meta)<=24*1024*1024
        rows=original.execute('SELECT sequence,path,digest,body FROM ioei_documents ORDER BY sequence,path').fetchall()
        bodies={}
        for sequence,path,digest_value,body in rows:
            assert digest_value=='sha256:'+hashlib.sha256(body).hexdigest()
            if digest_value in bodies:assert bodies[digest_value]==body
            else:bodies[digest_value]=body
        original_pages=dict(original.execute('SELECT name,sum(pgsize) FROM dbstat GROUP BY name'))
        old_table_bytes=sum(original_pages[name] for name in ('ioei_documents','sqlite_autoindex_ioei_documents_1'))
        model.execute('PRAGMA page_size=1024')
        model.execute('CREATE TABLE compact_references (sequence INTEGER NOT NULL, path TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(sequence,path))')
        model.execute('CREATE TABLE compact_bodies (digest TEXT PRIMARY KEY, body BLOB NOT NULL)')
        model.executemany('INSERT INTO compact_bodies VALUES(?,?)',sorted(bodies.items()))
        model.executemany('INSERT INTO compact_references VALUES(?,?,?)',[(sequence,path,digest_value) for sequence,path,digest_value,_ in rows])
        model.commit()
        model_pages=dict(model.execute('SELECT name,sum(pgsize) FROM dbstat GROUP BY name'))
        new_table_bytes=sum(value for name,value in model_pages.items() if name!='sqlite_schema')
        rebuilt=model.execute('SELECT r.sequence,r.path,r.digest,b.body FROM compact_references r JOIN compact_bodies b ON b.digest=r.digest ORDER BY r.sequence,r.path').fetchall()
        assert rebuilt==rows
        estimate=entry['bytes']-old_table_bytes+new_table_bytes
        result=dict(kind='in-memory-exact-deduplication-sizing-model',sourceDatabaseSha256=entry['sha256'],
            sourceDatabaseBytes=entry['bytes'],originalSingleFileLimit=16*1024*1024,pageSize=page_size,
            logicalDocuments=len(rows),uniqueBodies=len(bodies),duplicateReferences=len(rows)-len(bodies),
            originalEvidenceTableAndIndexBytes=old_table_bytes,modeledReferenceBodyAndIndexBytes=new_table_bytes,
            modeledAllocatedByteReduction=old_table_bytes-new_table_bytes,estimatedAuthorityDatabaseBytes=estimate,
            estimatedHeadroomBytes=16*1024*1024-estimate,modelPageBreakdown=model_pages,
            allReconstructedRowsByteIdentical=True,sourceMutated=False,implementedStore=False,
            originalScopeStatus='failed',scopeReclassified=False,
            limitations=['Estimate replaces only evidence document table/index pages; actual transaction history, freelist/pointermap/schema growth and sidecars can differ.',
                'No actual compact-store implementation, public interface, migration, crash/quota behavior, fresh worker/import or retention pass is established.'])
    finally:original.close();model.close()
    assert digest(source)==entry['sha256']
    with (BASE/'deduplication-sizing.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({key:result[key] for key in ('sourceDatabaseBytes','modeledAllocatedByteReduction','estimatedAuthorityDatabaseBytes','estimatedHeadroomBytes','allReconstructedRowsByteIdentical','implementedStore')}))
finally:os.close(owner)

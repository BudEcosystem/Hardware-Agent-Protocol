"""Inspect closed retained databases without changing their bytes or opening Runtime."""
import hashlib,json,sqlite3,sys
from pathlib import Path
B=Path.cwd()/'artifacts/implementation/pat-io-snapshot-reuse';name=sys.argv[1];F=B/'results'/name
proof=json.loads((F/'proof.json').read_bytes());result=json.loads((F/'attempt/result.json').read_bytes())
assert result['childState']=='exited'and not(Path('/proc')/str(result['pid'])).exists()
root=F/'attempt/scratch';rows=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for p in sorted(root.rglob('*.db')):
 assert p.is_file()and not p.is_symlink();assert not p.with_name(p.name+'-wal').exists()and not p.with_name(p.name+'-journal').exists()
 pin=sha(p)
 db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
 try:
  size=db.execute('PRAGMA page_size').fetchone()[0];pages=db.execute('PRAGMA page_count').fetchone()[0]
  integrity=[r[0]for r in db.execute('PRAGMA integrity_check')];assert integrity==['ok']
  payload,unused=db.execute('SELECT sum(payload),sum(unused) FROM dbstat').fetchone()
 finally:db.close()
 assert sha(p)==pin
 with p.open('rb')as f:header=f.read(100)
 assert header[:16]==b'SQLite format 3\0'and int.from_bytes(header[16:18],'big')==size
 assert p.stat().st_size==size*pages
 rows.append(dict(path=p.relative_to(root).as_posix(),sha256=pin,bytes=p.stat().st_size,pageSize=size,
  pageCount=pages,payloadBytes=payload,unusedBytes=unused,integrity=integrity))
out=dict(scope='Read-only layout/integrity observations on complete terminated retained states; no physical power-loss or quota attestation.',
 attempt=name,databases=rows,totalBytes=sum(r['bytes']for r in rows),payloadBytes=sum(r['payloadBytes']for r in rows),
 unusedBytes=sum(r['unusedBytes']for r in rows),rawScratchBytes=proof['rawScratchBytes'],databaseBytesUnchanged=True)
with(F/'storage-audit.json').open('x')as f:f.write(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(attempt=name,databases=len(rows),pageSizes=sorted({r['pageSize']for r in rows}),
 totalBytes=out['totalBytes'],payloadBytes=out['payloadBytes'],unusedBytes=out['unusedBytes'])))

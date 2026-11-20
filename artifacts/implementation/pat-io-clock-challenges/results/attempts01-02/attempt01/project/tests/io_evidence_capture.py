"""Original test-only logical DB snapshots; retain raw workspace on capture failure."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time


class EvidenceWorkspace:
    """No GC finalizer: unsuccessful capture must not erase original database files."""
    def __init__(self):
        self.name=tempfile.mkdtemp(prefix='hms-io-proof-')
        self.capture_failed=False
        self.failures=[]

    def failed(self, error, phase='capture'):
        self.capture_failed=True
        self.failures.append({'phase':phase,'type':type(error).__name__,'message':str(error)[:4096]})
        try:
            (Path(self.name)/'retention-failures.json').write_text(json.dumps({
                'failures':self.failures,
                'rawWorkspaceRetained':True,'scope':'Raw database/WAL files are not a verified logical snapshot.'},indent=2)+'\n')
        except BaseException:pass

    def cleanup(self):
        if not self.capture_failed:
            shutil.rmtree(self.name)


def close_retaining(workspace, runtime):
    """Retain post-close-failure state even if tearDown already captured success."""
    if runtime is None:
        return
    try:
        runtime.close()
    except BaseException as exc:
        workspace.failed(exc,phase='runtime-close')
        raise


def snapshot_databases(directory, target, context):
    """Cooperative backup bound; not a hard OS or SQLite-time guarantee."""
    target.mkdir(parents=True,exist_ok=False)
    sources=sorted(directory.glob('*.db'))
    record={'profile':'hms.io-test-db-capture/1','status':'capturing','logicalSnapshot':True,
            'sourceDirectory':str(directory),'sourceFiles':[p.name for p in sources],'files':[]}
    (target/'capture.json').write_text(json.dumps(record,indent=2)+'\n')
    try:
        for path in sources:
            deadline=time.monotonic()+10
            def progress(_status,_remaining,_total):
                if time.monotonic()>=deadline:raise TimeoutError('Controlled DB capture exceeded its cooperative budget')
            with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=1)) as source:
                with closing(sqlite3.connect(target/path.name,timeout=1)) as dest:
                    source.backup(dest,pages=64,progress=progress,sleep=0.01)
            body=(target/path.name).read_bytes()
            record['files'].append({'path':path.name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
        (target/'context.json').write_text(json.dumps(context,indent=2)+'\n')
        record['status']='captured'
    except BaseException as exc:
        record.update(status='failed',error={'type':type(exc).__name__,'message':str(exc)[:4096]})
        raise
    finally:
        (target/'capture.json').write_text(json.dumps(record,indent=2)+'\n')

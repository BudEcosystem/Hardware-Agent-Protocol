"""Retain reviewable imports using one frozen copied-input attempt, no worker."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

attempt=Path(sys.argv[1]).resolve()
status=json.loads((attempt/'result.json').read_bytes())
if status['exitCode'] != 0 or status['inputsStable'] is not True:
    raise SystemExit('A stable passing copied test attempt is required')
tree=attempt/'tree'
sys.path[:0]=[str(tree/'tests'),str(tree/'src'),str(tree/'baseline/producer')]
import test_evidence as fixtures
import pat_simulation_evidence as evidence
from hms.contracts import canonical
from hms.journal import Context
import sqlite3

output=attempt/'examples';output.mkdir(exist_ok=False)
summary=[]
try:
    for case in ('case-04','case-01'):
        folder=output/case;folder.mkdir()
        trust,source=fixtures.sample(case)
        start=time.monotonic();bundle=evidence.reduce_attempt(trust,source['result'],source['files']);reduced=time.monotonic()-start
        db=sqlite3.connect(folder/'evidence.sqlite')
        try:
            store=evidence.EvidenceStore(db,trust)
            start=time.monotonic();result=store.import_bundle(bundle);imported=time.monotonic()-start
            receipt=fixtures.receipt(trust,result)
            db.execute('BEGIN');db.set_authorizer(fixtures.authorizer(('typeof','length')))
            try:
                start=time.monotonic();verified=store.verify_evidence(Context('historical-review',trust['deployment']),receipt);seconds=time.monotonic()-start
            finally:
                db.set_authorizer(None);db.rollback()
        finally:db.close()
        manifest=json.loads(bundle['documents'][bundle['groupDigest']])
        (folder/'trust.json').write_bytes(canonical(trust))
        (folder/'group.json').write_bytes(bundle['documents'][bundle['groupDigest']])
        (folder/'catalog-result.json').write_bytes(canonical(result))
        (folder/'receipt-projection.json').write_bytes(canonical(receipt))
        summary.append({'sourceCase':case,'groupDigest':bundle['groupDigest'],'caseCount':len(manifest['cases']),
            'documentCount':manifest['closureDocuments'],'logicalBytes':manifest['closureBytes'],
            'sqliteFileBytes':(folder/'evidence.sqlite').stat().st_size,'reduceSeconds':reduced,
            'importSeconds':imported,'verifySeconds':seconds,'verified':verified})
except BaseException:
    (output/'failure.txt').write_text(traceback.format_exc());raise
finally:
    (output/'summary.json').write_text(json.dumps({'profile':'hms.staged-evidence-examples/0.1',
        'scope':'Historical worker evidence imported into staged SQLite only; receipt projections are not published catalog evaluations.',
        'imports':{'evidence':evidence.__file__,'fixtures':fixtures.__file__},'examples':summary},indent=2)+'\n')
print(json.dumps(summary,indent=2))

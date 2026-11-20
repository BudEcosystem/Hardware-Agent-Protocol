"""Recheck retained bytes after continuation; do not recreate missing raw trees."""
import hashlib
import json
from pathlib import Path
import time

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PINS={'implementation01':'a7e03e59584b61e09efe40fbd093c423acfdc4c037c6d5d24273019bdda3f2b5',
      'harness01':'dc350cdb4847178e203b307ac20b142a6a73e072f373a4f71316abe585b4feea',
      'harness02':'094098cab10de007e509f99895997915f6956634cb045f0d241ae333a01b08dc'}
def read(path):return json.loads(path.read_bytes())
def sha(path):
    assert not path.is_symlink() and path.is_file() and path.stat().st_size<=16777216
    return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(path,row):assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],str(path)
def inventory(folder):
    rows=[]
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():rows.append(dict(path=path.relative_to(folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])
for name,pin in PINS.items():
    folder=BASE/name;assert sha(folder/'index.json')==pin
    for row in read(folder/'index.json')['files']:verify((ROOT if name.startswith('implementation') else folder)/row['path'],row)
reports=[]
for name,attempt_name,report_name in (('harness01','attempt01-pure63','PURE-RESULTS.json'),('harness02','attempt01-actual','RESULTS.json')):
    attempt=BASE/name/'attempts'/attempt_name;result=read(attempt/'result.json');audit=read(BASE/report_name)
    assert sha(attempt/'result.json')==audit['resultSha256']
    assert result['childState']=='exited' and result['currentPass'] is (name=='harness01')
    assert result['status']==('passed' if name=='harness01' else 'failed')
    for label,prefix in (('inputs',attempt/'project'),('frozen',ROOT),('harness',attempt/'harness')):
        rows=read(attempt/(label+'-before.json'));assert rows==read(attempt/(label+'-after.json'))
        for row in rows:verify(prefix/row['path'],row)
    assert read(attempt/'external-before.json')==read(attempt/'external-after.json')
    rows=inventory(attempt/'scratch');assert rows==read(attempt/'scratch-index.json')
    assert sum(row['bytes'] for row in rows)==audit['rawBytes']==result['scratchRetainedBytes']
    assert len(rows)==audit['rawFiles']
    raw=Path(result['scratchPath'])
    if raw.exists():
        assert inventory(raw)==rows
        raw_state='present-and-bytes-match'
    else:raw_state='missing-at-this-recheck'
    reports.append(dict(harness=name,attempt=attempt_name,resultSha256=sha(attempt/'result.json'),
        originalStatus=result['status'],rawPath=str(raw),currentRawState=raw_state,
        retainedFiles=len(rows),retainedBytes=result['scratchRetainedBytes'],retainedCopyVerified=True))
actual=BASE/'harness02/attempts/attempt01-actual/scratch/test_actual_original_matrix_import_and_cold_vault_history'
for path,pin in read(BASE/'RESULTS.json')['readonlySourceDatabases'].items():assert sha(actual/path)==pin
summary=dict(status='retained-copies-verified',observedAtUnixNs=time.time_ns(),sourcePins=PINS,scopes=reports,
    originalAuditsRetained=True,originalWriterIdentityReacquiredNow=False,databasesOpened=0,
    originalMissingPathsRecreated=False,attemptsRerun=False,productionQualificationChanged=False,goalStatus='active')
with (BASE/'RETENTION-RECHECK.json').open('x') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
print(json.dumps(dict(status=summary['status'],rawStates=[r['currentRawState'] for r in reports],databasesOpened=0,goalStatus='active')))

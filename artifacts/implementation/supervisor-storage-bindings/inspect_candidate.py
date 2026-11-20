"""Read/import-only identity inspection; refuses SQL, processes and writes."""
import hashlib
import json
import os
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parent
PROJECT=BASE/'implementation01/project'
assert sys.flags.isolated and sys.flags.dont_write_bytecode
approved=BASE.parents[2]/'artifacts/implementation/pat-statement-cache/harness01/references/approved-external-roots.json'
raw=approved.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='4155d501cb1e11fe535ea9d774a9b1b0e8f68bfabbc9195d79e392452d869570'
selected=json.loads(raw)
for row in selected['selectedMetadata']:
    body=Path(row['metadataPath']).read_bytes()
    assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256']
sys.path[:0]=[str(PROJECT)]+selected['roots']

def guard(event,args):
    if event.startswith('socket.') or event in {'sqlite3.connect','subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn','os.mkdir','os.remove','os.rename'}:
        raise AssertionError('Inspection effect: '+event)
    if event=='open':
        mode,flags=args[1:3]
        if type(mode) is str and any(c in mode for c in 'wax+') or type(flags) is int and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
            raise AssertionError('Inspection file write')

sys.addaudithook(guard)
from hms_qualification.supervisor.io_service_execution import BoundQualificationSupervisor
from hms_qualification.supervisor.storage_binding import StorageAttemptLedger
from hms_qualification.supervisor.supervisor_contracts import supervisor_identity
from hms_qualification.supervisor.qualification_supervisor import _image_rows
from hms_qualification.evidence.contracts import identity as legacy
from hms_qualification.evidence_authority.contracts import identity as consumer
from hms_qualification.evidence_vault.contracts import identity as vault
from hms_qualification.vault_recorded_io.contracts import identity as host
from hms.pat_simulation_worker import simulation_identities
rows=_image_rows()
assert len({r[0] for r in rows})==len(rows)
assert 'hms_qualification/supervisor/storage_binding.py' in {r[0] for r in rows}
for name,path,pin in rows:assert hashlib.sha256(path.read_bytes()).hexdigest()==pin
print(json.dumps(dict(importEffects=False,producerImageFiles=len(rows),worker=simulation_identities(),
    supervisor=supervisor_identity(simulation_identities()),legacy=legacy(),consumer=consumer(),vault=vault(),host=host()),indent=2))

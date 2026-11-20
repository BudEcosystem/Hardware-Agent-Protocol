"""Validate archived JSON projections only; no Runtime/daemon or database opens."""
from pathlib import Path
import copy
import hashlib
import importlib.metadata
import json
import sys
import traceback
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'inputs'))
from hms import api_contracts
from hms.contracts import canonical
assert Path(api_contracts.__file__).resolve().is_relative_to(ROOT/'inputs')
rows=[]
for case in sorted((ROOT/'cases').iterdir()):
 authority=json.loads((case/'authority.db.json').read_text())['tables']
 board=json.loads((case/'board.db.json').read_text())['tables']
 for op in authority['operations']['rows']:
  receipt=next((item for item in board['io_receipts']['rows'] if item['operation']==op['id']),None)
  if receipt is None:continue
  value=receipt['document']
  if value['state'] in {'pending','rejected_before_start'}:continue
  # Exact Runtime.operation + IoRouteAdapter.result projection over retained
  # rows. This does not reopen the board or claim independent receipt validity.
  claims=sorted([{'resource':r['resource'],'fence':r['fence']} for r in authority['claims']['rows'] if r['operation_id']==op['id']],key=lambda r:r['resource'])
  output={'primitive':op['intent']['actionId'],'result':value['result'],'safeIdleState':value['idleState'],'receiptDigest':receipt['digest']}
  response={'protocol':'hms.operation/0.1','operationId':op['id'],'requestDigest':op['digest'],
   'instanceId':op['intent']['instanceId'],'actionId':op['intent']['actionId'],
   'executionState':op['state'],'cancellationState':op['cancel_state'],'effectVerification':op['verification'],
   'mayHaveActed':bool(op['may_have_acted']),'eventSequence':op['sequence'],'resourceClaims':claims,
   'result':{'evidenceKind':'simulation','output':output}}
  errors=[{'message':e.message,'path':list(e.path),'schemaPath':list(e.schema_path)} for e in api_contracts._VALIDATORS['operation'].iter_errors(response)]
  failure=None
  try:api_contracts.validate_result('operation',response,{'operationId':op['id']})
  except api_contracts.ResponseError as exc:
   frames=traceback.extract_tb(exc.__traceback__)
   failure={'class':type(exc).__name__,'message':str(exc),'frames':[{'file':f.filename,'line':f.lineno,'function':f.name,'source':f.line} for f in frames]}
  assert not errors and failure is not None
  assert any('output.get("effectCommitted")' in (f['source'] or '') for f in failure['frames'])
  rows.append({'case':case.name,'reconstruction':'Archived rows, terminal snapshot after failed request; exact source projection, not raw rejected wire response.',
   'operationId':op['id'],'state':op['state'],'receiptState':value['state'],'response':response,
   'jsonSchemaErrors':errors,'crossFieldFailure':failure})
assert len(rows)==4
report={'profile':'hms.archived-io-response-diagnosis/0.1','cases':rows,'validatorModule':str(Path(api_contracts.__file__).resolve()),
 'jsonschemaVersion':importlib.metadata.version('jsonschema'),'runtimeOrDaemonExecuted':False,'databaseOpened':False,
 'conclusion':'All four archived terminal projections pass retained JSON Schema but fail exact legacy simulation output.effectCommitted Boolean cross-field check.'}
(ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'cases':len(rows),'schemaValid':len(rows),'legacyCrossFieldFailures':len(rows),'states':[r['state'] for r in rows]},indent=2))

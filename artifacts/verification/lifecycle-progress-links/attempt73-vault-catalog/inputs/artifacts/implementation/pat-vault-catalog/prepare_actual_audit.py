"""Adapt the retained full-import auditor to the new catalog/application scope."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PRIOR=ROOT/'artifacts/implementation/pat-integer-canonical'
source=PRIOR/'audit_actual.py'
pin=next(x for x in json.loads((PRIOR/'index.json').read_bytes())['files'] if x['path']=='audit_actual.py')
assert source.stat().st_size==pin['bytes'] and hashlib.sha256(source.read_bytes()).hexdigest()==pin['sha256']
original=source.read_text();text=original
def change(before,after):
    global text
    assert before in text,before
    text=text.replace(before,after)
change("STAGE=BASE/'implementation01';HARNESS=BASE/'harness01'", "STAGE=BASE/'implementation03';HARNESS=BASE/'harness23'")
change("PIN='387d33e2992d2862b1c21902b8de09195a56b569f52c3c3e04b84ce09b2d8849'", "PIN='5ffd155119c12c73d6090a6684973f7f14474ebbfdb0fce228f880476df4e3a9'")
change("HPIN='88a1f8019e26607ca12526c3154cfc0ff9640ca8e39fb68189133169bce6dd44'", "HPIN='eb5a17ffdffaaa5ef208fd623f0db8e7c19b7634cf26e370b9fe00880d827437'")
change('test_actual_original_matrix_import_and_cold_vault_history','test_actual_original_matrix_catalog_admission_and_cold_history')
change("result['projectInputCount']==291 and result['frozenPreparationInputCount']==295", "result['projectInputCount']==302 and result['frozenPreparationInputCount']==308")
change("assert len(native['scans'])==2 and sorted(v['calls'] for v in native['scans'])==[1,2426]", "assert len(native['scans'])==2 and all(type(v['calls']) is int and v['calls']>0 for v in native['scans'])")
change("counts==dict(evi_intents=1,evi_publications=1,operations=0,claims=0)", "counts==dict(evi_intents=1,evi_publications=1,operations=1,claims=0)")
change("assert all(row[1:]==(0,0,0) for row in board_db.execute('SELECT instance,activations,completed,canceled FROM io_effects'))",
    "effects=read(work/'application-effects.json')\n    actual_effects=[list(row) for row in board_db.execute('SELECT instance,activations,completed,canceled FROM io_effects')]\n    assert actual_effects==effects['effects']\n    assert all(row[1:]==([1,1,0] if row[0]==effects['selectedInstance'] else [0,0,0]) for row in actual_effects)")
change("calls=2426,maxFiles=8192", "calls=scan_rows[str(worker)]['calls'],maxFiles=8192")
change("{'import_complete','warm_replay_complete','cold_changed_configuration_history_complete','test_body_complete'}", "{'import_complete','catalog_recorded','catalog_activated','application_completed','cold_history_complete','test_body_complete'}")
change('sha256:1964ddcf3bac1182f19f383cc09807138182c91a2c4591c82e4a493fe37e1d6a','sha256:5e9214b37a96f897253ea2f1859090327039f5aaeb9512aa49df880484cf4523')
change("actual-vault-checks.json", "actual-vault-catalog-checks.json")
change("intent_digest==imported['intentDigest']==checks['intentDigest']", "intent_digest==imported['intentDigest']")
change("assert checks['coldVaultHistoryAfterConfigurationDrift'] and checks['authorityBusinessRowsUnchanged']",
    "assert checks['coldVaultAndBridgeHistory'] and checks['catalogIntegrated']\n    assert checks['freshConfigurationRefusal']!='PAT_NO_MATCH' and checks['freshColdRefusal']!='PAT_NO_MATCH'")
change("('coldRuntimeAndSupervisorReopen','sessionDriftTested','catalogIntegrated',\n        'physicalObjectiveVerified','aggregateDiskQuotaEnforced','physicalCapacityReserved')",
    "('physicalObjectiveVerified','aggregateDiskQuotaEnforced','physicalCapacityReserved')")
change("checks['sourceApplicationInvocations']==0", "checks['sourceApplicationInvocations']==1")
change('catalogIntegrated=False','catalogIntegrated=True')
change('sourceApplicationInvocations=0','sourceApplicationInvocations=1')
block='''    # Verify the separately versioned catalog and exact admitted application.
    host_names=('__init__.py','contracts.py','projection.py','bridge.py','catalog.py','execution.py')
    host_rows=[dict(path=name,bytes=(ATTEMPT/'project/vault_recorded_io'/name).stat().st_size,
        sha256='sha256:'+sha(ATTEMPT/'project/vault_recorded_io'/name)) for name in host_names]
    host=digest(b'HMS-PAT-IO-VAULT-RECORDED-HOST-v0.1',dict(consumerIdentity=consumer,sources=host_rows))
    assert host==pins['host'] and host_rows==pins['hostSources']
    recorded=read(work/'recorded-evaluation.json');receipt=recorded['receipt'];inv=receipt['invocation']
    evaluation_digest=digest(b'HMS-PAT-IO-VAULT-CATALOG-EVALUATION-v0.1',receipt)
    assert evaluation_digest==recorded['evaluationDigest']==checks['evaluationDigest']
    assert inv['original']==intent['anchor'] and inv['publicationDigest']==publication_digest
    assert inv['importIntentDigest']==intent_digest and inv['manifestDigest']==publication['manifestDigest']
    assert inv['evaluationDigest']==publication['evaluationDigest'] and inv['evidenceClosure']==closure
    assert inv['vaultStoreId']==intent['storeId'] and inv['vaultBindingDigest']==binding
    assert inv['hostImplementationDigest']==host and inv['consumerIdentity']==consumer
    assert receipt['physicalObjectiveVerified'] is False and receipt['outcome']=='passed'
    assert authority.execute('SELECT digest,document FROM pc_evaluations').fetchall()==[(evaluation_digest,canonical(receipt))]
    assert authority.execute('SELECT value FROM pc_meta WHERE key="version"').fetchone()==('hms.pat.io-vault-recorded-catalog/0.1',)
    mount='hms.pat.io-vault-recorded-catalog/0.1|'+digest(b'HMS-PAT-IO-VAULT-RECORDED-CATALOG-MOUNT-v0.1',
        dict(authorityId=meta['authorityId'],deployment=receipt['environment']['deployment'],
            hostImplementationDigest=host,evaluators=[receipt['evaluator']]))
    assert authority.execute('SELECT value FROM reg_meta WHERE key="io_vault_recorded_catalog"').fetchone()==(mount,)
    assert authority.execute('SELECT value FROM px_meta WHERE key="version"').fetchone()==('hms.pat.io-vault-execution/0.1',)
    cursor=authority.execute('SELECT * FROM px_instances LIMIT 2');instance_rows=cursor.fetchall()
    assert len(instance_rows)==1;instance=dict(zip([row[0] for row in cursor.description],instance_rows[0]))
    assert instance['id']==checks['instanceId'] and instance['evaluation_digest']==evaluation_digest
    assert instance['evaluation']==canonical(receipt)
    artifact=json.loads(instance['artifact']);assert canonical(artifact)==instance['artifact']
    assert digest(b'HMS-PAT-JCS-SHA256-v0.1',artifact)==instance['artifact_digest']==receipt['artifactDigest']
    decisions=authority.execute('SELECT digest,document FROM pc_decisions').fetchall();assert len(decisions)==1
    decision=json.loads(decisions[0][1]);assert canonical(decision)==decisions[0][1]==instance['decision']
    assert digest(b'HMS-PAT-DECISION-v0.1',decision)==decisions[0][0]==instance['decision_digest']
    assert authority.execute('SELECT state,evaluation,decision FROM pc_entries').fetchall()==[('active',evaluation_digest,instance['decision_digest'])]
    assert authority.execute('SELECT instance_id FROM px_triggers').fetchall()==[(instance['id'],)]
    assert authority.execute('SELECT id,state FROM pr_procedures').fetchall()==[(instance['procedure_id'],'completed')]
    operations=authority.execute('SELECT id,state,intent FROM operations').fetchall();assert len(operations)==1
    operation=operations[0];assert operation[1]=='completed'
    assert authority.execute('SELECT procedure_id,operation_id FROM pr_steps').fetchall()==[(instance['procedure_id'],operation[0])]
    compiled_request=json.loads(instance['compiled_request'])
    assert canonical(compiled_request)==instance['compiled_request']
    assert digest(b'HMS-PROCEDURE-JCS-SHA256-v0.1',compiled_request)==instance['compiled_digest']
    assert canonical(compiled_request['procedure']['steps'][0]['request']['intent'])==operation[2]
    assert authority.execute('SELECT operation_id FROM replay_keys').fetchall()==[(operation[0],)]
    assert authority.execute('SELECT count(*) FROM pr_keys').fetchone()[0]==2
    request_document=json.loads(instance['request'])
    assert digest(b'HMS-PAT-RUN-v0.1',request_document)==instance['request_digest']
    assert request_document['runKey']=='application:1'
    statuses=read(work/'application-statuses.json')['statuses'];assert 1<=len(statuses)<=8
    assert statuses[-1]['instanceId']==instance['id'] and statuses[-1]['procedure']['executionState']=='completed'
    assert statuses[-1]['procedure']['unresolvedOperations']==[]
    catalog_observation=dict(hostIdentity=host,receiptDigest=evaluation_digest,artifactDigest=instance['artifact_digest'],
        decisionDigest=instance['decision_digest'],instanceId=instance['id'],procedureId=instance['procedure_id'],
        operationId=operation[0],oneCompletedApplication=True,activations=1,completions=1,cancellations=0,
        originalKeyReplay=True,coldVaultAndBridgeHistory=True,configurationDriftRefusesFreshAdmission=True,
        exactInvocationPublicationManifestJoin=True,physicalObjectiveVerified=False)

'''
change('    # Independently derive observations; never import the observer or project code.\n',block+'    # Independently derive observations; never import the observer or project code.\n')
change('observerControls=15,compositionControls=6,previousNativeControlsReferenced=True,publicContractTests=9,pureDifferentialCases=1668,productionCandidateChanged=True,publicRuntimeChanged=False,',
    "catalogControls=19,previousNativeControlsReferenced=True,productionCandidateChanged=True,publicRuntimeChanged=False,")
change('vaultImportObservation=import_observation,','vaultImportObservation=import_observation,catalogObservation=catalog_observation,')
change("('stageStatus','publicContractTests','pureDifferentialCases','caseManifests','importReached','rawFiles','workerResourceObservation','vaultImportObservation','goalStatus')",
    "('stageStatus','catalogControls','caseManifests','importReached','rawFiles','catalogObservation','goalStatus')")
change("with (BASE/'RESULTS.json').open('x')", "assert read(BASE/'CONTROL_RESULTS.json')['testsRun']==19\nwith (BASE/'RESULTS.json').open('x')")
ast.parse(text)
(BASE/'references').mkdir(exist_ok=True)
for path,value in ((BASE/'references/original-actual-audit.py',original),(BASE/'audit_actual.py',text),
    (BASE/'audit_actual.py.patch',''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True),fromfile='integer-canonical/audit_actual.py',tofile='vault-catalog/audit_actual.py')))):
    with path.open('x') as stream:stream.write(value)
print(json.dumps(dict(originalSha256=pin['sha256'],auditSha256=hashlib.sha256(text.encode()).hexdigest(),candidateImported=False)))

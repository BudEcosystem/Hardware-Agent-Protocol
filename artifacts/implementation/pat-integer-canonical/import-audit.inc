    # Independently verify publication and every retained vault body/reference.
    def body_sha(body):return 'sha256:'+hashlib.sha256(body).hexdigest()
    imported=read(work/'original-import.json');checks=read(work/'actual-vault-checks.json')
    intent=imported['intent'];publication=imported['receipt'];evaluation=imported['evaluation']
    intent_digest=digest(b'HMS-PAT-VAULT-IMPORT-INTENT-v0.1',intent)
    publication_digest=digest(b'HMS-PAT-VAULT-PUBLICATION-v0.1',publication)
    assert intent_digest==imported['intentDigest']==checks['intentDigest']
    assert publication_digest==imported['receiptDigest']==checks['importReceiptDigest']
    assert intent['sequence']==publication['sequence']==1 and intent['previousIntentDigest'] is None and publication['previousPublicationDigest'] is None
    assert intent['consumerIdentity']==evaluation['consumerIdentity']==consumer
    assert intent['storeId']==meta['vault']['storeId'] and publication['intentDigest']==intent_digest
    assert intent['bindingDigest']==digest(b'HMS-PAT-VAULT-ORIGINAL-BINDING-v0.1',intent['anchor'])
    intent_rows=authority.execute('SELECT sequence,evaluator,run,intent,record FROM evi_intents LIMIT 2').fetchall()
    publication_rows=authority.execute('SELECT sequence,intent,record FROM evi_publications LIMIT 2').fetchall()
    assert intent_rows==[(1,reservation['evaluatorId'],reservation['runId'],intent_digest,canonical(intent))]
    assert publication_rows==[(1,intent_digest,canonical(publication))]
    returned=json.loads(saved[0][2])
    assert saved[0][2]==(worker/'worker-return.json').read_bytes()==canonical(returned)
    assert body_sha(saved[0][2])==report['returnDigest']
    assert returned==dict(profile='hms.pat.io-supervisor-return/0.1',attemptId=record['attemptId'],
        bundleDigest=request['bundleDigest'],requestDigest=record['requestDigest'],
        groupResultDigest=body_sha((output/'result.json').read_bytes()),status='captured')
    expected_anchor=dict(authorityId=reservation['authorityId'],deployment=reservation['deployment'],
        evaluatorId=reservation['evaluatorId'],runId=reservation['runId'],artifactDigest=reservation['artifactDigest'],
        reservationDigest=handoff['reservationDigest'],configurationReceiptDigest=reservation['configurationReceiptDigest'],
        configurationDigest=request['context']['configurationDigest'],configurationRevision=request['context']['configurationRevision'],
        supervisorAuthorityId=handoff['supervisorAuthorityId'],handoffDigest=archive['association']['receiptDigest'],
        requestDigest=record['requestDigest'],attemptId=record['attemptId'],bundleDigest=request['bundleDigest'],
        producerIdentity=request['supervisorIdentity'],producerImplementation=request['implementation'],
        recordDigest=digest(b'HMS-PAT-IO-ORIGINAL-RECORD-v0.1',record),returnDigest=report['returnDigest'],
        groupResultDigest=returned['groupResultDigest'],outputClosure=report['evidenceIntegrity'])
    assert intent['anchor']==evaluation['anchor']==expected_anchor
    assert evaluation['outcome']=='passed' and evaluation['scope']=='complete-finite-synthetic-io-matrix'
    assert evaluation['inspectedCases']==30 and evaluation['unresolvedEffects']==0
    assert all(evaluation[key] is False for key in ('physicalObjectiveVerified','wallDeadlineAttested','aggregateDiskQuotaEnforced','catalogActivated'))
    assert authority.execute('SELECT request FROM iosr_runs').fetchall()==[(canonical(request),)]
    manifest_rows=vault.execute('SELECT sequence,intent,binding,record FROM ev_manifests LIMIT 2').fetchall()
    assert len(manifest_rows)==1
    sequence,stored_intent,binding,manifest_wire=manifest_rows[0]
    manifest=json.loads(manifest_wire)
    assert manifest_wire==canonical(manifest) and (sequence,stored_intent,binding)==(1,intent_digest,intent['bindingDigest'])
    assert manifest['scope']=='immutable-bytes-only' and manifest['previousManifestDigest'] is None
    assert manifest['sequence']==1 and manifest['intentDigest']==intent_digest and manifest['bindingDigest']==binding
    assert manifest['authorityId']==meta['authorityId'] and manifest['storeId']==meta['vault']['storeId']
    assert publication['manifestDigest']==digest(b'HMS-PAT-EVIDENCE-VAULT-MANIFEST-v0.1',manifest)
    assert vault.execute('SELECT count(*),sum(length(body)),max(length(body)) FROM ev_bodies').fetchone()[0]==2798
    assert vault.execute('SELECT sum(length(body)) FROM ev_bodies').fetchone()[0]<=24*1024*1024
    bodies={}
    for name,body in vault.execute('SELECT digest,body FROM ev_bodies LIMIT 2799'):
        assert type(body)is bytes and len(body)<=16777216 and body_sha(body)==name and name not in bodies
        bodies[name]=body
    refs=vault.execute('SELECT sequence,path,digest FROM ev_documents ORDER BY path LIMIT 4012').fetchall()
    assert len(refs)==4011 and len(bodies)==2798 and {row[2] for row in refs}==set(bodies)
    files={};chain=hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0')
    for sequence,name,value in refs:
        assert sequence==1 and name not in files and re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',name)
        assert all(part not in ('.','..') for part in name.split('/')) and len(name)<=288
        body=bodies[value];files[name]=body
        chain.update(canonical(dict(path=name,bytes=len(body),sha256=value))+b'\n')
    closure=dict(documents=len(files),bytes=sum(map(len,files.values())),digest='sha256:'+chain.hexdigest())
    assert closure==manifest['closure']==publication['closure']
    assert files['evaluation.json']==canonical(evaluation) and body_sha(files['evaluation.json'])==publication['evaluationDigest']
    assert body_sha(files['inspection/summary.json'])==evaluation['inspectionDigest']
    inspection=json.loads(files['inspection/summary.json'])
    assert [row['caseId'] for row in inspection['cases']]==[row['caseId'] for row in matrix['cases']]
    assert all(inspection[key] is True for key in ('requiredMatrixCoverageChecked','independentOutcomeChecked',
        'archiveAccountingChecked','trustedSetupMatched','implementationIdentityMatched'))
    for i,case in enumerate(inspection['cases']):
        body=files['inspection/case-%02d.json'%i]
        assert hashlib.sha256(body).hexdigest()==case['inspectionSha256'] and len(body)==case['inspectionBytes']
        assert json.loads(body)['caseId']==case['caseId'] and case['expectedResponseVerified'] is True
    expected_files={}
    for name,value in dict(reservation=reservation,handoff=handoff,request=request,attempt=record).items():
        expected_files['original/control/'+name+'.json']=canonical(value)
    expected_files['original/control/return.json']=saved[0][2]
    source_documents=authority.execute('SELECT sequence,path,body FROM iosr_documents LIMIT 40').fetchall()
    assert len(source_documents)<=39
    for sequence,name,body in source_documents:
        assert sequence==1 and re.fullmatch(r'(inputs|cases)/[A-Za-z0-9_.-]+',name) and len(body)<=65536
        assert body==(worker/'bundle'/name).read_bytes()
        expected_files['original/bundle/'+name]=body
    expected_files['original/bundle/header.json']=canonical(request['bundleHeader'])
    assert (worker/'bundle/header.json').read_bytes()==expected_files['original/bundle/header.json']
    output_rows=inventory(output);output_chain=hashlib.sha256(b'HMS-PAT-IO-OUTPUT-CLOSURE-v0.1\0')
    for row in sorted(output_rows,key=lambda row:tuple(row['path'].split('/'))):
        output_chain.update(canonical(row)+b'\n')
        expected_files['original/output/'+row['path']]=(output/row['path']).read_bytes()
    output_closure=dict(fileCount=len(output_rows),bytes=sum(row['bytes'] for row in output_rows),orderedDigest='sha256:'+output_chain.hexdigest())
    assert output_closure==report['evidenceIntegrity']
    assert all(files.get(name)==body for name,body in expected_files.items())
    inspection_names={'evaluation.json','inspection/summary.json'}|{'inspection/case-%02d.json'%i for i in range(30)}
    assert set(files)==set(expected_files)|inspection_names
    group=read(output/'result.json')
    assert group['status']=='captured' and group['error'] is None and group['allMatrixCasesCaptured']
    assert len(group['cases'])==30 and group['accounting']['charged']==inspection['accounting']
    assert [row['caseId'] for row in group['cases']]==[row['caseId'] for row in matrix['cases']]
    for row in group['cases']:
        ref=row['manifest'];verify(output/ref['path'],dict(bytes=ref['bytes'],sha256=ref['sha256']))
    assert checks['originalAttemptId']==record['attemptId'] and checks['completeCases']==30
    assert checks['oneQualificationWorker'] and checks['realReducerUsed'] and checks['exactOriginalKeyReplay']
    assert checks['coldVaultHistoryAfterConfigurationDrift'] and checks['authorityBusinessRowsUnchanged']
    assert all(checks[key] is False for key in ('coldRuntimeAndSupervisorReopen','sessionDriftTested','catalogIntegrated',
        'physicalObjectiveVerified','aggregateDiskQuotaEnforced','physicalCapacityReserved'))
    assert checks['sourceApplicationInvocations']==0
    storage=checks['storage']
    assert storage==dict(authorityBytes=(work/'runtime/authority.db').stat().st_size,
        vaultBytes=(work/'vault/evidence.db').stat().st_size,references=len(refs),bodies=len(bodies))
    assert storage['authorityBytes']<=16777216 and storage['vaultBytes']<=15728640
    import_observation=dict(originalImportAndPublicationAssociated=True,allVaultBodiesAndReferencesVerified=True,
        originalBundleAndOutputBytesEqual=True,originalOutputClosure=output_closure,importedClosure=closure,
        completeCases=30,syntheticUnresolvedEffects=0,publicationDigest=publication_digest,intentDigest=intent_digest,
        manifestDigest=publication['manifestDigest'],inspectionSha256=evaluation['inspectionDigest'],storage=storage,
        vaultUnreservedPageCapHeadroomBytes=15728640-storage['vaultBytes'],catalogIntegrated=False,
        physicalObjectiveVerified=False,semanticReducerExecutedInOriginalScope=True,semanticReducerReexecutedByAudit=False)

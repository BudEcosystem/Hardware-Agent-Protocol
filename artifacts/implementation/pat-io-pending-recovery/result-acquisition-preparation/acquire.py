"""One-shot retention and read-only evidence comparison; no project imports.

This verifies capture integrity, not qualification or independent effect semantics.
Run from the HMS root. Never deletes or changes the original attempt/scratch.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-pending-recovery'
SOURCE = BASE / 'harness01/attempts/attempt01-recovery46'
OUT = BASE / 'results/attempt01-passed46'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path, row):
    assert path.is_file() and not path.is_symlink(), str(path)
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], str(path)


def inventory(path):
    rows = []
    for entry in sorted(path.rglob('*')):
        assert not entry.is_symlink(), str(entry)
        if entry.is_dir():
            continue
        assert stat.S_ISREG(entry.stat().st_mode), str(entry)
        rows.append({'path': entry.relative_to(path).as_posix(),
                     'bytes': entry.stat().st_size, 'sha256': sha(entry)})
    return rows


def identity(path):
    value = path.lstat()
    assert stat.S_ISDIR(value.st_mode)
    return dict(path=str(path), device=value.st_dev, inode=value.st_ino,
                uid=value.st_uid, gid=value.st_gid, mode=stat.S_IMODE(value.st_mode))


def write(name, value):
    with (OUT / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


result = read(SOURCE / 'result.json')
assert result['currentPass'] is True and result['errors'] == []
assert result['childState'] == 'exited' and result['exitCode'] == 0
assert not Path('/proc/' + str(result['pid'])).exists()
assert result['counts'] == dict(testsRun=46, failures=0, errors=0, skips=0,
                                expectedFailures=0, unexpectedSuccesses=0)

seals = []
for relative, expected in [
    ('implementation01', 'fd57b0ae6dcdf882d9092d0ab240a034e1643e9f909875f0df06f34a5577207b'),
    ('harness01', 'a5a5fa41dbd93ea80f7cce1fd80f2c5fc57df5130b1ad59211291d96d25c58c4'),
]:
    index = BASE / relative / 'index.json'
    assert sha(index) == expected
    rows = read(index)['files']
    for row in rows:
        base = ROOT if relative == 'implementation01' else BASE / relative
        verify(base / row['path'], row)
    seals.append({'path': str(index.relative_to(ROOT)), 'sha256': expected, 'filesVerified': len(rows)})

for prefix, directory, count in [('inputs', SOURCE / 'project', 5904),
                                  ('frozen', ROOT, 5907), ('harness', SOURCE / 'harness', 6)]:
    rows = read(SOURCE / (prefix + '-before.json'))
    assert rows == read(SOURCE / (prefix + '-after.json')) and len(rows) == count
    for row in rows:
        verify(directory / row['path'], row)
external = read(SOURCE / 'external-before.json')
assert external == read(SOURCE / 'external-after.json') and len(external['files']) == 159
for row in external['files']:
    verify(Path(row['resolvedPath']), row)
origins = read(SOURCE / 'imports.json')
assert origins['violations'] == origins['prohibitedAttempts'] == []
assert origins['summary']['recordCount'] == len(origins['records']) and origins['summary']['allOriginsMatched'] is True
for row in origins['records']:
    if 'sha256' in row:
        assert sha(Path(row['origin'])) == row['sha256'], row['origin']
for name in ['compiler', 'driver']:
    assert read(SOURCE / (name + '-before.json')) == read(SOURCE / (name + '-after.json'))
selection = read(SOURCE / 'harness/targets.json')['targets']
actual = read(SOURCE / 'actual-tests.json')
assert actual['loaded'] == actual['executed'] == selection
log = (SOURCE / 'output.log').read_text()
timing = re.search(r'Ran 46 tests in ([0-9.]+)s\n\nOK\n$', log)
assert timing is not None
test_seconds = float(timing.group(1))
assert [line.split('(')[1].split(')')[0] for line in log.splitlines() if line.endswith(' ... ok')] == selection

raw_before = read(SOURCE / 'raw-scratch-before.json')
raw = Path(result['scratchPath'])
assert identity(raw) == raw_before['identity'] and identity(raw.parent) == raw_before['parent']
scratch_rows = read(SOURCE / 'scratch-index.json')
assert inventory(raw) == inventory(SOURCE / 'scratch') == scratch_rows
scratch_bytes = sum(row['bytes'] for row in scratch_rows)
assert scratch_bytes <= 64*1024*1024 and len(scratch_rows) <= 8192
before = inventory(SOURCE)
shutil.copytree(SOURCE, OUT / 'attempt')
assert inventory(OUT / 'attempt') == before == inventory(SOURCE)

TABLES = {
    'board': set('io_meta io_resources io_owners io_fences io_receipts io_receipt_versions io_effects'.split()),
    'authority': set(('meta series namespaces operations replay_keys resource_floors claims events '
                      'io_dispatch_links io_authority_receipts pr_meta pr_procedures pr_steps pr_keys pr_events '
                      'rt_catalog rt_adapters rt_io_installation rc_catalog rc_generations rc_tokens rc_proofs').split()),
}


def decode(cell):
    assert set(cell) == {'type', 'value'}
    kind, value = cell['type'], cell['value']
    if kind == 'blob-utf8':
        assert type(value) is str
        return value.encode('utf-8')
    assert (kind == 'null' and value is None or kind == 'integer' and type(value) is int or
            kind == 'text' and type(value) is str)
    return value


observations = []
checkpoint_count = table_reference_count = configuration_snapshots = configuration_records = configuration_table_references = 0
active_states = []
pending_states = []
selection_data = read(SOURCE/'harness/targets.json')
active_phases = selection_data['activeGrantPhases']
pending_plans = selection_data['pendingFaultPlans']
copied = OUT / 'attempt/scratch'
for workspace in sorted(copied.iterdir()):
    manifest = workspace / 'engine-0.json'
    if not manifest.exists():
        assert workspace.name == 'test_nonempty_output_directory_is_not_opened_as_runtime_state'
        continue
    manifest = read(manifest)
    assert manifest['closed'] is True and manifest['cleanupErrors'] == []
    refs, report = manifest['records'], manifest['report']
    assert report['qualificationPassed'] is False and report['independentOutcomeChecked'] is False
    assert [r['path'] for r in refs] == ['%06d.json' % i for i in range(len(refs))]
    trial = workspace / 'trial-0'
    docs = {}
    for ref in refs:
        verify(trial / 'records' / ref['path'], ref)
        assert ref['bytes'] <= 65536
        docs[ref['path']] = read(trial / 'records' / ref['path'])
    assert len(refs) <= 4096 and sum(r['bytes'] for r in refs) <= 16 * 1024 * 1024
    clock, pending, last_phase, checkpoints = 1000000, None, 0, []
    for number, ref in enumerate(refs):
        doc = docs[ref['path']]
        assert doc['profile'] == 'hms.pat.io-trial-record/0.1'
        kind, value = doc['kind'], doc['value']
        if kind == 'clock_advanced':
            assert value['from'] == clock and type(value['to']) is int and value['to'] > clock
            clock = value['to']
        elif kind == 'call_started':
            assert pending is None and value['clock'] == clock and value['phase'] == last_phase + 1
            pending = (value['phase'], value['label']); last_phase = value['phase']
        elif kind in {'call_returned', 'call_failed'}:
            assert pending == (value['phase'], value['label']) and value['clock'] == clock
            pending = None
        elif kind == 'runtime_opened':
            assert value['wallMs'] == clock
        elif kind == 'checkpoint':
            assert value['wallMs'] == value['monotonicMs'] == clock
            assert len(value['tables']) == 29
            expected = {(s, t) for s, tables in TABLES.items() for t in tables}
            assert {(t['store'], t['table']) for t in value['tables']} == expected
            for table in value['tables']:
                count, columns = 0, None
                assert len(table['pages']) == max(1, (table['rowCount'] + 7) // 8)
                for page_ref in table['pages']:
                    idx = int(page_ref['path'][:6])
                    assert idx < number and refs[idx] == page_ref
                    page = docs[page_ref['path']]
                    assert page['kind'] == 'table_page'
                    page = page['value']
                    assert page['store'] == table['store'] and page['table'] == table['table']
                    assert page['first'] == count and page['totalRows'] == table['rowCount']
                    assert len(page['rows']) == min(8, table['rowCount'] - count)
                    assert all(len(row) == len(page['columns']) for row in page['rows'])
                    for row in page['rows']:
                        for cell in row:
                            decode(cell)
                    if columns is not None:
                        assert columns == page['columns']
                    columns = page['columns']; count += len(page['rows'])
                assert count == table['rowCount']
                table_reference_count += 1
            checkpoints.append(value); checkpoint_count += 1
    assert pending is None and clock == report['clock']
    final = checkpoints[-1]
    assert final['label'] == 'test_final'
    dbs = list((trial / 'state').glob('*.db'))
    assert len(dbs) == 2
    stores = {'authority': trial / 'state/authority.db',
              'board': next(p for p in dbs if p.name.startswith('synthetic-io-board-'))}
    values = {}
    for store, database in stores.items():
        connection = sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
            for table in [t for t in final['tables'] if t['store'] == store]:
                pages = [docs[r['path']]['value'] for r in table['pages']]
                columns = pages[0]['columns']
                assert all(re.fullmatch('[a-z_]+', name) for name in [table['table']] + columns)
                actual_columns = [r[1] for r in connection.execute('PRAGMA table_info(' + table['table'] + ')')]
                assert actual_columns == columns
                fields = ','.join('"' + c + '"' for c in columns)
                actual_rows = connection.execute('SELECT ' + fields + ' FROM "' + table['table'] + '" ORDER BY ' + fields).fetchall()
                captured = [tuple(decode(c) for c in row) for page in pages for row in page['rows']]
                assert actual_rows == captured, (workspace.name, store, table['table'])
                values[table['table']] = actual_rows
        finally:
            connection.close()
    configuration = manifest.get('configuration')
    compared_configuration = 0
    if configuration is not None:
        assert all(configuration[k] is False for k in ('configurationAttested','independentOutcomeChecked','qualificationPassed'))
        cfg_refs = configuration['records']; cfg_docs = {}
        configuration_records += len(cfg_refs)
        assert configuration['combinedRecords'] == len(refs)+len(cfg_refs) <= 4096
        assert configuration['combinedBytes'] == sum(r['bytes'] for r in refs+cfg_refs) <= 16*1024*1024
        for ref in cfg_refs:
            verify(trial/'configuration'/ref['path'],ref); assert ref['bytes'] <= 65536
            cfg_docs[ref['path']] = read(trial/'configuration'/ref['path'])
            assert cfg_docs[ref['path']]['profile'] == 'hms.pat.io-configuration-record/0.1'
        cp_refs = [r for r in refs if docs[r['path']]['kind'] == 'checkpoint']
        snapshots = [r for r in cfg_refs if cfg_docs[r['path']]['kind'] == 'snapshot']
        assert len(snapshots) == len(cp_refs)
        assert configuration['snapshots'] == [dict(checkpoint=c,configuration=s) for c,s in zip(cp_refs,snapshots)]
        expected_tables = set(('reg_meta reg_types reg_instances reg_capabilities reg_bindings reg_binding_history '
            'reg_presence reg_endpoint_sessions reg_session_history reg_observations reg_streams reg_stream_history '
            'reg_grants reg_resource_requirements reg_resource_instances').split())
        used = {'000000.json'}
        for c,s in zip(cp_refs,snapshots):
            cp = docs[c['path']]['value']; snap = cfg_docs[s['path']]['value']; used.add(s['path'])
            assert snap['checkpoint'] == c
            assert all(snap[k] == cp[k] for k in ('phase','label','wallMs','monotonicMs','clockEpoch'))
            assert len(snap['tables']) == 15 and {t['table'] for t in snap['tables']} == expected_tables
            resolver = snap['resolver']; position = int(resolver['path'][:6])
            assert cfg_refs[position] == resolver and position < int(s['path'][:6])
            assert cfg_docs[resolver['path']]['kind'] == 'resolver_configuration'; used.add(resolver['path'])
            for table in snap['tables']:
                count = 0; columns = None
                projection = 'public_registry_metadata' if table['table']=='reg_meta' else 'complete'
                assert table['projection'] == projection and len(table['pages']) == max(1,(table['rowCount']+7)//8)
                for page_ref in table['pages']:
                    position = int(page_ref['path'][:6]); assert cfg_refs[position] == page_ref and position < int(s['path'][:6])
                    page = cfg_docs[page_ref['path']]; assert page['kind']=='table_page'; page=page['value']; used.add(page_ref['path'])
                    assert page['table']==table['table'] and page['projection']==projection and page['first']==count
                    assert page['totalRows']==table['rowCount'] and len(page['rows'])==min(8,table['rowCount']-count)
                    assert columns is None or columns==page['columns']; columns=page['columns']
                    for cells in page['rows']:
                        assert len(cells)==len(columns)
                        for cell in cells: decode(cell)
                    count += len(page['rows'])
                assert count==table['rowCount']; configuration_table_references += 1
            configuration_snapshots += 1
        assert used == set(cfg_docs)
        final_config = cfg_docs[snapshots[-1]['path']]['value']; assert final_config['label']=='test_final'
        connection = sqlite3.connect(stores['authority'].resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            for table in final_config['tables']:
                pages=[cfg_docs[r['path']]['value'] for r in table['pages']]; columns=pages[0]['columns']
                assert all(re.fullmatch('[a-z_]+',name) for name in [table['table']]+columns)
                assert [r[1] for r in connection.execute('PRAGMA table_info('+table['table']+')')]==columns
                fields=','.join('"'+c+'"' for c in columns)
                where,params=(' WHERE key IN (?,?,?)',('deployment','revision','version')) if table['table']=='reg_meta' else ('',())
                actual_rows=connection.execute('SELECT '+fields+' FROM "'+table['table']+'"'+where+' ORDER BY '+fields,params).fetchall()
                captured=[tuple(decode(c) for c in row) for page in pages for row in page['rows']]
                assert actual_rows==captured,(workspace.name,table['table']); compared_configuration += 1
            secret=connection.execute("SELECT value FROM reg_meta WHERE key='cursor_key'").fetchone()[0].encode()
            assert all(secret not in p.read_bytes() for directory in ('records','configuration') for p in (trial/directory).iterdir())
        finally: connection.close()
    if workspace.name in active_phases:
        expected = manifest['expectedAuthority']; change, = expected['grantChanges']
        assert change['phase']==active_phases[workspace.name] and change['label']=='drive:adapters:before'
        assert expected['principal']=='pat-io-trial-worker' and expected['deployment']=='simulation:io-hub'
        changed=False
        for snap_ref in snapshots:
            snap=cfg_docs[snap_ref['path']]['value']
            if (snap['phase'],snap['label'])==(change['phase'],change['label']): changed=True
            table=next(t for t in snap['tables'] if t['table']=='reg_grants')
            rows=[dict(zip(cfg_docs[r['path']]['value']['columns'],[decode(c) for c in row])) for r in table['pages'] for row in cfg_docs[r['path']]['value']['rows']]
            assert rows==(change['grants'] if changed else expected['initialGrants'])
        assert changed
        assert len(values['operations'])==1 and len(values['io_receipts'])==1 and len(values['io_receipt_versions'])==2
        assert not values['claims'] and not values['io_owners'] and not report['unresolvedOperations']
        receipt=json.loads(values['io_receipts'][0][4])
        counts=tuple(sum(row[i] for row in values['io_effects']) for i in (1,2,3))
        completed=workspace.name=='test_completed_effect_reconciles_after_permission_withdrawal'
        expected_reason=None if completed else 'client_cancel' if workspace.name=='test_prior_cancel_request_keeps_its_cause_after_revocation' else 'authority_or_binding_lost'
        assert counts==((1,1,0) if completed else (1,0,1))
        assert receipt['result']==dict(activationCommitted=True,cycleCompleted=completed,safeIdle=True,reason=expected_reason)
        assert report['procedure']['executionState']==('completed' if completed else 'canceled' if expected_reason=='client_cancel' else 'failed')
        reply_loss='reply_loss' in workspace.name or workspace.name=='test_completed_effect_reconciles_after_permission_withdrawal'
        if reply_loss:
            error_cp=next(c for c in checkpoints if c['label']=='drive:adapters:after_error')
            def retained(name):
                table=next(t for t in error_cp['tables'] if t['table']==name)
                return [dict(zip(docs[r['path']]['value']['columns'],[decode(c) for c in row])) for r in table['pages'] for row in docs[r['path']]['value']['rows']]
            error_op,=retained('operations'); assert error_op['state']=='outcome_unknown'
            assert retained('claims') and not retained('io_owners')
            error_receipt,=retained('io_receipts'); assert error_receipt['state']==('completed' if completed else 'canceled')
        active_states.append({'method':workspace.name,'grantPhase':change['phase'],'parentState':report['procedure']['executionState'],
            'effects':counts,'receiptReason':expected_reason,'replyLossRetained':reply_loss,'claimsReleasedAfterReceipt':True})
    if workspace.name in pending_plans:
        expected = manifest['expectedAuthority']; principal, deployment = 'pat-io-trial-worker','simulation:io-hub'
        changes = []
        if workspace.name in selection_data['pendingWithdrawalPhase']:
            changes = [{'phase':selection_data['pendingWithdrawalPhase'][workspace.name],'label':'drive:adapters:before',
                'grants':[dict(principal=principal,deployment=deployment,target='sim:gpio5',verb='read')]}]
        assert expected == dict(profile='hms.pat.io-trusted-authority/0.1',principal=principal,deployment=deployment,
            initialRegistryRevision=13,initialGrants=[dict(principal=principal,deployment=deployment,target='*',verb='admin')],grantChanges=changes)
        assert manifest['expectedFaults'] == pending_plans[workspace.name]
        op_id, = report['operationIds']; faults = pending_plans[workspace.name]['faults']
        assert manifest['injectedFaults'] == [dict(phase=f['phase'],point=f['point'],operationId=op_id) for f in faults]
        grants, next_change = expected['initialGrants'],0
        for snap_ref in snapshots:
            snap=cfg_docs[snap_ref['path']]['value']
            if next_change<len(changes) and (snap['phase'],snap['label'])==(changes[next_change]['phase'],changes[next_change]['label']):
                grants=changes[next_change]['grants'];next_change+=1
            table=next(t for t in snap['tables'] if t['table']=='reg_grants')
            rows=[dict(zip(cfg_docs[r['path']]['value']['columns'],[decode(c) for c in row])) for r in table['pages'] for row in cfg_docs[r['path']]['value']['rows']]
            assert rows==grants
        assert next_change==len(changes)
        def rows_at(cp,name):
            table=next(t for t in cp['tables'] if t['table']==name)
            return [dict(zip(docs[r['path']]['value']['columns'],[decode(c) for c in row])) for r in table['pages'] for row in docs[r['path']]['value']['rows']]
        assert len(values['operations'])==1 and len(values['io_receipts'])==1 and len(values['io_receipt_versions'])==2
        assert not values['claims'] and not values['io_owners'] and not report['unresolvedOperations']
        operation,=rows_at(final,'operations'); assert operation['id']==op_id and operation['state']=='failed' and operation['may_have_acted']==1
        receipt=json.loads(values['io_receipts'][0][4]); assert receipt['operationId']==op_id and receipt['sequence']==2 and receipt['state']=='canceled'
        assert receipt['result']==dict(activationCommitted=True,cycleCompleted=False,safeIdle=True,reason='reconciliation_stop')
        counts=tuple(sum(row[i] for row in values['io_effects']) for i in (1,2,3));assert counts==(1,0,1)
        canceled=workspace.name=='test_cancel_request_does_not_relabel_unknown_pending_recovery'
        assert report['procedure']['executionState']==('canceled' if canceled else 'failed')
        assert operation['cancel_state']==('requested' if canceled else 'not_requested')
        baseline=rows_at(checkpoints[0],'io_resources')
        assert rows_at(final,'io_resources')==baseline
        fault_states=[]
        for fault in faults:
            begin=fault['point']=='board.begin.after_commit'; terminal=fault['point']=='journal.reconcile.before_commit'
            label='drive:adapters:after' if begin else 'drive:adapters:after_error'
            cp=next(c for c in checkpoints if (c['phase'],c['label'])==(fault['phase'],label))
            op,=rows_at(cp,'operations'); assert op['id']==op_id and op['state']=='outcome_unknown'
            claims=rows_at(cp,'claims'); owners=rows_at(cp,'io_owners'); current,=rows_at(cp,'io_receipts')
            captured=json.loads(current['document']); assert claims and len(claims)==len(captured['claims'])
            assert (current['sequence'],current['state'])==((2,'canceled') if terminal else (1,'pending'))
            if terminal:
                assert not owners and captured['result']['reason']=='reconciliation_stop' and captured['result']['safeIdle'] is True
            else:
                assert {(r['resource'],r['operation'],r['fence']) for r in owners}=={(r['resource'],op_id,r['fence']) for r in claims}
                assert captured['result']==dict(activationCommitted=True,cycleCompleted=False,safeIdle=False,reason=None)
                states={r['resource']:json.loads(r['state']) for r in rows_at(cp,'io_resources')}
                assert {a:states[a] for a in captured['activeState']}==captured['activeState']
            call=next(d for d in docs.values() if d['kind'] in {'call_returned','call_failed'} and d['value']['phase']==fault['phase'])
            if begin:
                assert call['kind']=='call_returned' and call['value']['result'] is None
                assert not rows_at(cp,'io_authority_receipts')
                unknown=next(e for e in rows_at(cp,'events') if e['kind']=='outcome_unknown')
                assert json.loads(unknown['payload'])==dict(reason='io_acceptance_unknown')
            else:
                assert call['kind']=='call_failed' and call['value']['exception']==fault['exception'] and call['value']['code']==fault['code']
            fault_states.append(dict(phase=fault['phase'],point=fault['point'],boardState=current['state'],heldClaims=len(claims),boardOwners=len(owners),engineCallReturned=begin))
        pending_states.append(dict(method=workspace.name,parentState=report['procedure']['executionState'],effects=counts,
            stopReason='reconciliation_stop',faultStates=fault_states,finalClaimsReleased=True))
    observations.append({'configurationTablesCompared':compared_configuration, 'method': workspace.name, 'records': len(refs), 'checkpoints': len(checkpoints),
        'tablesComparedToClosedDatabases': 29, 'clock': clock,
        'parentState': report['procedure']['executionState'] if report['procedure'] else None,
        'unresolvedOperations': report['unresolvedOperations'], 'heldClaims': len(values['claims']),
        'boardOwners': len(values['io_owners']), 'currentReceipts': len(values['io_receipts']),
        'receiptVersions': len(values['io_receipt_versions']), 'effectRows': values['io_effects']})

assert len(observations) == 45
assert sum(o['configurationTablesCompared'] for o in observations) == 390
lost = next(o for o in observations if o['method'] == 'test_missing_current_receipt_remains_unresolved')
assert len(lost['unresolvedOperations']) == lost['heldClaims'] == lost['boardOwners'] == 1
assert lost['currentReceipts'] == 0 and lost['receiptVersions'] == 1
assert inventory(OUT / 'attempt') == before == inventory(SOURCE)
assert inventory(raw) == scratch_rows and identity(raw) == raw_before['identity']
records = sum(o['records'] for o in observations)
assert len(active_states)==6 and [sum(s['effects'][i] for s in active_states) for i in range(3)]==[6,1,5]
assert sum(s['replyLossRetained'] for s in active_states)==2
assert len(pending_states)==8 and [sum(s['effects'][i] for s in pending_states) for i in range(3)]==[8,0,8]
assert sum(len(s['faultStates']) for s in pending_states)==10
write('pending-states.json',{'scope':'Root retained-state association checks, not independent trusted-fault/cause qualification.','states':pending_states})
write('active-states.json',{'scope':'Root retained-data consistency checks, not independent guard-cause qualification.','states':active_states})
write('observations.json', {'scope':'Capture integrity only; no independent configuration/authorization attestation.',
    'checkpoints':checkpoint_count, 'tableReferencesChecked':table_reference_count,
    'configurationRecords':configuration_records, 'configurationSnapshots':configuration_snapshots,
    'configurationTableReferencesChecked':configuration_table_references,
    'closedDatabasesReadOnly':90, 'finalTablesCompared':45*29+390, 'states':observations})
write('proof.json', {'scope':'Actual original-host pending-recovery46 tests and retained raw I/O phases.',
    'counts':result['counts'], 'testSeconds':test_seconds, 'elapsedSeconds':result['elapsedSeconds'],
    'projectInputsVerified':5904,'frozenInputsVerified':5907,'activeHarnessInputsVerified':6,
    'externalFilesVerified':159,'preparationSeals':seals,'originSummary':origins['summary'],
    'actualOriginFileHashesRechecked':True,'bytecodeReadsRefused':len(origins['deniedBytecodeReads']),
    'compilerAndDriverStable':True,'methodOrderAndLogVerified':True,'rawScratch':raw_before['identity'],
    'rawScratchOriginalRetained':True,'rawAndCopiedScratchFilesVerified':len(scratch_rows),'rawScratchBytes':scratch_bytes,
    'attemptFilesAcquired':len(before),'executionRecordsVerified':records,'configurationRecordsVerified':configuration_records,
    'engineStates':45,'readOnlyDatabases':90,'finalCheckpointTablesCompared':45*29+390,
    'newActiveTrials':6,'newEffects':dict(activations=6,completed=1,canceled=5),'replyLossCases':2,
    'newPendingTrials':8,'pendingEffects':dict(activations=8,completed=0,canceled=8),'injectedFaultsChecked':10,
    'pendingRecoveryIndependentlyChecked':False,'activeRevocationIndependentlyChecked':False,'independentReview':False,'configurationAttested':False,'independentOutcomeChecked':False,'qualificationPassed':False,
    'limitations':['Capture association/serialization, not independent authorization attestation.',
        'The existing composed checker refuses pending-unknown recovery; independent trusted-fault/cause checking and qualification remain unfinished.',
        'Fault and auxiliary-actor composition, current compiler identity, aggregate enforcement and public qualification remain unfinished.',
        'Original private host simulation only; no physical device or live inference.',
        'No live HMS changes or extension of historical full748 regression.']})
print(json.dumps({'attemptFiles':len(before),'scratchFiles':len(scratch_rows),'executionRecords':records,
    'configurationRecords':configuration_records,'configurationSnapshots':configuration_snapshots,
    'checkpoints':checkpoint_count,'finalTables':45*29+390}))

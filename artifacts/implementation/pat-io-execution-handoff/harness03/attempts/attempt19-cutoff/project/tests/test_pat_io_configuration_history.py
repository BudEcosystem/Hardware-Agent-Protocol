"""Retained actual configurations and rehashed adversarial data, without I/O execution."""
import ast
import builtins
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical, intent_digest
from hms.pat_io_configuration_history import IoConfigurationError, SCHEMA, _configuration, inspect_configuration_history
from hms.pat_io_transcript import SCHEMAS, _read, inspect_transcript
from test_pat_io_board_history import decode_tables

FIXTURES = Path(__file__).parent/'data/io-configuration'
GPIO = 'test_configuration_gpio_retains_all_tables_and_legacy_semantics'
REOPEN = 'test_configuration_reopen_retains_session_and_epoch_changes'
REVOKED = 'test_configuration_revoked_grant_after_admission_prevents_effect'
REPEAT = 'test_configuration_unchanged_pages_and_resolver_are_reused'


def load(name=GPIO):
    fixture, = [f for f in json.loads((FIXTURES/'index.json').read_bytes())['fixtures'] if f['method']==name]
    directory = FIXTURES/name; manifest = json.loads((directory/'manifest.json').read_bytes())
    files = {r['path']:(directory/'records'/r['path']).read_bytes() for r in manifest['records']}
    cfg = {r['path']:(directory/'configuration'/r['path']).read_bytes() for r in manifest['configuration']['records']}
    return dict(references=manifest['records'],files=files,configuration=manifest['configuration'],configuration_files=cfg,
        expected_setup={json.loads(files[r['path']])['kind']:json.loads(files[r['path']])['value'] for r in manifest['records'][:4]},
        expected_authority=fixture['expectedAuthority'])


def rewrite(name=GPIO, *, mutate=lambda value,tables,resolver:None, legacy=lambda value,tables:None, edit=lambda doc:None):
    """Data-only canonical page/reference reconstruction; no producer imports."""
    case = load(name); original = {r['path']:json.loads(case['files'][r['path']]) for r in case['references']}
    def writer(profile):
        refs, files, cache = [], {}, {}
        def add(kind,value,reuse=False):
            doc = {'profile':profile,'kind':kind,'value':value}; edit(doc)
            raw = canonical(doc); sha = hashlib.sha256(raw).hexdigest()
            if reuse and sha in cache: return copy.deepcopy(cache[sha])
            path = '%06d.json'%len(refs); ref = {'path':path,'bytes':len(raw),'sha256':sha}
            files[path]=raw; refs.append(ref)
            if reuse: cache[sha]=ref
            return copy.deepcopy(ref)
        return refs,files,add
    refs, files, add = writer('hms.pat.io-trial-record/0.1'); cp_mapping = {}
    for ref in case['references']:
        doc = copy.deepcopy(original[ref['path']]); kind,value = doc['kind'],doc['value']
        if kind=='table_page': continue
        if kind=='checkpoint':
            tables = decode_tables(original,value); legacy(value,tables)
            for table in value['tables']:
                fields,types,_,_ = SCHEMAS[table['store']][table['table']]; columns=fields.split(','); types=types.split()
                rows=tables[table['table']]
                rows.sort(key=lambda r:tuple((0,0) if r[c] is None else (1,r[c]) if type(r[c]) is int else (3 if t.startswith('b') else 2,r[c].encode()) for c,t in zip(columns,types)))
                table['rowCount']=len(rows); table['pages']=[]
                for offset in range(0,max(1,len(rows)),8):
                    cells=[[{'type':'null' if r[c] is None else {'t':'text','i':'integer','b':'blob-utf8'}[t[0]],'value':r[c]} for c,t in zip(columns,types)] for r in rows[offset:offset+8]]
                    table['pages'].append(add('table_page',{'store':table['store'],'table':table['table'],'columns':columns,'first':offset,'totalRows':len(rows),'rows':cells},True))
        elif kind=='trial_observation':
            value.update(evidenceRecords=len(refs),evidenceBytes=sum(r['bytes'] for r in refs))
        new_ref=add(kind,value)
        if kind=='checkpoint': cp_mapping[ref['path']]=new_ref
    old_config={r['path']:json.loads(case['configuration_files'][r['path']]) for r in case['configuration']['records']}
    c_refs,c_files,c_add=writer('hms.pat.io-configuration-record/0.1'); pairs=[]
    header=copy.deepcopy(old_config['000000.json']['value']); header['setupRecords']=refs[:4]; c_add('header',header)
    for ref in case['configuration']['records']:
        doc=old_config[ref['path']]
        if doc['kind']!='snapshot': continue
        value=copy.deepcopy(doc['value']); tables=decode_tables(old_config,value)
        resolver=copy.deepcopy(old_config[value['resolver']['path']]['value']); mutate(value,tables,resolver)
        value['checkpoint']=cp_mapping[value['checkpoint']['path']]
        value['resolver']=c_add('resolver_configuration',resolver,True)
        for table in value['tables']:
            fields,types,_,_=SCHEMA[table['table']]; columns=fields.split(','); types=types.split(); rows=tables[table['table']]
            rows.sort(key=lambda r:tuple(r[c] for c in columns)); table['rowCount']=len(rows); table['pages']=[]
            for offset in range(0,max(1,len(rows)),8):
                cells=[[{'type':t,'value':r[c]} for c,t in zip(columns,types)] for r in rows[offset:offset+8]]
                table['pages'].append(c_add('table_page',{'table':table['table'],'projection':table['projection'],
                    'columns':columns,'first':offset,'totalRows':len(rows),'rows':cells},True))
        new_ref=c_add('snapshot',value); pairs.append({'checkpoint':value['checkpoint'],'configuration':new_ref})
    case.update(references=refs,files=files,configuration_files=c_files)
    case['configuration'].update(records=c_refs,snapshots=pairs,configurationBytes=sum(r['bytes'] for r in c_refs),
        combinedRecords=len(refs)+len(c_refs),combinedBytes=sum(r['bytes'] for r in refs+c_refs))
    return case


def blob(row, change):
    value=json.loads(row['document']); change(value); row['document']=canonical(value).decode()


class IoConfigurationHistoryTests(unittest.TestCase):
    def rejected(self, case, code, *, structural=True):
        transcript=_read(case['references'],case['files'],case['expected_setup'])
        if structural: _configuration(transcript,case['references'],case['files'],case['configuration'],case['configuration_files'])
        with self.assertRaises(IoConfigurationError) as caught: inspect_configuration_history(**case)
        self.assertEqual(caught.exception.code,'PAT_IO_CONFIGURATION_'+code)

    def test_all_twelve_actual_trials_match_trusted_configuration_and_permissions(self):
        totals=dict(namespaces=0,parents=0,parentSteps=0,admissions=0,dispatches=0,parentRefusals=0,dispatchRefusals=0)
        snapshots=records=0
        for fixture in json.loads((FIXTURES/'index.json').read_bytes())['fixtures']:
            with self.subTest(method=fixture['method']):
                result=inspect_configuration_history(**load(fixture['method']))
                for flag in ('configurationHistoryChecked','trustedGrantPlanMatched','authorizationDecisionsChecked'): self.assertTrue(result[flag])
                for flag in ('configurationAttested','compilerIdentityAttested','observationSampleSemanticsChecked','activeRevocationChecked','operationHistoryChecked','procedureHistoryChecked','boardHistoryChecked','independentOutcomeChecked','qualificationPassed'): self.assertFalse(result[flag])
                for key in totals: totals[key]+=result['decisions'][key]
                snapshots+=result['configurationSnapshots']; records+=result['configurationRecords']
        self.assertEqual((snapshots,records),(206,504))
        self.assertEqual(totals,dict(namespaces=12,parents=11,parentSteps=27,admissions=21,dispatches=20,parentRefusals=1,dispatchRefusals=1))

    def test_data_rewriter_preserves_both_original_streams(self):
        before,after=load(),rewrite()
        for key in ('references','files','configuration','configuration_files'): self.assertEqual(before[key],after[key])

    def test_grants_cannot_authorize_themselves_without_trusted_input(self):
        case=load(); case['expected_authority']['initialGrants']=[]
        self.rejected(case,'GRANTS')

    def test_unchanged_admin_grant_cannot_hide_expected_revocation(self):
        case=rewrite(REVOKED,mutate=lambda v,t,r:t.update(reg_grants=load()['expected_authority']['initialGrants']))
        self.rejected(case,'GRANTS')

    def test_matching_claimed_grants_still_cannot_issue_unauthorized_namespace(self):
        case=rewrite(mutate=lambda v,t,r:t.update(reg_grants=[])); case['expected_authority']['initialGrants']=[]
        self.rejected(case,'NAMESPACE_AUTHORIZATION')

    def test_invoke_grant_does_not_replace_required_read_permission(self):
        grants=[dict(principal='pat-io-trial-worker',deployment='simulation:io-hub',target='*',verb='namespace'),
                dict(principal='pat-io-trial-worker',deployment='simulation:io-hub',target='sim:gpio5',verb='invoke:gpio_pulse')]
        case=rewrite(mutate=lambda v,t,r:t.update(reg_grants=copy.deepcopy(grants))); case['expected_authority']['initialGrants']=grants
        self.rejected(case,'PARENT_AUTHORIZATION')

    def test_read_grant_does_not_replace_action_permission(self):
        grants=[dict(principal='pat-io-trial-worker',deployment='simulation:io-hub',target='*',verb='namespace'),
                dict(principal='pat-io-trial-worker',deployment='simulation:io-hub',target='sim:gpio5',verb='read')]
        case=rewrite(mutate=lambda v,t,r:t.update(reg_grants=copy.deepcopy(grants))); case['expected_authority']['initialGrants']=grants
        self.rejected(case,'PARENT_AUTHORIZATION')

    def test_grant_change_requires_prior_administrator_authority(self):
        grants=[dict(principal='pat-io-trial-worker',deployment='simulation:io-hub',target=target,verb=verb) for target,verb in
                [('*','namespace'),('sim:gpio5','read'),('sim:gpio5','invoke:gpio_pulse')]]
        case=rewrite(REVOKED,mutate=lambda v,t,r:t.update(reg_grants=copy.deepcopy(grants)) if v['phase']<4 else None)
        case['expected_authority']['initialGrants']=grants
        self.rejected(case,'GRANT_CHANGE_AUTHORIZATION')

    def test_unobserved_trusted_grant_change_does_not_silently_pass(self):
        case=load(); case['expected_authority']['grantChanges']=[{'phase':999,'label':'drive:cycle:before','grants':[]}]
        self.rejected(case,'GRANT_PLAN')

    def test_duplicate_grant_rows_refuse_after_rehash(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_grants'].append(copy.deepcopy(t['reg_grants'][0]))),'ROW_ORDER',structural=False)

    def test_wrong_registry_revision_refuses(self):
        def change(v,t,r):
            next(row for row in t['reg_meta'] if row['key']=='revision')['value']='999'
        self.rejected(rewrite(mutate=change),'REGISTRY_META')

    def test_cursor_key_cannot_be_added_to_public_projection(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_meta'].append({'key':'cursor_key','value':'synthetic-secret'})),'INTEGER',structural=False)

    def test_retired_instance_is_not_a_current_installation(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_instances'][0].update(retired=1)),'INSTANCE')

    def test_invented_instance_identity_refuses(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_instances'][0].update(identity_ref='unrelated:identity')),'INSTANCE')

    def test_missing_capability_refuses(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_capabilities'].pop()),'CAPABILITIES')

    def test_missing_resource_requirement_refuses(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_resource_requirements'].pop()),'RESOURCE_REQUIREMENTS')

    def test_binding_route_cannot_change_with_consistent_history_hash(self):
        def change(v,t,r):
            target=t['reg_bindings'][0]['instance']
            for row in t['reg_bindings']+t['reg_binding_history']:
                if row['instance']==target:
                    blob(row,lambda b:b.update(adapterId='io:routeB'))
                    if 'digest' in row: row['digest']=hashlib.sha256(row['document'].encode()).hexdigest()
        self.rejected(rewrite(mutate=change),'BINDING')

    def test_binding_history_cannot_be_missing(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_binding_history'].pop()),'BINDING_HISTORY')

    def test_configuration_change_during_execution_is_not_requalified(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_bindings'][0].update(active=0) if v['phase']>=3 else None),'IMMUTABLE_CONFIGURATION')

    def test_type_contract_hash_does_not_authorize_different_effect_semantics(self):
        def change(v,t,r):
            row=t['reg_types'][0]; old=row['digest']; blob(row,lambda b:next(iter(b['execution']['actions'].values())).update(effect='unreviewed:effect'))
            row['digest']='sha256:'+hashlib.sha256(b'HMS-TYPE-BUNDLE-v0.1\0'+row['document'].encode()).hexdigest()
            for instance in t['reg_instances']:
                if instance['type_digest']==old: instance['type_digest']=row['digest']
        self.rejected(rewrite(mutate=change),'TYPE')

    def test_unready_route_refuses(self):
        self.rejected(rewrite(legacy=lambda v,t:t['rt_adapters'][0].update(ready=0)),'ROUTES')

    def test_changed_generation_token_refuses(self):
        self.rejected(rewrite(legacy=lambda v,t:t['rc_tokens'][0].update(generation='generation:2')),'GENERATIONS')

    def test_changed_resource_proof_binding_hash_refuses(self):
        self.rejected(rewrite(legacy=lambda v,t:t['rc_proofs'][0].update(binding_digest='a'*64)),'PROOFS')

    def test_resolver_metadata_cannot_change_with_recomputed_registration_identity(self):
        def change(v,t,r):
            r['registrations'][0]['argumentMetadata']['gpio_pulse']['durationMs']['unit']='s'
            registration=r['registrations'][0]
            identity={'profile':r['resolverProfile'],'installationDigest':registration['installationDigest'],'driverDigest':registration['driverDigest'],'registrations':r['registrations']}
            r['registrationIdentity']='sha256:'+hashlib.sha256(b'HMS-PAT-IO-BINDING-REGISTRATIONS-v1\0'+canonical(identity)).hexdigest()
        self.rejected(rewrite(mutate=change),'RESOLVER')

    def test_missing_session_history_refuses(self):
        self.rejected(rewrite(REOPEN,mutate=lambda v,t,r:t['reg_session_history'].pop()),'SESSION_HISTORY')

    def test_presence_cannot_claim_another_route(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_presence'][0].update(adapter='io:routeB')),'PRESENCE')

    def test_presence_expiry_must_match_retained_sample_clock(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_presence'][0].update(expires_ms=1000000)),'PRESENCE')

    def test_observation_source_is_bound_to_the_installed_route(self):
        self.rejected(rewrite(mutate=lambda v,t,r:blob(t['reg_observations'][0],lambda b:b.update(source='other:source'))),'OBSERVATION_PROVENANCE')

    def test_missing_observation_refuses(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_observations'].pop()),'OBSERVATION_INVENTORY')

    def test_invented_stream_history_refuses(self):
        self.rejected(rewrite(mutate=lambda v,t,r:t['reg_stream_history'].append({'instance':'sim:gpio5','property':'value','epoch':'unused:stream'})),'STREAM_HISTORY')

    def test_same_sequence_cannot_acquire_a_new_payload(self):
        def change(v,t,r):
            if v['label']=='lower:before':
                for row in t['reg_observations']: blob(row,lambda b:(b['receipt'].update(ticksMs=999999),b['acquisition'].update(ticksMs=999999)))
                for row in t['reg_presence']: row['expires_ms']=1002999
        self.rejected(rewrite(mutate=change),'OBSERVATION_ORDER')

    def test_operation_principal_must_match_trusted_actor(self):
        self.rejected(rewrite(legacy=lambda v,t:[r.update(principal='other:actor') for r in t['operations']]),'PRINCIPAL')

    def test_admission_uses_the_captured_registry_revision(self):
        def change(v,t):
            for row in t['operations']:
                admission=json.loads(row['admission']); admission['policy_revision']='registry:999'; row['admission']=canonical(admission).decode()
        self.rejected(rewrite(legacy=change),'ADMISSION_REVISION')

    def test_possible_execution_cannot_omit_dispatch_authorization_link(self):
        self.rejected(rewrite(legacy=lambda v,t:t.update(io_dispatch_links=[])),'DISPATCH_LINK')

    def test_operation_cannot_change_authorized_intent_after_admission(self):
        def change(v,t):
            if v['phase']>=4:
                for row in t['operations']:
                    intent=json.loads(row['intent']); intent['arguments']['durationMs']=2
                    row['intent']=canonical(intent).decode(); row['digest']=intent_digest(intent)
        self.rejected(rewrite(legacy=change),'DECISION_CHANGED')

    def test_admission_requires_current_endpoint_session(self):
        def change(v,t):
            for row in t['operations']:
                intent=json.loads(row['intent']); intent['endpointSession']='wrong:session'; row['intent']=canonical(intent).decode(); row['digest']=intent_digest(intent)
        self.rejected(rewrite(legacy=change),'LIVE_BINDING')

    def test_permission_refusal_cannot_be_attributed_to_another_cause(self):
        def change(v,t):
            for row in t['events']:
                if row['kind']=='rejected_before_dispatch': row['payload']=canonical({'reason':'START_DEADLINE'}).decode()
        self.rejected(rewrite(REVOKED,legacy=change),'REFUSAL_CAUSE')

    def test_permission_refusal_cannot_hide_possible_execution(self):
        def change(v,t):
            for row in t['operations']:
                if row['state']=='rejected_before_dispatch': row['may_have_acted']=1
        self.rejected(rewrite(REVOKED,legacy=change),'REFUSAL_EFFECT')

    def test_identical_final_recaptures_are_structurally_accepted(self):
        case=load(REPEAT)
        self.assertTrue(inspect_transcript(case['references'],case['files'],expected_setup=case['expected_setup'])['serializationChecked'])
        self.assertTrue(inspect_configuration_history(**case)['configurationHistoryChecked'])

    def test_changed_configuration_between_final_recaptures_refuses(self):
        seen=[]
        def change(v,t,r):
            if v['label']=='test_final':
                seen.append(1)
                if len(seen)==2:
                    for row in t['reg_observations']: blob(row,lambda b:b.update(sequence=b['sequence']+1))
        self.rejected(rewrite(REPEAT,mutate=change),'FINAL_CHANGED')

    def test_changed_execution_between_final_recaptures_refuses(self):
        seen=[]
        def change(v,t):
            if v['label']=='test_final':
                seen.append(1)
                if len(seen)==2: t['io_effects'][0]['activations']+=1
        case=rewrite(REPEAT,legacy=change)
        with self.assertRaisesRegex(IoConfigurationError,'PAT_IO_CONFIGURATION_TRANSCRIPT'): inspect_configuration_history(**case)

    def test_configuration_cells_keep_their_sqlite_type(self):
        def edit(doc):
            if doc['profile']=='hms.pat.io-configuration-record/0.1' and doc['kind']=='table_page' and doc['value']['table']=='reg_types': doc['value']['rows'][0][1]['type']='text'
        self.rejected(rewrite(edit=edit),'CELL',structural=False)

    def test_snapshot_cannot_reference_a_future_page(self):
        def edit(doc):
            if doc['kind']=='snapshot': doc['value']['tables'][0]['pages'][0]['path']='999999.json'
        self.rejected(rewrite(edit=edit),'REFERENCE',structural=False)

    def test_combined_record_limit_is_checked_before_configuration_decode(self):
        case=load(); count=4097-len(case['references']); raw=next(iter(case['configuration_files'].values()))
        case['configuration']['records']=[{'path':'%06d.json'%i,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for i in range(count)]
        case['configuration_files']={r['path']:raw for r in case['configuration']['records']}
        self.rejected(case,'BOUNDS',structural=False)

    def test_combined_byte_limit_is_checked_before_configuration_decode(self):
        case=load(); raw=b' '*65536
        case['configuration']['records']=[{'path':'%06d.json'%i,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for i in range(256)]
        case['configuration_files']={r['path']:raw for r in case['configuration']['records']}
        self.rejected(case,'BOUNDS',structural=False)

    def test_public_flags_cannot_claim_qualification(self):
        case=load(); case['configuration']['qualificationPassed']=True
        self.rejected(case,'MANIFEST',structural=False)

    def test_checking_is_pure_and_does_not_mutate_acquired_input(self):
        case=load(); before=copy.deepcopy(case)
        with patch.object(builtins,'open',side_effect=AssertionError('file I/O')), patch.object(Path,'read_bytes',side_effect=AssertionError('file I/O')), patch.object(sqlite3,'connect',side_effect=AssertionError('SQL')), patch.object(time,'monotonic',side_effect=AssertionError('clock')):
            self.assertTrue(inspect_configuration_history(**case)['configurationHistoryChecked'])
        self.assertEqual(case,before)

    def test_checker_imports_only_contracts_and_independent_readers(self):
        path=Path(__file__).parents[1]/'hms/pat_io_configuration_history.py'
        tree=ast.parse(path.read_text()); imports={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
        self.assertEqual(imports,{'__future__','contracts','pat_io_correspondence','pat_io_board_history','pat_io_transcript','resource_topology'})
        self.assertEqual({a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names},{'hashlib','re'})

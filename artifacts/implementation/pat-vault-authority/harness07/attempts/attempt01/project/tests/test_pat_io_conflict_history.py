"""Retained original-runtime probes and independently rehashed false claims."""
import builtins
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from hms.pat_contracts import PatError
from hms.pat_io_conflict_capture import ConflictIoTrialEngine
from hms.pat_io_conflict_history import inspect_conflict_history
from hms.pat_io_configuration_history import _validated_configuration_history
from hms.pat_io_procedure_history import _fold as procedures
from hms.pat_io_transcript import _read
from test_pat_io_configuration_capture import IoConfigurationCaptureTests
from test_pat_io_contracts import program, descriptor


def rewrite(case, edit):
    """Rehash all execution/configuration associations after a data-only edit."""
    case = copy.deepcopy(case)
    def remap(value, mapping):
        if type(value) is dict:
            if set(value) == {'path', 'bytes', 'sha256'} and value['path'] in mapping:
                return copy.deepcopy(mapping[value['path']])
            return {k: remap(v, mapping) for k, v in value.items()}
        if type(value) is list: return [remap(v, mapping) for v in value]
        return value
    def stream(refs, files, *, configuration=False):
        result, output, mapping = [], {}, {}
        for ref in refs:
            original = json.loads(files[ref['path']]); doc = remap(original, mapping)
            if configuration and doc['kind'] == 'header':
                doc['value']['setupRecords'] = [execution[r['path']] for r in original['value']['setupRecords']]
            if configuration and doc['kind'] == 'snapshot':
                doc['value']['checkpoint'] = execution[original['value']['checkpoint']['path']]
            edit(doc)
            if doc['kind'] == 'trial_observation':
                doc['value'].update(evidenceRecords=len(result), evidenceBytes=sum(r['bytes'] for r in result))
            body = canonical(doc); name = '%06d.json' % len(result)
            new = dict(path=name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            mapping[ref['path']] = new; result.append(new); output[name] = body
        return result, output, mapping
    refs, files, execution = stream(case['references'], case['files'])
    cr, cf, _ = stream(case['configuration']['records'], case['configuration_files'], configuration=True)
    pairs = [dict(checkpoint=json.loads(cf[r['path']])['value']['checkpoint'], configuration=r)
             for r in cr if json.loads(cf[r['path']])['kind'] == 'snapshot']
    case.update(references=refs, files=files, configuration_files=cf)
    case['configuration'].update(records=cr, snapshots=pairs, configurationBytes=sum(r['bytes'] for r in cr),
        combinedRecords=len(refs)+len(cr), combinedBytes=sum(r['bytes'] for r in refs+cr))
    return case


class IoConflictHistoryTests(IoConfigurationCaptureTests):
    def make(self, *, count=1, pwm=False, submit=True, duty=None, level=None):
        directory = self.workspace/'trial-0'; directory.mkdir(mode=0o700)
        artifact = program(count=count, pwm=pwm)
        if duty is not None: artifact['steps'][0]['arguments']['dutyPermille'] = {'literal': duty}
        if level is not None: artifact['steps'][0]['arguments']['level'] = {'literal': level}
        engine = ConflictIoTrialEngine(directory, artifact, self.document, descriptor(self.document, pwm=pwm))
        self.engines.append(engine); engine.lower({'duration': 20})
        if submit: engine.submit()
        return engine

    def probe(self, engine):
        original = copy.deepcopy(engine.plan); parent = engine.procedure_id
        before = engine.status(); effects = [tuple(r) for r in engine.runtime.io_board.db.execute('SELECT * FROM io_effects ORDER BY instance')]
        self.assertEqual(engine.submit(), before)
        with self.assertRaisesRegex(JournalError, '^KEY_CONFLICT$'): engine.submit_conflict()
        self.assertEqual(engine.plan, original); self.assertEqual(engine.procedure_id, parent)
        self.assertEqual(engine.status(), before)
        self.assertEqual([tuple(r) for r in engine.runtime.io_board.db.execute('SELECT * FROM io_effects ORDER BY instance')], effects)
        records = len(engine.records); config = engine.configuration_manifest()
        with self.assertRaisesRegex(PatError, 'PAT_IO_CONFLICT_ALREADY_ATTEMPTED'): engine.submit_conflict()
        self.assertEqual(len(engine.records), records); self.assertEqual(engine.configuration_manifest(), config)

    def retain_and_close(self):
        super().retain_and_close()
        for index, engine in enumerate(self.engines):
            owner = engine.owner
            authority = getattr(self, 'authority_plan', None) or {
                'profile':'hms.pat.io-trusted-authority/0.1','principal':owner.principal,'deployment':owner.deployment,
                'initialRegistryRevision':13,'initialGrants':[{'principal':owner.principal,'deployment':owner.deployment,'target':'*','verb':'admin'}],
                'grantChanges':[]}
            case = dict(references=engine.records,
                files={r['path']:(engine.record_directory/r['path']).read_bytes() for r in engine.records},
                configuration=engine.configuration_manifest(),
                configuration_files={r['path']:(engine.directory/'configuration'/r['path']).read_bytes() for r in engine.configuration_records},
                expected_setup=dict(artifact=engine.artifact, installation=engine.document,
                    original_descriptor=engine.original_descriptor, static_contract=engine.contract), expected_authority=authority)
            result = inspect_conflict_history(**case)
            self.assertTrue(result['sameKeyConflictChecked']); self.assertTrue(result['exactReplayChecked'])
            self.assertEqual(len(result['conflictsChecked']), 1); self.assertFalse(result['qualificationPassed'])
            self.assertFalse(result['independentOutcomeChecked'])
            # Older public readers and the standalone parent fold cannot treat
            # the new phase as a proved refusal just because its code matches.
            with self.assertRaises(ValueError): _read(case['references'], case['files'], case['expected_setup'])
            transcript = _read(case['references'], case['files'], case['expected_setup'], conflict_profile=True)
            with self.assertRaisesRegex(ValueError, 'PAT_IO_PROCEDURE_CONFLICT_CAUSE'): procedures(transcript)
            if getattr(self, 'attack_checks', False): self.attacks(case)
            path = self.workspace/('engine-%d.json' % index); manifest = json.loads(path.read_bytes())
            manifest.update(expectedAuthority=authority, independentConflictInspection=result,
                            rehashedRefusals=15 if getattr(self, 'attack_checks', False) else 0,
                            privateGuardChecks=2 if getattr(self, 'attack_checks', False) else 0,
                            purityChecked=getattr(self, 'attack_checks', False))
            path.write_text(json.dumps(manifest, indent=2)+'\n')

    def attacks(self, case):
        def request_edit(change):
            def edit(doc):
                if doc['kind'] != 'conflict_input': return
                value = doc['value']; change(value['request'])
                value['requestDigest'] = 'sha256:'+hashlib.sha256(b'HMS-PROCEDURE-JCS-SHA256-v0.1\0'+canonical(value['request'])).hexdigest()
            return edit
        original = next(json.loads(v)['value']['request'] for v in case['files'].values() if json.loads(v)['kind']=='compiled_plan')
        changes = [
            lambda r: r.update(procedureKey='new:parent'),
            lambda r: r.update(replayNamespace='replay:foreign:1:key'),
            lambda r: r['procedure']['steps'][0]['request'].update(operationKey='new:child'),
            lambda r: r['procedure']['steps'][0]['request']['intent'].update(instanceId='sim:other'),
            lambda r: r['procedure']['steps'][0]['request']['intent']['arguments'].update(durationMs=21),
            lambda r: r['procedure']['steps'][0]['request']['intent']['arguments'].update(level=1),
            lambda r: r['procedure']['timing'].update(latestStartUnixMs=1000499),
            lambda r: r.update(extra=True),
        ]
        edits = [request_edit(c) for c in changes]
        for field, value in [('requestDigest','sha256:'+'0'*64), ('phase',1), ('extra',True)]:
            edits.append(lambda d,k=field,v=value: d['value'].update({k:v}) if d['kind']=='conflict_input' else None)
        for field,value in [('code','ACCESS_DENIED'),('code','INVALID_REPLAY_NAMESPACE'),('exception','PatError')]:
            edits.append(lambda d,k=field,v=value: d['value'].update({k:v}) if d['kind']=='call_failed' and d['value']['label']=='submit_conflict' else None)
        for edit in edits:
            with self.subTest(edit=edits.index(edit)):
                attacked = rewrite(case, edit)
                with self.assertRaises(ValueError): inspect_conflict_history(**attacked)
        # 15 rehashed attacks, two private-guard checks, and a purity check.
        with self.assertRaises(ValueError): inspect_conflict_history(**rewrite(case, lambda d: d.update(profile='hms.pat.io-trial-record/0.1') if d['profile']=='hms.pat.io-trial-record/0.2' else None))
        transcript,snapshots,permissions,_,_ = _validated_configuration_history(case['references'],case['files'],case['configuration'],case['configuration_files'],expected_setup=case['expected_setup'],expected_authority=case['expected_authority'],conflict_profile=True)
        from hms.pat_io_conflict_history import _probes
        denied = copy.deepcopy(permissions)
        for value in denied.values(): value['read'] = False
        with self.assertRaisesRegex(ValueError, 'READ_PRECEDENCE'): _probes(transcript,snapshots,denied,case['expected_setup'],case['expected_authority'])
        with self.assertRaisesRegex(ValueError, 'CONFLICT_CAUSE'): procedures(transcript, checked_conflicts={0:'KEY_CONFLICT'})
        def veto(*args, **kwargs): raise AssertionError('pure checker performed I/O or read a clock')
        with patch.object(builtins,'open',veto), patch.object(Path,'open',veto), patch.object(sqlite3,'connect',veto), patch.object(time,'time',veto), patch.object(time,'monotonic',veto):
            self.assertTrue(inspect_conflict_history(**case)['sameKeyConflictChecked'])
        self.assertEqual(original['procedureKey'], 'trial:parent')

    def test_conflict_gpio_accepted_preserves_multistep_request(self):
        engine = self.make(count=2); self.probe(engine)
        self.assertEqual(engine.finish()['executionState'], 'completed'); self.assertEqual(self.effects(engine),(2,2,0))

    def test_conflict_pwm_pending_keeps_claims_and_one_activation(self):
        engine = self.make(pwm=True); engine.drive('procedure'); engine.drive('adapters')
        claims = copy.deepcopy(engine.operations()[0]['claims']); self.probe(engine)
        self.assertEqual(engine.operations()[0]['claims'], claims)
        self.assertEqual(engine.finish()['executionState'], 'completed'); self.assertEqual(self.effects(engine,'sim:pwm5'),(1,1,0))

    def test_conflict_gpio_completed_rejects_rehashed_false_claims(self):
        engine = self.make(); engine.finish(); self.probe(engine); self.attack_checks = True
        self.assertEqual(self.effects(engine),(1,1,0))

    def test_conflict_pwm_wraps_duty_at_installed_maximum(self):
        engine = self.make(pwm=True,duty=1000); engine.finish(); self.probe(engine)
        self.assertEqual(self.effects(engine,'sim:pwm5'),(1,1,0))

    def test_conflict_gpio_zero_level_uses_other_valid_level(self):
        engine = self.make(level=0); engine.finish(); self.probe(engine)
        self.assertEqual(self.effects(engine),(1,1,0))

    def test_conflict_canceled_parent_does_not_start_children(self):
        engine = self.make(); engine.cancel(); engine.finish(); self.probe(engine)
        self.assertEqual(engine.status()['executionState'],'canceled'); self.assertEqual(self.effects(engine),(0,0,0))

    def test_conflict_completed_reopen_preserves_original_namespace(self):
        engine = self.make(); engine.finish(); old = engine.runtime.io_board.session; engine.reopen()
        self.assertNotEqual(old,engine.runtime.io_board.session); self.probe(engine)
        self.assertEqual(self.effects(engine),(1,1,0))

    def test_conflict_replay_after_namespace_wall_expiry_without_pruning(self):
        engine = self.make(submit=False); before = len(engine.records)
        with self.assertRaisesRegex(PatError,'PAT_IO_CONFLICT_NOT_SUBMITTED'): engine.submit_conflict()
        self.assertEqual(len(engine.records),before)
        engine.submit(); engine.finish()
        expiry = engine.runtime.journal._db.execute('SELECT expires_ms FROM namespaces').fetchone()[0]
        engine.advance_to(expiry+1); self.probe(engine); self.assertEqual(self.effects(engine),(1,1,0))

    def test_conflict_read_retained_invoke_withdrawn_still_conflicts(self):
        engine = self.make(); engine.finish(); owner=engine.owner
        self.authority_plan = {'profile':'hms.pat.io-trusted-authority/0.1','principal':owner.principal,'deployment':owner.deployment,
            'initialRegistryRevision':13,'initialGrants':[{'principal':owner.principal,'deployment':owner.deployment,'target':'*','verb':'admin'}],
            'grantChanges':[{'phase':engine.phase+1,'label':'submit:before','grants':[{'principal':owner.principal,'deployment':owner.deployment,'target':'sim:gpio5','verb':'read'}]}]}
        self.revoke_invoke(engine); self.probe(engine); self.assertEqual(self.effects(engine),(1,1,0))

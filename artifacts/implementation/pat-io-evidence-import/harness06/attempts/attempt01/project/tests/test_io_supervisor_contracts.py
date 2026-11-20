"""I/O supervisor carriers and protected file transport, without SQL or spawn."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'supervisor'))
from hms.contracts import canonical
from hms.pat_io_run_bundle import prepare_io_run_bundle
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_combined_matrix import bindings
from test_pat_io_contracts import program
from test_pat_io_group_history import authority
import supervisor_contracts as contracts
import bundle_io
import qualification_supervisor as supervision


class IoSupervisorContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        document=normalize_installation(installation()); selected=bindings(document)
        cls.context=dict(deployment=document['topology']['deployment'],evaluatorId='eval:supervised-io',runId='run:gpio',
            configurationDigest='sha256:'+'6'*64,configurationRevision=1)
        cls.options=dict(candidate=program(literal=True),installation=document,descriptor=selected['gpio']['descriptor'],
            challenge_bindings=selected,authority=authority(document))
        cls.bundle=prepare_io_run_bundle(context=cls.context,**cls.options)
        cls.request=contracts.prepare_request(cls.bundle,context=cls.context)

    def root(self,label='root'):
        parent=Path(os.environ['TMPDIR'])/self._testMethodName
        parent.mkdir(mode=0o700)
        p=parent/label; p.mkdir(mode=0o700); return p

    def retained(self):
        root=self.root(); fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        self.addCleanup(os.close,fd)
        bundle_io.retain_bundle(fd,self.request,self.bundle)
        return root,fd

    def test_request_is_bounded_detached_and_pure_replay_does_not_read_sources(self):
        self.assertLessEqual(len(canonical(self.request)),65536)
        with patch.object(contracts,'supervisor_identity',side_effect=AssertionError('identity')), \
             patch.object(sqlite3,'connect',side_effect=AssertionError('SQL')):
            parsed=contracts.parse_request(self.request)
        parsed['context']['runId']='changed'
        self.assertEqual(self.request['context'],self.context)
        self.assertEqual(contracts.run_key(self.request),(self.context['deployment'],self.context['evaluatorId'],self.context['runId']))

    def test_request_refuses_float_bool_context_and_malformed_header(self):
        variants=[]
        for field,value in [('maxArchives',True),('maxFilesPerAttempt',8193),('maxRetainedBytes',256*1024*1024+1)]:
            changed=copy.deepcopy(self.request);changed['limits'][field]=value;variants.append(changed)
        for value in (True,1.0):
            changed=copy.deepcopy(self.request);changed['context']['configurationRevision']=value;variants.append(changed)
        for field,value in [('manifest',[]),('caseIds',[]),('inputBytes',True)]:
            changed=copy.deepcopy(self.request);changed['bundleHeader'][field]=value
            changed['bundleDigest']=contracts.bundle_digest(canonical(changed['bundleHeader']));variants.append(changed)
        changed=copy.deepcopy(self.request);changed['extra']=True;variants.append(changed)
        for value in variants:
            with self.assertRaises((contracts.SupervisorError,ValueError)): contracts.parse_request(value)

    def test_request_reservation_accounts_for_input_documents_output_and_control(self):
        lower=contracts.DEFAULT_LIMITS|dict(attemptReservationBytes=20*1024*1024)
        with self.assertRaisesRegex(contracts.SupervisorError,'RESERVATION_TOO_SMALL'):
            contracts.prepare_request(self.bundle,context=self.context,limits=lower)
        self.assertEqual(self.request['limits'],contracts.DEFAULT_LIMITS)
        self.assertEqual(self.request['groupLimits']['maxWallMs'],60000)

    def test_changed_bundle_or_supervisor_source_cannot_pass_fresh_validation(self):
        changed=copy.deepcopy(self.bundle);changed['documents']['cases/00.json']=b'{}'
        with self.assertRaises((contracts.SupervisorError,ValueError)):contracts.validate_fresh(self.request,changed)
        with patch.object(contracts,'_IMPORTED_SOURCES',[]):
            with self.assertRaisesRegex(contracts.SupervisorError,'IMPLEMENTATION_CHANGED'):
                contracts.validate_fresh(self.request,self.bundle)

    def test_image_includes_all_seven_dependencies_and_endpoint_manifest(self):
        self.assertEqual(set(contracts.PACKAGES),{'jsonschema','referencing','jsonschema-specifications','attrs','rpds-py','typing_extensions','idna'})
        rows=supervision._image_rows(); paths=[r[0] for r in rows]
        self.assertEqual(len(paths),len(set(paths)))
        self.assertIn('protocol/endpoint/scenario-manifest.json',paths)
        self.assertIn('supervisor/bundle_io.py',paths)
        self.assertIn('dependencies/typing_extensions.py',paths)
        self.assertIn('dependencies/idna/core.py',paths)
        for _,source,fingerprint in rows:self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),fingerprint)

    def test_retained_inputs_are_exact_private_and_durable_before_return(self):
        root=self.root();fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY);self.addCleanup(os.close,fd)
        with patch.object(bundle_io.os,'fsync',wraps=os.fsync) as sync:
            value=bundle_io.retain_bundle(fd,self.request,self.bundle)
        self.assertEqual(value,self.bundle);self.assertGreaterEqual(sync.call_count,40)
        for path in (root/'bundle').rglob('*'):
            self.assertEqual(path.stat().st_mode&0o777,0o700 if path.is_dir() else 0o600)
        with self.assertRaises(FileExistsError):bundle_io.retain_bundle(fd,self.request,self.bundle)

    def test_retained_input_extra_file_missing_file_and_tampered_bytes_refuse(self):
        root,fd=self.retained();p=root/'bundle/cases/00.json';raw=p.read_bytes();p.write_bytes(b'{}')
        with self.assertRaises(ValueError):bundle_io.load_bundle(fd,self.request)
        p.write_bytes(raw);extra=root/'bundle/extra';extra.write_bytes(b'')
        with self.assertRaisesRegex(contracts.SupervisorError,'INPUT_CLOSURE'):bundle_io.load_bundle(fd,self.request)
        # Leave the final deliberately altered fixture, including the extra file.

    def test_retained_input_permissions_and_hardlinks_refuse(self):
        root,fd=self.retained();p=root/'bundle/inputs/authority.json';p.chmod(0o644)
        with self.assertRaisesRegex(contracts.SupervisorError,'UNSAFE_FILE'):bundle_io.load_bundle(fd,self.request)
        p.chmod(0o600);other=root/'hardlink';os.link(p,other)
        with self.assertRaisesRegex(contracts.SupervisorError,'UNSAFE_FILE'):bundle_io.load_bundle(fd,self.request)

    def test_bundle_mapping_snapshot_rejects_custom_keys_before_callbacks(self):
        class Key(str):pass
        changed=copy.deepcopy(self.bundle);raw=changed['documents'].pop('inputs/authority.json')
        changed['documents'][Key('inputs/authority.json')]=raw
        with patch.object(Key,'__hash__',side_effect=AssertionError('hash')):
            with self.assertRaises(contracts.SupervisorError):contracts.snapshot_bundle(changed)
        detached=contracts.snapshot_bundle(self.bundle);detached['documents'].clear()
        self.assertEqual(len(self.bundle['documents']),37)

    def test_physical_attempt_identifier_is_distinct_from_logical_run(self):
        identifier='a'*32;launch=bundle_io.launch_input(self.request,identifier)
        self.assertEqual(launch['attemptId'],identifier)
        self.assertEqual(launch['request']['context']['runId'],'run:gpio')
        for wrong in ('../escape',self.context['runId'],True,'g'*32):
            with self.assertRaises(contracts.SupervisorError):bundle_io.launch_input(self.request,wrong)

    def test_output_transport_hashes_complete_tree_and_rejects_wrong_attempt(self):
        root,fd=self.retained();out=root/'output';out.mkdir(mode=0o700)
        for key in ('candidate','installation','descriptor','bindings','matrix','implementation'):
            p=out/(key+'.json');p.write_bytes(self.bundle['documents']['inputs/'+key+'.json']);p.chmod(0o600)
        matrix=json.loads(self.bundle['documents']['inputs/matrix.json'])
        result=dict(profile='hms.pat.io-group-capture/0.1',status='failed',matrixDigest=self.request['bundleHeader']['matrixDigest'],
            artifactDigest=matrix['artifactDigest'],identities=self.request['implementation'])
        p=out/'result.json';p.write_bytes(canonical(result));p.chmod(0o600)
        returned=dict(profile='hms.pat.io-supervisor-return/0.1',attemptId='a'*32,requestDigest=contracts.request_digest(self.request),
            bundleDigest=self.request['bundleDigest'],groupResultDigest=contracts.digest(canonical(result)),status='failed')
        first=bundle_io.output_integrity(fd,self.request,returned,'a'*32)
        self.assertEqual(first['fileCount'],7)
        p=out/'partial.bin';p.write_bytes(b'retained unfinished bytes');p.chmod(0o600)
        second=bundle_io.output_integrity(fd,self.request,returned,'a'*32)
        self.assertEqual(second['fileCount'],8);self.assertNotEqual(first['orderedDigest'],second['orderedDigest'])
        for key,value in [('attemptId','b'*32),('bundleDigest','sha256:'+'0'*64),('requestDigest','sha256:'+'0'*64)]:
            with self.assertRaisesRegex(contracts.SupervisorError,'RESULT_ASSOCIATION'):
                bundle_io.output_integrity(fd,self.request,returned|{key:value},'a'*32)
        # This synthetic malformed failed result deliberately has no case semantics.
        self.assertNotIn('semanticQualificationVerified',second)


if __name__=='__main__':unittest.main()

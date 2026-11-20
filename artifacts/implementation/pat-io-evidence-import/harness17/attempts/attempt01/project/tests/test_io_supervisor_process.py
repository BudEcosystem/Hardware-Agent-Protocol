"""One owned finite GPIO group, durable replay and independent archive reading."""
import json
import os
from pathlib import Path
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_io_group_history import inspect_io_group
from hms.pat_io_run_bundle import parse_io_run_bundle
from test_io_supervisor_contracts import IoSupervisorContractsTests, contracts, supervision, bundle_io


class IoSupervisorProcessTests(IoSupervisorContractsTests):
    def test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays(self):
        root=self.root('supervisor'); phases=[]; expected=self.bundle; request=self.request
        class Checked(supervision.QualificationSupervisor):
            def _checkpoint(inner,phase,row):
                phases.append(phase)
                if phase=='launching':
                    fd=supervision._directory(inner.ledger.fd,row['record']['attemptId'])
                    try:
                        self.assertEqual(bundle_io.load_bundle(fd,request),expected)
                        launch=contracts.document(contracts.read_file(fd,'input.json'))
                        self.assertEqual(launch,bundle_io.launch_input(request,row['record']['attemptId']))
                    finally: os.close(fd)
        service=Checked(root,create=True)
        try:
            with self.assertRaisesRegex(contracts.SupervisorError,'OWNER_BUSY'):
                supervision.QualificationSupervisor(root)
            row=service.execute(request,expected)
            self.assertEqual(row['record']['state'],'archived')
            archive=row['record']['archive'];self.assertTrue(archive['transportComplete'],archive)
            self.assertFalse(archive['semanticQualificationVerified']);self.assertFalse(archive['totalDiskQuotaEnforced'])
            self.assertIsNone(archive['unresolvedEffects'])
            returned=contracts.document(row['returnBytes']);self.assertEqual(returned['status'],'captured')
            self.assertEqual(returned['attemptId'],row['record']['attemptId'])
            self.assertEqual(phases,['admitted','launching','spawned','producer_settled','archived'])
            self.assertFalse(service._owned)
            with patch.object(supervision,'validate_fresh',side_effect=AssertionError('replay replanned')):
                self.assertEqual(service.execute(request),row)
            changed=json.loads(canonical(request));changed['limits']['maxStreamBytes']-=1
            with self.assertRaisesRegex(contracts.SupervisorError,'KEY_CONFLICT'):service.execute(changed)
            self.assertEqual(service.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(),(1,))
        finally:
            for identifier in list(service._owned):service.stop_owned(identifier)
            service.close()
        reopened=supervision.QualificationSupervisor(root)
        try:
            with patch.object(supervision,'validate_fresh',side_effect=AssertionError('reopen replay replanned')):
                self.assertEqual(reopened.execute(request),row)
        finally:reopened.close()
        output=root/row['record']['attemptId']/'output'
        files={p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()}
        parsed=parse_io_run_bundle(expected['header'],expected['documents'],expected_context=self.context,
            expected_bundle_digest=expected['bundleDigest'])
        checked=inspect_io_group(files,expected_inputs=parsed['expected_inputs'],expected_cases=parsed['expected_cases'])
        self.assertTrue(checked['summary']['independentOutcomeChecked'])
        self.assertEqual(len(checked['inspections']),30)
        self.assertFalse(checked['summary']['qualificationPassed'])
        inspection=root.parent/'inspection';inspection.mkdir(mode=0o700)
        (inspection/'summary.json').write_bytes(canonical(checked['summary']))
        for i,value in enumerate(checked['inspections']):(inspection/('case-%02d.json'%i)).write_bytes(canonical(value))
        (inspection/'supervisor-checks.json').write_bytes(canonical(dict(phases=phases,physicalAttemptId=row['record']['attemptId'],
            requestDigest=row['record']['requestDigest'],bundleDigest=expected['bundleDigest'],archive=archive,
            completeGroupCaptured=True,independentGroupInspection=True,exactReplayBeforeAndAfterReopen=True,
            changedSameKeyRefused=True,preLaunchInputsMatched=True,oneWorkerLaunched=True,qualificationPassed=False)))

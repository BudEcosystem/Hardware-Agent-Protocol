"""Pure reducer over an unchanged legacy capture, with a synthetic association.

No version2 supervisor/handoff authority or evidence-store import is claimed.
No worker is executed. The historical capture retains all30 required cases.
"""
import copy
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'supervisor'))
from hms.contracts import canonical
from hms.journal import JournalError
from evidence import archive, reducer
from evidence.contracts import identity, sha


class IoEvidenceReducerTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tests/fixtures/recorded-io-group'
        original = json.loads((self.root / 'original-row.json').read_bytes())
        self.row = dict(request=original['request'], record=original['record'],
                        returnBytes=(self.root / 'worker-return.json').read_bytes())
        self.assertEqual(canonical(original['returned']), self.row['returnBytes'])
        self.reservation = json.loads((self.root / 'run-reservation.json').read_bytes())
        bundle = dict(header=(self.root / 'bundle/header.json').read_bytes(),
            bundleDigest=self.row['request']['bundleDigest'], documents={
                path.relative_to(self.root / 'bundle').as_posix(): path.read_bytes()
                for part in ('inputs', 'cases') for path in (self.root / 'bundle' / part).iterdir()})
        self.reservation['preparedRun'] = dict(request=self.row['request'], bundle=bundle)
        saved = self.reservation['reservation']
        self.association = dict(receipt={key: saved[key] for key in ('authorityId', 'deployment', 'evaluatorId', 'runId', 'requestDigest')},
            receiptDigest='sha256:' + 'f' * 64)
        self.association['receipt'].update(reservationDigest=self.reservation['reservationDigest'],
            supervisorAuthorityId='supervisor:' + 'f' * 32, attemptId=self.row['record']['attemptId'])
        self.files = {path.relative_to(self.root / 'output').as_posix(): path.read_bytes()
                      for path in (self.root / 'output').rglob('*') if path.is_file()}
        self.consumer = identity()

    def reduce(self, row=None, files=None):
        return reducer.reduce_original(self.reservation, self.association,
            self.row if row is None else row, self.files if files is None else files, self.consumer)

    def test_complete_legacy_capture_reduces_without_claiming_new_handoff(self):
        result = self.reduce()
        self.assertEqual(result['evaluation']['inspectedCases'], 30)
        self.assertEqual(result['evaluation']['unresolvedEffects'], 0)
        self.assertFalse(result['evaluation']['physicalObjectiveVerified'])
        self.assertFalse(result['evaluation']['catalogActivated'])
        self.assertNotEqual(result['evaluation']['anchor']['producerIdentity'], self.consumer)
        output = Path(os.environ['TMPDIR']) / self._testMethodName; output.mkdir()
        (output / 'pure-reducer-result.json').write_bytes(canonical(dict(
            provenance='legacy-v1-capture-with-synthetic-association', realHandoff=False,
            workerExecuted=False, published=False, evaluation=result['evaluation'], closure=result['closure'])))
        (output / 'summary.json').write_bytes(result['documents']['inspection/summary.json'])

    def test_incomplete_group_refuses_even_with_recomputed_transport_closure(self):
        files = dict(self.files)
        name = next(name for name in sorted(files) if '/' in name and name.endswith('/manifest.json'))
        del files[name]
        row = copy.deepcopy(self.row)
        row['record']['archive']['evidenceIntegrity'] = archive.output_closure(files)
        with self.assertRaises((JournalError, ValueError)): self.reduce(row=row, files=files)

    def test_different_attempt_return_cannot_be_substituted(self):
        row = copy.deepcopy(self.row); returned = json.loads(row['returnBytes'])
        returned['attemptId'] = '0' * 32; row['returnBytes'] = canonical(returned)
        row['record']['archive']['returnDigest'] = sha(row['returnBytes'])
        with self.assertRaisesRegex(JournalError, 'RETURN'): self.reduce(row=row)

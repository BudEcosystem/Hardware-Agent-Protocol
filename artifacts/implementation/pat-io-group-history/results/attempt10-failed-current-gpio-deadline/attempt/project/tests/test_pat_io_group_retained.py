"""Inspect the retained complete source01 group with the corrected pure reader."""
import builtins
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_io_group_history import inspect_io_group, IoGroupHistoryError


class RetainedIoGroupTests(unittest.TestCase):
    def test_complete_retained_gpio_and_archive_adversaries(self):
        root = Path(__file__).parent / 'data/io-current-group'
        files = {p.relative_to(root / 'group').as_posix(): p.read_bytes()
            for p in (root / 'group').rglob('*') if p.is_file()}
        expected_inputs = {key: json.loads((root / 'requested' / (key + '.json')).read_bytes())
            for key in ('candidate', 'installation', 'descriptor', 'bindings', 'matrix', 'implementation')}
        expected_cases = [json.loads(p.read_bytes()) for p in sorted((root / 'requested').glob('case-*.json'))]
        options = dict(expected_inputs=expected_inputs, expected_cases=expected_cases)
        pins = {key: hashlib.sha256(value).hexdigest() for key, value in files.items()}
        with patch.object(builtins, 'open', side_effect=AssertionError('file I/O')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('file read')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('SQL')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            checked = inspect_io_group(files, **options)
            original = json.loads(files['result.json'])
            changed = copy.deepcopy(original); changed['accounting']['charged']['records'] += 1
            attacked = dict(files); attacked['result.json'] = canonical(changed)
            with self.assertRaisesRegex(IoGroupHistoryError, 'GROUP_ACCOUNTING'):
                inspect_io_group(attacked, **options)
            with self.assertRaisesRegex(IoGroupHistoryError, 'ARCHIVE_CLOSURE'):
                inspect_io_group(files | {'unreported.json': b'{}'}, **options)
            changed = copy.deepcopy(original)
            manifest = json.loads(files['case-00/manifest.json']); manifest['report']['schedulerTicks'] += 1
            encoded = canonical(manifest)
            changed['cases'][0]['manifest'] = dict(path='case-00/manifest.json', bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest())
            attacked = files | {'case-00/manifest.json': encoded, 'result.json': canonical(changed)}
            with self.assertRaisesRegex(IoGroupHistoryError, 'REPORT'):
                inspect_io_group(attacked, **options)
            changed_cases = copy.deepcopy(expected_cases)
            changed_cases[0]['expected_authority']['initialRegistryRevision'] += 1
            with self.assertRaises(IoGroupHistoryError):
                inspect_io_group(files, expected_inputs=expected_inputs, expected_cases=changed_cases)
        self.assertEqual(pins, {key: hashlib.sha256(value).hexdigest() for key, value in files.items()})
        summary = checked['summary']; self.assertEqual(len(checked['inspections']), 30)
        self.assertTrue(summary['requiredMatrixCoverageChecked']); self.assertTrue(summary['independentOutcomeChecked'])
        self.assertTrue(summary['archiveAccountingChecked']); self.assertTrue(summary['trustedSetupMatched'])
        for key in ('configurationAttested', 'implementationIdentityAttested', 'runAssociationAttested',
                'wallDeadlineAttested', 'actualAggregateStorageEnforced', 'physicalMeasurementChecked', 'qualificationPassed'):
            self.assertFalse(summary[key])
        self.assertEqual(summary['accounting']['actualChildOperations'], 28)
        self.assertEqual(summary['accounting']['schedulerTicks'], 99)
        self.assertTrue(checked['inspections'][0]['outcome']['nominalCompletionSatisfied'])
        self.assertEqual([r['staticOutcome'] for r in checked['inspections'][1:5]],
            ['refused', 'not_applicable', 'not_applicable', 'not_applicable'])
        directory = Path(tempfile.gettempdir()) / self._testMethodName
        directory.mkdir(mode=0o700)
        (directory / 'summary.json').write_bytes(canonical(summary))
        for i, value in enumerate(checked['inspections']):
            (directory / ('case-%02d.json' % i)).write_bytes(canonical(value))
        (directory / 'checks.json').write_bytes(canonical(dict(retainedSource01GroupOnly=True,
            correctedReaderSource='implementation04', sourceAndExpectedInputsUnchanged=True,
            independentReaderPure=True, archiveAdversariesRefused=4, currentGroupAccepted=False,
            qualificationPassed=False)))

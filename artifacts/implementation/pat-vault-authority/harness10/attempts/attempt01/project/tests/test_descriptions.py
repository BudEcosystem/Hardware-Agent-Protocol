"""Behavior checks for draft-artifact validation; not runtime conformance tests."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('descriptions', ROOT / 'scripts/check_descriptions.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Descriptions(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((ROOT / 'examples/microscope-focus.json').read_text())

    def test_examples_are_structurally_valid(self):
        for path in (ROOT / 'examples').glob('*.json'):
            MODULE.validate(json.loads(path.read_text()))

    def test_command_cannot_reference_unlisted_resources(self):
        self.document['actions'][0]['resources'] = ['unlisted-axis']
        with self.assertRaisesRegex(ValueError, 'Unknown action resource'):
            MODULE.validate(self.document)

    def test_required_observation_must_exist(self):
        self.document['actions'][0]['required_observations'] = ['missing-encoder']
        with self.assertRaisesRegex(ValueError, 'Unknown required observation'):
            MODULE.validate(self.document)

    def test_limits_do_not_silently_convert_units(self):
        self.document['limits'][0]['bounds']['unit'] = 'mm'
        with self.assertRaisesRegex(ValueError, 'units differ'):
            MODULE.validate(self.document)

    def test_nonfinite_parameter_bounds_are_rejected(self):
        self.document['actions'][0]['parameters']['position']['quantity']['maximum'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            MODULE.validate(self.document)

    def test_inverted_or_expanded_limit_is_rejected(self):
        for low, high, message in [(50, 20, 'Inverted'), (0, 101, 'exceeds')]:
            value = copy.deepcopy(self.document)
            value['limits'][0]['bounds'].update(minimum=low, maximum=high)
            with self.assertRaisesRegex(ValueError, message):
                MODULE.validate(value)

    def test_duplicate_identifiers_cannot_hide_actions(self):
        self.document['actions'].append(copy.deepcopy(self.document['actions'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            MODULE.validate(self.document)

    def test_unrecognized_enforcement_level_is_rejected(self):
        self.document['limits'][0]['enforcement'] = 'prompt-instruction'
        with self.assertRaises(ValidationError):
            MODULE.validate(self.document)


if __name__ == '__main__':
    unittest.main()

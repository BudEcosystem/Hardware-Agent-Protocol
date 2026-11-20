"""Verify the prototype's semantics are not inferred from valid TD syntax alone."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

from jsonschema import ValidationError

from hms.contracts import ContractError, parse_invoke

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('wot_profile', ROOT / 'scripts/check_wot_profile.py')
PROFILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROFILE)


class WotProfile(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((ROOT / 'examples/wot/microscope-focus.json').read_text())
        self.action = self.document['actions']['move_absolute']
        self.intent = self.action['input']['properties']['intent']['properties']

    def test_scenario_fixtures_pass_pinned_td_schema_and_profile_lint(self):
        for path in (ROOT / 'examples/wot').glob('*.json'):
            PROFILE.validate(json.loads(path.read_text()), PROFILE.FEATURES)

    def test_schema_valid_unknown_required_feature_blocks_hms_use(self):
        self.document['hms:requiredFeatures'].append('new-control-semantics/1')
        PROFILE.TD.validate(self.document)
        with self.assertRaisesRegex(ValueError, 'Unsupported required'):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_form_security_override_does_not_inherit_authentication(self):
        self.document['securityDefinitions']['public'] = {'scheme': 'nosec'}
        self.action['forms'][0]['security'] = ['public']
        PROFILE.TD.validate(self.document)
        with self.assertRaisesRegex(ValueError, 'effective bearer'):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_undefined_security_reference_is_rejected(self):
        self.action['forms'][0]['security'] = ['missing-definition']
        with self.assertRaisesRegex(ValueError, 'Unresolved effective'):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_unqualified_raw_arguments_cannot_replace_invocation_envelope(self):
        self.action['input'] = {'type': 'number'}
        PROFILE.TD.validate(self.document)
        with self.assertRaisesRegex(ValueError, 'envelope'):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_physical_protocol_does_not_invent_a_wot_form_operation(self):
        self.action['forms'][0]['op'] = 'hms.execute'
        with self.assertRaises(ValidationError):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_static_profile_rejects_writable_property_and_bulk_write_routes(self):
        self.document['properties']['position']['readOnly'] = False
        with self.assertRaisesRegex(ValueError, 'read-only'):
            PROFILE.validate(self.document, PROFILE.FEATURES)
        self.document['properties']['position']['readOnly'] = True
        self.document['forms'] = [{'href':'https://example.invalid/raw','op':'writeallproperties'}]
        with self.assertRaisesRegex(ValueError, 'bulk forms'):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_unrecognized_optional_annotation_is_preserved(self):
        self.document['hms:displayHint'] = {'futureMetadata': True}
        before = copy.deepcopy(self.document)
        PROFILE.validate(self.document, PROFILE.FEATURES)
        self.assertEqual(self.document, before)

    def test_insecure_url_is_not_repaired_silently(self):
        self.action['forms'][0]['href'] = 'http://example.invalid/invoke'
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_recipe_identifiers_are_discrete(self):
        document = json.loads((ROOT / 'examples/wot/manufacturing-inspection.json').read_text())
        schema = document['actions']['run_recipe']['input']['properties']['intent']['properties']['arguments']
        validator = PROFILE.Draft7Validator(schema)
        self.assertTrue(validator.is_valid({'recipe': 2}))
        self.assertFalse(validator.is_valid({'recipe': 1.5}))
        self.assertFalse(validator.is_valid({'recipe': 4}))

    def test_read_only_property_cannot_advertise_write_form(self):
        self.document['properties']['position']['forms'][0]['op'] = ['readproperty', 'writeproperty']
        PROFILE.TD.validate(self.document)
        with self.assertRaisesRegex(ValueError, 'form operation'):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_schema_keywords_cannot_disguise_scalar_invocation(self):
        self.action['input']['type'] = 'string'
        PROFILE.TD.validate(self.document)
        with self.assertRaisesRegex(ValueError, 'envelope must be an object'):
            PROFILE.validate(self.document, PROFILE.FEATURES)
        self.action['input']['type'] = 'object'
        self.action['input']['properties']['operationKey']['type'] = 'number'
        with self.assertRaisesRegex(ValueError, 'identity fields'):
            PROFILE.validate(self.document, PROFILE.FEATURES)
        self.action['input']['properties']['operationKey']['type'] = 'string'
        self.intent['arguments']['type'] = 'number'
        with self.assertRaisesRegex(ValueError, 'arguments must be an object'):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_same_prefix_cannot_rebind_required_semantics(self):
        self.document['@context'][1]['hms'] = 'https://example.invalid/different-vocabulary#'
        PROFILE.TD.validate(self.document)
        with self.assertRaisesRegex(ValueError, 'fixture context'):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_full_projected_requests_validate_with_host_parser(self):
        for path in (ROOT / 'examples/wot').glob('*.json'):
            with self.subTest(path=path.name):
                document = json.loads(path.read_text())
                action = next(iter(document['actions'].values()))
                schema = action['input']
                fields = schema['properties']['intent']['properties']
                intent = {name: field['const'] for name, field in fields.items() if 'const' in field}
                argument = next(iter(fields['arguments']['properties']))
                intent.update(arguments={argument: 2 if argument == 'recipe' else 50},
                              requiredEffect='capability_completion',
                              timing={'notBeforeUnixMs': 1000, 'latestStartUnixMs': 2000,
                                      'maxRunMs': 100, 'latestCompletionUnixMs': 3000})
                request = {'protocol': 'hms.invoke/0.1', 'replayNamespace': 'fixture-namespace',
                           'operationKey': 'fixture-operation', 'intent': intent}
                PROFILE.Draft7Validator(schema).validate(request)
                self.assertEqual(parse_invoke(json.dumps(request).encode()), request)
                # The TD projection intentionally does not promise generic
                # rejection of unknown input fields. The host parser owns it.
                request['unrecognized'] = True
                PROFILE.Draft7Validator(schema).validate(request)
                with self.assertRaises(ContractError):
                    parse_invoke(json.dumps(request).encode())

    def test_each_intent_identity_and_generation_is_pinned(self):
        for key in ('instanceId', 'actionId', 'descriptionDigest', *PROFILE.GENERATION_KEYS):
            with self.subTest(key=key):
                document = copy.deepcopy(self.document)
                fields = document['actions']['move_absolute']['input']['properties']['intent']['properties']
                fields[key]['const'] = 'wrong-generation'
                PROFILE.TD.validate(document)
                with self.assertRaisesRegex(ValueError, f'pinned {key}'):
                    PROFILE.validate(document, PROFILE.FEATURES)

    def test_every_host_envelope_intent_and_timing_field_is_required(self):
        schemas = [self.action['input'], self.action['input']['properties']['intent'], self.intent['timing']]
        for schema in schemas:
            for key in list(schema['required']):
                with self.subTest(key=key):
                    schema['required'].remove(key)
                    try:
                        with self.assertRaisesRegex(ValueError, 'required .* keys'):
                            PROFILE.validate(self.document, PROFILE.FEATURES)
                    finally:
                        schema['required'].append(key)

    def test_static_lint_rejects_weakened_protocol_timing_and_effect_constraints(self):
        cases = [
            (self.action['input']['properties']['protocol'], 'const', 'hms.invoke/future'),
            (self.intent['timing']['properties']['maxRunMs'], 'minimum', 0),
            (self.intent['timing']['properties']['latestStartUnixMs'], 'maximum', 2**63),
            (self.intent['requiredEffect'], 'enum', ['capability_completion']),
        ]
        for schema, key, replacement in cases:
            with self.subTest(key=key, replacement=replacement):
                old = schema[key]
                schema[key] = replacement
                try:
                    with self.assertRaisesRegex(ValueError, 'schema constraints'):
                        PROFILE.validate(self.document, PROFILE.FEATURES)
                finally:
                    schema[key] = old

    def test_physical_contract_digest_is_checked_independently_of_input_pin(self):
        changed = 'sha256:' + '0' * 64
        self.document['hms:descriptionDigest'] = changed
        self.intent['descriptionDigest']['const'] = changed
        with self.assertRaisesRegex(ValueError, 'retained physical-contract'):
            PROFILE.validate(self.document, PROFILE.FEATURES)

    def test_action_units_and_motion_frame_survive_the_projection(self):
        position = self.intent['arguments']['properties']['position']
        self.assertEqual(position['unit'], 'um')
        self.assertEqual(position['hms:coordinateFrame'],
                         'urn:bud:hms:example:microscope-focus:uncalibrated-focus-axis')
        document = json.loads((ROOT / 'examples/wot/home-ventilation.json').read_text())
        opening = document['actions']['set_opening']['input']['properties']['intent']['properties']['arguments']
        self.assertEqual(opening['properties']['opening']['unit'], 'percent')

    def test_json_schema_only_keyword_cannot_hide_in_nested_td_input(self):
        self.intent['arguments']['additionalProperties'] = False
        # The informative schema permits extensions; this profile's selected
        # normative DataSchema vocabulary rejects the unqualified keyword.
        PROFILE.TD.validate(self.document)
        with self.assertRaisesRegex(ValueError, 'DataSchema keyword'):
            PROFILE.validate(self.document, PROFILE.FEATURES)


if __name__ == '__main__':
    unittest.main()

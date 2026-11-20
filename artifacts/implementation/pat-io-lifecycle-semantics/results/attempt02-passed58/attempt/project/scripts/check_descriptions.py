#!/usr/bin/env python3
"""Validate draft description examples and cross-references, not device safety."""
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas/device-description.schema.json').read_text())
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA)


def validate(document):
    VALIDATOR.validate(document)
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite numbers cannot describe physical values')
        if isinstance(value, dict):
            for child in value.values():
                finite(child)
        elif isinstance(value, list):
            for child in value:
                finite(child)
    finite(document)
    resources = document['resources']
    if len(resources) != len(set(resources)):
        raise ValueError('Duplicate resource identifiers')
    observation_ids = [item['id'] for item in document['observations']]
    action_ids = [item['id'] for item in document['actions']]
    if len(observation_ids) != len(set(observation_ids)) or len(action_ids) != len(set(action_ids)):
        raise ValueError('Duplicate observation or action identifiers')
    quantities = {}
    for action in document['actions']:
        Draft202012Validator.check_schema(action['input_schema'])
        if not set(action['resources']) <= set(resources):
            raise ValueError('Unknown action resource')
        if not set(action['required_observations']) <= set(observation_ids):
            raise ValueError('Unknown required observation')
        for name, parameter in action['parameters'].items():
            quantity = parameter['quantity']
            if quantity['minimum'] > quantity['maximum']:
                raise ValueError('Inverted parameter bounds')
            quantities[action['id'] + '.' + name] = quantity
    for limit in document['limits']:
        bounds = limit['bounds']
        parameter = quantities.get(limit['parameter'])
        if parameter is None:
            raise ValueError('Unknown limit parameter')
        if bounds['unit'] != parameter['unit']:
            raise ValueError('Limit and parameter units differ')
        if bounds['minimum'] > bounds['maximum']:
            raise ValueError('Inverted limit bounds')
        if bounds['minimum'] < parameter['minimum'] or bounds['maximum'] > parameter['maximum']:
            raise ValueError('Limit exceeds declared parameter range')


if __name__ == '__main__':
    paths = sorted((ROOT / 'examples').glob('*.json'))
    for path in paths:
        validate(json.loads(path.read_text()))
        print('valid draft example:', path.name)
    print('Structural and reference checks only; no hardware or runtime conformance tested.')

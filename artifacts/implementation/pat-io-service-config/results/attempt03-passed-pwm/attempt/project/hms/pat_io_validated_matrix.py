"""Explicit trusted validated input bundle for one current I/O group.

This is an in-process optimization, not authority or deployment attestation.
Each reuse compares detached bounded trees with exact numeric types. Runtime
installation, binding, permission and effect guards remain independent.
"""
from .pat_contracts import require, snapshot
from .pat_io_combined_matrix import IoCombinedMatrixPolicy
from .pat_io_contracts import _same


class ValidatedIoMatrix:
    def __init__(self, *, candidate, installation, descriptor, challenge_bindings, limits=None):
        self._inputs = dict(candidate=snapshot(candidate), installation=snapshot(installation),
            descriptor=snapshot(descriptor), challenge_bindings=snapshot(challenge_bindings))
        policy = IoCombinedMatrixPolicy(self._inputs['installation'])
        args = (self._inputs['candidate'], self._inputs['descriptor'], self._inputs['challenge_bindings'])
        matrix = policy.generate(*args, limits=limits)
        self._digest = policy.validate(matrix, *args, limits=matrix['limits'])
        self._inputs['matrix'] = snapshot(matrix)

    def matrix(self):
        return snapshot(self._inputs['matrix'])

    @property
    def digest(self):
        return self._digest

    def assert_matrix(self, matrix):
        require(_same(snapshot(matrix), self._inputs['matrix']), 'PAT_IO_GROUP_PLAN_MISMATCH')

    def validate_inputs(self, *, matrix, candidate, installation, descriptor, challenge_bindings):
        # Five separately bounded documents; no hash-only or Python == match
        # that could collapse True/1/1.0. Nothing supplied here is retained.
        inputs = dict(matrix=matrix, candidate=candidate, installation=installation,
            descriptor=descriptor, challenge_bindings=challenge_bindings)
        for name, value in inputs.items():
            require(_same(snapshot(value), self._inputs[name]), 'PAT_IO_GROUP_PLAN_MISMATCH')
        return self._digest

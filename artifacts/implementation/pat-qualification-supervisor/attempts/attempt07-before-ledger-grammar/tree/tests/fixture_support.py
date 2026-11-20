"""Original current-runtime descriptor capture, derived from the pinned worker test."""
import copy
import json
from pathlib import Path
import tempfile

from hms.contracts import canonical
from hms.installations import installation_digest, legacy_installation
from hms.journal import Context
from hms.pat_simulation_contracts import CEILINGS, FAN_METADATA
from hms.pat_simulation_worker import make_capsule, simulation_identities
from hms.pat_simulation_evidence import TRUST_PROFILE, PROFILE, CHECKS
from hms.runtime import Runtime
from supervisor_contracts import prepare_request


def request(run='run:original', *, worker_limits=None):
    limits = dict(CEILINGS if worker_limits is None else worker_limits)
    identities = simulation_identities(limits)
    installation = legacy_installation()
    artifact = json.loads((Path(__file__).parent / 'fixtures/fan.json').read_text())
    artifact['parameters'] = {}
    for index, step in enumerate(artifact['steps']): step['arguments']['level'] = {'literal': 17 + index}
    owner = Context('fixture-owner', 'simulation:local')
    with tempfile.TemporaryDirectory(prefix='hms-qualification-fixture-') as directory:
        runtime = Runtime(directory, create=True, owner=owner, wall_clock_ms=lambda: 1000,
                          monotonic_ms=lambda: 1000)
        try:
            binding, _ = runtime.registry._binding(installation['instances']['fan'])
            descriptor = {'type': runtime.registry._type(binding['typeDigest']), 'binding': binding,
                'endpointSession': runtime.adapters[installation['adapterId']].plant.session,
                'driverProfile': 'sqlite-simulation', 'driverDigest': identities['driverDigest'],
                'installationDigest': 'sha256:' + installation_digest(installation),
                'argumentMetadata': copy.deepcopy(FAN_METADATA)}
        finally: runtime.close()
    capsule = make_capsule(artifact, installation, {'fan': descriptor}, deployment='simulation:local',
        runtime_layout='legacy', configuration={'revision': 1, 'digest': 'sha256:' + '1'*64},
        attempt_id='attempt:' + run, limits=limits)
    return prepare_request({'profile': TRUST_PROFILE, 'deployment': 'simulation:local', 'runId': run,
        'evaluator': {'evaluatorId': 'sim:staged-supervisor', 'implementationDigest': identities['workerDigest'],
            'policyDigest': identities['policyDigest'], 'requiredChecks': [{'id': key, 'category': cat} for key, cat in CHECKS],
            'evidenceProfile': PROFILE}, 'input': capsule})

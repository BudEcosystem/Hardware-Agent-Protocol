"""Original current-runtime descriptor capture, derived from the pinned worker test."""
import copy
import json
import os
from pathlib import Path
import tempfile

from hms.contracts import canonical
from hms.installations import installation_digest, legacy_installation
from hms.journal import Context
from hms.pat_simulation_contracts import (CEILINGS, FAN_METADATA, CONFIG_PROFILE, POLICY,
    parse_service_config, config_digest)
from hms.pat_contracts import pat_digest
from hms.pat_simulation_worker import make_capsule, simulation_identities
from hms.pat_simulation_evidence import TRUST_PROFILE, PROFILE, CHECKS
from hms.runtime import Runtime
from supervisor_contracts import prepare_request, supervisor_identity


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
    config=parse_service_config({'profile':CONFIG_PROFILE,'policy':POLICY,'limits':limits,
        'registrations':[{'instanceId':binding['instanceId'],'driverProfile':descriptor['driverProfile'],
            'typeDigest':binding['typeDigest'],'installationDigest':descriptor['installationDigest'],
            'argumentMetadata':copy.deepcopy(FAN_METADATA)}],
        'qualifications':[{'artifactDigest':pat_digest(artifact),'roleInstances':{'fan':binding['instanceId']}}]})
    configured_digest=config_digest(config)
    implementation=supervisor_identity(identities)
    evaluator={'evaluatorId':'sim:supervisor-696','implementationDigest':implementation,
        'policyDigest':identities['policyDigest'],'requiredChecks':[{'id':key,'category':cat} for key,cat in CHECKS],
        'evidenceProfile':PROFILE}
    # Trusted test setup is retained before launch. It is not a mounted service
    # configuration or an attestation that a production principal approved it.
    setup=Path(os.environ['RETAIN_SETUP']);setup.mkdir(mode=0o700,parents=True,exist_ok=True)
    body=canonical({'profile':'hms.supervisor-test-configuration/0.1','configuration':config,
        'configurationDigest':configured_digest,'evaluator':evaluator,'workerIdentities':identities})
    target=setup/(configured_digest[7:]+'.json')
    if target.exists():assert target.read_bytes()==body
    else:
        with target.open('xb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
        target.chmod(0o600)
        fd=os.open(setup,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    capsule = make_capsule(artifact, installation, {'fan': descriptor}, deployment='simulation:local',
        runtime_layout='legacy', configuration={'revision': 1, 'digest': configured_digest},
        attempt_id='attempt:' + run, limits=limits)
    return prepare_request({'profile': TRUST_PROFILE, 'deployment': 'simulation:local', 'runId': run,
        'evaluator':evaluator,'input':capsule})

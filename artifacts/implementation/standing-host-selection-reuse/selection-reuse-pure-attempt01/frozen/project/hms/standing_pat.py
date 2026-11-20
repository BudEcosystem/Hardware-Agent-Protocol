"""One exact standing PAT domain and original native qualification catalog.

Source candidate only. The installed producer reads a retained original runner
attempt; it never launches code and no management call accepts results or paths.
This profile qualifies the literal synthetic domain only. It supplies neither
physical qualification nor protected host/control-storage capacity.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import stat
import threading
import time

from .contracts import canonical, identifier, parse_json
from .journal import Context
from .standing_contracts import (ROOT, document, exact, require, uint, digest, sha,
                                 identity, parse_installation, parse_request)
from .standing_wire import Configuration

PROFILE = 'hms.pat.standing-controller/0.1'
COMPILER = 'hms.standing-compiler/literal-native-domain/0.1'
CATALOG = 'hms.standing-catalog/original-native/0.1'
PRODUCER = 'hms.standing-native-producer/0.1'
RESERVATION = 'hms.standing-native-reservation/0.1'
ATTEMPT = 'hms.standing-native-attempt/0.1'
EVALUATOR = 'standing-native-controls-v1'
TASK_KIND = 'standing-cooling-control'
INPUT_PROFILE = 'synthetic-demand-rpm-v1'
MAX_ENTRIES = 16
MAX_FILE = 2 * 1024 * 1024
MAX_SNAPSHOT = 8 * 1024 * 1024
LEASE_NS = 2_000_000_000

# Exact copied original sources, not hashes of a caller-selected test program.
SOURCE_PINS = {
    'tests/standing_controls.c': 'sha256:5d1feec5ffa339b6662c8772a3a5c5cf9985c44bb7fb522ceb7ea1ac66144ac6',
    'tests/standing_fixture.c': 'sha256:27fadcda6c53b9588d221c274871ec2f728e1af7d1a38aa85ca650665217245e',
    'tests/standing_fixture.h': 'sha256:5022b3f4a288dd6053a45c1c9479c9edc37115fda5c1198653a5f77de9d5d878',
    'tests/standing_vectors.h': 'sha256:e0fbcf9af80adcdeef1568d7d9509c7293db7afd33872c11f2d269ae77d4a071',
    'protocol/endpoint/endpoint.c': 'sha256:ede804ea4df5ccb61c2c7254f3dcdbb91a6e53edcafad43d045147bf42df64d7',
    'protocol/endpoint/endpoint.h': 'sha256:b5d2ad99e751cbc273e0e3383274a2deca93fbd6fce4b3f0646852b8b6217507',
    'protocol/endpoint/standing.c': 'sha256:3ae3d9e65cf213413f8f5148bc119d304a4c7046269446b032f45e201773e25b',
    'protocol/endpoint/standing.h': 'sha256:e41b6b01fc717b4dcafcf38ea5876044f6b19a97b9c3b8732221deb7baecbd89',
    'protocol/endpoint/link.c': 'sha256:129d81dc23bc6c1d702f8b23b615457634273aa40d52c866870ea92464823c9c',
    'protocol/endpoint/link.h': 'sha256:7afd7b6e97c9f79c69e75f0aa466055e63e1189cd5b0af3d83962e4d45297bf1',
    'protocol/serial/frame.c': 'sha256:4bb8120c648852d3205f743df308ded521d64639607c7926c493c7cb8bb2771f',
    'protocol/serial/frame.h': 'sha256:29870e0821d724f39116f6f2ff81b4245bd9810680b235e45f116b11615ec7d7',
}
CASES = ('wire_and_refusals', 'replay_and_renewal', 'ledger_ack_resume',
         'pending_ack_and_feedback', 'source_and_clock_faults', 'late_dispatch_and_limits',
         'prepared_expiry_and_revoke', 'loss_witness_ordering', 'acquisition_boundaries',
         'interrupted_feedback_ack', 'finite_interoperation', 'stop_backpressure')
EXPECTED_STDOUT = b'{"cases":12,"assertions":638,"physical_qualification":false}\n'
CONFIGURATION = {'lowerDemand': 20000, 'upperDemand': 30000, 'requiredImprovement': 0,
                 'minimumOnFeedback': 500, 'samplePeriod': 10, 'demandMaxAge': 100,
                 'feedbackMaxAge': 100, 'minimumOnDwell': 0, 'minimumOffDwell': 0,
                 'feedbackWindow': 50, 'offCode': 0, 'onCode': 1, 'lossCode': 0, 'policy': 0}
LIMITS = {'activationCap': 100, 'commandedOnMs': 500, 'leaseHorizonMs': 1000}
RUN_LIMITS = {'cpuSeconds': 10, 'wallSeconds': 30, 'fileBytes': 1048576, 'processes': 1}
DOMAIN = {'profile': 'hms.standing-native-domain/0.1', 'kernel': 1, 'mask': 3,
          'parameters': {}, 'configuration': CONFIGURATION, 'limits': LIMITS,
          'evidenceMode': 'simulation', 'sourceEpochs': [1, 1], 'caseClosure': list(CASES),
          'sourcePins': SOURCE_PINS, 'physicalEligible': False, 'protectedCapacity': False}
DOMAIN_DIGEST = identity('HMS-STANDING-NATIVE-DOMAIN-v0.1', DOMAIN)
SOURCE_DIGEST = identity('HMS-STANDING-NATIVE-SOURCES-v0.1', SOURCE_PINS)


def _same_typed(value, expected, code):
    require(type(value) is type(expected), code)
    if type(expected) is dict:
        exact(value, expected)
        for key in expected:
            _same_typed(value[key], expected[key], code)
    elif type(expected) is list:
        require(len(value) == len(expected), code)
        for left, right in zip(value, expected):
            _same_typed(left, right, code)
    else:
        require(value == expected, code)


def installation_digest(installation):
    return identity('HMS-STANDING-INSTALLATION-v0.1', parse_installation(installation))


def installed_artifact(installation):
    """Return the only configuration/domain supported by this compiler."""
    installed = parse_installation(installation)
    return _artifact_record(installed, installation_digest(installed))


def _artifact_record(installed, installed_digest):
    """Shared pure construction; callers own their validation sequence."""
    return document({'profile': PROFILE, 'id': 'standing-native-golden-v1',
        'taskKind': TASK_KIND, 'inputProfile': INPUT_PROFILE, 'parameters': {},
        'kernel': 1, 'configuration': CONFIGURATION, 'limits': LIMITS,
        'evidenceMode': 'simulation', 'outagePolicy': 'bounded-local-continuation',
        'placement': {'routeId': installed['routeId'], 'instanceId': installed['instanceId']},
        'requirements': {'installationDigest': installed_digest,
            'driverImageDigest': installed['driverImageDigest'],
            'driverSourceDigest': installed['driverSourceDigest'],
            'qualificationImageDigest': installed['qualificationImageDigest'],
            'hostImplementationDigest': installed['hostImplementationDigest']},
        'qualificationDomainDigest': DOMAIN_DIGEST})


def parse_artifact(value, installation):
    artifact = document(value)
    expected = installed_artifact(installation)
    _match_artifact(artifact, expected)
    installed = parse_installation(installation)
    _qualified_endpoint(installed)
    return artifact


def _match_artifact(artifact, expected):
    exact(artifact, expected)
    # Labels are metadata, never domains. Multiple compatible promoted labels
    # still make selection ambiguous; an original run cannot be reassociated.
    for key in ('id', 'taskKind', 'inputProfile'):
        identifier(artifact[key])
        expected[key] = artifact[key]
    _same_typed(artifact, expected, 'PAT_DOMAIN_UNQUALIFIED')


def _qualified_endpoint(installed):
    endpoint = installed['endpoint']
    require(endpoint['boot'] == 1 and endpoint['epochs'] == [1, 1] and
            endpoint['incarnationHex'] == bytes(range(0xa0, 0xb0)).hex() and
            endpoint['firmwareHex'] == bytes(range(0xb0, 0xd0)).hex() and
            endpoint['manifestHex'] == bytes(range(0xc0, 0xe0)).hex(), 'PAT_INSTALLATION_UNQUALIFIED')


def artifact_digest(artifact):
    return identity('HMS-STANDING-PAT-v0.1', artifact)


def _configuration():
    return Configuration(20000, 30000, 0, 500, 10, 100, 100, 0, 0, 50)


@dataclass(frozen=True)
class Compiled:
    _wire: bytes
    configuration: Configuration

    @property
    def document(self):
        return parse_json(self._wire)


def compile_artifact(value, installation):
    artifact = parse_artifact(value, installation)
    installed = parse_installation(installation)
    return _compile_record(artifact, installed, installation_digest)


def _compile_record(artifact, installed, digest_installation):
    # The resolver is one of the two installed pure helpers below. It runs at
    # the original field-construction position; no authority callback enters.
    compiler = identity('HMS-STANDING-COMPILER-v0.1', {'profile': COMPILER,
        'hostImplementationDigest': installed['hostImplementationDigest'],
        'sourceDigest': SOURCE_DIGEST, 'domainDigest': DOMAIN_DIGEST})
    configuration = _configuration()
    result = {'profile': COMPILER, 'artifactDigest': artifact_digest(artifact),
        'compilerDigest': compiler, 'installationDigest': digest_installation(installed),
        'hostImplementationDigest': installed['hostImplementationDigest'],
        'driverImageDigest': installed['driverImageDigest'], 'driverSourceDigest': installed['driverSourceDigest'],
        'qualificationImageDigest': installed['qualificationImageDigest'], 'sourceDigest': SOURCE_DIGEST,
        'domainDigest': DOMAIN_DIGEST, 'configurationHex': configuration.payload().hex(),
        'kernel': 1, 'resourceMask': 3, 'sourceEpochs': [1, 1], 'limits': LIMITS,
        'evidenceMode': 'simulation', 'physicalEligible': False, 'protectedCapacity': False}
    return Compiled(canonical(result), configuration)


class _CatalogCompilationInput:
    """One private pure call's detached snapshot, never retained authority."""
    __slots__ = ('_installed',)

    def __init__(self, installation):
        self._installed = parse_installation(installation)

    def identity(self, installed):
        require(installed is self._installed, 'COMPILATION_SNAPSHOT')
        return identity('HMS-STANDING-INSTALLATION-v0.1', installed)


def _compile_catalog_artifact(value, installation):
    # Preserve artifact-document-first refusal order. The snapshot is created
    # at the old first installation-validation point and ends at this return.
    # It is never carried over a DB/evidence/policy callback or another call.
    artifact = document(value)
    snapshot = _CatalogCompilationInput(installation)
    installed = snapshot._installed
    expected = _artifact_record(installed, snapshot.identity(installed))
    _match_artifact(artifact, expected)
    _qualified_endpoint(installed)
    return _compile_record(artifact, installed, snapshot.identity)


def _relative(name):
    require(type(name) is str and 1 <= len(name) <= 240 and '\\' not in name, 'EVIDENCE_PATH')
    path = Path(name)
    require(not path.is_absolute() and all(part not in ('', '.', '..') for part in name.split('/')),
            'EVIDENCE_PATH')
    return name


def _decimal_tick(value):
    require(type(value) is str and value.isascii() and value.isdigit() and
            (value == '0' or not value.startswith('0')) and len(value) <= 20, 'ATTEMPT_TIME')
    result = int(value)
    require(result <= 2**64 - 1, 'ATTEMPT_TIME')
    return result


@dataclass
class _EvidenceLease:
    producer: object
    thread: int
    expires: int
    reservation_wire: bytes
    receipt_wire: bytes
    identity_wire: bytes
    files: tuple
    active: bool = True

    def check(self):
        owner = self.producer
        require(self.active and owner._held is self and self.thread == threading.get_ident() and
                time.monotonic_ns() < self.expires and owner.enabled and
                canonical(owner.manifest) == owner._original, 'QUALIFICATION_LEASE_UNAVAILABLE')
        require(owner.journal.policy is owner.policy, 'QUALIFICATION_POLICY_CHANGED')

    @property
    def evidence(self):
        self.check()
        return parse_json(self.identity_wire)


class InstalledNativeProducer:
    """Installed original-attempt reader; no launch or caller evidence ingress.

    root/manifest are installation-owned arguments. The manifest pins an
    immutable reservation, original attempt receipt, original stdout/stderr and
    binary. Original endpoint source pins are additionally hardcoded above.
    Advisory shared locks and retained bytes are held through the authority
    commit. The trusted runner must publish once and obey those file locks;
    hostile same-user file writers are outside this local POSIX contract.
    """
    def __init__(self, journal, root, *, manifest):
        require(not journal._db.in_transaction, 'TRANSACTION_REENTRY')
        self.journal, self.policy = journal, journal.policy
        self.root = Path(root).resolve(strict=True)
        require(self.root.is_dir(), 'EVIDENCE_PATH')
        self.manifest = document(manifest, 16384)
        exact(self.manifest, ('profile', 'evaluatorId', 'runId', 'runnerDigest', 'domainDigest',
            'sourcePins', 'binaryPath', 'binaryDigest', 'argv', 'reservationPath', 'reservationDigest',
            'receiptPath', 'receiptDigest', 'stdoutPath', 'stdoutDigest', 'stderrPath', 'stderrDigest'))
        m = self.manifest
        require(m['profile'] == PRODUCER and m['evaluatorId'] == EVALUATOR and m['domainDigest'] == DOMAIN_DIGEST,
                'EVALUATOR_UNQUALIFIED')
        identifier(m['runId'])
        _same_typed(m['sourcePins'], SOURCE_PINS, 'QUALIFICATION_SOURCE_CHANGED')
        for name in ('runnerDigest', 'binaryDigest', 'reservationDigest', 'receiptDigest', 'stdoutDigest', 'stderrDigest'):
            digest(m[name])
        paths = [m[name] for name in ('binaryPath', 'reservationPath', 'receiptPath', 'stdoutPath', 'stderrPath')]
        for name in paths:
            _relative(name)
        require(len(set(paths)) == 5, 'EVIDENCE_PATH')
        require(m['argv'] == [str(self.root / m['binaryPath'])] and type(m['argv']) is list,
                'QUALIFICATION_ARGV')
        require(m['stdoutDigest'] == sha(EXPECTED_STDOUT) and m['stderrDigest'] == sha(b''), 'QUALIFICATION_OUTPUT')
        self._original = canonical(m)
        self.identity = identity('HMS-STANDING-NATIVE-PRODUCER-v0.1', m)
        self._held = None
        self._mutex = threading.RLock()
        self.enabled = True

    def _read_locked(self, stack, root, name, expected, maximum):
        path = root / _relative(name)
        require(path.resolve(strict=True) == path and path.is_relative_to(root), 'EVIDENCE_PATH')
        stream = stack.enter_context(os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb'))
        fcntl.flock(stream.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'EVIDENCE_LIMIT')
        body = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        require(signature(before) == signature(after) and len(body) == before.st_size and sha(body) == expected,
                'QUALIFICATION_BYTES_CHANGED')
        return body

    def _validate(self, reservation_wire, receipt_wire, stdout, stderr):
        m = self.manifest
        reservation, receipt = document(reservation_wire, 16384), document(receipt_wire, 16384)
        require(canonical(reservation) == reservation_wire and canonical(receipt) == receipt_wire,
                'QUALIFICATION_NONCANONICAL')
        common = ('evaluatorId', 'runId', 'attemptId', 'runnerDigest', 'domainDigest', 'sourcePins',
                  'binaryPath', 'binaryDigest', 'argv')
        exact(reservation, ('profile', *common, 'limits', 'state'))
        exact(receipt, ('profile', *common, 'reservationDigest', 'stdoutDigest', 'stderrDigest',
                       'exitCode', 'terminationSignal', 'startedMonotonicNs', 'finishedMonotonicNs',
                       'ownership', 'physicalQualification', 'protectedCapacity'))
        require(reservation['profile'] == RESERVATION and reservation['state'] == 'reserved' and
                receipt['profile'] == ATTEMPT, 'ORIGINAL_ATTEMPT_REQUIRED')
        identifier(reservation['attemptId'])
        _same_typed(reservation['limits'], RUN_LIMITS, 'QUALIFICATION_LIMITS')
        for key in common:
            expected = reservation[key] if key == 'attemptId' else m[key]
            _same_typed(reservation[key], expected, 'QUALIFICATION_ASSOCIATION')
            _same_typed(receipt[key], expected, 'QUALIFICATION_ASSOCIATION')
        require(receipt['reservationDigest'] == m['reservationDigest'] and
                receipt['stdoutDigest'] == m['stdoutDigest'] and receipt['stderrDigest'] == m['stderrDigest'],
                'QUALIFICATION_ASSOCIATION')
        uint(receipt['exitCode'], 255)
        uint(receipt['terminationSignal'], 255)
        require(receipt['exitCode'] == 0 and receipt['terminationSignal'] == 0 and
                stdout == EXPECTED_STDOUT and stderr == b'', 'QUALIFICATION_NOT_PASSED')
        for key in ('physicalQualification', 'protectedCapacity'):
            require(type(receipt[key]) is bool and not receipt[key], 'QUALIFICATION_SCOPE')
        start, end = _decimal_tick(receipt['startedMonotonicNs']), _decimal_tick(receipt['finishedMonotonicNs'])
        require(start < end and end - start <= RUN_LIMITS['wallSeconds'] * 1_000_000_000,
                'QUALIFICATION_DEADLINE')
        owned = receipt['ownership']
        exact(owned, ('pid', 'waitedPid', 'spawnCount', 'reaped', 'cleanupComplete', 'openChildHandles'))
        uint(owned['pid'], 2**31 - 1, 1)
        uint(owned['waitedPid'], 2**31 - 1, 1)
        uint(owned['spawnCount'], 1, 1)
        uint(owned['openChildHandles'], 0)
        require(owned['pid'] == owned['waitedPid'] and type(owned['reaped']) is bool and owned['reaped'] and
                type(owned['cleanupComplete']) is bool and owned['cleanupComplete'], 'QUALIFICATION_CLEANUP')
        return {'profile': ATTEMPT, 'producerDigest': self.identity,
                'evaluatorId': EVALUATOR, 'runId': m['runId'], 'attemptId': receipt['attemptId'],
                'reservationDigest': m['reservationDigest'], 'receiptDigest': m['receiptDigest'],
                'runnerDigest': m['runnerDigest'], 'binaryDigest': m['binaryDigest'],
                'sourceDigest': SOURCE_DIGEST, 'domainDigest': DOMAIN_DIGEST,
                'stdoutDigest': m['stdoutDigest'], 'stderrDigest': m['stderrDigest'],
                'caseClosure': list(CASES), 'cases': 12, 'assertions': 638,
                'physicalQualification': False, 'protectedCapacity': False}

    @contextmanager
    def snapshot(self, evaluator_id, run_id):
        require(not self.journal._db.in_transaction, 'TRANSACTION_REENTRY')
        require(evaluator_id == EVALUATOR and run_id == self.manifest['runId'], 'EVALUATOR_UNAVAILABLE')
        with self._mutex:
            require(self._held is None and self.enabled and canonical(self.manifest) == self._original,
                    'QUALIFICATION_SNAPSHOT_REENTRY')
            with ExitStack() as stack:
                m, charge = self.manifest, 0
                retained = []
                for name, expected in sorted(SOURCE_PINS.items()):
                    body = self._read_locked(stack, ROOT, name, expected, 1024 * 1024)
                    charge += len(body)
                    require(charge <= MAX_SNAPSHOT, 'QUALIFICATION_SNAPSHOT_LIMIT')
                    retained.append(('source:' + name, body))
                blobs = {}
                for kind in ('binary', 'reservation', 'receipt', 'stdout', 'stderr'):
                    limit = MAX_FILE if kind == 'binary' else (16384 if kind in ('reservation', 'receipt') else 4096)
                    blobs[kind] = self._read_locked(stack, self.root, m[kind + 'Path'], m[kind + 'Digest'], limit)
                    charge += len(blobs[kind])
                    retained.append(('evidence:' + kind, blobs[kind]))
                    require(charge <= MAX_SNAPSHOT, 'QUALIFICATION_SNAPSHOT_LIMIT')
                evidence = self._validate(blobs['reservation'], blobs['receipt'], blobs['stdout'], blobs['stderr'])
                held = _EvidenceLease(self, threading.get_ident(), time.monotonic_ns() + LEASE_NS,
                                      blobs['reservation'], blobs['receipt'], canonical(evidence), tuple(retained))
                self._held = held
                try:
                    held.check()
                    yield held
                finally:
                    held.active = False
                    self._held = None


_DDL = (
    'CREATE TABLE sp_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
    '''CREATE TABLE sp_artifacts (digest TEXT PRIMARY KEY, document BLOB NOT NULL,
       state TEXT NOT NULL CHECK(state IN ('candidate','promoted','suspended')),
       evaluation TEXT, decision TEXT)''',
    '''CREATE TABLE sp_evaluations (digest TEXT PRIMARY KEY, artifact TEXT NOT NULL
       REFERENCES sp_artifacts(digest), evaluator TEXT NOT NULL, run_id TEXT NOT NULL,
       document BLOB NOT NULL, UNIQUE(evaluator,run_id))''',
    '''CREATE TABLE sp_decisions (digest TEXT PRIMARY KEY, artifact TEXT NOT NULL
       REFERENCES sp_artifacts(digest), document BLOB NOT NULL)''',
)


@dataclass(frozen=True)
class Selected:
    _wire: bytes
    configuration: Configuration

    @property
    def document(self):
        return parse_json(self._wire)

    @property
    def artifact_digest(self):
        return self.document['artifactDigest']

    @property
    def evaluation_digest(self):
        return self.document['evaluationDigest']

    @property
    def decision_digest(self):
        return self.document['decisionDigest']

    @property
    def compiler_digest(self):
        return self.document['compilerDigest']


class StandingCatalog:
    def __init__(self, journal, policy, producer, create=False):
        require(journal.standing_profile and journal.policy is policy and type(producer) is InstalledNativeProducer and
                producer.journal is journal and type(create) is bool, 'CATALOG_INSTALLATION')
        self.journal, self.policy, self.producer, self._db = journal, policy, producer, journal._db
        self._selection = None
        self._installation = installation_digest(policy.installation)
        require(policy.installation['qualificationImageDigest'] == producer.manifest['binaryDigest'],
                'QUALIFICATION_IMAGE_CHANGED')
        with journal._transaction():
            found = {row[0] for row in self._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sp_%'")}
            expected = {'sp_meta', 'sp_artifacts', 'sp_evaluations', 'sp_decisions'}
            if create:
                require(not found, 'CATALOG_EXISTS')
                for sql in _DDL:
                    self._db.execute(sql)
                for key, value in {'profile': CATALOG, 'installation': self._installation,
                                   'producer': producer.identity, 'revision': '0'}.items():
                    self._db.execute('INSERT INTO sp_meta VALUES (?,?)', (key, value))
            else:
                require(found == expected, 'CATALOG_UNAVAILABLE')
            require(self._meta('profile') == CATALOG and self._meta('installation') == self._installation and
                    self._meta('producer') == producer.identity, 'CATALOG_IDENTITY_CHANGED')

    def _meta(self, key):
        row = self._db.execute('SELECT value FROM sp_meta WHERE key=?', (key,)).fetchone()
        require(row is not None, 'CATALOG_UNAVAILABLE')
        return row[0]

    def _bump(self):
        revision = int(self._meta('revision'))
        uint(revision, 2**32 - 2)
        self._db.execute("UPDATE sp_meta SET value=? WHERE key='revision'", (str(revision + 1),))

    def _image(self):
        return self.policy.hold_image() if self.policy._held_image is None else nullcontext(self.policy.check_image)

    def _fresh(self, context, *, admin=False):
        require(self._db.in_transaction, 'TRANSACTION_REQUIRED')
        if admin:
            self.policy.authorize(context, 'admin', '*')
        installation, _ = self.policy.fresh(context)
        require(installation_digest(installation) == self._installation and
                self._meta('profile') == CATALOG and self._meta('installation') == self._installation and
                self.producer.identity == self._meta('producer') and
                installation['qualificationImageDigest'] == self.producer.manifest['binaryDigest'],
                'CATALOG_IDENTITY_CHANGED')
        return installation

    def _row(self, artifact):
        digest(artifact)
        row = self._db.execute('SELECT * FROM sp_artifacts WHERE digest=?', (artifact,)).fetchone()
        require(row is not None and len(row['document']) <= 65536, 'ARTIFACT_UNAVAILABLE')
        return row

    def _compiled(self, row, installation):
        artifact = document(bytes(row['document']))
        require(artifact_digest(artifact) == row['digest'], 'ARTIFACT_CHANGED')
        return artifact, _compile_catalog_artifact(artifact, installation)

    def _evidence_guard(self, context, held, artifact, compilation):
        expected = canonical(compilation.document)
        def check():
            held.check()
            installed = self._fresh(context, admin=True)
            _, current = self._compiled(self._row(artifact), installed)
            require(canonical(current.document) == expected, 'QUALIFICATION_CHANGED')
            require(held.evidence['binaryDigest'] == installed['qualificationImageDigest'], 'QUALIFICATION_IMAGE_CHANGED')
        check()
        self.journal._require_at_commit(check)

    def publish(self, context, artifact):
        with self._image():
            with self.journal._transaction():
                installed = self._fresh(context, admin=True)
                parsed = parse_artifact(artifact, installed)
                result = artifact_digest(parsed)
                prior = self._db.execute('SELECT document FROM sp_artifacts WHERE digest=?', (result,)).fetchone()
                if prior is not None:
                    require(bytes(prior[0]) == canonical(parsed), 'ARTIFACT_CONFLICT')
                else:
                    require(self._db.execute('SELECT count(*) FROM sp_artifacts').fetchone()[0] < MAX_ENTRIES,
                            'CATALOG_CAPACITY')
                    self._db.execute('INSERT INTO sp_artifacts VALUES (?,?,?,?,?)',
                                     (result, canonical(parsed), 'candidate', None, None))
                    self._bump()
                self.journal._require_at_commit(lambda: self._fresh(context, admin=True) and None)
                return result

    def record_evaluation(self, context, artifactDigest, evaluatorId, runId):
        digest(artifactDigest)
        identifier(evaluatorId)
        identifier(runId)
        with self._image():
            # This original receipt/source/binary read happens before BEGIN.
            with self.producer.snapshot(evaluatorId, runId) as held:
                with self.journal._transaction():
                    installed = self._fresh(context, admin=True)
                    row = self._row(artifactDigest)
                    _, compiled = self._compiled(row, installed)
                    self._evidence_guard(context, held, artifactDigest, compiled)
                    evaluation = {'profile': 'hms.standing-evaluation/original-native/0.1',
                        'artifactDigest': artifactDigest, 'compilerDigest': compiled.document['compilerDigest'],
                        'installationDigest': self._installation, 'domainDigest': DOMAIN_DIGEST,
                        'evidence': held.evidence, 'outcome': 'passed-literal-synthetic-domain'}
                    result = identity('HMS-STANDING-EVALUATION-v0.1', evaluation)
                    prior = self._db.execute('SELECT digest,document FROM sp_evaluations WHERE evaluator=? AND run_id=?',
                                             (evaluatorId, runId)).fetchone()
                    if prior is not None:
                        require(prior['digest'] == result and bytes(prior['document']) == canonical(evaluation),
                                'ORIGINAL_RUN_CONFLICT')
                        require(row['evaluation'] == result, 'EVALUATION_CHANGED')
                    else:
                        require(self._db.execute('SELECT count(*) FROM sp_evaluations').fetchone()[0] < MAX_ENTRIES,
                                'CATALOG_CAPACITY')
                        self._db.execute('INSERT INTO sp_evaluations VALUES (?,?,?,?,?)',
                                         (result, artifactDigest, evaluatorId, runId, canonical(evaluation)))
                        self._db.execute('UPDATE sp_artifacts SET evaluation=?,decision=NULL,state=? WHERE digest=?',
                                         (result, 'candidate', artifactDigest))
                        self._bump()
                    def final_evaluation():
                        current = self._row(artifactDigest)
                        require(current['evaluation'] == result, 'EVALUATION_CHANGED')
                        self._evaluation(current, compiled, held)
                    self.journal._require_at_commit(final_evaluation)
                    return result

    def _evaluation(self, row, compiled, held):
        require(row['evaluation'] is not None, 'EVALUATION_UNAVAILABLE')
        saved = self._db.execute('SELECT * FROM sp_evaluations WHERE digest=?', (row['evaluation'],)).fetchone()
        require(saved is not None and len(saved['document']) <= 16384, 'EVALUATION_UNAVAILABLE')
        evaluation = document(bytes(saved['document']), 16384)
        expected = {'profile': 'hms.standing-evaluation/original-native/0.1',
                    'artifactDigest': row['digest'], 'compilerDigest': compiled.document['compilerDigest'],
                    'installationDigest': self._installation, 'domainDigest': DOMAIN_DIGEST,
                    'evidence': held.evidence, 'outcome': 'passed-literal-synthetic-domain'}
        require(saved['artifact'] == row['digest'] and saved['evaluator'] == EVALUATOR and
                saved['run_id'] == self.producer.manifest['runId'] and canonical(evaluation) == canonical(expected) and
                identity('HMS-STANDING-EVALUATION-v0.1', evaluation) == row['evaluation'], 'EVALUATION_CHANGED')
        return evaluation

    def promote(self, context, artifactDigest):
        with self._image():
            with self.producer.snapshot(EVALUATOR, self.producer.manifest['runId']) as held:
                with self.journal._transaction():
                    installed = self._fresh(context, admin=True)
                    row = self._row(artifactDigest)
                    _, compiled = self._compiled(row, installed)
                    self._evaluation(row, compiled, held)
                    self._evidence_guard(context, held, artifactDigest, compiled)
                    decision = {'profile': 'hms.standing-promotion/0.1', 'artifactDigest': artifactDigest,
                        'evaluationDigest': row['evaluation'], 'compilerDigest': compiled.document['compilerDigest'],
                        'installationDigest': self._installation, 'domainDigest': DOMAIN_DIGEST,
                        'authority': self.journal.authority_id, 'deployment': context.deployment,
                        'physicalEligible': False, 'protectedCapacity': False}
                    result = identity('HMS-STANDING-PROMOTION-v0.1', decision)
                    prior = self._db.execute('SELECT document FROM sp_decisions WHERE digest=?', (result,)).fetchone()
                    if prior is not None:
                        require(bytes(prior[0]) == canonical(decision), 'DECISION_CONFLICT')
                    else:
                        require(self._db.execute('SELECT count(*) FROM sp_decisions').fetchone()[0] < MAX_ENTRIES,
                                'CATALOG_CAPACITY')
                        self._db.execute('INSERT INTO sp_decisions VALUES (?,?,?)', (result, artifactDigest, canonical(decision)))
                    if row['state'] != 'promoted' or row['decision'] != result:
                        self._db.execute('UPDATE sp_artifacts SET state=?,decision=? WHERE digest=?', ('promoted', result, artifactDigest))
                        self._bump()
                    def final_promotion():
                        current = self._row(artifactDigest)
                        require(current['state'] == 'promoted' and current['decision'] == result and
                                current['evaluation'] == row['evaluation'], 'PROMOTION_CHANGED')
                        self._evaluation(current, compiled, held)
                        saved = self._db.execute('SELECT artifact,document FROM sp_decisions WHERE digest=?', (result,)).fetchone()
                        require(saved is not None and saved['artifact'] == artifactDigest and
                                bytes(saved['document']) == canonical(decision), 'PROMOTION_CHANGED')
                    self.journal._require_at_commit(final_promotion)
                    return result

    def suspend(self, context, artifactDigest):
        with self._image():
            with self.journal._transaction():
                self._fresh(context, admin=True)
                row = self._row(artifactDigest)
                if row['state'] != 'suspended':
                    self._db.execute('UPDATE sp_artifacts SET state=? WHERE digest=?', ('suspended', artifactDigest))
                    self._bump()
                self.journal._require_at_commit(lambda: self._fresh(context, admin=True) and None)

    def _inventory(self, request):
        rows = self._db.execute('SELECT * FROM sp_artifacts ORDER BY digest LIMIT ?', (MAX_ENTRIES + 1,)).fetchall()
        require(len(rows) <= MAX_ENTRIES, 'CATALOG_CAPACITY')
        items, candidates = [], []
        for row in rows:
            require(len(row['document']) <= 65536, 'ARTIFACT_LIMIT')
            artifact = document(bytes(row['document']))
            require(artifact_digest(artifact) == row['digest'], 'ARTIFACT_CHANGED')
            items.append([row['digest'], sha(bytes(row['document'])), row['state'], row['evaluation'], row['decision']])
            if artifact.get('taskKind') == request['taskKind'] and artifact.get('inputProfile') == request['inputProfile']:
                if row['state'] == 'promoted':
                    candidates.append(row)
        return canonical({'revision': self._meta('revision'), 'entries': items}), candidates

    @contextmanager
    def hold_selection(self, context, request):
        """Acquire complete applicable evidence before the admission transaction.

        Caller holds policy.hold_image around this scope, then enters the Journal
        transaction and invokes select/check_selection. No filesystem I/O occurs
        in either selection or its registered final commit check.
        """
        request = parse_request(request)
        require(not self._db.in_transaction and self._selection is None, 'SELECTION_REENTRY')
        with self.journal._transaction():
            self._fresh(context)
            inventory, candidates = self._inventory(request)
        require(len(candidates) == 1, 'NO_ELIGIBLE_ARTIFACT' if not candidates else 'AMBIGUOUS_ARTIFACT')
        with self.producer.snapshot(EVALUATOR, self.producer.manifest['runId']) as held:
            self._selection = (context, threading.get_ident(), canonical(request), inventory, held)
            try:
                yield held
            finally:
                self._selection = None

    def _selected(self, context, request):
        installed = self._fresh(context)
        held = self._selection
        require(held is not None and held[0] == context and held[1] == threading.get_ident() and
                held[2] == canonical(request), 'SELECTION_UNAVAILABLE')
        held[4].check()
        inventory, candidates = self._inventory(request)
        require(inventory == held[3] and len(candidates) == 1, 'SELECTION_CHANGED')
        row = candidates[0]
        artifact, compiled = self._compiled(row, installed)
        evaluation = self._evaluation(row, compiled, held[4])
        require(row['decision'] is not None, 'PROMOTION_UNAVAILABLE')
        saved = self._db.execute('SELECT artifact,document FROM sp_decisions WHERE digest=?', (row['decision'],)).fetchone()
        require(saved is not None and len(saved['document']) <= 16384 and saved['artifact'] == row['digest'], 'PROMOTION_UNAVAILABLE')
        decision = document(bytes(saved['document']), 16384)
        expected = {'profile': 'hms.standing-promotion/0.1', 'artifactDigest': row['digest'],
            'evaluationDigest': row['evaluation'], 'compilerDigest': compiled.document['compilerDigest'],
            'installationDigest': self._installation, 'domainDigest': DOMAIN_DIGEST,
            'authority': self.journal.authority_id, 'deployment': context.deployment,
            'physicalEligible': False, 'protectedCapacity': False}
        require(canonical(decision) == canonical(expected) and identity('HMS-STANDING-PROMOTION-v0.1', decision) == row['decision'],
                'PROMOTION_CHANGED')
        require(request['parameters'] == {} and request['evidenceMode'] == artifact['evidenceMode'] and
                all(request['limits'][key] == artifact['limits'][key] for key in LIMITS), 'PAT_DOMAIN_UNQUALIFIED')
        result = {'profile': 'hms.standing-selection/0.1', 'artifactDigest': row['digest'],
            'evaluationDigest': row['evaluation'], 'decisionDigest': row['decision'],
            'compilerDigest': compiled.document['compilerDigest'], 'installationDigest': self._installation,
            'catalogRevision': int(self._meta('revision')), 'artifact': artifact,
            'compilation': compiled.document, 'evaluation': evaluation, 'decision': decision}
        return Selected(canonical(result), compiled.configuration)

    def select(self, context, request):
        request = parse_request(request)
        selected = self._selected(context, request)
        self.check_selection(selected, context)
        return selected

    def check_selection(self, selected, context):
        require(type(selected) is Selected and self._selection is not None, 'SELECTION_UNAVAILABLE')
        request = parse_json(self._selection[2])
        expected, held = selected._wire, self._selection
        def check():
            require(self._selection is held, 'SELECTION_CHANGED')
            current = self._selected(context, request)
            require(current._wire == expected and current.configuration == selected.configuration, 'SELECTION_CHANGED')
        check()
        self.journal._require_at_commit(check)

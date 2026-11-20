"""Bounded pre-run carriers for a finite synthetic I/O group.

The caller retains the returned header, documents and digest before release.
Parsing requires a separately retained digest and trusted logical context;
hash agreement alone authenticates no configuration, process or physical run.
Parsing supplied bytes is pure after module import. Fresh validation separately
rebuilds the setup and reads current installed identities. Neither executes it.
"""
import hashlib
import re

from .contracts import SAFE_INTEGER, ContractError, canonical, parse_json

PROFILE = 'hms.pat.io-run-bundle/0.1'
INPUTS = ('candidate', 'installation', 'descriptor', 'bindings', 'matrix', 'implementation', 'authority')
CONTEXT = ('deployment', 'evaluatorId', 'runId', 'configurationDigest', 'configurationRevision')
MAX_DOCUMENT_BYTES = 65536
MAX_CASES = 32
MAX_DOCUMENTS = len(INPUTS) + MAX_CASES
MAX_INPUT_BYTES = MAX_DOCUMENTS * MAX_DOCUMENT_BYTES
CEILINGS = dict(maxCases=32, maxChildOperations=512, maxSchedulerTicks=2048,
    maxProducerBytes=16*1024*1024, maxRecords=4096, maxDocumentBytes=65536,
    maxDerivedBytes=20*1024*1024, maxWallMs=60000)


class IoRunBundleError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_RUN_BUNDLE_' + code
        super().__init__(self.code)


def _require(value, code):
    if not value: raise IoRunBundleError(code)


def _closed(value, keys, code):
    _require(type(value) is dict and set(value) == set(keys), code)


def _integer(value, low, high, code):
    _require(type(value) is int and low <= value <= high, code)


def _strict(value):
    _require(type(value) in (dict, list, str, int, bool, type(None)), 'SCALAR')
    if type(value) is dict:
        for child in value.values(): _strict(child)
    elif type(value) is list:
        for child in value: _strict(child)


def _document(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_DOCUMENT_BYTES, 'DOCUMENT')
    try:
        value = parse_json(raw); _strict(value)
        _require(canonical(value) == raw, 'CANONICAL')
        return value
    except ContractError as error:
        raise IoRunBundleError('DOCUMENT') from error


def _snapshot(value):
    if type(value) is bytes: return _document(value)
    try:
        raw = canonical(value)  # Bound depth/nodes/types before recursion.
        _strict(value)          # JCS must not turn an original float into int.
        return parse_json(raw)
    except ContractError as error:
        raise IoRunBundleError('DOCUMENT') from error


def _digest(value):
    _require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value), 'DIGEST')


def _hash(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


def _context(value):
    value = _snapshot(value); _closed(value, CONTEXT, 'CONTEXT')
    for key in ('deployment', 'evaluatorId', 'runId'):
        _require(type(value[key]) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}', value[key]), 'CONTEXT')
    _digest(value['configurationDigest'])
    _integer(value['configurationRevision'], 1, SAFE_INTEGER, 'CONTEXT')
    return value


def _authority(value, deployment):
    _closed(value, ('profile', 'principal', 'deployment', 'initialRegistryRevision', 'initialGrants', 'grantChanges'), 'AUTHORITY')
    _integer(value['initialRegistryRevision'], 1, SAFE_INTEGER, 'AUTHORITY')
    owner = dict(principal='pat-io-trial-worker', deployment=deployment)
    expected = owner | dict(profile='hms.pat.io-trusted-authority/0.1',
        initialRegistryRevision=value['initialRegistryRevision'],
        initialGrants=[owner | dict(target='*', verb='admin')], grantChanges=[])
    _require(canonical(value) == canonical(expected), 'AUTHORITY')


def bundle_digest(header):
    """Digest exact bounded header bytes; this alone does not validate a bundle."""
    _require(type(header) is bytes and 0 < len(header) <= MAX_DOCUMENT_BYTES, 'HEADER')
    return 'sha256:' + hashlib.sha256(b'HMS-PAT-IO-RUN-BUNDLE-v0.1\0' + header).hexdigest()


def _paths(count):
    return ['inputs/' + name + '.json' for name in INPUTS] + ['cases/%02d.json' % i for i in range(count)]


def _parse(header, documents, expected_context, expected_bundle_digest):
    context = _context(expected_context); _digest(expected_bundle_digest)
    _require(bundle_digest(header) == expected_bundle_digest, 'HEADER_ASSOCIATION')
    value = _document(header)
    _closed(value, ('profile', 'context', 'manifest', 'inputBytes', 'caseIds', 'matrixDigest', 'inputSetDigest'), 'HEADER')
    _require(value['profile'] == PROFILE, 'PROFILE')
    _require(canonical(_context(value['context'])) == canonical(context), 'CONTEXT_ASSOCIATION')
    ids = value['caseIds']
    _require(type(ids) is list and 1 <= len(ids) <= MAX_CASES, 'CASES')
    for item in ids: _digest(item)
    _require(len(set(ids)) == len(ids), 'CASES')
    paths = _paths(len(ids))
    _require(type(documents) is dict and len(documents) == len(paths) and set(documents) == set(paths), 'CLOSURE')
    _require(all(type(k) is str and type(v) is bytes and 0 < len(v) <= MAX_DOCUMENT_BYTES
        for k, v in documents.items()), 'DOCUMENT')
    _integer(value['inputBytes'], 1, MAX_INPUT_BYTES, 'INPUT_BYTES')
    _require(sum(map(len, documents.values())) == value['inputBytes'], 'INPUT_BYTES')
    manifest = value['manifest']
    _require(type(manifest) is list and len(manifest) == len(paths), 'MANIFEST')
    decoded = {}
    for path, row in zip(paths, manifest):
        _closed(row, ('path', 'bytes', 'sha256'), 'REFERENCE')
        _integer(row['bytes'], 1, MAX_DOCUMENT_BYTES, 'REFERENCE')
        raw = documents[path]
        _require(row['path'] == path and row['bytes'] == len(raw) and
            type(row['sha256']) is str and row['sha256'] == hashlib.sha256(raw).hexdigest(), 'REFERENCE')
        decoded[path] = _document(raw)
    _require(value['inputSetDigest'] == _hash(b'HMS-PAT-IO-INPUT-SET-v0.1', manifest), 'INPUT_SET')
    inputs = {key: decoded['inputs/' + key + '.json'] for key in INPUTS}
    authority = inputs.pop('authority'); matrix = inputs['matrix']
    _authority(authority, context['deployment'])
    _require(inputs['installation']['topology']['deployment'] == context['deployment'], 'DEPLOYMENT')
    _require(matrix['profile'] == 'hms.pat.io-combined-matrix/0.3', 'MATRIX')
    _closed(matrix['limits'], CEILINGS, 'LIMITS')
    for key, maximum in CEILINGS.items(): _integer(matrix['limits'][key], 1, maximum, 'LIMITS')
    _require(len(ids) <= matrix['limits']['maxCases'], 'CASES')
    _require(value['matrixDigest'] == _hash(b'HMS-PAT-IO-COMBINED-MATRIX-v0.1', matrix), 'MATRIX')
    _require(type(matrix['cases']) is list and len(matrix['cases']) == len(ids) and
        [case['caseId'] for case in matrix['cases']] == ids, 'CASES')
    _require(matrix['artifactDigest'] == _hash(b'HMS-PAT-JCS-SHA256-v0.1', inputs['candidate']), 'ARTIFACT')
    identity = inputs['implementation']
    _closed(identity, ('compilerDigest', 'driverDigest', 'workerDigest', 'storageProfile'), 'IDENTITY')
    for key in ('compilerDigest', 'driverDigest', 'workerDigest'): _digest(identity[key])
    _require(identity['driverDigest'] == matrix['driverDigest'] == inputs['installation']['driverDigest'] and
        identity['storageProfile'] == 'hms.sqlite.compact/0.1', 'IDENTITY')
    cases = [decoded['cases/%02d.json' % i] for i in range(len(ids))]
    for expected, case in zip(cases, matrix['cases']):
        _require(type(expected) is dict and canonical(expected['expected_case']) == canonical(case), 'CASE_ASSOCIATION')
        _require(canonical(expected['expected_setup']['installation']) == canonical(inputs['installation']), 'SETUP_ASSOCIATION')
    return dict(context=context, authority=authority, expected_inputs=inputs, expected_cases=cases,
        bundleDigest=expected_bundle_digest)


def parse_io_run_bundle(header, documents, *, expected_context, expected_bundle_digest):
    """Check bounded exact carriers against external anchors; do not replan.

This structural check is not semantic qualification or a fresh identity check.
Returned trees are detached from the input mapping and from each other.
"""
    try:
        return _parse(header, documents, expected_context, expected_bundle_digest)
    except (KeyError, IndexError, TypeError, ContractError) as error:
        raise IoRunBundleError('SHAPE') from error


def prepare_io_run_bundle(*, context, candidate, installation, descriptor, challenge_bindings, authority, limits=None):
    """Build the complete bounded input collection using current trusted code."""
    context = _context(context)
    authority = _snapshot(authority); _authority(authority, context['deployment'])
    # Kept out of the parser's call graph: this setup reads installed identities.
    from .pat_io_group_setup import prepare_io_group
    prepared = prepare_io_group(candidate=candidate, installation=installation, descriptor=descriptor,
        challenge_bindings=challenge_bindings, authority=authority, limits=limits)
    values = prepared['expected_inputs'] | dict(authority=authority)
    cases = prepared['expected_cases']; paths = _paths(len(cases))
    documents = {path: canonical(value) for path, value in zip(paths, [values[k] for k in INPUTS] + cases)}
    manifest = [dict(path=p, bytes=len(documents[p]), sha256=hashlib.sha256(documents[p]).hexdigest()) for p in paths]
    matrix = values['matrix']
    header = canonical(dict(profile=PROFILE, context=context, manifest=manifest,
        inputBytes=sum(map(len, documents.values())), caseIds=[c['caseId'] for c in matrix['cases']],
        matrixDigest=_hash(b'HMS-PAT-IO-COMBINED-MATRIX-v0.1', matrix),
        inputSetDigest=_hash(b'HMS-PAT-IO-INPUT-SET-v0.1', manifest)))
    digest = bundle_digest(header)
    parse_io_run_bundle(header, documents, expected_context=context, expected_bundle_digest=digest)
    return dict(header=header, documents=documents, bundleDigest=digest)


def validate_fresh_io_run_bundle(header, documents, *, expected_context, expected_bundle_digest):
    """Rebuild exact setup before effects; source reads do not attest a process."""
    parsed = parse_io_run_bundle(header, documents, expected_context=expected_context,
        expected_bundle_digest=expected_bundle_digest)
    inputs = parsed['expected_inputs']
    rebuilt = prepare_io_run_bundle(context=parsed['context'], authority=parsed['authority'],
        candidate=inputs['candidate'], installation=inputs['installation'], descriptor=inputs['descriptor'],
        challenge_bindings=inputs['bindings'], limits=inputs['matrix']['limits'])
    _require(rebuilt['header'] == header and rebuilt['documents'] == documents and
        rebuilt['bundleDigest'] == expected_bundle_digest, 'FRESH_MISMATCH')
    return parsed

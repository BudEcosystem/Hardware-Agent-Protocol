"""Pure serialized evaluation; supplied anchors alone authenticate no run."""
from hms.contracts import canonical
from hms.pat_io_run_bundle import parse_io_run_bundle
from hms.pat_io_group_history import inspect_io_group
from .archive import terminal, output_closure
from .contracts import EVALUATION, require, document, sha, hash_value, closure


def anchor(reservation, association, row):
    require(association is not None and row is not None, 'HANDOFF_MISSING')
    returned = terminal(row)
    saved = reservation['reservation']; handoff = association['receipt']
    require(handoff['reservationDigest'] == reservation['reservationDigest'] and
        handoff['requestDigest'] == saved['requestDigest'] == row['record']['requestDigest'] and
        handoff['attemptId'] == row['record']['attemptId'] and
        row['request'] == reservation['preparedRun']['request'] and
        all(handoff[key] == saved[key] for key in ('authorityId', 'deployment', 'evaluatorId', 'runId')), 'ASSOCIATION')
    return dict(authorityId=saved['authorityId'], deployment=saved['deployment'], evaluatorId=saved['evaluatorId'],
        runId=saved['runId'], artifactDigest=saved['artifactDigest'], reservationDigest=reservation['reservationDigest'],
        configurationReceiptDigest=saved['configurationReceiptDigest'],
        configurationDigest=row['request']['context']['configurationDigest'],
        configurationRevision=row['request']['context']['configurationRevision'],
        supervisorAuthorityId=handoff['supervisorAuthorityId'], handoffDigest=association['receiptDigest'],
        requestDigest=saved['requestDigest'], attemptId=handoff['attemptId'], bundleDigest=saved['bundleDigest'],
        producerIdentity=row['request']['supervisorIdentity'], producerImplementation=row['request']['implementation'],
        recordDigest=hash_value(b'HMS-PAT-IO-ORIGINAL-RECORD-v0.1', row['record']),
        returnDigest=sha(row['returnBytes']), groupResultDigest=returned['groupResultDigest'],
        outputClosure=row['record']['archive']['evidenceIntegrity'])


def reduce_original(reservation, association, row, files, consumer_identity):
    """Check every declared case; no runtime, compiler, clock, SQL or I/O calls."""
    anchored = anchor(reservation, association, row)
    require(output_closure(files) == anchored['outputClosure'], 'OUTPUT_CHANGED')
    require(sha(files.get('result.json', b'')) == anchored['groupResultDigest'], 'RESULT_CHANGED')
    bundle = reservation['preparedRun']['bundle']; request = row['request']
    parsed = parse_io_run_bundle(bundle['header'], bundle['documents'], expected_context=request['context'],
                                 expected_bundle_digest=request['bundleDigest'])
    inspected = inspect_io_group(files, expected_inputs=parsed['expected_inputs'], expected_cases=parsed['expected_cases'])
    evidence = {'original/output/' + name: body for name, body in files.items()}
    evidence.update({'original/bundle/' + name: body for name, body in bundle['documents'].items()})
    evidence['original/bundle/header.json'] = bundle['header']
    controls = dict(reservation=reservation['reservation'], handoff=association['receipt'], request=request,
                    attempt=row['record'])
    evidence.update({'original/control/' + name + '.json': canonical(value) for name, value in controls.items()})
    evidence['original/control/return.json'] = row['returnBytes']
    evidence['inspection/summary.json'] = canonical(inspected['summary'])
    for i, result in enumerate(inspected['inspections']):
        evidence['inspection/case-%02d.json' % i] = canonical(result)
    evaluation = dict(profile=EVALUATION, anchor=anchored, consumerIdentity=consumer_identity,
        outcome='passed', scope='complete-finite-synthetic-io-matrix',
        inspectionDigest=sha(evidence['inspection/summary.json']), inspectedCases=len(inspected['inspections']),
        unresolvedEffects=0, physicalObjectiveVerified=False, wallDeadlineAttested=False,
        aggregateDiskQuotaEnforced=False, catalogActivated=False)
    evidence['evaluation.json'] = canonical(evaluation)
    return dict(evaluation=evaluation, documents=evidence, closure=closure(evidence))

"""Prepare bounded trusted checker inputs before a finite synthetic group run.

This is installed setup code, not an independent reader or deployment attestor.
The initial authority revision/grants come from separate trusted configuration.
The caller must retain this bundle before releasing the worker.
"""
import copy

from .contracts import canonical
from .pat_contracts import closed, integer, require, snapshot
from .pat_io_contracts import IoSequencePolicy
from .pat_io_group_worker import _identities
from .pat_io_validated_matrix import ValidatedIoMatrix


def prepare_io_group(*, candidate, installation, descriptor, challenge_bindings, authority, limits=None):
    options = dict(candidate=snapshot(candidate), installation=snapshot(installation),
        descriptor=snapshot(descriptor), challenge_bindings=snapshot(challenge_bindings))
    authority = snapshot(authority)
    closed(authority, {'profile', 'principal', 'deployment', 'initialRegistryRevision', 'initialGrants', 'grantChanges'},
        'PAT_IO_GROUP_SETUP_AUTHORITY')
    integer(authority['initialRegistryRevision'], 1)
    owner = dict(principal='pat-io-trial-worker', deployment=options['installation']['topology']['deployment'])
    require(authority == owner | dict(profile='hms.pat.io-trusted-authority/0.1',
        initialRegistryRevision=authority['initialRegistryRevision'], initialGrants=[owner | dict(target='*', verb='admin')],
        grantChanges=[]), 'PAT_IO_GROUP_SETUP_AUTHORITY')
    plan = ValidatedIoMatrix(**options, limits=limits)
    matrix = plan.matrix()
    policy = IoSequencePolicy(options['installation'])
    programs = {p['digest']: p['artifact'] for p in matrix['programs']}
    contracts = {}
    def setup(digest, chosen):
        key = digest, canonical(chosen)
        if key not in contracts:
            contracts[key] = policy.qualify(programs[digest], chosen)
        return dict(artifact=copy.deepcopy(programs[digest]), installation=copy.deepcopy(options['installation']),
            original_descriptor=copy.deepcopy(chosen), static_contract=copy.deepcopy(contracts[key]))
    expected = []
    for case in matrix['cases']:
        if case['kind'] == 'resource_challenge':
            actors = {}
            for role, actor in case['actors'].items():
                value = setup(actor['programDigest'], options['challenge_bindings'][role]['descriptor'])
                del value['installation']; actors[role] = value
            args = dict(expected_setup=actors['gpio'] | {'installation': copy.deepcopy(options['installation'])},
                expected_case=copy.deepcopy(case), expected_actors=actors, expected_authority=copy.deepcopy(authority))
        else:
            args = dict(expected_setup=setup(case['programDigest'], options['descriptor']),
                expected_case=copy.deepcopy(case), expected_authority=copy.deepcopy(authority))
            if case['kind'] == 'fixed_challenge':
                name = case['definition']['scenario']
                if name in {'binding_before_dispatch', 'binding_pending', 'full_authority_withdrawal'}:
                    args.pop('expected_authority')
                    args['expected_authority_change'] = owner | dict(
                        initialRegistryRevision=authority['initialRegistryRevision'],
                        initialGrants=copy.deepcopy(authority['initialGrants']),
                        action=case['definition']['control']['action'],
                        phase=4 if name == 'binding_before_dispatch' else 5,
                        target=options['descriptor']['binding']['instanceId'])
                phases = {'permission_before_parent': (2, 'submit:before'),
                    'permission_before_dispatch': (4, 'drive:adapters:before'),
                    'permission_pending': (5, 'drive:adapters:before'),
                    'permission_after_completion': (6, 'drive:adapters:before')}
                if name in phases:
                    phase, label = phases[name]
                    args['expected_authority']['grantChanges'] = [dict(phase=phase, label=label,
                        grants=[owner | dict(target=options['descriptor']['binding']['instanceId'], verb='read')])]
                if name in {'cancel_accepted', 'cancel_pending', 'reopen_accepted', 'reopen_pending',
                        'completion_reply_lost', 'pending_reply_lost', *phases}:
                    faults = []
                    if name in {'completion_reply_lost', 'pending_reply_lost', 'permission_after_completion'}:
                        begin = name == 'pending_reply_lost'
                        faults = [dict(phase=4 if begin else 5, label='drive:adapters',
                            point='board.begin.after_commit' if begin else 'journal.record_execution.before_commit',
                            exception='JournalError', code='injected:io_begin_reply_loss' if begin else
                            'injected:io_lifecycle_completion_reply_loss', occurrences=1)]
                    args['expected_faults'] = faults
        canonical(args)  # Each setup is an individually bounded carrier.
        expected.append(args)
    inputs = dict(candidate=options['candidate'], installation=options['installation'], descriptor=options['descriptor'],
        bindings=options['challenge_bindings'], matrix=matrix, implementation=_identities())
    for value in inputs.values(): canonical(value)
    return dict(expected_inputs=inputs, expected_cases=expected)

"""Independent same-key conflict and exact-replay checks over paired histories.

Only the explicit v0.2 trial profile is accepted. Trusted configuration/grants,
PAT correspondence, device effects, operation events and parent state are joined;
no runtime/compiler/provider is imported and no effect or qualification is run.
"""
import copy
import hashlib

from .contracts import canonical, parse_json
from .pat_io_authorized_history import _guards
from .pat_io_board_history import _reduce as _board, _tables
from .pat_io_configuration_history import _validated_configuration_history
from .pat_io_correspondence import _Program, _inspect as _correspondence
from .pat_io_observation_history import _samples
from .pat_io_operation_history import _fold as _operations
from .pat_io_procedure_history import _fold as _procedures
from .pat_io_refusal_history import _refusals


class IoConflictHistoryError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_CONFLICT_' + code
        super().__init__(self.code)


def require(value, code):
    if not value: raise IoConflictHistoryError(code)


def _one(rows, code):
    require(len(rows) == 1, code)
    return rows[0]


def _digest(value):
    return 'sha256:' + hashlib.sha256(b'HMS-PROCEDURE-JCS-SHA256-v0.1\0' + canonical(value)).hexdigest()


def _probes(transcript, snapshots, permissions, expected_setup, expected_authority):
    program = _Program(expected_setup); model = program.model
    plan = _one([r['value']['request'] for r in transcript['records'] if r['kind'] == 'compiled_plan'], 'PLAN')
    changed = copy.deepcopy(plan)
    args = changed['procedure']['steps'][0]['request']['intent']['arguments']
    if model.details[model.target]['primitive'] == 'gpio_pulse':
        args['level'] = 0 if args['level'] == 1 else 1
    else:
        args['dutyPermille'] = 0 if args['dutyPermille'] == 1000 else args['dutyPermille'] + 1
    expected_digest = _digest(changed)
    require(expected_digest != _digest(plan), 'UNCHANGED_REQUEST')
    calls = {c['phase']: c for c in transcript['calls']}
    frames = {s['checkpoint']['record']: s for s in snapshots}
    before = {}; conflicts = {}; checked = []; replays = []
    for cp in transcript['checkpoints']:
        value = cp['value']; phase, label = value['phase'], value['label']
        if label.endswith(':before'):
            before[phase] = cp; continue
        if not label.endswith((':after', ':after_error')): continue
        prior = before.pop(phase); call = calls[phase]
        if call['label'] not in {'submit', 'submit_conflict'}: continue
        old = _tables(transcript, prior); current = _tables(transcript, cp)
        if call['label'] == 'submit' and not old['pr_procedures']: continue
        namespace = _one([n for n in old['namespaces'] if n['token'] == plan['replayNamespace']], 'NAMESPACE')
        series = _one(old['series'], 'NAMESPACE')
        owner = expected_authority['principal'], expected_authority['deployment']
        require((namespace['principal'], namespace['deployment']) == owner and
                (series['principal'], series['deployment']) == owner and
                namespace['epoch'] >= series['floor'], 'NAMESPACE_PRECEDENCE')
        # Existing-key replay checks the retained namespace floor; elapsed expiry
        # and fresh-admission deadlines are not replay predicates.
        reservation = _one([r for r in old['pr_keys'] if r['namespace'] == plan['replayNamespace'] and
                            r['caller_key'] == plan['procedureKey']], 'PARENT_KEY')
        parent = _one([r for r in old['pr_procedures'] if r['id'] == reservation['procedure_id']], 'PARENT')
        require(reservation['step_id'] is None and (parent['principal'], parent['deployment']) == owner and
                parent['digest'] == _digest(plan) and canonical(parse_json(parent['request'])) == canonical(plan), 'PARENT_REQUEST')
        require(permissions[prior['record']] == permissions[cp['record']] and permissions[prior['record']]['read'], 'READ_PRECEDENCE')
        require(current == old, 'EXECUTION_MUTATION')
        old_config, new_config = frames[prior['record']], frames[cp['record']]
        require(old_config['tables'] == new_config['tables'] and old_config['resolver'] == new_config['resolver'] and
                all(old_config['value'][k] == new_config['value'][k] for k in ('authorityId', 'ownerEpoch', 'session')), 'CONFIGURATION_MUTATION')
        if call['label'] == 'submit_conflict':
            supplied = call['conflictInput']
            require(canonical(supplied['request']) == canonical(changed) and supplied['requestDigest'] == expected_digest, 'REQUEST')
            model.intent(supplied['request']['procedure']['steps'][0]['request']['intent'])
            require(not call['returned'] and call['outcome']['exception'] == 'JournalError' and
                    call['outcome']['code'] == 'KEY_CONFLICT', 'CAUSE')
            conflicts[cp['record']] = 'KEY_CONFLICT'
            checked.append(dict(phase=phase, procedureId=parent['id'], originalDigest=parent['digest'],
                                conflictingDigest=expected_digest, code='KEY_CONFLICT', additionalChildOperations=0))
        else:
            require(call['returned'], 'REPLAY_REFUSAL')
            replays.append(dict(phase=phase, procedureId=parent['id'], additionalChildOperations=0))
    require(not before and len(conflicts) == 1 and replays, 'PROBE_INVENTORY')
    return conflicts, checked, replays


def inspect_conflict_history(references, files, configuration, configuration_files, *, expected_setup, expected_authority):
    """Inspect one recorded conflict and at least one exact parent replay.

The accepted context retains read authority and uses the original namespace and
all original parent/child keys. Lost replies and full-read withdrawal require
their separately versioned extensions; an error string alone proves no cause.
"""
    transcript, snapshots, permissions, denied, config = _validated_configuration_history(
        references, files, configuration, configuration_files, expected_setup=expected_setup,
        expected_authority=expected_authority, conflict_profile=True)
    correspondence = _correspondence(transcript, expected_setup)
    require(all(c['returned'] or c['label'] in {'submit_conflict', 'submit', 'resume'}
                for c in transcript['calls']), 'UNSUPPORTED_FAILURE')
    conflicts, probes, replays = _probes(transcript, snapshots, permissions, expected_setup, expected_authority)
    parents, children, refusals = _refusals(transcript, snapshots, permissions)
    causes, guards = _guards(transcript, snapshots, permissions, denied)
    board = _board(transcript, expected_setup, checked_causes=causes)
    operations = _operations(transcript, expected_setup, checked_refusals=children)
    procedures = _procedures(transcript, checked_refusals=parents, checked_conflicts=conflicts)
    result = dict(profile='hms.pat.io-conflict-history-inspection/0.1',
        sameKeyConflictChecked=True, exactReplayChecked=True, configurationHistoryChecked=True,
        patCorrespondenceChecked=True, boardHistoryChecked=True, operationHistoryChecked=True,
        procedureHistoryChecked=True, observationSampleSemanticsChecked=True, trustedGrantPlanMatched=True,
        conflictsChecked=probes, replaysChecked=replays, refusalsChecked=refusals, guardsChecked=guards,
        configuration=config, correspondence=correspondence, board=board, operations=operations,
        procedures=procedures, sampling=_samples(transcript, snapshots), configurationAttested=False,
        compilerIdentityAttested=False, independentOutcomeChecked=False, allFaultScenariosChecked=False,
        physicalMeasurementChecked=False, qualificationPassed=False)
    canonical(result)
    return result

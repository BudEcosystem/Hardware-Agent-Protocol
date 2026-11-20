"""Pure reader for complete finite-I/O phase transcripts.

This checks the closed serialization and phase grammar. It neither imports the
producer/provider nor decides effect correctness, settlement or qualification.
The caller supplies separately trusted setup; files are already acquired bytes.
"""
from __future__ import annotations

import hashlib
import re

from .contracts import ContractError, SAFE_INTEGER, canonical, identifier, parse_json

PROFILE = 'hms.pat.io-trial-record/0.1'
MAX_RECORDS = 4096
MAX_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT = 65536
ORIGIN = 1000000
SETUP = ('artifact', 'installation', 'original_descriptor', 'static_contract')
CALLS = {'lower', 'submit', 'cancel', 'resume', 'drive:cycle', 'drive:procedure', 'drive:adapters'}

# Independent closed wire table grammar: columns, SQLite scalar kinds, primary
# key columns and row ceiling. t=text, b=canonical UTF-8 JSON BLOB, i=integer.
# A ? allows SQL NULL. No SQL, provider schema or producer constants are imported.
SCHEMAS = {
    'board': {
        'io_meta': ('key,value', 't t', 'key', 32),
        'io_resources': ('resource,state', 't b', 'resource', 128),
        'io_owners': ('resource,operation,fence', 't t i', 'resource', 128),
        'io_fences': ('resource,fence,operation', 't i t', 'resource', 128),
        'io_receipts': ('operation,state,sequence,digest,document', 't t i t b', 'operation', 16),
        'io_receipt_versions': ('operation,sequence,digest,document', 't i t b', 'operation,sequence', 32),
        'io_effects': ('instance,activations,completed,canceled', 't i i i', 'instance', 128),
    },
    'authority': {
        'meta': ('key,value', 't t', 'key', 32),
        'series': ('principal,deployment,next_epoch,floor,last_expiry', 't t i i i', 'principal,deployment', 1),
        'namespaces': ('token,principal,deployment,epoch,expires_ms', 't t t i i', 'token', 1),
        'operations': ('id,principal,deployment,digest,intent,admission,state,cancel_state,verification,may_have_acted,sequence,attempt_id,owner_epoch', 't t t t b b t t t i i t? i', 'id', 16),
        'replay_keys': ('namespace,caller_key,operation_id', 't t t', 'namespace,caller_key', 16),
        'resource_floors': ('deployment,resource,fence', 't t i', 'deployment,resource', 128),
        'claims': ('deployment,resource,operation_id,fence', 't t t i', 'deployment,resource', 128),
        'events': ('operation_id,sequence,time_ms,clock_status,kind,payload', 't i i t t b', 'operation_id,sequence', 1024),
        'io_dispatch_links': ('operation,document,digest', 't b t', 'operation', 16),
        'io_authority_receipts': ('operation,sequence,document,digest', 't i b t', 'operation,sequence', 32),
        'pr_meta': ('key,value', 't t', 'key', 8),
        'pr_procedures': ('id,principal,deployment,digest,request,state,reason,cursor,cancel_requested,cancel_delivery,sequence', 't t t t b t t? i i b i', 'id', 1),
        'pr_steps': ('procedure_id,ordinal,step_id,request,digest,operation_id', 't i t b t t?', 'procedure_id,ordinal', 16),
        'pr_keys': ('namespace,caller_key,procedure_id,step_id', 't t t t?', 'namespace,caller_key', 17),
        'pr_events': ('procedure_id,sequence,time_ms,clock_status,kind,payload', 't i i t t b', 'procedure_id,sequence', 1024),
        'rt_catalog': ('singleton,profile,legacy,owner', 'i t i t', 'singleton', 1),
        'rt_adapters': ('adapter,document,digest,ready', 't b t i', 'adapter', 16),
        'rt_io_installation': ('singleton,document,digest', 'i b t', 'singleton', 1),
        'rc_catalog': ('singleton,profile,topology,topology_digest,routes,routes_digest,current_revision', 'i t b t b t i', 'singleton', 1),
        'rc_generations': ('revision,document,digest', 'i b t', 'revision', 1),
        'rc_tokens': ('node,generation,revision', 't t i', 'node,generation', 128),
        'rc_proofs': ('instance,generation,revision,document,digest,binding_digest', 't t i b t t', 'instance,generation', 128),
    },
}
TABLES = {(store, table) for store, tables in SCHEMAS.items() for table in tables}


class IoTranscriptError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(value, code='PAT_IO_TRANSCRIPT_SHAPE'):
    if not value:
        raise IoTranscriptError(code)


def closed(value, fields):
    require(type(value) is dict and set(value) == set(fields))


def integer(value, lo=0, hi=SAFE_INTEGER):
    require(type(value) is int and lo <= value <= hi)
    return value


def document(body):
    require(type(body) is bytes and 1 <= len(body) <= MAX_DOCUMENT, 'PAT_IO_TRANSCRIPT_BOUNDS')
    value = parse_json(body)
    require(canonical(value) == body, 'PAT_IO_TRANSCRIPT_CANONICAL')
    return value


def cell(value, expected):
    closed(value, {'type', 'value'})
    kind, data = value['type'], value['value']
    if kind == 'null':
        require(expected.endswith('?') and data is None, 'PAT_IO_TRANSCRIPT_CELL')
        return None
    expected = expected.rstrip('?')
    require(kind == {'t': 'text', 'b': 'blob-utf8', 'i': 'integer'}[expected], 'PAT_IO_TRANSCRIPT_CELL')
    if expected == 'i':
        return integer(data, -SAFE_INTEGER)
    require(type(data) is str and len(data) <= MAX_DOCUMENT, 'PAT_IO_TRANSCRIPT_CELL')
    body = data.encode('utf-8')
    require(len(body) <= MAX_DOCUMENT, 'PAT_IO_TRANSCRIPT_BOUNDS')
    if expected == 'b':
        document(body)
        return body
    return data


def sqlite_order(row):
    # SQLite's BINARY order for this profile: NULL, integer, UTF-8 text, BLOB.
    return tuple((0, 0) if value is None else (1, value) if type(value) is int else
                 (2, value.encode('utf-8')) if type(value) is str else (3, value) for value in row)


def page(value):
    closed(value, {'store', 'table', 'columns', 'first', 'totalRows', 'rows'})
    key = (value['store'], value['table'])
    require(key in TABLES, 'PAT_IO_TRANSCRIPT_TABLE')
    fields, types, _, limit = SCHEMAS[key[0]][key[1]]
    columns, types = fields.split(','), types.split()
    require(value['columns'] == columns and type(value['columns']) is list, 'PAT_IO_TRANSCRIPT_COLUMNS')
    total = integer(value['totalRows'], 0, limit)
    first = integer(value['first'], 0, max(0, total - 1))
    require(first % 8 == 0 and type(value['rows']) is list and
            len(value['rows']) == min(8, total - first), 'PAT_IO_TRANSCRIPT_PAGES')
    rows = []
    for raw in value['rows']:
        require(type(raw) is list and len(raw) == len(columns), 'PAT_IO_TRANSCRIPT_COLUMNS')
        rows.append(tuple(cell(v, t) for v, t in zip(raw, types)))
    return {'key': key, 'first': first, 'total': total, 'rows': tuple(rows)}


def _read(references, files, expected_setup):
    require(type(references) is list and 1 <= len(references) <= MAX_RECORDS, 'PAT_IO_TRANSCRIPT_BOUNDS')
    require(type(files) is dict and len(files) == len(references), 'PAT_IO_TRANSCRIPT_INVENTORY')
    closed(expected_setup, SETUP)
    expected = {kind: canonical(expected_setup[kind]) for kind in SETUP}
    refs, docs, pages, used, fingerprints = {}, [], {}, set(), set()
    total = 0
    for index, reference in enumerate(references):
        closed(reference, {'path', 'bytes', 'sha256'})
        name = '%06d.json' % index
        require(reference['path'] == name and name in files, 'PAT_IO_TRANSCRIPT_INVENTORY')
        integer(reference['bytes'], 1, MAX_DOCUMENT)
        require(type(reference['sha256']) is str and re.fullmatch('[0-9a-f]{64}', reference['sha256']) is not None)
        body = files[name]
        require(type(body) is bytes and len(body) == reference['bytes'], 'PAT_IO_TRANSCRIPT_HASH')
        total += len(body)
        require(total <= MAX_BYTES, 'PAT_IO_TRANSCRIPT_BOUNDS')
        require(hashlib.sha256(body).hexdigest() == reference['sha256'], 'PAT_IO_TRANSCRIPT_HASH')
        value = document(body)
        closed(value, {'profile', 'kind', 'value'})
        require(value['profile'] == PROFILE and type(value['kind']) is str)
        refs[name] = reference
        docs.append(value)
        if index < 4:
            require(value['kind'] == SETUP[index] and canonical(value['value']) == expected[SETUP[index]],
                    'PAT_IO_TRANSCRIPT_SETUP')
        elif value['kind'] == 'table_page':
            require(reference['sha256'] not in fingerprints, 'PAT_IO_TRANSCRIPT_DUPLICATE_PAGE')
            fingerprints.add(reference['sha256'])
            pages[name] = page(value['value'])
    require(set(files) == set(refs), 'PAT_IO_TRANSCRIPT_INVENTORY')

    def checkpoint(value, position):
        closed(value, {'phase', 'label', 'wallMs', 'monotonicMs', 'clockEpoch', 'tables'})
        integer(value['phase'], 0, MAX_RECORDS)
        require(type(value['label']) is str and len(value['label']) <= 128)
        require(type(value['tables']) is list and len(value['tables']) == len(TABLES), 'PAT_IO_TRANSCRIPT_TABLES')
        seen, tables = set(), {}
        for table in value['tables']:
            closed(table, {'store', 'table', 'rowCount', 'pages'})
            key = (table['store'], table['table'])
            require(key in TABLES and key not in seen, 'PAT_IO_TRANSCRIPT_TABLES')
            seen.add(key)
            columns, _, primary, limit = SCHEMAS[key[0]][key[1]]
            columns = columns.split(',')
            count = integer(table['rowCount'], 0, limit)
            require(type(table['pages']) is list and len(table['pages']) == max(1, (count + 7) // 8),
                    'PAT_IO_TRANSCRIPT_PAGES')
            previous, keys, found = None, set(), 0
            for reference in table['pages']:
                closed(reference, {'path', 'bytes', 'sha256'})
                name = reference['path']
                require(type(name) is str and name in pages and refs[name] == reference and
                        int(name[:6]) < position, 'PAT_IO_TRANSCRIPT_REFERENCE')
                retained = pages[name]
                require(retained['key'] == key and retained['first'] == found and retained['total'] == count,
                        'PAT_IO_TRANSCRIPT_PAGES')
                used.add(name)
                for row in retained['rows']:
                    order = sqlite_order(row)
                    require(previous is None or previous < order, 'PAT_IO_TRANSCRIPT_ROW_ORDER')
                    previous = order
                    primary_key = tuple(row[columns.index(c)] for c in primary.split(','))
                    require(primary_key not in keys and None not in primary_key, 'PAT_IO_TRANSCRIPT_PRIMARY_KEY')
                    keys.add(primary_key)
                found += len(retained['rows'])
            require(found == count, 'PAT_IO_TRANSCRIPT_PAGES')
            tables[key] = tuple(r['path'] for r in table['pages'])
        return tables

    state, clock, phase, ticks = 'open_first', ORIGIN, 0, 0
    active = None
    opened, sessions, checkpoints, calls = [], set(), [], []
    lower_seen = plan_seen = False
    final_observation = None
    written = sum(references[i]['bytes'] for i in range(min(4, len(references))))
    for index, record in enumerate(docs[4:], 4):
        kind, value = record['kind'], record['value']
        require(state != 'done', 'PAT_IO_TRANSCRIPT_TRAILING')
        if kind == 'table_page':
            require(state in {'baseline', 'ready', 'after_call', 'after_reopen'}, 'PAT_IO_TRANSCRIPT_PHASE')
        elif kind == 'runtime_opened':
            closed(value, {'create', 'wallMs', 'ownerEpoch', 'authorityId', 'session', 'originalEnvironment', 'workerEnvironment'})
            require(state in {'open_first', 'open_again'}, 'PAT_IO_TRANSCRIPT_PHASE')
            integer(value['wallMs']); integer(value['ownerEpoch'], 1)
            identifier(value['authorityId']); identifier(value['session'])
            require(value['wallMs'] == clock and value['create'] is (state == 'open_first'), 'PAT_IO_TRANSCRIPT_CLOCK')
            require(value['session'] not in sessions, 'PAT_IO_TRANSCRIPT_SESSION')
            if opened:
                require(value['authorityId'] == opened[-1]['authorityId'] and
                        value['ownerEpoch'] == opened[-1]['ownerEpoch'] + 1 and
                        canonical(value['originalEnvironment']) == canonical(opened[0]['originalEnvironment']),
                        'PAT_IO_TRANSCRIPT_REOPEN')
            else:
                require(value['ownerEpoch'] == 1, 'PAT_IO_TRANSCRIPT_REOPEN')
            sessions.add(value['session']); opened.append(value)
            state = 'baseline' if value['create'] else 'after_reopen'
        elif kind == 'checkpoint':
            tables = checkpoint(value, index)
            require(opened and type(value['wallMs']) is int and type(value['monotonicMs']) is int and
                    value['wallMs'] == value['monotonicMs'] == clock and
                    value['clockEpoch'] == opened[-1]['authorityId'] + ':' + str(opened[-1]['ownerEpoch']),
                    'PAT_IO_TRANSCRIPT_CLOCK')
            label = value['label']
            if state in {'baseline', 'after_reopen'}:
                require(label == state and value['phase'] == phase, 'PAT_IO_TRANSCRIPT_PHASE')
                state = 'ready'
            elif state == 'final_report':
                # Diagnostic re-capture may repeat the final snapshot. It may
                # introduce no changed table, phase, clock or intervening action.
                require(docs[index-1]['kind'] == 'checkpoint' and value == checkpoints[-1]['value'],
                        'PAT_IO_TRANSCRIPT_PHASE')
            elif state == 'after_call':
                expected_label = active['label'] + (':after' if active['returned'] else ':after_error')
                require(label == expected_label and value['phase'] == phase, 'PAT_IO_TRANSCRIPT_PHASE')
                state = 'plan' if active['label'] == 'lower' and active['returned'] else 'ready'
                calls.append(active); active = None
            else:
                require(state == 'ready', 'PAT_IO_TRANSCRIPT_PHASE')
                if label in {'before_reopen', 'test_final'}:
                    require(value['phase'] == phase, 'PAT_IO_TRANSCRIPT_PHASE')
                    state = 'open_again' if label == 'before_reopen' else 'final_report'
                else:
                    require(label.endswith(':before') and label[:-7] in CALLS and value['phase'] == phase + 1,
                            'PAT_IO_TRANSCRIPT_PHASE')
                    phase += 1
                    active = {'label': label[:-7], 'phase': phase, 'clock': clock}
                    state = 'call_start'
            checkpoints.append({'record': index, 'value': value, 'tables': tables})
        elif kind == 'call_started':
            closed(value, {'phase', 'label', 'clock'})
            require(state == 'call_start' and value == active, 'PAT_IO_TRANSCRIPT_PHASE')
            integer(value['phase']); integer(value['clock'])
            if value['label'] == 'lower':
                require(lower_seen and phase == 1 and not plan_seen, 'PAT_IO_TRANSCRIPT_PHASE')
            if value['label'] == 'submit':
                require(plan_seen, 'PAT_IO_TRANSCRIPT_PHASE')
            if value['label'].startswith('drive:'):
                ticks += 1
                require(ticks <= 2048, 'PAT_IO_TRANSCRIPT_BOUNDS')
            state = 'call_end'
        elif kind in {'call_returned', 'call_failed'}:
            fields = {'phase', 'label', 'clock', 'result'} if kind == 'call_returned' else {'phase', 'label', 'clock', 'exception', 'code'}
            closed(value, fields)
            require(state == 'call_end' and all(value[key] == active[key] for key in ('phase', 'label', 'clock')),
                    'PAT_IO_TRANSCRIPT_PHASE')
            integer(value['phase']); integer(value['clock'])
            if kind == 'call_failed':
                require(type(value['exception']) is str and (value['code'] is None or type(value['code']) is str))
            active.update(returned=kind == 'call_returned', outcome=value)
            state = 'after_call'
        elif kind == 'clock_advanced':
            closed(value, {'from', 'to'})
            integer(value['from']); integer(value['to'], clock + 1)
            require(state == 'ready' and value['from'] == clock, 'PAT_IO_TRANSCRIPT_CLOCK')
            clock = value['to']
        elif kind == 'lower_input':
            closed(value, {'parameters', 'context'})
            require(state == 'ready' and phase == 0 and not lower_seen and
                    type(value['parameters']) is dict and type(value['context']) is dict, 'PAT_IO_TRANSCRIPT_PHASE')
            for tagged in value['parameters'].values():
                closed(tagged, {'type', 'value'})
                tag, raw = tagged['type'], tagged['value']
                require((tag == 'integer' and type(raw) is int or tag == 'number' and type(raw) in {int, float} or
                         tag == 'string' and type(raw) is str or tag == 'boolean' and type(raw) is bool or
                         tag == 'null' and raw is None), 'PAT_IO_TRANSCRIPT_PARAMETER_TAG')
            lower_seen = True
        elif kind == 'compiled_plan':
            require(state == 'plan' and not plan_seen and canonical(value) == canonical(calls[-1]['outcome']['result']),
                    'PAT_IO_TRANSCRIPT_PLAN')
            plan_seen = True; state = 'ready'
        elif kind == 'trial_observation':
            closed(value, {'profile', 'clock', 'procedure', 'operationIds', 'unresolvedOperations', 'schedulerTicks',
                           'evidenceRecords', 'evidenceBytes', 'qualificationPassed', 'independentOutcomeChecked'})
            require(state in {'ready', 'final_report'} and value['profile'] == 'hms.pat.io-trial-observation/0.1' and
                    value['qualificationPassed'] is False and value['independentOutcomeChecked'] is False,
                    'PAT_IO_TRANSCRIPT_OBSERVATION')
            for name, expected_value in [('clock', clock), ('schedulerTicks', ticks),
                                          ('evidenceRecords', index), ('evidenceBytes', written)]:
                integer(value[name]); require(value[name] == expected_value, 'PAT_IO_TRANSCRIPT_OBSERVATION')
            for key in ['operationIds', 'unresolvedOperations']:
                require(type(value[key]) is list and len(value[key]) <= 16 and
                        all(type(v) is str for v in value[key]) and len(set(value[key])) == len(value[key]))
                for identity in value[key]:
                    identifier(identity)
            require(set(value['unresolvedOperations']) <= set(value['operationIds']))
            require(value['procedure'] is None or type(value['procedure']) is dict)
            if state == 'final_report':
                final_observation = value; state = 'done'
        else:
            raise IoTranscriptError('PAT_IO_TRANSCRIPT_KIND')
        written += references[index]['bytes']
    require(state == 'done' and used == set(pages), 'PAT_IO_TRANSCRIPT_INCOMPLETE')
    return {'records': docs, 'pages': pages, 'checkpoints': checkpoints, 'calls': calls,
            'opened': opened, 'lastClock': clock, 'ticks': ticks, 'bytes': total,
            'finalObservation': final_observation}


def inspect_transcript(references, files, *, expected_setup):
    """Check acquired bytes without I/O; return no qualification or effect claim.

    expected_setup must come from the trusted trial configuration. Extracting it
    from an untrusted transcript would not establish the intended association.
    Startup of shared contract parsing imports its pinned schema/dependencies;
    this function itself reads no files, clocks, database or provider state.
    """
    try:
        value = _read(references, files, expected_setup)
        observation = value['finalObservation']
        return {'profile': 'hms.pat.io-transcript-inspection/0.1',
            'recordCount': len(value['records']), 'recordBytes': value['bytes'],
            'checkpointCount': len(value['checkpoints']), 'callCount': len(value['calls']),
            'runtimeOpens': len(value['opened']), 'lastClock': value['lastClock'],
            'schedulerTicks': value['ticks'], 'serializationChecked': True,
            'producerReportedUnresolved': list(observation['unresolvedOperations']),
            'independentOutcomeChecked': False, 'qualificationPassed': False}
    except IoTranscriptError:
        raise
    except (ContractError, KeyError, TypeError, ValueError, IndexError, UnicodeError, RecursionError) as error:
        raise IoTranscriptError('PAT_IO_TRANSCRIPT_SHAPE') from error

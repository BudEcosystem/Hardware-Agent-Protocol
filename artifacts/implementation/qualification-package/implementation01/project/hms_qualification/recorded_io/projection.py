"""Bounded main-schema snapshots usable under the catalog SELECT-only guard.

These reads authenticate no caller data. A prepared entry is inserted only after
the actual installed consumer and complete original-run reducer agree. Current
reads compare exact control bytes and selected evidence, not stored pass flags.
"""
from hms.contracts import SAFE_INTEGER
from hms_qualification.evidence.contracts import MAX_DOCUMENT_BYTES, MAX_STORE_BYTES, MAX_STORE_DOCUMENTS, sha
from .contracts import require, MAX_MEMO_BYTES

I = ('integer', SAFE_INTEGER)
T = ('text', 128)
B = ('blob', 4096)
TABLES = (
    ('iosc_meta', 1, (('singleton', I), ('record', B))),
    ('iosc_versions', 128, (('sequence', I), ('evaluator', T), ('revision', I),
        ('configuration', ('blob', 65536)), ('pin', B), ('receipt', B))),
    ('iosc_mutations', 128, (('principal', T), ('operation_key', T), ('request', ('blob', 2048)), ('sequence', I))),
    ('iosr_meta', 1, (('singleton', I), ('record', B))),
    ('iosr_runs', 32, (('sequence', I), ('evaluator', T), ('run', T), ('intent', ('blob', 2048)),
        ('configuration_sequence', I), ('request', ('blob', 65536)), ('receipt', B))),
    ('iosr_documents', 32 * 39, (('sequence', I), ('path', ('text', 256)), ('body', ('blob', 65536)))),
    ('iose_meta', 1, (('singleton', I), ('record', B))),
    ('iose_handoffs', 32, (('sequence', I), ('evaluator', T), ('run', T), ('receipt', B))),
    ('ioec_meta', 1, (('singleton', I), ('record', ('blob', 16384)))),
    ('ioec_runs', 32, (('sequence', I), ('evaluator', T), ('run', T), ('receipt', ('blob', 16384)))),
    ('ioec_documents', MAX_STORE_DOCUMENTS, (('sequence', I), ('path', ('text', 288)), ('digest', ('text', 71)))),
)
ANCHORS = ('deployment', 'version', 'io_service_configuration', 'hms_qualification.supervisor.io_service_runs',
           'hms_qualification.supervisor.io_service_execution', 'io_evidence_compact')

def _charge(rows):
    return sum(512 + sum(len(value.encode('utf-8')) if type(value) is str else
                        len(value) if type(value) is bytes else 32 for value in row) for row in rows)

def scan(db, table, fields, maximum, *, where='', parameters=(), remaining=MAX_MEMO_BYTES):
    """Only source-constant table/field/where specifications reach this helper."""
    require(db.in_transaction, 'TRANSACTION_REQUIRED')
    suffix = ' FROM main.' + table + where + ' LIMIT ?'
    args = tuple(parameters) + (maximum + 1,)
    types = db.execute('SELECT ' + ','.join('typeof(' + field + ')' for field, _ in fields) + suffix, args).fetchall()
    require(len(types) <= maximum, 'READ_BOUND')
    for row in types:
        require(tuple(row) == tuple(kind for _, (kind, _) in fields), 'STORAGE_TYPE')
    sized = [(field, kind, limit) for field, (kind, limit) in fields if kind != 'integer']
    if sized:
        sizes = db.execute('SELECT ' + ','.join('length(' + field + ')' if kind == 'blob'
            else 'length(CAST(' + field + ' AS BLOB))' for field, kind, _ in sized) + suffix, args).fetchall()
        require(len(sizes) == len(types), 'STORAGE_CHANGED')
        for row in sizes:
            require(all(type(value) is int and 0 <= value <= spec[2]
                        for value, spec in zip(row, sized)), 'READ_BOUND')
        require(sum(sum(row) + 512 + 32 * len(fields) for row in sizes) <= remaining, 'PREPARATION_CAPACITY')
    else:
        require(len(types) * (512 + 32 * len(fields)) <= remaining, 'PREPARATION_CAPACITY')
    rows = tuple(tuple(row) for row in db.execute('SELECT ' + ','.join(field for field, _ in fields) + suffix, args))
    require(len(rows) == len(types), 'STORAGE_CHANGED')
    for row in rows:
        for value, (_, (kind, limit)) in zip(row, fields):
            if kind == 'integer':
                require(type(value) is int and 0 <= value <= limit, 'STORAGE_TYPE')
    require(_charge(rows) <= remaining, 'PREPARATION_CAPACITY')
    return tuple(sorted(rows))

def point(db, table, fields, where, parameters):
    rows = scan(db, table, fields, 1, where=where, parameters=parameters)
    require(len(rows) == 1, 'ASSOCIATION_UNAVAILABLE')
    return rows[0]

def schema(db):
    # Prefix ranges preserve schema ownership without SQL function callbacks.
    suffix = " FROM main.sqlite_master WHERE (name COLLATE BINARY >= 'iosc_' AND name COLLATE BINARY < 'iosc`') OR (tbl_name COLLATE BINARY >= 'iosc_' AND tbl_name COLLATE BINARY < 'iosc`') OR (name COLLATE BINARY >= 'iosr_' AND name COLLATE BINARY < 'iosr`') OR (tbl_name COLLATE BINARY >= 'iosr_' AND tbl_name COLLATE BINARY < 'iosr`') OR (name COLLATE BINARY >= 'iose_' AND name COLLATE BINARY < 'iose`') OR (tbl_name COLLATE BINARY >= 'iose_' AND tbl_name COLLATE BINARY < 'iose`') OR (name COLLATE BINARY >= 'ioec_' AND name COLLATE BINARY < 'ioec`') OR (tbl_name COLLATE BINARY >= 'ioec_' AND tbl_name COLLATE BINARY < 'ioec`') LIMIT 33"
    types = db.execute('SELECT typeof(name),typeof(type),typeof(tbl_name),typeof(sql)' + suffix).fetchall()
    require(len(types) == 22 and all(tuple(row[:3]) == ('text', 'text', 'text') and row[3] in ('text', 'null')
                                   for row in types), 'SCHEMA_CHANGED')
    sizes = db.execute('SELECT length(CAST(name AS BLOB)),length(CAST(type AS BLOB)),length(CAST(tbl_name AS BLOB)),length(CAST(sql AS BLOB))' + suffix).fetchall()
    require(len(sizes) == len(types), 'SCHEMA_CHANGED')
    for row, kinds in zip(sizes, types):
        require(all(type(value) is int and 0 < value <= 128 for value in row[:3]) and
                ((kinds[3] == 'null' and row[3] is None) or
                 (kinds[3] == 'text' and type(row[3]) is int and 0 < row[3] <= 4096)), 'SCHEMA_CHANGED')
    return tuple(sorted(tuple(row) for row in db.execute('SELECT name,type,tbl_name,sql' + suffix)))

def object_index(db):
    args = (MAX_STORE_DOCUMENTS + 1,)
    checks = db.execute('SELECT typeof(digest),length(CAST(digest AS BLOB)),typeof(body),length(body) FROM main.ioec_bodies LIMIT ?', args).fetchall()
    require(len(checks) <= MAX_STORE_DOCUMENTS, 'READ_BOUND')
    for row in checks:
        require(tuple(row[:3]) == ('text', 71, 'blob') and type(row[3]) is int and
                0 <= row[3] <= MAX_DOCUMENT_BYTES, 'STORAGE_TYPE')
    require(sum(row[3] + 256 for row in checks) <= MAX_STORE_BYTES, 'READ_BOUND')
    rows = tuple(sorted(tuple(row) for row in db.execute('SELECT digest,length(body) FROM main.ioec_bodies LIMIT ?', args)))
    require(len(rows) == len(checks), 'STORAGE_CHANGED')
    return rows

def snapshot(db):
    require(db.in_transaction, 'TRANSACTION_REQUIRED')
    parts = [('schema', schema(db))]
    charge = _charge(parts[0][1])
    for table, maximum, fields in TABLES:
        rows = scan(db, table, fields, maximum, remaining=MAX_MEMO_BYTES - charge)
        charge += _charge(rows)
        parts.append((table, rows))
    rows = scan(db, 'reg_meta', (('key', T), ('value', T)), len(ANCHORS),
        where=' WHERE key IN (' + ','.join('?' for _ in ANCHORS) + ')', parameters=ANCHORS,
        remaining=MAX_MEMO_BYTES - charge)
    require(tuple(row[0] for row in rows) == tuple(sorted(ANCHORS)), 'ASSOCIATION_UNAVAILABLE')
    parts.append(('anchors', rows)); charge += _charge(rows)
    authority = point(db, 'meta', (('value', ('text', 32)),), ' WHERE key=?', ('authority',))
    parts.append(('authority', (authority,))); charge += _charge((authority,))
    objects = object_index(db)
    parts.append(('objects', objects)); charge += _charge(objects)
    require(charge <= MAX_MEMO_BYTES, 'PREPARATION_CAPACITY')
    return tuple(parts), charge

def verify_files(db, sequence, expected):
    """Snapshot already preflighted current types/lengths of all actual bodies."""
    require(db.in_transaction, 'TRANSACTION_REQUIRED')
    rows = db.execute('SELECT d.path,b.body FROM main.ioec_documents d JOIN main.ioec_bodies b ON b.digest=d.digest WHERE d.sequence=? LIMIT ?',
                      (sequence, len(expected) + 1)).fetchall()
    require(len(rows) == len(expected), 'EVIDENCE_CHANGED')
    saved = dict(expected)
    seen = set()
    for name, body in rows:
        require(name in saved and name not in seen and type(body) is bytes and body == saved[name], 'EVIDENCE_CHANGED')
        seen.add(name)
    require(seen == set(saved), 'EVIDENCE_CHANGED')

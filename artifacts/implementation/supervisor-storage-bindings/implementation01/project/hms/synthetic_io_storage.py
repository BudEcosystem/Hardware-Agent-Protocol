"""Bound allocation from trusted-schema SQLite rows before reading their bodies."""
from .contracts import MAX_BYTES
from .journal import JournalError


def _require(condition):
    if not condition:
        raise JournalError('IO_STORAGE_SHAPE')


def _where(keys):
    # Names are internal schema constants; document/user strings are parameters.
    _require(all(key.isidentifier() for key in keys))
    return ' AND '.join(key+'=?' for key in keys) or '1'


def bounded_rows(db, table, columns, *, limit, keys=None, blobs=()):
    _require(table.isidentifier() and all(column.isidentifier() for column in columns) and type(limit) is int and 1 <= limit <= 256)
    keys = keys or {}; where = _where(keys); parameters = tuple(keys.values())
    # Fetch only SQLite type/length integers first, never an unbounded body.
    projection = ','.join('typeof('+column+'),length(CAST('+column+' AS BLOB))' for column in columns)
    metadata = db.execute('SELECT '+projection+' FROM '+table+' WHERE '+where+' LIMIT ?',(*parameters,limit+1)).fetchall()
    _require(len(metadata) <= limit)
    for row in metadata:
        for index,column in enumerate(columns):
            kind,length = row[index*2:index*2+2]
            _require(kind == 'blob' if column in blobs else kind in {'text','integer'})
            _require(type(length) is int and 0 <= length <= (MAX_BYTES if column in blobs else 128))
    rows = db.execute('SELECT '+','.join(columns)+' FROM '+table+' WHERE '+where+' LIMIT ?',(*parameters,limit+1)).fetchall()
    _require(len(rows) == len(metadata))
    return rows


def document_row(db, table, keys, *, extra=()):
    rows = bounded_rows(db,table,('document','digest',*extra),limit=1,keys=keys,blobs=('document',))
    return rows[0] if rows else None


def metadata_text(db, key):
    row = db.execute('SELECT typeof(value),length(CAST(value AS BLOB)) FROM io_meta WHERE key=?',(key,)).fetchone()
    _require(row is not None and row[0] == 'text' and type(row[1]) is int and 0 <= row[1] <= (MAX_BYTES if key == 'installation' else 128))
    return db.execute('SELECT value FROM io_meta WHERE key=?',(key,)).fetchone()[0]

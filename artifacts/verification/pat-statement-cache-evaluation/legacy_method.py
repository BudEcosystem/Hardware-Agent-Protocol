def _table(self, db, store, table, specification):
    fields, limit = specification
    columns = fields.split(',')
    schema = db.execute('PRAGMA table_info(' + table + ')').fetchmany(33)
    require(len(schema) <= 32 and [row[1] for row in schema] == columns, 'PAT_IO_TRIAL_STORAGE_SHAPE')
    count = db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
    require(type(count) is int and count <= limit, 'PAT_IO_TRIAL_STORAGE_LIMIT')
    sizes = ','.join('max(length(CAST(' + column + ' AS BLOB)))' for column in columns)
    require(all(value is None or value <= 65536 for value in db.execute('SELECT ' + sizes + ' FROM ' + table).fetchone()),
            'PAT_IO_TRIAL_STORAGE_LIMIT')
    rows = db.execute('SELECT ' + fields + ' FROM ' + table + ' ORDER BY ' + fields + ' LIMIT ?', (limit + 1,)).fetchall()
    require(len(rows) == count, 'PAT_IO_TRIAL_STORAGE_CHANGED')
    def cell(value):
        if type(value) is bytes:
            return {'type': 'blob-utf8', 'value': value.decode('utf-8')}
        require(value is None or type(value) in {int, str}, 'PAT_IO_TRIAL_STORAGE_TYPE')
        return {'type': 'null' if value is None else 'integer' if type(value) is int else 'text', 'value': value}
    pages = []
    # Empty tables still have a page and explicit zero row count.
    for offset in range(0, max(count, 1), 8):
        pages.append(self._write('table_page', {'store': store, 'table': table, 'columns': columns,
            'first': offset, 'totalRows': count, 'rows': [[cell(value) for value in row] for row in rows[offset:offset + 8]]}, reuse=True))
    return {'store': store, 'table': table, 'rowCount': count, 'pages': pages}

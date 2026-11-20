def _configuration_table(self, db, table, specification):
    fields, kinds, limit = specification; columns, kinds = fields.split(','), kinds.split()
    schema = db.execute('PRAGMA table_info(' + table + ')').fetchmany(33)
    require([r[1] for r in schema] == columns, 'PAT_IO_CONFIGURATION_STORAGE_SHAPE')
    where, params = (' WHERE key IN (?,?,?)', PUBLIC_META) if table == 'reg_meta' else ('', ())
    if table == 'reg_meta':
        keys = db.execute('SELECT key FROM reg_meta ORDER BY key LIMIT 5').fetchall()
        require([r[0] for r in keys] == ['cursor_key', 'deployment', 'revision', 'version'], 'PAT_IO_CONFIGURATION_STORAGE_SHAPE')
    count = db.execute('SELECT count(*) FROM ' + table + where, params).fetchone()[0]
    require(type(count) is int and count <= limit, 'PAT_IO_CONFIGURATION_STORAGE_LIMIT')
    type_check = ' AND '.join('typeof(' + c + ') = ?' for c in columns)
    sizes_sql = ','.join('max(length(CAST(' + c + ' AS BLOB)))' for c in columns)
    metadata = db.execute('SELECT min(' + type_check + '),' + sizes_sql + ' FROM ' + table + where,
                          (*kinds, *params)).fetchone()
    require(not count or metadata[0] == 1, 'PAT_IO_CONFIGURATION_STORAGE_TYPE')
    sizes = metadata[1:]
    require(all(v is None or type(v) is int and v <= 65536 for v in sizes), 'PAT_IO_CONFIGURATION_STORAGE_LIMIT')
    rows = db.execute('SELECT ' + fields + ' FROM ' + table + where + ' ORDER BY ' + fields + ' LIMIT ?', (*params, limit + 1)).fetchall()
    require(len(rows) == count, 'PAT_IO_CONFIGURATION_STORAGE_CHANGED')
    def cell(value, kind):
        if kind == 'blob':
            cache = getattr(self, '_canonical_blob_checks', None)
            if cache is None:
                cache = self._canonical_blob_checks = CanonicalBlobs()
            require(cache.is_canonical(value, canonical=canonical, parser=parse_json), 'PAT_IO_CONFIGURATION_STORAGE_DOCUMENT')
            return {'type': 'blob-utf8', 'value': value.decode('utf-8')}
        require(type(value) is (int if kind == 'integer' else str), 'PAT_IO_CONFIGURATION_STORAGE_TYPE')
        return {'type': 'integer' if kind == 'integer' else 'text', 'value': value}
    pages = []
    projection = 'public_registry_metadata' if table == 'reg_meta' else 'complete'
    for offset in range(0, max(1, count), 8):
        pages.append(self._configuration_write('table_page', {'table': table, 'projection': projection,
            'columns': columns, 'first': offset, 'totalRows': count,
            'rows': [[cell(value, kind) for value, kind in zip(row, kinds)] for row in rows[offset:offset + 8]]}, reuse=True))
    return {'table': table, 'projection': projection, 'rowCount': count, 'pages': pages}

"""Bounded exact table-page encodings; never a database or authority cache."""
from collections import OrderedDict
import hashlib

from .contracts import canonical

MAX_PAGES = 128
MAX_ENCODING_BYTES = 1024 * 1024
_COMMON = {'table', 'columns', 'first', 'totalRows', 'rows'}


def _key(profile, value):
    # Only the closed, small page shapes produced after the original SQL checks
    # are memoized. Other values keep the original canonicalization path/errors.
    if type(profile) is not str or type(value) is not dict:
        return None
    fields = set(value)
    if fields == _COMMON | {'store'}:
        domain = ('store', value['store'])
    elif fields == _COMMON | {'projection'}:
        domain = ('projection', value['projection'])
    else:
        return None
    if type(domain[1]) is not str or type(value['table']) is not str:
        return None
    if type(value['first']) is not int or type(value['totalRows']) is not int:
        return None
    columns, rows = value['columns'], value['rows']
    if (type(columns) is not list or len(columns) > 32 or
            not all(type(c) is str for c in columns) or type(rows) is not list or len(rows) > 8):
        return None
    cells = []
    for row in rows:
        if type(row) is not list or len(row) != len(columns):
            return None
        page_row = []
        for cell in row:
            if type(cell) is not dict or set(cell) != {'type', 'value'} or type(cell['type']) is not str:
                return None
            scalar = cell['value']
            if scalar is not None and type(scalar) not in (int, str):
                return None
            page_row.append((cell['type'], type(scalar), scalar))
        cells.append(tuple(page_row))
    return (profile, domain, value['table'], tuple(columns), value['first'], value['totalRows'], tuple(cells))


class PageEncodings:
    """Per-engine immutable encodings, bounded by entries and encoded bytes.

    Keys retain exact immutable scalars and explicit types, never caller lists
    or mappings. Hits affect encoding only. Writers still run their own original
    reservations, checks, charges, exclusive writes, flush/fsync and publication.
    """
    def __init__(self):
        self._entries = OrderedDict()
        self.encoding_bytes = 0

    def encode(self, profile, value):
        key = _key(profile, value)
        if key is not None and key in self._entries:
            self._entries.move_to_end(key)
            return self._entries[key]
        data = canonical({'profile': profile, 'kind': 'table_page', 'value': value})
        result = (data, hashlib.sha256(data).hexdigest())
        if key is not None:
            while self._entries and (len(self._entries) >= MAX_PAGES or
                    self.encoding_bytes + len(data) > MAX_ENCODING_BYTES):
                _, (old, _) = self._entries.popitem(last=False)
                self.encoding_bytes -= len(old)
            if len(data) <= MAX_ENCODING_BYTES:
                self._entries[key] = result
                self.encoding_bytes += len(data)
        return result

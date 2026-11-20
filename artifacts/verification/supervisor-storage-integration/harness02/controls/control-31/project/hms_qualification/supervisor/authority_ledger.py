"""Explicit version-2 attempt authority; legacy ledgers are never migrated."""
import re
import uuid

from hms_qualification.supervisor.attempt_ledger import AttemptLedger, ATTEMPT_SQL, INDEX_SQL
from hms_qualification.supervisor.supervisor_contracts import require

PROFILE = 'hms.pat.supervisor-authority/0.1'
META_SQL = 'CREATE TABLE qs_meta(version INTEGER NOT NULL CHECK(version=2), authority TEXT NOT NULL CHECK(length(authority)=43))'


def authority_id(value):
    require(type(value) is str and re.fullmatch(r'supervisor:[0-9a-f]{32}', value) is not None,
            'QUALIFICATION_AUTHORITY_INVALID')
    return value


class AuthorityAttemptLedger(AttemptLedger):
    def __init__(self, root, *, create=False, expected_authority=None):
        require(type(create) is bool, 'QUALIFICATION_AUTHORITY_INVALID')
        if create:
            require(expected_authority is None, 'QUALIFICATION_AUTHORITY_CREATE_OPTIONS')
        else:
            authority_id(expected_authority)
        self._creating_authority = create
        self._created_authority = None
        self._expected_authority = expected_authority
        super().__init__(root, create=create)

    def _create_metadata(self):
        require(self._creating_authority, 'QUALIFICATION_LEDGER_MISSING')
        self._created_authority = 'supervisor:' + uuid.uuid4().hex
        self._expected_authority = self._created_authority
        self.db.execute(META_SQL)
        self.db.execute('INSERT INTO qs_meta VALUES(2,?)', (self._created_authority,))

    def _check_metadata(self):
        require(self.db is not None, 'QUALIFICATION_LEDGER_CLOSED')
        require(not self._creating_authority or self._created_authority is not None,
                'QUALIFICATION_AUTHORITY_ALREADY_EXISTS')
        require(self.db.execute('SELECT 1 FROM sqlite_temp_master LIMIT 1').fetchone() is None,
                'QUALIFICATION_SCHEMA_INVALID')
        suffix = ' FROM sqlite_master LIMIT 7'
        rows = self.db.execute('SELECT typeof(name),length(CAST(name AS BLOB)),typeof(type),'
            'length(CAST(type AS BLOB)),typeof(tbl_name),length(CAST(tbl_name AS BLOB)),typeof(sql),'
            'length(CAST(sql AS BLOB))' + suffix).fetchall()
        require(len(rows) == 5, 'QUALIFICATION_SCHEMA_INVALID')
        for row in rows:
            require(all(row[i] == 'text' and type(row[i+1]) is int and 1 <= row[i+1] <= 128
                        for i in (0, 2, 4)), 'QUALIFICATION_SCHEMA_INVALID')
            require((row[6] == 'null' and row[7] is None) or
                    (row[6] == 'text' and type(row[7]) is int and 1 <= row[7] <= 4096),
                    'QUALIFICATION_SCHEMA_INVALID')
        expected = {('qs_meta', 'table', 'qs_meta', META_SQL),
                    ('qs_attempts', 'table', 'qs_attempts', ATTEMPT_SQL),
                    ('qs_singleflight', 'index', 'qs_attempts', INDEX_SQL),
                    ('sqlite_autoindex_qs_attempts_1', 'index', 'qs_attempts', None),
                    ('sqlite_autoindex_qs_attempts_2', 'index', 'qs_attempts', None)}
        require(set(self.db.execute('SELECT name,type,tbl_name,sql' + suffix)) == expected,
                'QUALIFICATION_SCHEMA_INVALID')
        rows = self.db.execute('SELECT typeof(version),CASE WHEN typeof(version)=\'integer\' THEN version ELSE NULL END,'
            'typeof(authority),length(CAST(authority AS BLOB)) FROM qs_meta LIMIT 2').fetchall()
        require(rows == [('integer', 2, 'text', 43)], 'QUALIFICATION_AUTHORITY_INVALID')
        retained = authority_id(self.db.execute('SELECT authority FROM qs_meta').fetchone()[0])
        require(retained == self._expected_authority, 'QUALIFICATION_AUTHORITY_MISMATCH')

    @property
    def authority_id(self):
        with self.lock:
            self._check_metadata()
            return self._expected_authority

    def _row(self, identifier):
        self._check_metadata()
        return super()._row(identifier)

    def lookup(self, deployment, evaluator, run):
        with self.lock:
            self._check_metadata()
            return super().lookup(deployment, evaluator, run)

@contextmanager
def _transaction(self):
    with self._mutex:
        self._reject_commit_reentry()
        if self._closed:
            raise JournalError("CLOSED")
        if self._poisoned:
            raise JournalError("JOURNAL_UNHEALTHY")
        if self._db.in_transaction:
            raise JournalError("POLICY_REENTRANCY")
        self._db.execute("BEGIN IMMEDIATE")
        self._transaction_start_changes = self._db.total_changes
        self._commit_checks = _CommitChecks(threading.get_ident(), [])
        try:
            yield
            self._check_business_commit()
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            # A refused evidence transition can also have observed expiry.
            # Preserve that clock floor independently of business rollback.
            try:
                if self._observed_clock > int(self._meta("last_clock")):
                    self._db.execute("BEGIN IMMEDIATE")
                    self._set_meta("last_clock", str(self._observed_clock))
                    self._db.execute("COMMIT")
            except BaseException:
                self._poisoned = True
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
            raise
        finally:
            self._commit_checks = None


def _reject_commit_reentry(self):
    state = self._commit_checks
    if state is not None and state.checking:
        state.violated = True
        raise JournalError("COMMIT_CHECK_REENTRANCY")


def _require_at_commit(self, check):
    """Register a trusted bounded check for this business transaction.

        This is an installed-service API, never a wire callback. Acquire evidence
        outside the authority transaction and retain its owner through commit.
        The callback must return None or raise; it may inspect held state and
        bounded main-database rows, but must not do file/provider I/O, reenter,
        sample authority time or replace connection hooks. It is not a sandbox.
        Reusing the same callable object is idempotent; at most 64 are accepted.
        A batch evidence view should register one check for the entire inventory.
        """
    with self._mutex:
        self._reject_commit_reentry()
        state = self._commit_checks
        if state is None or state.thread != threading.get_ident() or self._closed or self._poisoned or (not self._db.in_transaction):
            raise JournalError('COMMIT_CHECK_TRANSACTION_REQUIRED')
        if not callable(check):
            state.violated = True
            raise JournalError('COMMIT_CHECK_INVALID')
        if any((check is previous for previous in state.callbacks)):
            return
        if len(state.callbacks) >= 64:
            state.violated = True
            raise JournalError('COMMIT_CHECK_LIMIT')
        state.callbacks.append(check)


def _check_business_commit(self):
    """Last synchronous check before COMMIT, not a real-time guarantee.

        Clock-floor commits deliberately bypass this boundary. A failed check
        rolls back business writes; the existing refusal path retains observed
        time. COMMIT can block or its reply can be lost: reconcile the original
        operation identity, never infer a rollback from a later exception.
        """
    self._reject_commit_reentry()
    state = self._commit_checks
    if state.violated:
        raise JournalError('COMMIT_CHECK_IMPURE')
    if not state.callbacks:
        return
    if state.thread != threading.get_ident() or not self._db.in_transaction or getattr(self, '_pat_evidence_guard', None) is not None:
        raise JournalError('COMMIT_CHECK_TRANSACTION_REQUIRED')
    connection = self._db
    before = connection.total_changes
    evidence_guard = {'denied': False}

    def authorize(action, first, second, database, source):
        if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ} and database in {None, 'main'}:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and first is None and (second in {'typeof', 'length'}) and (database is None):
            return sqlite3.SQLITE_OK
        state.violated = True
        return sqlite3.SQLITE_DENY
    state.checking = True
    self._pat_evidence_guard = evidence_guard
    try:
        connection.set_authorizer(authorize)
        for check in tuple(state.callbacks):
            if check() is not None:
                raise JournalError('COMMIT_CHECK_INVALID_RESPONSE')
    finally:
        try:
            connection.set_authorizer(None)
        finally:
            if self._pat_evidence_guard is not evidence_guard:
                state.violated = True
            self._pat_evidence_guard = None
            state.checking = False
        if state.violated or evidence_guard['denied'] or self._db is not connection or (self._commit_checks is not state) or (not connection.in_transaction) or (connection.total_changes != before):
            raise JournalError('COMMIT_CHECK_IMPURE')


def _meta(self, key):
    row = self._db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if row is None:
        raise JournalError("MISSING_AUTHORITY_METADATA")
    return row[0]


def _set_meta(self, key, value):
    self._db.execute("UPDATE meta SET value=? WHERE key=?", (value, key))

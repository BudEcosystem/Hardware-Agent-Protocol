def _verify_evidence(self, evaluator, context, receipt):
    if evaluator.verify_evidence is None:
        return True, None
    if not self._db.in_transaction:
        raise JournalError("PAT_EVIDENCE_TRANSACTION_REQUIRED")
    outer_guard = getattr(self.journal, "_pat_evidence_guard", None)
    if outer_guard is not None:
        outer_guard["denied"] = True
        raise JournalError("PAT_EVIDENCE_REENTRANT")
    before = self._db.total_changes
    guard = {"denied": False}

    def authorize(action, _first, _second, database, _source):
        if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ} and database in {None, "main"}:
            return sqlite3.SQLITE_OK
        # BLOB metadata must be checked before fetching a retained body.
        # TEXT length is not its byte size (and stops at an embedded NUL),
        # so verifiers must require typeof(body) == 'blob' as well.
        # Overriding these built-ins violates the trusted provider contract.
        if (action == sqlite3.SQLITE_FUNCTION and _first is None and
                _second in {"typeof", "length"} and database is None):
            return sqlite3.SQLITE_OK
        guard["denied"] = True
        return sqlite3.SQLITE_DENY

    # Journal owns this connection and otherwise installs no authorizer.
    # The guard remains installed through fetch/evaluation, including any
    # re-preparation. Reentry cannot replace another catalog's guard.
    self.journal._pat_evidence_guard = guard
    try:
        self._db.set_authorizer(authorize)
        try:
            valid = evaluator.verify_evidence(context, copy.deepcopy(receipt))
        except Exception:
            # Callback error codes cannot masquerade as a known ineligible
            # candidate and manufacture uniqueness in PAT selection.
            return False, "PAT_EVIDENCE_UNAVAILABLE"
    finally:
        try:
            self._db.set_authorizer(None)
        finally:
            self.journal._pat_evidence_guard = None
        if guard["denied"] or not self._db.in_transaction or self._db.total_changes != before:
            # Must escape _eligible, even if the callback swallowed its SQL
            # error. Returning False could otherwise commit a mutation.
            raise JournalError("PAT_EVIDENCE_PROVIDER_IMPURE")
    if valid is False:
        return False, "PAT_EVIDENCE_INVALID"
    if valid is not True:
        return False, "PAT_EVIDENCE_INVALID_RESPONSE"
    return True, None

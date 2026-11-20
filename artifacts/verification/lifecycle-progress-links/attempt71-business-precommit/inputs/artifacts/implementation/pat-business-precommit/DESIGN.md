# Business commit checks for held PAT evidence

This candidate extends the passing [integer canonicalization source](../pat-integer-canonical/README.md).
It addresses the [catalog integration boundary](../pat-vault-original-run/CATALOG-NOTES.md),
without changing the old compact-evidence catalog or mounting a new vault catalog.

`Journal._require_at_commit(check)` registers an installed service's bounded check
on the current, mutex-owned business transaction. The same callable object is
idempotent; at most 64 distinct checks are retained. A future catalog batch view
should register one check covering its complete relevant candidate inventory.
Registration cannot come from a JSON request. Every scope drops its checks on
success or failure; another thread cannot insert one into the owner's transaction.

The journal calls the registered checks after the transaction body has produced
all admission rows and immediately before issuing its business `COMMIT`. A check
returns `None` or raises. The callback runs with a main-database read authorizer;
only SELECT/READ and the `typeof`/`length` metadata functions are permitted. A
swallowed forbidden SQL action, callback registration error or check reentry
still causes rollback. Checks cannot call journal close, a new transaction,
authority-clock sampling or the commit checker recursively. The authorizer is
removed and callback state cleared on failure, including `BaseException`.
The checker also holds the catalog's evidence-guard marker. Nested use of the
existing catalog verifier cannot replace this authorizer or make a swallowed
reentry committable. A commit callback must call its bounded view validator
directly, rather than reentering `PatCatalog._verify_evidence`.

The existing `_now` clock-floor commit/rebegin deliberately bypasses these
checks, retaining their registration for the ensuing business commit. A check's
refusal rolls back admission, claims, fences and replay rows together, while the
existing refusal path preserves observed time. This prevents an expired refusal
from being revived by a clock rollback. A successful COMMIT followed by a lost
reply remains committed and must be reconciled by its original replay identity.

This is the final synchronous validation boundary, not a hard deadline guarantee
across a blocking SQLite commit. Trusted callbacks must perform no archive,
filesystem, provider, network or other blocking work. The SQL guard is not an
arbitrary-Python sandbox; connection hook replacement, built-in replacement and
direct private-state tampering remain outside the installed-service contract.
Multiple checks run in order and do not constitute simultaneous clock samples.

The controls use real Journal transactions and actual small vault snapshots.
Vault fixture manifests assert immutable bytes only, not a passed qualification.
The future profile must still prepare a bounded multi-manifest view outside the
authority transaction, verify publication/authority associations, preserve all
relevant candidates, and connect recording, promotion and admission to this check.
Expiry, replacement and release are exercised at this new commit boundary.
Manifest drift, revocation and configuration/session changes require the new
catalog profile and its own integrated controls. No physical adapter is exercised.

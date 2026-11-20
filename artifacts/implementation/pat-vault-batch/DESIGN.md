# One held inventory for all relevant PAT evidence

The preceding [Journal boundary](../pat-business-precommit/README.md) can validate
a held evidence lease at business commit. Its next consumer needs several PAT
manifests under one owner; independent or nested single leases cannot provide that
inventory. This candidate adds `EvidenceVault.snapshot_many` without changing the
existing single snapshot, Journal or compact catalog implementation.

The caller supplies an exact tuple of exact `(intentDigest, bindingDigest)`
tuples, with distinct intents. At most the descriptor's manifest count (never
more than 32) is accepted. Inside one read transaction, the vault validates its
state, every requested association and aggregate limits before materializing any
selected body. It then validates every selected body and closure and yields one
handle covering the complete sorted key set. Missing, conflicting or corrupted
members refuse the whole view. The implementation never evicts or silently drops
a requested member to fit a budget.

The caller may lower the document and byte limits. Effective limits also respect
the installed descriptor. Logical charge is each manifest's canonical byte length
plus 512, plus each document reference's body length, UTF-8 path length and 512.
Repeated bodies are charged for every reference; identical immutable bytes are
shared in the returned views. Usage separately reports expanded and unique body
bytes. These are deterministic logical bounds, not measured Python heap sizes or
backed capacity reservations. The existing full-state metadata scan is bounded by
the vault descriptor; the narrower caller budget bounds selected materialization.

The handle exposes checked membership, detached manifests/documents and usage.
All members share the same owner, thread, read transaction and exclusive lease.
Its lifetime starts after preparation. A check performs no file or SQL reads; it
does not interrupt Python at expiry or guarantee latency across SQLite COMMIT.
Single and batch leases exclude each other. Release invalidates the entire handle.

At admission, the new catalog must hold this view, validate the complete relevant
inventory and authority/publication associations, and register one stable final
check through `Journal._require_at_commit`. The present tests connect a real
batch lease to real Journal admission, including expiry after writes and lease
cleanup failure after commit. A post-commit failure does not erase the operation;
original-key replay must recover it without another admission.

Vault manifests prove retained byte identity only. This component does not make a
PAT eligible, implement the distinct catalog receipt/mount, perform learning, or
qualify physical behavior. Conservative implementation identities change with the
new vault source; this stage does not migrate old installed descriptors in place.

# Independent immutable evidence vault

This candidate implements the bulk-store component of the
[control-storage design](../../verification/pat-storage-capacity/DESIGN.md).
All 275 inherited project files remain unchanged. Four new production modules
and one new test module are added in an isolated project copy. This is not a
publicly mounted service or the complete separated-store profile.

## Contract

`descriptor(authority_id, ...)` creates a new installation descriptor containing
the authority/store identities, current implementation identity and lowerable
limits. An installer must retain that exact descriptor in the control authority;
that installer is not part of this candidate. Supplying an authority ID or binding
digest to this library does not authenticate the caller or prove an original run.

`EvidenceVault(path, expected, create=...)` owns a private POSIX directory/file
binding and exclusive owner lock. Creation is exclusive. Reopen requires existing
files and the exact descriptor. Both paths verify a 1,024-byte page layout, DELETE
journaling, synchronous EXTRA and the actual page cap before application writes.
The maximum configured cap is 15 MiB; this does not cover live sidefiles or reserve
filesystem capacity. Reopen refuses retained journal/WAL/shared-memory paths,
including dangling symlinks. Qualified hot-journal recovery remains future work.
No missing or corrupt store is silently recreated or repaired.

`seal(intent_digest, binding_digest, documents)` validates bounded paths and bytes,
deduplicates only exact bodies, and commits one complete immutable manifest with
all document references in one independent SQLite transaction. Exact intent replay
checks the original binding and every selected current byte before returning the
original manifest. Conflict, missing/corrupt state and capacity failures refuse.
Each manifest says `immutable-bytes-only`: sealing is neither semantic inspection,
PAT qualification, nor publication in the control authority.

`snapshot(intent_digest, binding_digest)` validates the complete selected contents
under a read transaction, then yields an opaque owner-bound handle. Public reads
return detached mappings. Its `check(owner)` performs no filesystem access and
requires the same owner, active transaction, thread and unexpired monotonic deadline.
A future authority publisher must check that handle immediately before its commit.
The handle expires when released. It invalidates on expiry; it cannot interrupt
arbitrary Python callbacks or guarantee lock-release, scheduling or stop latency.
The context manager always attempts rollback and restores the connection's read
mode. A failed cleanup poisons that vault instance.

Private directory permissions, exact file identities and cooperative owner locks
are the supported ownership model. This is not isolation from root, arbitrary
same-user code or code that bypasses the provider. Keep auxiliary database FDs open
through active SQLite transactions; closing arbitrary same-process FDs to that
database can interfere with POSIX record locks. The provider's identity FD closes
only after its SQLite connection closes.

## Scope of validation

The reviewed selection contains 21 new controls and one original-data method.
Controls cover identity, exclusive ownership, missing/replaced paths, sidefiles,
strict descriptor/document types, exact deduplication, replay conflicts, logical
and page capacity, body/schema/typed-record corruption, read-transaction exclusion,
snapshot ownership/expiry and injected failures before/after commit. A real
unmodified Journal records completion and releases claims after the separate vault
hits SQLITE_FULL. Its policy/evidence are synthetic; no driver executes.

The original-data method reads a fresh immutable copy of the preceding passing
authority database, whose exact hash is pinned. It seals all 4,011 references and
2,798 distinct bodies, compares every byte, reopens and replays under the same
15 MiB vault ceiling. This reuses retained evidence from the complete 30-case
scope. It does not rerun a worker or independently requalify the physical behavior.

The child permits only these 22 methods, at most 64 declared SQLite opens, no
network/subprocess/device access, exact project/dependency origins and no writes
to input sources or the retained-data fixture. It has 120 CPU seconds, 512 MiB
address space and a 16 MiB per-file bound; the parent has the original 180-second
wall limit, 4 MiB output and 256 MiB scratch limits. Audit hooks are cooperative
guardrails, not OS isolation. Every failure and synthetic corruption fixture is
retained. One deliberate dangling symlink is inventoried without following it.

## Required integration after this component

Implement and verify authority-owned store installation, durable import intents,
capacity admission, the original-run semantic consumer, atomic reference
publication, interruption reconciliation and an explicit catalog snapshot profile.
Keep the legacy compact/profile checks unchanged. The ordinary Journal still lacks
pre-recovery cap enforcement and backed capacity for outstanding obligations.
No hard aggregate quota, physical reservation, independent stop path, public PAT
tool, natural-language synthesis, persistent Arduino application or actual device,
driver or hub provider is supplied by this component.

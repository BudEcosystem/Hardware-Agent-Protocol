# Authority-owned evidence publication

This candidate adds a distinct `hms.pat.vault-import/0.1` profile to the sealed
[independent vault component](../pat-evidence-vault/README.md). It leaves all 280
inherited project files unchanged, including the legacy consumer, compact store,
catalog, execution service and Journal. Three new production modules implement the
association and publication path. The new profile is not publicly mounted.

## Installation and original intent

Installation accepts actual `IoServiceExecutionStore`, `Journal` and
`EvidenceVault` objects. The vault descriptor must name the live Journal authority,
and the vault must have an independent connection. The administrator's current
registry grant authorizes creation of the installation. The authority retains the
exact descriptor, supervisor identity, deployment, consumer source identity and
lowerable logical limits in a record anchored in `reg_meta`. A claimed authority
identifier or arbitrary path is not a replacement for these installed objects.

This association operates under the existing Journal's local ownership contract.
It does not retrofit the vault's stronger pathname handling or pre-recovery page
limit into Journal. The vault itself retains its own current file identities and
page cap. No database is attached to the control connection.

Import calls accept only an authenticated embedding context and evaluator/run
names. The existing execution service supplies the original reservation, handoff,
request and terminal supervisor record. The importer commits a bounded intent
before reading the producer archive. Its unique original evaluator/run key, full
anchor, binding digest, source identity and chain digest persist across failures.
There is no qualification-worker launch path in this importer.

Each admitted intent consumes 33,792 logical control bytes: two maximum 16 KiB
records plus 1 KiB accounting overhead. The installation's maximum is 256 KiB and
can be lowered; intent count is also bounded by the supervisor and vault. Charges
remain after failure and publication. This accounting is deliberately distinct
from physical allocation: it reserves no filesystem space and cannot guarantee
that a later SQLite commit succeeds. Aggregate quota and capacity owed to active
control operations still require implementation.

## Independent seal and atomic publication

The existing archive reader checks the original producer directory and evidence.
The existing semantic reducer validates the complete declared synthetic matrix
outside the control transaction. Its result is sealed under the durable intent
and binding digest in the independent vault. Sealing still means immutable bytes,
not PAT eligibility or physical qualification.

| Durable boundary | Authority intents | Vault manifests | Authority publications |
|---|---:|---:|---:|
| Before intent commit | 0 | 0 | 0 |
| Intent committed | 1 | 0 | 0 |
| Evidence seal committed | 1 | 1 | 0 |
| Reference published | 1 | 1 | 1 |

A sealed but unpublished manifest remains retained. Reconciliation re-inspects
its original output bytes with the unchanged semantic reducer and verifies the
complete reconstructed document set. It does not read a replacement archive or
start another worker. Only absence of this original intent's manifest permits the
original archive read. Corrupt, unavailable or mismatched evidence refuses.

Publication holds a current vault read transaction, verifies every selected byte,
and commits only a bounded reference record in the Journal. Current permissions,
configuration revision, original reservation/handoff/attempt, consumer identity,
manifest and closure must still match. The opaque snapshot is checked immediately
before the authority commit. Its five-second deadline invalidates stale handles;
it does not interrupt Python or guarantee a scheduling/stop latency.

The lock order is execution ownership, then vault read ownership, then a short
Journal transaction. Source checks, archive reads, semantic inspection and
supervisor lookup occur outside the Journal transaction. A previously published
receipt can be read after a configuration change as historical evidence, but it
still requires current access and current vault bytes. Catalog eligibility is a
separate future profile and must recheck present execution conditions.

Lost publication replies reconcile the same persisted receipt. The metadata-only
`pending` method reports the original intent and publication flag without claiming
bulk availability. Missing evidence never turns a published run into a novel run.

## Verification limits

The original 19 controls use a real synthetic runtime authority, independent vault and
bound supervisor ledger, with a declared substitute semantic oracle. No actual
qualification worker or physical device executes. The failed setup scopes are
retained separately from production assertions. Each corrected scope uses fresh
private `/tmp` state, preserves that raw state and exact retained copies, and keeps
the existing time, file, memory, output and connection bounds. The corrected source
adds one post-seal revocation control. Its importer preserves authority refusals
after normal snapshot release; vault expiry or cleanup errors still take precedence.
The full current-source selection is incomplete; see [current results](README.md).

The real semantic reducer is unchanged, but this new profile still needs an
actual retained-original-run import audit, a distinct held-snapshot catalog
adapter and full catalog/application/replay verification. Public API/CLI/MCP and
Harness mounting, prompt synthesis and validated learning, persistent MCU
controllers, actual I/O/driver/hub providers, hard storage quotas and physical
commissioning remain part of the active end-to-end objective.

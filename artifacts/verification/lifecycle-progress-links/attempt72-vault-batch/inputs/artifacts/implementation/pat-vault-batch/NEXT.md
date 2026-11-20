# Implement the distinct authority-vault catalog profile

The required [multi-manifest view](implementation01/README.md) and
[business commit boundary](../pat-business-precommit/README.md) now exist. Their
60 current controls pass. Use this source as the baseline for the actual catalog
integration; do not repeat unchanged component tests or worker timing trials.

Create a distinct bridge, receipt, catalog mount and execution profile. The old
`RecordedIoBridge`/`RecordedPatCatalog` pair expects compact `ioec_*` evidence in
the authority database; keep that profile's exact type checks and SQL guard.
The new receipt must retain the original import intent/anchor and separately
bind the publication digest, vault store/manifest identity, evaluation digest,
full closure, evaluator/consumer implementation and applicability dependencies.

Preparation must resolve and validate original source association and semantic
evidence outside the control transaction. Build an explicitly bounded view for
the entire authorized, statically relevant candidate set. Acquire one
`snapshot_many` lease with a complete exact key set. Missing, invalid or
unavailable evidence cannot be silently omitted, treated as novelty, or make a
different PAT uniquely eligible.

Inside the authority transaction, compare the inventory/revisions, retained
publication/intent rows and current configuration, driver, binding and endpoint
session dependencies. Use only the prepared view and bounded main-schema reads.
Register one stable callable through `Journal._require_at_commit`; call the
prepared view's validator directly, without nesting `PatCatalog._verify_evidence`.
The callback must account for the transaction's intended catalog mutations rather
than rejecting its own writes. Source loading, archive access, reduction and cache
insertion/eviction remain outside this transaction.

Preserve original-key replay before fresh evidence preparation. A committed
operation remains historical truth even if its old evidence or configuration is
unavailable. A lost commit reply or later lease-cleanup exception requires
reconciliation of that exact identity, never a replacement operation or new key.
The batch API currently normalizes Journal exceptions thrown through its context
like the single API; the catalog wrapper must preserve its own refusal semantics
while still releasing and checking the held view.

Verify recording, promotion, multi-candidate selection, revocation, changed
manifest/publication references, configuration/session drift, commit-time expiry,
lost replies and historical replay. Then exercise the complete original
worker/import/catalog/promotion/application flow on this exact profile, including
the full original evidence dataset. The current 32-manifest test uses small byte
fixtures; it does not claim multiple fully qualified physical or synthetic PATs.

Backed control capacity, aggregate quotas and recovery, public mounting/full
regression, native Harness integration, prompt synthesis and learned promotion,
persistent Arduino/device applications, real I/O/driver/hub providers, microscope
commissioning and incomplete research remain in the full goal.

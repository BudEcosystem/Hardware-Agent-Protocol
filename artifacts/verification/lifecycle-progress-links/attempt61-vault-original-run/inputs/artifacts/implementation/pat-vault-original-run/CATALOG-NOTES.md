# Catalog boundary found during actual-run preparation

This is a source review, not an implemented catalog profile or a passing test.
The inspected sources are retained unchanged in
[the corrected snapshot](implementation02/README.md).

The existing `RecordedIoBridge` accepts exactly `CompactIoEvidenceStore`, and
`RecordedPatCatalog` accepts exactly that bridge class. The bridge's payload takes
the original anchor from the compact receipt. The authority-vault profile instead
retains the anchor in a separately identified import intent and publishes a
manifest reference. These require an explicit new invocation/mount profile;
loosening type checks would not supply the missing semantics.

The [legacy projection](implementation02/project/recorded_io/projection.py)
reads `ioec_*` metadata, references and current bodies from the main authority
connection. The catalog's [evidence guard](implementation02/project/hms/pat_catalog.py)
permits main-schema SELECT/READ and narrowly selected metadata functions while
checking transaction continuity and mutation counts. The independent vault
cannot become another main-schema table or an attached database inside that
callback. Preserve the old profile's guard and current-byte checks.

The new profile needs an owner-held evidence snapshot acquired before entering
the control transaction. Inside the guarded callback it should consume an
already validated, bounded view and perform pure owner/thread/lifetime checks,
plus bounded current authority and applicability comparisons. Archive reading,
semantic reduction, source loading and cache admission belong outside the control
transaction. A cached payload alone does not establish current evidence validity.

The [Journal transaction](implementation02/project/hms/journal.py) commits after
its caller returns and currently has no evidence precommit hook. Its clock-floor
logic can also commit and reopen a transaction before business mutation. Checking
a snapshot only inside the evaluator callback, or after the outer commit, would
not establish validity immediately before the business commit. Any new integration
must provide and test that boundary explicitly while preserving clock-floor
behavior and existing profiles. A post-commit exception requires reconciliation
of the committed decision; it must not trigger a replacement operation.

Selection may consider several relevant PATs. The current vault handle allows
one active lease, so a batch/multi-manifest view or another explicitly bounded
strategy is required. It must preserve the whole candidate set through admission.
Unavailable evidence for a relevant candidate cannot silently manufacture a
unique match or a novelty response. The user requirement to ask the agent only
for unfamiliar scenarios still requires deterministic refusal/recovery for known
invalid states and temporary unavailability.

Before public mounting, verify expired/replaced snapshots immediately before
commit, changed manifests/authority references, revocation, configuration and
endpoint-session drift, multiple relevant candidates, lost commit replies and
historical exact-key replay. Repeat the complete worker/import/catalog/application
flow on the new profile. The older compact-profile result remains historical
evidence for its own implementation.

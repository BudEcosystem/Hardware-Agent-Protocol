# Connect the held evidence view to selection and admission

Use [source03](implementation03/README.md) as the new candidate baseline. Its
Journal commit boundary is implemented and tested; do not repeat unchanged host
controls or deadline-seeking worker trials. The new vault catalog profile remains
the next required implementation, following the original
[boundary review](../pat-vault-original-run/CATALOG-NOTES.md).

1. Extend the vault with one bounded, owner-held multi-manifest read view. The
   existing single active lease cannot be nested once per PAT. Validate every
   requested manifest and body in the same read transaction, charge aggregate
   references and bytes, and retain exact owner/thread/lifetime identity. Share
   immutable body bytes where appropriate; never omit a requested unavailable
   manifest to fit a cache or create an apparently unique candidate.
2. Define a distinct invocation, catalog receipt and mount identity for authority
   import intents, publications and vault manifests. The old compact catalog
   stores evidence in `ioec_*` main-schema tables; its exact type checks and SQL
   guard remain unchanged. The new profile must validate the original anchor,
   source association, semantic result and publication before preparing bounded
   views outside the control transaction.
3. Gather the entire authorized, statically relevant candidate inventory before
   opening the held vault view. Inside the admission transaction, revalidate
   inventory/revisions, publication references and current configuration, driver,
   binding and endpoint-session applicability. Archive access, reducer execution,
   source loading and cache insertion/eviction stay outside this transaction.
   An unavailable relevant candidate must abort selection; it must not become
   `PAT_NO_MATCH` or cause another PAT to appear uniquely eligible.
4. Register one stable callable for the complete held view through
   `Journal._require_at_commit`. The final callback checks lease identity/lifetime
   and bounded current authority/applicability rows directly. Do not reenter
   `PatCatalog._verify_evidence`: its authorizer ownership is now deliberately
   incompatible with nested commit-check invocation. Account for expected catalog
   mutations when checking promotion/recording; a whole-database equality check
   would incorrectly reject the operation's own writes.
5. Preserve original-key historical replay before fresh evidence preparation.
   A committed operation must remain retrievable when its old configuration,
   session or vault is unavailable. If COMMIT succeeds but a reply or subsequent
   lease cleanup fails, reconcile that original identity. Do not create a new
   operation or reinterpret the error as proof that the first was rolled back.

Integrated controls must cover multiple relevant PATs, unavailable evidence,
manifest/publication drift, revocation, configuration and endpoint-session drift,
expiry/replacement after selection but before commit, and commit-reply loss. Then
run the complete original worker/import/catalog/promotion/application/replay flow
on the exact new source under the original bounds.

The passing previous vault nearly fills its page cap; its 280,576 bytes of
unreserved headroom are not capacity owed to future work. Backed control capacity,
aggregate quotas/recovery, public mounting/full regression and native Harness
packaging remain required. Prompt synthesis and learned promotion, persistent
Arduino/device controllers, real I/O and driver/hub providers, microscope
commissioning and incomplete primary-source reading remain in the full goal.

# Lifecycle publication scope revision

Parent-approved staging revision after independent review, 2026-11-07. The original sealed `artifacts/verification/io-driver-hub-resource-design/DESIGN.md` is unchanged. Attempts 01 and 02 remain immutable. The attempt-02 seal and every byte it indexed are retained under `seals/02/`, with its original root-relative entries mapped beneath `seals/02/files/`.

The original pure lifecycle helper considered only consumers directly depending on the changed driver/service. However, `binding_proof` derives one binding generation from **all actions of an instance**. Publishing a new binding generation can affect an active sibling action even when that action's own dependencies exclude the target service. Treating the direct dependency set as the entire busy scope would not match existing Registry binding granularity.

The revised `generation_change_claims` performs two steps:

1. Find every instance with at least one consumer whose resolved dependency closure includes the target.
2. Include every action of each such instance in `affectedConsumers`, and union all their canonical claim atoms with the target's lifecycle atom.

The existing 32-claim cap applies **after** this expansion. Overflow refuses; no actions or atoms are truncated. Unrelated instances remain outside the publication scope unless their own proof depends on the target. Shared physical atoms can still cause legitimate contention. This supports multi-action instances rather than requiring one action per instance or inventing finer binding publication.

This is a change to the pure exclusion-set contract, not a claim of executable lifecycle support. Actual busy checking, atomic generation/binding publication, authority, installed-provider support, receipt recovery and physical safety remain unimplemented here. The new regression uses a modeled active sibling claim set to prove intersection; it does not run concurrent actions or Journal admission.

Attempt 03 adds a two-service, multi-action instance with a separate unrelated instance, verifies relevant binding identity changes and unrelated identity stability, and checks that expansion beyond 32 atoms refuses even though every individual action and the old direct-dependency set would fit.

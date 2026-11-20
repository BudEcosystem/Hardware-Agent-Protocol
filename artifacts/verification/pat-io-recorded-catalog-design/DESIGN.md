# Recorded invocation and current applicability

Keep the existing compiler's `hms.pat.environment/0.1` as the static environment embedded in the new catalog receipt. Add separately versioned `invocation` and `applicability` records. This preserves the meaning of the compiler output while making the stronger original-run/current-device contract explicit. The new catalog mount and receipt use explicit versions; no legacy metadata, evaluation or failed run is migrated implicitly.

The authorized request names only artifact, evaluator and original logical run. Installed code resolves the source authority, deployment, configuration receipt/digest/revision, original reservation/handoff/attempt, producer identity, compact consumer identity, import receipt and complete evidence closure. The receipt's invocation binds all of these to the installed evaluator implementation, policy and exact required matrix. It cannot name a caller path, result document, new attempt or replacement worker.

The applicability record contains the original source-device role assignment and dependency evidence: instance and binding identity, endpoint session, control/calibration generations, driver and installation identity, argument metadata, compiler and relevant resource proofs. The adapter derives these from retained original inputs whose correspondence the complete reducer checked. It must not derive them from the worker's reconstructed runtime. The finite-I/O profile remains scoped to its actual supported resources; hub/provider profiles need their own implementations and evidence.

Use three explicit phases:

1. **Prepare outside admission.** Authorize through the installed compact store, resolve the exact original run, read all retained bytes and run complete semantic reinspection. Bind the result to the consumer/evaluator version, import receipt and byte closure in bounded process-owned preparation state. Callers cannot insert prepared pass flags. A restart starts cold; preparation is read-only and launches no worker.
2. **Record in one Journal transaction.** Reauthorize, check current authoritative associations and reread bounded current retained bytes. Compare them with the prepared result and resolved invocation before publishing the versioned catalog receipt. A concurrent different result under the same logical key remains a retained conflict that inhibits reuse. A lost reply resolves the original record.
3. **Promote or execute with current applicability.** Verify the versioned receipt, exact current retained bytes, installed evaluator/consumer identity and current allowed source configuration/dependencies. Do this under the existing SQL/reentry guard using the shared Journal. External ledger/filesystem inspection, semantic reduction and nested transactions do not belong here. Historical receipt reads remain possible after ordinary device/configuration drift; they authorize no fresh action.

An in-memory preparation cache is an optimization, not a new source of truth. Its entry/byte limits, source-version binding and current-byte verification must be explicit. Missing/cold/changed evidence causes an availability refusal and cannot become an omitted candidate. New source or evaluator code requires explicit invalidation/revalidation. Trusted installed code must define how source changes are recognized outside admission; the verifier cannot perform an implicit filesystem check under the SQL-only contract.

Selection requires a corresponding recorded-profile path. First establish the request's static domain and authorized assignments, without reading inaccessible environments. For each relevant authorized candidate, validate the recorded receipt and required applicability/evidence availability before using a mismatch to remove it from the candidate set. Missing source presence, stale configuration/session, corrupted evidence and unavailable preparation must have explicit refusal outcomes. They must not become `PAT_NO_MATCH` merely because a check moved before or after the legacy environment comparison. A valid domain mismatch can still mean no applicable PAT; that decision is distinct from unavailable evidence. Do not silently change legacy selection behavior.

The new profile should be explicit host code so that the completed worker image and existing consumer identity remain unchanged. If a transitive dependency must change, produce a new identity and revalidate explicitly. Do not broaden the old producer closure without recording the consequence. The legacy execution constructor accepts a catalog sharing its Journal, but that alone does not establish compatibility: selection, stored-instance replay and public routing must all be checked.

| Required check | Expected result |
| --- | --- |
| Actual original 30-case import → record → promote → deterministic execution | Exact original identities; no second qualification worker; bounded simulated effects |
| Replay catalog recording after configuration/session drift or lost reply | Same historical receipt and key; no fresh execution authorization |
| Current configuration, source session, driver, resource or calibration changes | Explicit current-applicability refusal with unchanged mutation/effect rows |
| Worker reconstruction has a different session | It does not overwrite or satisfy the source-device applicability record |
| Cold or evicted preparation; changed/missing body | Availability refusal; no new worker or agent fallback |
| A second candidate is valid while the first has unavailable evidence | No manufactured unique selection |
| Inaccessible source assignment | No protected environment read or disclosure; authorized unrelated work remains possible |
| Concurrent conflicting evaluation under one key | Both records retained; affected reuse suspended |
| Revocation between preparation and publication | No catalog publication or action |
| Verifier attempts SQL mutation, nested transaction or reentry | Admission unwinds through the existing guard |
| Old receipt/profile under a new mount | Explicit unsupported/version refusal; no silent rewrite |
| Public CLI/MCP/Harness paths | Same invocation, applicability, conflict and availability semantics |

Retain the original execution, effect and storage ceilings. Measure current-byte verification cost before claiming admission latency. Protected control capacity and general allocated-storage quotas remain separate work. This document is a source-informed design, not an implemented or tested catalog adapter.

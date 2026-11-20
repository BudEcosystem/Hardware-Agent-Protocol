# Next: deadline diagnosis and durable supervisor handoff

Use the [frozen source](implementation01/index.json) and [retained results](results/README.md). A run reservation commits the original candidate, configuration receipt, request and all input documents. It is not an execution receipt. The full reserved-worker test reached a deadline in both its ordinary and passive diagnostic attempts, before the configuration/session-change replay portion. Do not infer that portion passed from the separate control tests.

## Preserve the execution boundary

The two failed logical runs remain archived failures, with their exact requests and partial state. Do not relaunch either, change its mutation key, clear its claim, repair its database or promote its partial evidence. New experiments require separately identified fixtures. An inherited regression pass does not repair either failed attempt.

The inherited owner-loss-after-settlement method also retains a worker deadline before its planned owner exit. Recovery archives the attempt as `OWNER_LOST` with no complete return; eight synthetic states and one claim remain. Preserve the pre-crash deadline receipt alongside the recovered archive so the later owner-loss reason does not erase the earlier cause of stopping. Its full-group and replay assertions remain unreached, and this failed logical run must not be relaunched either.

The owner-loss-after-spawn method retains a failed worker return with `PAT_IO_GROUP_WALL_LIMIT`, 26 of 30 completed-case entries, 23 states and one claim. Its exact output closure is intact, but full outcome inspection and later replay assertions were not reached. This demonstrates a worker-enforced limit as well as the separately observed supervisor limits; it does not establish why the workload missed its budget. Keep this failed run and its partial evidence unchanged.

The passive diagnostic measures about 34.68 CPU seconds over 59.118 sampled wall seconds for the worker, with system CPU pressure during the interval. These observations are not a causal experiment. The parent also performs full retention scans; previous instrumentation found repeated serialization and setup work. The run-store code executes before worker launch and is not called by the worker, so optimizing reservation parsing alone cannot explain a worker deadline correction. Keep the 60-second execution bound, complete matrix, effect limits and retention checks intact. Investigate a concrete source of duplicated pure work or a deployable protected-capacity mechanism, then measure the changed candidate under an explicitly recorded workload. Do not treat lower background load, a passing retry or a higher case count as a production fix.

## Bind the execution store before public mounting

The current supervisor's `supervisorIdentity` is a code/dependency identity. Its two-table ledger metadata records version 1, not a unique durable supervisor authority. The Journal authority and reservation identify the intended run, but the public service does not yet pin which durable supervisor store is responsible for it. The same request handed to a newly created empty supervisor store could be admitted again. A configured pathname or matching source hash does not close this gap.

A future checked service boundary needs a separately versioned supervisor-authority identity persisted in the supervisor ledger and pinned by the Journal's administrative mount record. Explicit creation and reopening must differ. Missing, replaced or mismatched stores must remain unavailable; they must not be silently recreated. Preserve legacy readers and existing fan behavior. An identity record alone does not detect rollback to an older copy of the same ledger; the handoff history must retain the original attempt association, and the deployment must state its storage/rollback assumptions.

The handoff must establish a durable association among the reservation digest, supervisor authority, exact request digest and original attempt ID before any producer is permitted to start. Since these are separate databases, specify the interruption states explicitly rather than claiming a cross-database atomic transaction. The existing supervisor performs admission, its `admitted` checkpoint, then launch; reopening an active attempt records interruption rather than silently resuming it. Any implementation must preserve that behavior and prevent a caller-supplied checkpoint or arbitrary callback from becoming the public authority mechanism.

| Interruption point | Required observable result |
|---|---|
| Reservation exists; supervisor admission was never begun | Retain the reservation and its exact inputs; distinguish this from an executed run |
| Supervisor admitted; Journal association not yet committed | Find the original row in the pinned supervisor store, reconcile its interrupted status, and do not create a second attempt |
| Association committed; producer not yet started | Retain the original attempt and known launch history; apply the existing interruption policy |
| Producer could have started | Query/reconcile the original attempt and its lease; missing evidence leaves execution uncertain |
| Original attempt row or supervisor authority is unavailable | Refuse fresh execution for that logical run; preserve historical association and uncertainty |
| Configuration, source, permissions or session changes | Historical status still refers to the original request; current authorization and eligibility govern new work |

The protocol design must also distinguish querying an old run from admitting new work. A current configuration check is not an effect-time lease. Hub or driver lifecycle changes must account for active dependent work and unresolved outcomes, even if the process hosting the agent has restarted.

## Complete the learning path

After the handoff, serialize import through the complete independent finite-I/O reader and an explicit I/O evidence profile. The earlier fan evidence store's four-check reducer and transaction ownership are incompatible with direct reuse for the 30-case I/O matrix. Pin original inputs, implementation and all output evidence; keep failed, corrupt, incomplete or cold evidence unavailable. Recheck current configuration and catalog eligibility before promotion.

The existing catalog environment has no service-configuration identity and its evaluator callback has no logical run ID. Introduce a versioned invocation/environment boundary or a separately checked service interface while preserving legacy behavior and historical replay. Public service mounting also needs enforced aggregate storage and protected control capacity; encoded byte accounting and periodic scans do not provide these.

The remaining end-to-end objective includes public PAT tools, agent synthesis and trace learning, deterministic applicability/novelty routing, persistent Arduino controllers, actual device I/O and driver providers, hub compute/storage/lifecycle control, streams, physical timing and microscope commissioning. The [SCPI header review](../../../research/instrumentation/scpi-headers-followup/README.md) adds native parser/session/effect constraints for future instrumentation providers. This candidate does not supply those bindings, and the full HMS goal remains active.

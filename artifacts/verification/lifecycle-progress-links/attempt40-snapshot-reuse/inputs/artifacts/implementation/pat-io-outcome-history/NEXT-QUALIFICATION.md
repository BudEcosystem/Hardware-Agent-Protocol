# Remaining route from checked groups to I/O PAT qualification

This audit preserves the [finite I/O design](../../verification/io-pat-qualification-design/DESIGN.md)
and [timing/outcome design](../pat-io-timing-oracle-design/DESIGN.md). The current
[snapshot-reuse result](../pat-io-snapshot-reuse/results/README.md) passes 132
distinct methods and completes fresh GPIO/PWM capture with independent inspection.
Each tested candidate is constant and single-step, with 30 cases including all
25 fixed challenges. Complete group evidence is necessary; it does not authorize
automatic promotion or establish physical/deployment qualification.

| Required qualification evidence | Current authoritative evidence | Remaining work |
|---|---|---|
| Whole declared-domain compatibility and timing | Producer contracts and independent reconstruction agree for the two complete current groups; existing pure domain checks remain | Bind both computations to trusted service configuration/process/run identity; preserve unsupported-domain refusal |
| Exact nominal/boundary/negative matrix | All generated cases for the two constant candidates execute and are independently reduced, including four negative cases per group | The ordinary parameterized example still exceeds the original 32-case ceiling and refuses. Do not claim arbitrary parameterized/application coverage or drop cases |
| Completion objective versus fault response | Nominal completion and all 25 fixed expected responses are checked; fault failures remain failed candidate contracts | Preserve this distinction through supervision, evidence import and catalog promotion; unknown effects cannot become success |
| Nominal scheduler timing | Current groups compose exact nominal scheduling and all eight fixed forward-time challenges | Add trusted run/wall association and measured aggregate enforcement; virtual scheduling is not physical timing |
| Cancellation and reopen | The current groups execute and independently inspect the required cases in the ten-case lifecycle family | Bind immutable requests, authority and retained state to the supervised current attempt |
| Lost pending/completion replies | Required lifecycle loss/recovery and retained-read variants execute and are independently checked | Preserve inconclusive attempts, exact keys, effects and claims through supervisor death/recovery and service import |
| Exact replay and same-key conflict | Current nominal histories prove replay without extra effects and reject the changed request under original keys | Keep that association in public qualification; unsupported withdrawal/pruned-namespace contexts cannot inherit it or retry with replacement keys |
| Start/run/wall/lease/clock boundaries | All eight timing and three clock/guard checks dispatch per current group | Attest process/run association and service bounds; checked virtual histories do not establish physical clocks or real-time guarantees |
| Shared pin/PWM/alias exclusion and independent-pad progress | Both complete groups independently inspect the four-actor shared-resource challenge with exact setup, identities and effects | Bind provider identity and declared actors to the trusted service; enforce aggregate resources without masking guards or introducing hidden actors |
| Permission, binding and session changes | All three authority challenges and permission-related lifecycle variants execute and pass exact independent outcome checks in each group | Establish current service/configuration/run attestation. Changed dependencies require rechecking; old requests cannot silently rebind |
| Unresolved or contradictory evidence | Readers refuse missing/contradictory evidence; prior failed captures retain unresolved accepted work and claims | Supervisor must retain exact incomplete evidence and durable ownership without resetting state or relabeling refusal as zero unresolved effects |
| Current implementation/configuration identity | Selected imports and inputs are pinned; separate pre-run setup and recorded compiler/driver/worker identities match the current inspected groups | Complete trusted configuration, import-closure, artifact/policy/source/attempt/process/run association. Identity matching and the seven-package compiler profile are not deployment attestation |
| Group budgets and retained evidence | Both groups pass original capture guards and exact independent operation/tick/record/byte accounting; the actual lowered record-cutoff test passes | Supply hard aggregate storage enforcement and protected control capacity. Cooperative checks and closed filesystem accounting are not an enforced aggregate quota |
| Persistent service and public PAT tools | Fan-specific libraries and a separately staged supervisor exist; complete I/O group capture/inspection is now available | Finish fixed trusted service configuration, aggregate enforcement, durable ownership, serialized evidence import and atomic catalog association before mounting public I/O qualification |

The next implementation joins trusted pre-run setup, exact child process/run and
retained output association to supervision, then enforces actual aggregate storage
before public qualification or promotion. The current reader's matrix, outcome,
archive, trusted-setup and identity-match flags are true. Configuration,
implementation, run and wall attestation; hard aggregate storage; physical
measurement; and qualification flags remain false.

All earlier failures remain immutable: the [historical-reader stage](../pat-io-group-history/results/README.md)
includes wrapper/launcher/deadline failures, and the [page-encoding stage](../pat-io-page-encoding/results/README.md)
retains the 23-case deadline failure and an instrumented 11-case run with accepted
work, a running parent and one claim. The current stage retains its original
test expectation failure and the test-only correction. None of those states was
reconciled or replaced to obtain the passing fresh runs. No timing, effect, case
or storage ceiling was widened.

Finite I/O qualification still does not implement persistent Arduino controllers,
natural-language synthesis/learning, real driver providers, microscope commissioning
or intelligence-hub lifecycle/compute management. These remain part of the original
end-to-end goal; the two complete synthetic groups do not substitute for them.

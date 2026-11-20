# Remaining route from checked trials to I/O PAT qualification

This audit follows the [24-test outcome result](results/attempt01/README.md) and
preserves the requirements of the [finite I/O design](../../verification/io-pat-qualification-design/DESIGN.md)
and [timing/outcome design](../pat-io-timing-oracle-design/DESIGN.md). A consistent,
independently checked trial is necessary evidence; it is not a complete group or
permission to promote an application.

| Required qualification evidence | Current authoritative implementation/evidence | Remaining work |
|---|---|---|
| Whole declared-domain compatibility and timing | `pat_io_contracts.py` produces the finite contract; new `pat_io_outcome_history.py` reconstructs it independently | Bind both computations to the current trusted worker/configuration; preserve unsupported-domain refusal before execution |
| Exact nominal/boundary/negative parameter matrix | The subsequent [combined planner](../pat-io-combined-matrix/results/attempt01/README.md) preserves domain cases and accounts for all 25 fixed challenges; 61 pure tests pass | Implement the recorded worker extensions and exact expected-outcome reduction; planned coverage is not executed coverage. The ordinary parameterized example exceeds the original case ceiling and refuses |
| Completion objective versus fault response | The new result distinguishes satisfied, failed and incomplete completion contracts | Define exact expected response per named trial. A correct cancellation can pass its fault check while failing the PAT completion objective; incomplete effects cannot qualify |
| Nominal scheduler timing | Configured GPIO/PWM and 16-step captures satisfy exact child and parent timing | Add retained nonzero-delay, late parent-reporting and boundary captures; historical completed cycles must remain true even when nominal timing fails |
| Cancellation and reopen | Original `test_pat_io_trials.py` captures accepted/pending cancellation and reopen; the configured family has pending reopen and later cancellation | Put every mandated case into the paired-configuration matrix and verify its exact trusted schedule, authority and terminal state |
| Lost pending/completion replies | Configured active/recovery fixtures cover retained activation, completed-before-withdrawal and failed reconciliation | Execute the required variants on the actual candidate/environment and account for them in one group; historical fixtures are not a current candidate's matrix |
| Exact replay and changed same-key conflict | `IoTrialEngine.submit()` records exact parent replay; it accepts only its original request | Add a closed recorded conflict operation with exact unchanged identifiers and independently derive the refusal. Do not retry mutation with a new key |
| Start, run, wall, lease and clock boundaries | Original trials have early lease waiting and run-deadline equality; static policy now checks sufficient whole-domain timing | Add paired raw captures for every required boundary and precedence. `advance_to` permits only forward integer time, so clock regression/epoch faults need an explicit retained failure path |
| Shared pin/PWM/alias exclusion and independent-pad progress | Installed topology has shared aliases; `IoTrialEngine` limits admission and operation inventory to the PAT's own steps | Introduce explicitly declared auxiliary actors, budgeted within the same 512-operation ceiling, with raw identity/claim/fence/effect evidence and independent outcome checks. Do not bypass the current guard with hidden fixture effects |
| Permission, binding and session changes | Current composition checks retained-read permission withdrawal and immutable configured bindings, plus supported reopen history | Add required binding/session and full-read-withdrawal cases. A changed dependency cannot inherit qualification or silently rebind an old request |
| Unresolved or contradictory evidence | Existing readers refuse missing/contradictory evidence; original trials preserve unknown effects | The supervised worker/group result must retain an inconclusive attempt with the exact evidence, never turn expected refusal into zero unresolved effects |
| Current implementation and configuration identity | Harness pins actual selected imports; compiler identity still has its documented optional-dependency gap | Reconstruct the current worker/environment, close identity scope and bind artifact/config/policy/source/attempt/run associations. Historical fixture identities remain historical |
| Group budgets and retained evidence | Current trial has 4,096 combined records, 16 MiB, 64 KiB documents, 2,048 ticks and 60-second wall limit | Enforce these at group scope with 32-case/512-operation preflight and 20 MiB derived-closure accounting. Per-trial limits alone do not establish aggregate admission |
| Persistent service and public PAT tools | Fan-specific evidence/memo libraries and separately staged supervisor exist | Finish fixed trusted service configuration, actual aggregate storage enforcement, durable ownership, serialized evidence import and atomic catalog association before mounting qualification |

The closed combined matrix and preflight now exist as an isolated library. The
next implementation is the recorded phase-engine extensions it requires, followed
by fresh candidate trials, group budget enforcement and independent expected-outcome
reduction. The planner separates candidate executions from fixed provider/authority
challenges, with exact binding and budget associations for both. It refuses a case
count that exceeds the original limits. Its passing planning tests do not establish
that the present engine can execute all of those challenges or fit actual evidence
and wall-time limits.

Finite I/O qualification still does not implement persistent Arduino controllers,
natural-language synthesis/learning, physical driver providers, microscope
commissioning or intelligence-hub lifecycle/compute management. Those remain
part of the original end-to-end goal.

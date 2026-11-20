# Harness procedure and PAT integration review

Status: read-only implementation design, 2026-11-07. This review ran no Harness
build, test, application, acquired program, model, native fixture, MCU or physical
I/O. It changed only this new evidence lane. It does not extend the historical
Harness integration receipt to the new procedure surface.

The inspected checkout is `/home/bud/Desktop/bud/hms-harness-a1626788`, base
`a16267881e98cdac5e1edd7ab6ff5d1dae0a8ff2`. Its `.git` file points into the live
Bud-Meta-Harness repository's worktree metadata. Preserve both that historical
checkout and the live repository. Future implementation should use a new
standalone clone with its own `.git`, pinned base and copied overlay inputs;
sharing read-only object storage does not justify sharing an index, refs, mutable
package files or build outputs. No clone was created in this review.

`inputs.json` pins 29 source/context inputs and retains exact copies under
`inputs/`. Full-file and selected-range reading are distinguished. The historical
multi-adapter receipt is an identity/context input, not a fresh test execution.
The parent concurrently updated only the Voyager research-status paragraph in
`docs/prompt-to-pat.md` after the snapshot. The reviewed delta is retained in
`context-drift.json`; it does not change the PAT interface or acceptance plan.
All inspected Harness inputs remained unchanged.

## Findings that determine the next change

The existing overlay has a complete service/provider/tool split. Its
`HardwareMethod` union, tool method table and generated output-schema method map
all expose nine methods. The current HMS authority exposes fourteen, adding
`procedure_submit`, `procedure_status`, `procedure_cancel`, `procedure_resume`
and `procedure_events`. The checked Python client already validates those new
requests and replies, including cross-field and request-correlated invariants.
The provider invokes that client once per request; it does not need another
transport or an AgentLoop business branch.

The generated Harness schema carries old source SHA
`313454429d8d4247dd41ab61e82480f174c7685f03f5a4b077f2ad94ad80705e`.
The reviewed current HMS local schema is
`1c8c29ca5bea858b92a9ce11304c8b0282051e9d43a21f4ae3a85743916d90d2`.
Adding only the TypeScript union or only model-facing descriptions would leave
the method/result surfaces inconsistent. Regeneration and an exact method-set
test must travel with the addition.

Harness native calls, PTC nested dispatch and AgentLoop calls already use the
same registry contribution. The tool package registers reversible effects;
unload must remove all fourteen contributions. The existing AgentLoop test
demonstrates durable discovery history, while the built SDK test demonstrates
primitive operation replay and separation of Harness work cancellation from
HMS operation cancellation. Neither tests procedure continuation yet.

The built SDK tests use a scripted `LlmAdapter.stream`: they are keyless, but
still enter the model abstraction. They cannot establish a deterministic PAT
path with zero model calls. Direct PTC execution does avoid a planning model in
the existing test, but an arbitrary retained JavaScript program is not an
eligible, versioned PAT with fresh parameter/resource binding. PTC's retained
`stateOwner` memory is explicitly process-local and is absent from the durable
Session format.

## Exact implementation map for the fourteen-tool increment

Paths below are relative to the future Harness clone unless marked HMS.

| File or component | Concrete change | Preserve |
|---|---|---|
| `packages/experimental/hardware/src/index.ts` | Extend `HardwareMethod` with exactly the five procedure methods. Update request JSDoc to distinguish parent envelope/ID and child operation IDs. | `HardwareReply`, same-UID provider authority and explicit `AbortSignal`; attribution never grants permission. |
| `packages/experimental/tool-hardware/src/index.ts` | Add `procedure_submit({request})`, status/cancel/resume with required `procedureId`, and events with required ID plus optional integer `after`/`limit`. Supply procedure-specific descriptions and an interruption message covering both parent and operation identity. | One registered executor for native/PTC; synchronous request snapshot; no automatic mutation retry; effect-scoped registration. |
| `packages/experimental/tool-hardware/src/output-schema.ts` | Regenerate from a pinned current HMS schema. Method map must be the exact fourteen-method set; submit/status/resume map to `procedureStatus`, cancel to `procedureCancel`, events to `procedureEvents`. | Closed success/error carrier, unchanged checked result, Session/call attribution, canonical JSON rendering. |
| HMS `integration/harness/generate_schemas.py` | Run only against the new clone after source pins settle. Add freshness/parity checking in the new verification lane; changing its projection policy is a separate deliberate choice. | Python remains authority for full bounds and semantics. The projection currently drops numeric/array/string bounds and may fall back to JSON for overlapping unions. |
| `packages/experimental/hardware-hms/src/index.ts` and `src/bridge.ts` | Revalidate with current HMS module/schema snapshot; expand tests for procedure uncertainty and cancellation. The generic one-call forwarding path needs no method-specific implementation. | Same-UID checked client, bounded input/output, sandbox selection, credential stripping, child termination and disposal. |
| `packages/experimental/hardware-hms/src/reply.ts` | Retain the closed bridge carrier decoder. Add procedure examples only where they check carrier behavior. | It intentionally trusts the local checked Python client for successful result semantics; do not present it as a separate full semantic validator. |
| `packages/experimental/tool-hardware/tests/hms-integration.spec.ts` or a new owned procedure spec | Loader/native and actual Node PTC coverage of all five additions, all fourteen names, exact replay, compact status/cancel semantics and HMR removal. | Real local daemon; independent evidence source; no extra mutating observer that manufactures a missing admission. |
| `packages/experimental/tool-hardware/tests/hms-sdk-profile.spec.ts` or new procedure SDK spec | Built `sdk` profile emits procedure calls using a scripted adapter, persists exact parent envelope, reopens work/Session, inspects interrupted state, explicitly resumes and queries child evidence. | Named profile launch and explicit test overlay; no production default opt-in, credential/network isolation. |
| New mixed-procedure launcher/spec beside compact tests | Own one SQLite route and native fixture(s) independently of daemon lifetime. Gate an actual native OP reply, kill/reopen only daemon, retain exact OP frames/queries and parent/child journals. | No physical transport, no replay by replacement key, one OP per native child. Existing single-compact fixture assumptions such as `noSQLitePlant` must not be copied into a mixed test. |
| Package English READMEs and profile README | State fourteen methods; fully bound straight-line procedure support; interrupted controls; minimal cancellation acknowledgement; independent child results; remaining PAT/domain limits. | Experimental/opt-in status, simulation evidence, no per-agent authority and no latency qualification. |
| New verification receipt and source/runtime snapshots | Pin new clone/source overlays, current HMS runtime/schema, node/pnpm/python, fixture build provenance, generated schema and all commands/output. | Old receipts/checkouts remain immutable and must not be silently rebased to the new results. |

Adding methods alone need not alter the Session event format. Existing
`tool/call`, `tool/result` and `tool/ptc-dispatch` carry arguments/results.
If a PAT catalog or new binding/promotion event is introduced, treat that as a
separate declared persistence-type change and review Session compatibility,
both SDK projections, reader behavior and snapshots under the repository rules.

## Required model-facing behavior

`hardware_procedure_submit` accepts the full retained `hms.procedure/0.1`
envelope. Describe parent acceptance as reservation/admission of an ordered
plan, not completion or simultaneous reservation of every future device.
Current authority and live readiness are checked again for each selected child.
An identical retry uses the same namespace, parent key and exact child requests;
changing any of them after an unknown outcome is a new physical attempt.

Status exposes parent control, cursor, per-step identities/state, held-resource
counts and unresolved operations. It does not contain all child result payloads.
Consumers must use `hardware_operation`/`hardware_events` for detailed child
evidence. `completed` is historical procedure control, and
`aggregateVerification: unverified` is not task success. Late failed/disputed
evidence remains visible. Canceled/expired parents may retain unresolved children
and claims; no presentation may collapse these to “stopped.”

`hardware_procedure_cancel` returns the minimal owner-safe acknowledgement,
including delivery `no_active_child`, `recorded`, `denied` or `already_terminal`.
It is a different result schema from procedure status. Preserve denied delivery
and its code without adding a follow-up status query that would fail after read
revocation. Harness work cancellation, tool abort, PTC cancellation, projection
EOF and provider unload end waiting; none implicitly calls domain cancellation.

On authority restart, parent control becomes `interrupted`. Existing child
receipt reconciliation proceeds, but later handoff/continuation requires explicit
`hardware_procedure_resume`. Session/work replay must never interpret an
interrupted parent as fresh admission, automatically call resume, or mint child
keys. An accepted paused child still expires under its original start/lease
deadline; interruption does not suspend time or permit it to starve unrelated
work on the same route.

## Validation and persistence hazards

The Python client is the semantic enforcement point across the bridge. The
reviewed result validator checks parent digest against the exact envelope,
child count/order/step IDs and intent digests, returned ID against requested ID,
cursor and contiguous linked prefix, state/claim/mayHaveActed consistency,
verification aggregation, unresolved operation list, cancellation delivery
correlation, and contiguous event sequence/cursor/head bounds. Keep these checks
in every projected call; a raw socket bridge or direct unvalidated JSON adapter
would bypass them.

The shallow Harness parameter schema can reject missing/wrong root fields while
Python enforces closed procedure fields, one-to-sixteen steps, typed child
invocations, key uniqueness, full timing containment, authority and replay
identity. Do not claim the generated ValueSchemaSpec reproduces all JSON Schema
bounds. Test invalid requests through the real executor/provider, not merely by
inspecting omitted schema fields.

The provider limits the complete method/params envelope to 65,536 bytes before
spawning. HMS wire wrappers, the bridge result, attribution, PTC output budgets
and Session records add separate overhead. Exercise maximum sixteen-step status,
large event pages, multibyte identifiers and exact byte boundaries. An output
overflow after dispatch is uncertain delivery, not proof that the parent was
never admitted. Do not drop step identities or substitute a success-shaped
truncation marker to fit a carrier.

The immutable envelope must be available before the first mutation is sent.
Native tool arguments and PTC subcall records supply session evidence, but the
planned process-loss test must verify what survives the actual crash point.
For a deterministic PAT executor, commit the bound envelope and instance identity
in its own durable authority-owned record before submitting; volatile JS
variables and a later outer `run_code` return are insufficient. Session history
is model context and attribution, not the physical execution authority.

## Deterministic PAT path: separate follow-on implementation

Start with a versioned straight-line PAT artifact that lowers to the existing
bound-sequence profile. Artifact identity is separate from each bound run. Store
typed inputs, applicability predicates, required capability/driver versions,
units/frames/calibration, resource/effect budgets, output/evidence obligations,
placement and pinned dependencies. Promotion records must retain failures and
rejected applicability examples; no model self-report proves eligibility.

Use a plugin-owned service/provider/consumer split, with deterministic structured
trigger input or an explicit human command through `ctx.commands`. The reviewed
architecture explicitly permits commands without a model turn. Avoid invoking
`agent.followup`, `session.run`, `BudMetaHarness.invoke` or a scripted model for
the eligible fast path: those are AgentLoop/model-path APIs. A trusted event
consumer can invoke the PAT service directly. Keep this behavior outside
AgentLoop; do not add speculative public tool names to the fourteen-method
increment before the artifact/binding consumer exists.

The deterministic router checks eligibility, exact version/dependencies, current
authority, current bindings and supported inputs. A unique eligible match binds
fresh namespace/keys/session/timing and persists the exact instance. Retrying the
same instance preserves all identities; a deliberate later run obtains new ones.
Reconcile unknown/active children before any revised physical attempt. Ambiguous,
novel or out-of-domain inputs produce a structured exception/escalation record,
and only the declared exception path involves the planning agent.

Measure model use at `prepareCall`/`stream` and any decision/provider path, not
only API credentials or network traffic. Successful eligible triggers must make
zero planning-model calls. “No model at all” additionally prohibits pinned
perception/numerical inference; report it separately. A new free-text prompt may
need semantic interpretation and must not be counted as a zero-inference route.
The current sequence profile supports neither branches/loops/streams nor MCU
program installation; reject unsupported lowering rather than silently emulate
timing-sensitive control through repeated host tool calls.

## Hub, driver and I/O extension plan

Expose concrete advertised capabilities through the registry and existing
prepare/invoke/procedure lifecycle. An intelligence host is also a managed
resource; its process UID or agent role does not grant arbitrary driver or host
administration. Keep provider effects behind explicit support matrices and
separate lifecycle permissions. Do not implement generic shell execution as a
substitute for a driver/OS capability contract.

Before adding raw GPIO/PWM/bus actions, introduce canonical resource dependency
and alias resolution in HMS admission: shared pins, timers, DMA channels, bus
addresses and higher-level actuator capabilities must resolve to the same
compatible claim graph. Resolve before claims/fence allocation, so alternate
tools cannot bypass conflicts. The present flat registry/claims/history are
foundations, not a completed hierarchical ownership graph.

Driver install/configure/drain/replace and hub reboot/network/inference-service
changes need affected-dependency discovery, prevention of incompatible admission,
declared drain/local-stop behavior, immutable artifact/config revisions and new
session/generation records. Restart cannot clear unresolved external effects.
Changing a dependency suspends/rechecks affected PAT applicability. Host loss
must remain reconcilable even when the caller waiting for the reply disappears.

Define acquisition streams and artifact lineage separately from command
responses: bounded rates/bursts/buffers, backpressure/drop policy, sequence gaps,
sample/material identity and clock/quality/error facts. Admit CPU/GPU memory,
queues and scheduling budgets as resources; independent watchdog/stop capacity
cannot be inferred from idle-GPU availability. Physical providers and combined
CPU/GPU/network/storage timing measurements remain required deployment work.

## Acceptance gates for the future implementation

`acceptance.json` provides machine-readable planned cases; none ran in this
review. The next bounded increment should pass these focused gates:

1. Exact fourteen-name native and PTC catalog parity, current schema digest and
   method/result mapping; opt-in Loader composition and disposal to zero tools.
2. Real native and Node PTC mixed SQLite/native-C procedure, exact parent replay,
   stable child IDs, one OP per native child and independent SQLite effect count.
3. Real daemon death after gated native admission but before durable reply;
   endpoint survives, recovery uses matching QUERY, no replacement OP, parent
   stays interrupted until explicit resume, and later child waits.
4. Built SDK/AgentLoop Session and work-item reopen retain the same parent
   envelope/ID and child prefix, reconstruct model-visible history, and do not
   conflate Harness work cancellation with procedure cancellation.
5. Invalid parent/digest/ID/prefix/cursor/event/cancel responses reject through
   the checked bridge; wrong namespace/key/session/bounds and reserved child
   bypass attempts reject through actual authority.
6. Parent cancel with denied child cancellation, revoked read, outstanding claims,
   expired deadline and late disputed result remain accurately projected.
7. Sixteen-step/multibyte/full-wrapper bounds, pre/post-dispatch abort and provider
   unload preserve uncertainty and exact retained identities; all resources reap.
8. Paused compact queue head permits an independent operation and expires without
   dispatch, as the new HMS transport regression now exercises locally.
9. Separate PAT prototype: eligible repeated structured triggers make zero
   planning-model calls; ambiguity/out-of-domain follows declared exception;
   restart retains artifact digest, bound input, executed prefix and identities.
10. Separate domain providers: pin/timer/raw/high-level alias conflicts, driver
    changes with active work, hub restart, stream gaps and compute pressure;
    synthetic success is never labeled physical validation.

The future clone must honor root/package/experimental AGENTS rules: named
profile launch, experimental dependency isolation, real Loader composition,
model-visible logging, reversible registration, lifecycle teardown, current
English documentation and required keyless snapshots. Plan build artifacts and
then build checking plus focused behavioral tests for that new tree; do not
re-run broad historical suites merely to change a receipt. No build or test was
started while the parent owned the active HMS full-suite session.

# Review of HMS draft 0.1 execution invariants

Review scope: `spec/00-scope.md` through `spec/04-scenarios.md`, inspected 2026-11-06. [Input hashes](../research/protocols/draft-review-inputs.json) identify the reviewed versions; section names remain authoritative if line numbers move. This review concerns a design draft, not missing implementation. “Implementation blocker” means the semantic decision must be resolved before implementing the affected guarantee. It does not mean research or other design work must stop.

The draft correctly separates command delivery from physical effects, preserves native controllers, rejects exactly-once claims based on transport, and avoids treating software checks as certified protection. The issues below arise where those principles need a precise execution rule.

## P0 — resolve before implementing mutating execution

### R1. Normal lease/log admission can block the operation intended to stop current work

**Class:** implementation blocker; concrete conflict between general and special rules.

**Sections:** [01 Architecture — Decision](../spec/01-architecture.md), paragraph after CLI example; [02 Execution — Admission and invocation](../spec/02-execution.md), steps 5–6; **Ownership and concurrency**; **Cancellation, stopping and disconnection**; [03 Registry/runtime — Runtime services](../spec/03-registry-runtime.md), mandatory logging failure paragraph.

All mutating surfaces must use the same admission rules; invocation requires all resource leases and a durable intent record. Unknown outcomes retain resource claims. A distinct `stop(resource)` is declared, but no exception or ownership relationship is defined. An operator authorized to stop a motor can therefore be refused because its running or unknown operation owns the motor. Disk failure can similarly deny every new mutation, including the software stop. An independent emergency circuit remains useful but does not resolve the software API contradiction.

**Proposed invariant:** cancellation targets an existing operation without acquiring a conflicting new exclusive lease. Installation-defined stop has a separate admission mode: authenticate and validate its bounded stop semantics, then allow it to preempt or join the affected authority domain according to policy. It must not wait behind the operation it stops. Specify whether any stop path may execute when durable logging is unavailable, and record that case as degraded audit; ordinary mutations remain denied. Do not allow the special mode to carry arbitrary actuator commands.

**Acceptance scenario:** hold an unresolved motion lease, fill the journal disk, then request an authorized stop from another operator. Verify the documented stop path remains available and a normal move remains denied.

### R2. A higher fence must invalidate queued work and authority must be checked at execution, not only arrival

**Class:** implementation blocker; missing execution invariant.

**Sections:** [02 — Ownership and concurrency](../spec/02-execution.md), first two paragraphs; **Bounded procedures and dynamic MCU commands**, tiny serial paragraph; [01 — Deployment profiles](../spec/01-architecture.md), P0/P1/P6.

Rejecting older fencing tokens on new requests does not stop an old owner’s already queued procedure from executing after handover. Lease expiry is described behaviorally, but the observing clock, enforcement location and relationship to the last accepted fence are unspecified. “One physically exclusive gateway” prevents concurrent bus masters but cannot revoke commands already buffered inside the device, or establish that a replacement gateway has authority while an old disconnected gateway still controls the bus.

**Proposed invariant:** define a resource authority generation, lease expiry in an enforceable clock domain, and a monotonically ordered fence scoped to that authority. Validate at queue acceptance and before each effectful step. A newer authority generation atomically invalidates old queued work and applies a declared policy to already-running work. Specify recovery of the fence after endpoint/gateway restart. For an incapable legacy endpoint, do not grant a conflicting owner until the exclusive gateway has demonstrated quiescence/reconciliation; advertise the weaker guarantee.

**Acceptance scenario:** queue steps under fence 10, transfer authority to 11, delay old frames, restart the endpoint, and partition the old gateway. No old step may start under the new ownership claim unless the explicitly declared bounded continuation policy authorizes that exact step.

### R3. Key retention cannot reject forgotten keys without an explicit replay boundary

**Class:** implementation blocker; incomplete durable storage semantics.

**Sections:** [02 — Idempotency and crash windows](../spec/02-execution.md), first paragraph; **Admission and invocation**, request fields and ordering.

The draft requires retaining mappings for a finite period and rejecting expired keys. Once a mapping is deleted, an opaque old caller key is indistinguishable from a new one. Also, the canonical request includes time/lease/epoch context, while retry behavior promises the same key returns the existing operation. Refreshing an expired lease or reconnecting can change that digest, or cause admission to reject a harmless result lookup before finding the existing operation.

**Proposed invariant:** specify a replay boundary: retained tombstones, authenticated expiring key epochs with a persisted minimum accepted epoch, or another concrete bounded scheme. Separate immutable physical intent from transport/session credential and renewed lease metadata; define exactly which fields affect deduplication. Authenticate every retry and authorize result access, but look up an existing operation before attempting a new physical admission. A retry never updates the original intent or re-dispatches it. A new authorization to perform another physical action needs a new key.

**Acceptance scenario:** retry after mapping retention expires, after lease renewal, after a crash, and after delegation revocation. Old actions cannot execute again; authorized result retrieval can return a known operation without new actuation rights; revoked actors cannot read protected results.

### R4. Boot identity, control authority and observation sequence epochs are conflated

**Class:** implementation blocker for reset/replay and tiny/legacy profiles.

**Sections:** [02 — Objects](../spec/02-execution.md), boot epoch rule; **Observations**, sequence rule; **Admission and invocation**, epoch field; [04 — Home IoT](../spec/04-scenarios.md), manual intervention changes control epoch; [01 — Deployment profiles](../spec/01-architecture.md), P0/P1.

The core carries a boot epoch but defines it to change whenever command history or position authority is lost. The home scenario separately references a control epoch, which is not defined in the core. A human can move a knob without rebooting the MCU, and an adapter process can restart its event sequence without rebooting the hardware. A legacy gateway may not observe a peripheral reboot at all. A tiny boot nonce also requires a uniqueness/recovery mechanism; naming a nonce does not establish one.

**Proposed invariant:** distinguish endpoint boot/session identity, resource control generation and stream producer epoch. Define which invalidate queued operations, inferred position, cached observations and cursors. Allow legacy endpoint boot identity to be explicitly unknown, with guarantees restricted accordingly. A gateway-generated session ID must not be represented as evidence of a physical reboot. State how reset detection or a new handshake establishes a valid tiny-endpoint session, and what happens when reset cannot be detected.

**Acceptance scenario:** manual turn while electronics stay powered; adapter-only restart; endpoint reset behind a continuously connected gateway; sequence wrap. Old inferred position and command authority cannot survive events that invalidate them.

## P1 — resolve before interoperable wire schemas and adapter conformance

### R5. Cancellation and reconciliation races have no legal lifecycle transitions

**Class:** implementation blocker for operation state-machine conformance.

**Section:** [02 — State and evidence](../spec/02-execution.md), diagram and surrounding paragraphs; **Cancellation, stopping and disconnection**.

The diagram permits cancellation only from `running` and gives `cancel_requested` only a `canceled` successor. A request can arrive while accepted/dispatching, or completion can win the race after cancellation is requested. A legacy action may finish without intermediate running evidence. The text requires reconciliation of `outcome_unknown`, but no resolution transitions are defined. “Any dispatched state” is also ambiguous about already terminal states.

**Proposed invariant:** publish an exhaustive transition table with evidence requirements and terminal-state rules. Cancellation request/acceptance should be tracked independently from execution outcome, allowing completion or failure to win. Define cancellation-before-dispatch, unsupported/rejected cancellation, direct completion evidence, and reconciliation updates. Preserve the fact that an outcome was previously unknown in the event history rather than rewriting it away. Keep `completed` plus failed/unverified effect evidence distinguishable from the operation’s success predicate.

**Acceptance scenario:** completion and cancel responses arrive in either order; cancel occurs before dispatch; a result is recovered after an unknown outcome. All produce legal, deterministic histories without a false canceled claim.

### R6. Deadline and observation time need separate, bounded clock semantics

**Class:** implementation blocker for freshness/deadline guarantees; not a requirement for synchronized clocks everywhere.

**Sections:** [02 — Observations](../spec/02-execution.md); **Admission and invocation**, `desired start/deadline policy`; **Bounded procedures**, `deadline/TTL`; [03 — Performance design and measurements](../spec/03-registry-runtime.md).

Observation `uncertainty` could mean measurement error or time error. Source acquisition and host receipt timestamps normally belong to different clocks. Receipt age alone cannot identify an old sample re-sent from a device cache; its acquisition-latency bound must include that cache. A TTL can expire at admission, queue start, or completion, which have different physical consequences. A hub-relative deadline cannot be blindly compared to an MCU timer, especially across reset/wrap.

**Proposed invariant:** separate measurement uncertainty, clock uncertainty and acquisition-latency bound, each with units and method. Include the clock domain/epoch for every timestamp. If acquisition age is unbounded, report unknown age and reject a freshness-required operation. Distinguish not-before, latest-start, maximum-run-duration and latest-completion deadlines; define where each is enforced and the declared miss behavior. For unsynchronized MCUs use local duration budgets established at a validated handshake/receipt with explicit transit assumptions, rather than inventing an absolute time conversion.

**Acceptance scenario:** replay a cached sample with a new receipt timestamp; skew clocks; reset/wrap the MCU clock; queue a command until its start deadline expires. No stale sample becomes fresh and no expired command starts merely because its packet arrived earlier.

### R7. Prevalidated local procedures conflict with unspecified per-action host admission

**Class:** implementation blocker for efficient bounded MCU execution.

**Sections:** [02 — Admission and invocation](../spec/02-execution.md), per-dispatch journal/lease rules; **Bounded procedures and dynamic MCU commands**; [03 — Performance design and measurements](../spec/03-registry-runtime.md), “each optimization must preserve per-action admission”.

A local tiny executor cannot persist a host journal entry or run a nine-service admission cycle for every motor pulse or compiled action step. Conversely, validating the whole program once cannot authorize later steps under changed interlocks, bindings or authority. The current wording does not locate those responsibilities, so conforming implementations could either destroy local timing or skip necessary runtime checks.

**Proposed invariant:** define a durable procedure admission covering an exact program digest, parameter set, resource handles, capabilities and budgets. Identify locally enforced per-step conditions and externally enforced conditions that require a barrier before continuation. State which internal steps are journaled/batched and how partial progress is reconciled after reset. A compiled procedure never gains permission to exceed its preauthorized envelope. No hard-time guarantee may depend on an unbounded host round trip.

**Acceptance scenario:** disconnect the hub during a validated scan; revoke authority or open a local interlock between steps; restart after step N. Only declared local continuation is possible and step N is not blindly repeated.

### R8. Binding invalidation and firmware compatibility need an atomic execution-generation check

**Class:** implementation blocker for registry/execution integration.

**Sections:** [02 — Discovery and descriptions](../spec/02-execution.md), pinned revisions; **Admission and invocation**, steps 1 and 7; [03 — Registry records](../spec/03-registry-runtime.md), invalidation paragraph; **Identity and lifecycle**, updates paragraph.

Immutable descriptions prevent their bytes changing, but do not prove that the current firmware/adapter/physical installation still implements those bytes. The request carries descriptor and calibration revisions but no explicit commissioned-binding generation. Geometry, fixture or manual state can change after admission and before a delayed queued step. Invalidation is required, but its effect on accepted and running work is not stated.

**Proposed invariant:** pin an execution binding generation covering the required firmware/adapter compatibility, geometry, attached equipment, calibration and relevant mode. Bind it to endpoint/gateway attestation or commissioned evidence as available. Invalidation prevents queued starts and invokes the declared running-operation policy; revalidation creates a new generation. Negotiate required semantic features explicitly and refuse missing ones; a compatible transport version does not establish compatible physical behavior.

**Acceptance scenario:** change objective/fixture or firmware after admission but before dispatch, including a cached registry read. The old operation cannot start against the new installation.

### R9. Snapshot-to-watch handoff can silently miss a state transition

**Class:** implementation blocker only for claims of gap-free state monitoring; wording is sufficient if the first profile explicitly advertises possible gaps.

**Sections:** [02 — Observations](../spec/02-execution.md); **Streams and bulk data**, watch cursors; [04 — all scenario sequences](../spec/04-scenarios.md).

The presence of sequence numbers and gap markers alone does not connect an observation to an event cursor. A state change between `observe` and `watch` can be missed without any sequence discontinuity visible to the consumer. Different device and gateway sequences worsen this unless their relationship is specified.

**Proposed invariant:** supply an observation revision/cursor with a valid replay handoff, or subscribe first then obtain/reconcile a snapshot under defined ordering. If an adapter cannot establish that relationship, advertise a possibly-gapped watch and require fresh re-observation for state-critical decisions. Define cursor scope, producer epoch, retention exhaustion and authorization rechecks.

**Acceptance scenario:** change state exactly between snapshot and subscription, then lose/reconnect the stream. The consumer either sees the change or sees an explicit inability to claim continuous observation.

## P2 — wording and precision

### R10. “Universal coverage” should be an extensibility requirement, not a proved representation theorem

**Class:** wording issue, not an implementation blocker.

**Section:** [00 — Intended outcome](../spec/00-scope.md), “every controllable device can be represented”.

The later caveats are good, but the absolute statement is stronger than the evidence. A representable stub with every action unsupported does not satisfy useful automation. Prefer “the model is designed to permit direct, gateway and retrofit representations across device classes; each claimed device/action needs a binding and evidence.” Preserve broad scope while avoiding declaring universality from an abstract envelope alone.

### R11. Distinguish publication revision from instance/execution revision in the glossary

**Class:** wording/schema preparation issue.

**Sections:** [01 — Description layer](../spec/01-architecture.md); [02 — Objects and Discovery](../spec/02-execution.md); [03 — Registry records](../spec/03-registry-runtime.md).

A device type describes capabilities, a description artifact may contain installation-specific calibration context, and the instance binds a description to firmware/calibration. Clarify whether reusable type artifacts and commissioned instance descriptions are different artifact kinds. Otherwise catalog reuse and signature ownership become ambiguous. Keep type digest, instance ID, binding generation, calibration revision and authority generation separate fields with explicit meanings.

## Recommended order

Resolve R1–R4 first because they govern whether hardware may execute or be stopped. Resolve R5–R8 before freezing operation/envelope schemas or implementing durable execution. Resolve R9 before any gap-free watch promise. R10–R11 can be addressed as prose/glossary edits. These changes refine the current broad design; none requires narrowing the intended device or scenario coverage.

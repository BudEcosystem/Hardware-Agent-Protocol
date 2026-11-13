# Execution semantics — proposed normative core

## Objects

A `DeviceType` describes supported capabilities. A `DeviceInstance` binds an immutable description digest to an enrolled identity, deployment, adapter, firmware revision, calibration revision, endpoint session identity and resource control generation. A `Resource` denotes an axis, bus, work envelope, sample, power budget or other exclusivity constraint. An `Observation` describes what was measured or inferred and when. An `Operation` records one physical intent and its lifecycle. A `Procedure` is a bounded composition of operations. A `DataRef` identifies an immutable capture or a live stream with independently defined retention.

Device identity MUST survive address changes. Endpoint boot/session identity MUST change when endpoint execution history resets. Unknown legacy boot identity MUST be reported as unknown, not replaced by a fabricated physical reboot. A gateway can supply an instance identity for a legacy device, but MUST declare that it authenticates the gateway rather than the physical endpoint. Reconnection MUST NOT silently bind an old identity to a replacement device.

## Discovery and descriptions

`discover(filter, cursor, limit)` returns authorized instance summaries with presence expiry, description digests and capability identifiers. `describe(instance, digest)` returns a versioned artifact, not a changing view. `bind` chooses a commissioned deployment binding with compatible units, coordinate frames, timing, feedback and resources. Matching a capability name alone is insufficient.

Descriptions MUST include the action's input/output schemas; units and coordinate frames; physical effect class; resources; preconditions; duration policy; cancellation and disconnect behavior; evidence needed for success; and implementations of applicable local limits. Natural-language manuals and tags assist interpretation but cannot grant authority or weaken enforced bounds.

Capability IDs use versioned namespaces. Reject unknown required semantics. Optional descriptive extensions may be ignored only when marked non-executable. Capability revisions and wire protocol versions are separate. Pins to descriptor and calibration revisions avoid silently interpreting an old request under new device geometry.

## Observations

`observe` returns value, unit, frame (where relevant), source, evidence kind, acquisition time, receipt time, clock domain/epoch, measurement uncertainty, clock uncertainty, acquisition-latency bound, quality, sequence, stream producer epoch, endpoint session identity, control generation and calibration revision. Evidence kinds distinguish physical sensor, controller-reported measurement, command echo, estimate and simulation. Quality includes valid, stale, invalid and unknown. Missing measurements MUST NOT become zero or the last commanded value.

A request specifies maximum acceptable age and required evidence kind. Measurement uncertainty, clock uncertainty and acquisition-latency bound are separate fields with explicit units and methods. Every timestamp names a clock domain and epoch. Acquisition clock identity includes its producer/source and endpoint session; matching domain/epoch labels from different producers do not establish a common timebase. Cross-producer comparisons require an explicit qualified mapping. Acquisition latency includes device caching: a recently received old sample is not fresh. Unbounded acquisition age is unknown and fails a freshness requirement. Age is computed conservatively from a local monotonic receipt clock and bounded acquisition latency, or a synchronized source clock with reported uncertainty. Clock synchronization failure cannot make stale data look fresh. Observation sequences restart or wrap only with a new stream producer epoch. A multi-device snapshot declares skew and per-item timestamps; it MUST NOT imply simultaneity without supporting synchronization.

## Admission and invocation

`invoke` carries a stable caller operation key, actor/delegation context from the authenticated channel, instance ID, endpoint session identity, control generation, action ID, descriptor digest, commissioned binding generation, calibration revision, typed arguments, start/completion timing policy, required evidence and resource lease reference. Credential secrets are carried out of band. The model cannot self-assert authorization with a boolean.

Before dispatch the runtime MUST:

1. Resolve the physical instance and pinned description; reject absent, expired or changed bindings.
2. Verify actor, action/resource scopes, delegation expiry and any required operator authorization bound to this exact request digest.
3. Validate types, finite numbers, units, frames and bounds. Implicit rounding, clamping or unit conversion must not alter intent; return a proposed normalized request for explicit acceptance where needed.
4. Verify required fresh state, calibration, interlocks, device mode and local limits. Required missing state denies dispatch; an explicitly commissioned degraded mode may define different requirements.
5. Acquire all required resource leases without deadlock and record the current fencing epoch.
6. Persist the operation intent and request digest before handing it to a worker. Resource reservation, journal admission and dispatch ownership must be atomic within the authority domain.
7. Recheck time-sensitive conditions as close to execution as feasible; native controllers enforce conditions whose timing cannot be guaranteed by the host.

Preflight is advisory and returns what was checked, when and against which versions. It cannot authorize later execution from a stale snapshot. A capability with no physical feedback may advertise command delivery success; it cannot promise verified task completion.

## State and evidence

| Current execution state | Allowed successor | Required evidence |
|---|---|---|
| accepted | dispatching | Durable dispatch ownership and current admission |
| accepted | rejected_before_dispatch / canceled | Proof no physical dispatch occurred; reason or accepted cancellation |
| dispatching | running / completed / failed / canceled / outcome_unknown | Endpoint evidence; direct completion or observed cancellation termination is permitted without an intermediate running event; missing reply implies uncertainty |
| running | completed / failed / canceled / outcome_unknown | Capability completion, known fault, observed cancellation condition, or insufficient evidence |
| outcome_unknown | running / completed / failed / canceled | Explicit reconciliation event with new evidence; retain the prior unknown history |
| completed / failed / canceled / rejected_before_dispatch | none | Corrections append an evidence-dispute event, never silently rewrite the outcome |

Cancellation is an orthogonal state: not_requested, requested, acknowledged, rejected, or confirmed. It can be requested while accepted, dispatching, running or outcome_unknown. Completion or failure may win a cancellation race. A late cancellation acknowledgement cannot overwrite a completed execution. Unsupported cancellation reports rejected while the execution state remains independently tracked.

`accepted` means durable admission, not movement. `dispatching` means delivery may have happened. `running` requires endpoint/adapter evidence, with its source stated. `completed` requires the capability's defined completion evidence; effect verification remains a separate field with `verified`, `unverified` or `failed`. An operation configured to require verified effects cannot complete successfully without them. `canceled` means a documented termination condition was observed; it is not interchangeable with “safe” or “at rest.” `failed` records known failure and any partial effects. `outcome_unknown` records insufficient evidence and inhibits conflicting follow-on actions until reconciliation.

A result includes operation ID, state, request digest, timestamps, dispatch history, physical-effect certainty, completion evidence, partial outputs and recovery guidance. Errors carry a stable code, failure phase, `may_have_acted`, retry classification, affected resources and evidence references. Distinguish validation refusal, authority denial, stale observation, expired lease, version mismatch, unsupported capability, device fault, timeout before dispatch and ambiguous timeout after dispatch.

Once physical execution might have occurred, a transport exception MUST NOT be reported as a guaranteed non-execution. Host restart MUST recover journaled operations and reconcile them with endpoint state before granting conflicting actions. Retain unresolved resource claims conservatively, with a documented operator recovery path.

## Idempotency and crash windows

The key namespace is principal + deployment + server-issued replay namespace epoch + caller key. The same key and canonical request digest returns the existing operation; the same key with a different digest is a conflict. The host profile uses server-issued replay namespaces with a persistent monotonic namespace epoch and an immutable expiry. Retain mappings until namespace expiry; then retain the minimum accepted epoch, rejecting old namespaces even when individual mappings are purged. Expiries are monotonically ordered within each principal/deployment namespace series; advance the persisted floor only past a contiguous expired range. Unexpired namespace mappings MUST NOT be deleted. A namespace reference is authenticated and checked independently of its caller-supplied local key. Tiny gateways own this durable bookkeeping when endpoints cannot. Recovering the database without its replay floor requires a new authority identity and invalidates old namespaces.

Authenticate and authorize result access, then look up an existing key before doing new actuation admission. Existing operations may be read under observation authority without reacquiring execution leases; revoked access still denies disclosure. The immutable intent digest includes target, action, arguments/units/frames, endpoint session/control generation, description/binding/calibration generations, timing policy and required effects. Credentials, transport IDs and renewed lease proofs are outside that digest. A retry cannot modify the original intent or cause redispatch. The experimental [host profile](08-host-contract.md) now pins JCS/domain-separated SHA-256 and wire fixtures; release interoperability and other binding contracts remain unfinished.

Network exactly-once delivery does not imply exactly-once physical execution. Native endpoints with durable deduplication can provide a stronger execution guarantee over a stated persistence window. Legacy devices generally cannot. If the host crashes between sending and recording the reply, reconnect MUST query/reconcile rather than resend a non-idempotent action. Relative motion, dispensing and toggle operations are especially sensitive. Absolute setpoints reduce some duplication effects but are not automatically harmless: repeating a heating cycle may extend exposure.

## Ownership and concurrency

Resource locks include shared workspaces and coupled actuators, not merely device IDs. A leader issues monotonically increasing fencing tokens scoped to the resource authority; an endpoint or exclusive gateway checks authority at acceptance and immediately before each effectful step, rejecting older tokens. A newer authority generation invalidates old queued work atomically and applies the declared interruption/continuation policy to running work. Where endpoints cannot fence, only one physically exclusive gateway can be authoritative. A distributed lock in a database alone does not stop a disconnected previous controller. If a legacy controller cannot revoke buffered commands, the gateway MUST demonstrate quiescence and reconcile them before assigning conflicting ownership. It advertises this weaker handover capability. Restart must restore a persistent fence floor or establish a fresh authenticated endpoint session that rejects all previous-session frames before granting authority.

Lease expiry triggers the installed loss-of-authority policy: controlled stop, hold, complete a bounded atomic step, or another assessed behavior. Do not prescribe power-off universally; gravity-held loads and thermal systems can require another response. Renewals cannot extend operation or exposure budgets unless the capability explicitly allows it. Watchdogs run independently of agent inference and blocking adapters.

Cross-device workflows are not ACID transactions. Use resource reservations, explicit barriers, step records, irreversible commit points and compensation procedures. Compensation is another physical action with its own checks, not a rollback promise. Loss of one participant prevents unsafe continuation and reports what already happened.

## Cancellation, stopping and disconnection

`cancel(operation)` is a request against the existing operation; it does not acquire a conflicting new exclusive lease. Its normal path has a durable record. A cancellation acknowledgement confirms receipt only. The adapter reports cancellation progress and final evidence. Releasing a tool AbortSignal MUST NOT drop the underlying operation record. `stop(resource)` is a distinct installation-defined operation. An emergency-stop hardware channel is independent of this software API.

Stop has a separate bounded admission mode: authenticate stop authority, resolve a commissioned stop procedure and its scope, then preempt/join the relevant authority without waiting behind the work being stopped. It cannot carry arbitrary move/setpoint commands. If normal journal storage is unavailable, a commissioned stop path MAY execute with explicit degraded-audit status, local evidence buffering where possible and later reconciliation. Ordinary new mutations remain denied. A stop must not be blocked solely because the stopped operation owns an unresolved lease. This exception does not waive stop authority or expand the permitted stop procedure.

A stop command has priority over normal work where the transport permits, with bounded queue behavior and independent watchdog fallback. Killing a worker is not proof of stopped equipment. A paused procedure retains explicit resource/energy commitments; pause must not silently let an energized actuator persist indefinitely. Operator recovery and restart are separate authorized transitions.

## Streams and bulk data

`watch` returns typed events with cursor, epoch, sequence and gap markers. Define replay retention, delivery ordering and subscription authorization. A snapshot carries a revision/cursor usable for replay, or the adapter uses subscribe-before-snapshot with a specified reconciliation order. If neither is supported, advertise possible gaps and require a fresh observation for state-critical decisions. Cursors are scoped to instance, stream producer epoch and authorization scope; exhaustion or lost ordering returns an explicit gap and resnapshot requirement. Use bounded queues and explicit drop/sample/block policies. Backpressure must not stall a control loop. Slow model consumers receive summaries or references, not an unbounded telemetry backlog.

Images and tensors use a data reference specifying dtype, shape, strides/layout, units/frames, capture time, calibration, hash for immutable data, access scope and expiry. Streaming references carry a distinct lifetime. A missing frame must not silently substitute a prior frame. Synchronization for image/motion experiments uses hardware trigger or a measured clock scheme; record uncertainty.

## Bounded procedures and dynamic MCU commands

A procedure declares required capabilities/resources, parameters, finite step/loop bounds, maximum runtime, per-action deadlines, state predicates, failure handling and cleanup. Compile only supported constructs. No unbounded recursion, arbitrary register writes or unbounded memory allocation in the tiny profile. Verify total instruction, queue and timing budgets before installing. Changes to actuator authorization or firmware require a separate maintenance mode.

For an Arduino-class target, dynamic commands mean runtime selection and parameterization of installed primitives (digital I/O, ADC sampling, PWM, motor/servo actions and bounded sequences) or a verified compact program. New arbitrary C++ is not dynamically executable without compilation/flashing. Optional larger-device sandbox execution (for example a suitable bytecode VM) remains constrained by resource handles; sandbox escape prevention is not a physical interlock.

The tiny serial binding must define framing, maximum message length, CRC for corruption detection, sequence, boot nonce, capability digest, action code, typed fixed-width parameters, deadline/TTL, response codes and resynchronization. CRC is not authentication. Untrusted buses require authentication or a physically protected exclusive gateway. The exact byte format, replay persistence and firmware implementation are unfinished work, not inferred from this prose.

## Identity, revision and time glossary

| Field | Meaning and invalidation |
|---|---|
| type digest | Immutable reusable capability definition; publisher owns its signature |
| instance ID | Enrolled physical asset identity; not its IP address or type |
| binding generation | Commissioned firmware/adapter compatibility, geometry, attachments, calibration and mode dependencies |
| calibration revision | Specific measurement/actuation transform and its validity evidence |
| endpoint session identity | Execution session established by authenticated handshake/reset detection; not inferred from gateway uptime |
| control generation | Resource authority/manual-intervention generation; invalidates old queued commands and affected inferred position |
| stream producer epoch | Producer restart/sequence-wrap domain; invalidates cursors and old-sequence comparisons |
| replay namespace epoch | Durable deduplication window; rejecting expired epochs prevents forgotten keys becoming new operations |

Type artifacts contain reusable capabilities, not mutable installation calibration. Instance binding artifacts contain commissioned facts and are signed/approved by the installation authority. Binding invalidation prevents queued starts and invokes the declared running-operation policy; successful revalidation creates a new generation. Check generation at execution, not solely at discovery. A new objective/fixture, changed adapter semantics or relevant firmware change cannot preserve an incompatible generation.

Manual intervention advances the control generation even when the electronics did not reboot. An adapter restart advances its stream epoch even when the endpoint session persists. When endpoint reset cannot be detected, advertise unknown session continuity, invalidate inferred position/queued ownership and reconcile before further effects. Tiny endpoints establish a unique session using a persistent boot counter or an authenticated gateway challenge plus a reset-to-disarmed handshake that purges old work; a random nonce with no uniqueness/handshake argument is insufficient.

Timing fields distinguish `not_before`, `latest_start`, `max_run_duration` and `latest_completion`. A command arriving before latest_start may still expire while queued. Reject an expired start before effects; after start, a deadline miss applies the commissioned interruption/termination policy and records possible effects. Clock mappings include epoch and uncertainty. Unsynchronized MCUs use validated local timers with explicit transit bounds and conservative budgets; reset/wrap invalidates timing assumptions. A measured clock bound is required before promising synchronized cross-device starts. Lease expiry uses the controller's monotonic clock/session, not unverified caller wall time.

## Procedure admission placement

Admit and journal one immutable procedure digest, argument set, binding generation, resource handles and total budgets before installation. Per-step admission is local enforcement of the authorized envelope: authority, generation, local interlocks and step/time limits. Conditions requiring new external evidence create explicit barriers that cannot be crossed offline. A local control pulse is not a separate network RPC or host journal transaction.

Declare which progress markers the endpoint persists and which are batched to the host. On reset, the last durable marker may precede an already-executed step; reconcile or report an unknown partial outcome rather than replay it. Offline continuation is allowed only within the preauthorized finite procedure and its local loss-of-contact policy. Hard timing cannot depend on an unbounded host round-trip. Revocation takes effect according to locally enforceable authority/lease timing; immediate remote revocation under a network partition is not promised.

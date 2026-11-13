# Device I/O, driver and intelligence-hub boundary

Status: independent HMS draft, with partial isolated implementations. This specifies the shared boundary required by [architecture](01-architecture.md) and [execution](02-execution.md); it does not introduce a commissioned wire version or claim support for a particular physical installation. The [implementation status](../PROGRESS.md) identifies what has actually been checked.

Current isolated evidence includes [eighteen host boundary controls](../artifacts/implementation/standing-host-boundaries/RESULTS.md)
and [phase-kernel native comparisons](../artifacts/implementation/standing-endpoint-phase-kernels/RESULTS.md).
The host capacity attempt times out; the AVR image still exceeds physical flash
by 6,418 bytes. Neither result establishes commissioned device, driver or hub
support, and neither changes the authority requirements below.

A separate [32-iteration diagnostic](../artifacts/implementation/standing-host-history-cost/RESULTS.md)
measures selection, policy and history validation while retaining the same
three shared claims. Its only wire operations are DESCRIBE, BIND, OPEN and STATUS.
It supplies no new physical eligibility, full-capacity result or authority bypass.

The [private selection-reuse candidate](../artifacts/implementation/standing-host-selection-reuse/RESULTS.md)
passes compiler equivalence and nine native management/freshness controls. It
reuses validated data only within one pure compilation; current authority and
final commit checks remain. This changes no normative I/O, driver or hub boundary.
The subsequent [unchanged full-capacity scenario](../artifacts/implementation/standing-host-selection-capacity/RESULTS.md)
still fails its thirty-second limit, retaining 110 settled never-handed-off STARTs,
one prepared START and three claims. Its audit validates retained failure evidence;
full capacity and public eligibility remain open.

## One authority path

Device channels, bus controllers, driver processes, clock/timer services, hub compute and retained control storage MUST participate in the same deployment resource graph. An agent-generated action, reused PAT, native SDK, CLI or local standing controller MUST use the declared normal-operation or bounded-loss authority. A direct driver API is not a second route around resource admission.

Each installed capability MUST resolve a typed action to an exact provider, device instance, configuration, dependency footprint and evidence contract. It MUST declare whether it consumes or changes shared peripheral state. Pin labels, register names, executable names and model names are insufficient bindings. Unsupported behavior MUST refuse; a provider cannot silently substitute a digital output for requested PWM or a command echo for a measured response.

## Observation and acquisition are different operations

Reading a retained observation is a data operation under result/read authority. It does not authorize a new device transaction. The returned record retains its original acquisition identity, age and quality; reading it again cannot refresh its acquisition time.

Acquiring a new observation MUST declare its actual effects. These may include selecting a multiplexer/reference, changing pin mode, clearing a register, consuming a FIFO entry, acknowledging a device or starting a bus transaction. Such effects require the corresponding claims, limits and lifecycle, even if the public result is called a sensor reading. A provider may advertise effect-free acquisition only when its installed implementation and device contract establish that property.

This distinction follows from concrete source behavior: the inspected Arduino AVR `digitalRead` disconnects PWM before reading its port, and `analogRead` selects shared converter state before starting conversion. The [retained source review](../research/embedded/avr-io-boundaries/README.md) records the exact version, full reading scope and limits. HMS describes the installed behavior rather than inferring effects from a function name.

## Authority presented at the actual effect boundary

The driver MUST receive enough immutable identity and current authority to associate every effect with its original finite operation, standing acquisition, output activation or bounded-loss episode. A constrained binding may use installed handles, provided they resolve to the same semantics:

| Required association | Purpose |
| --- | --- |
| Deployment, endpoint session and control generation | Reject work from an earlier authority or boot |
| Installed provider/configuration and physical binding identity | Reject stale driver or device assumptions |
| Finite operation identity; or standing deployment plus acquisition attempt, output activation or loss episode identity | Associate retries and evidence with the actual kind of effect |
| Complete resource footprint and current fences | Exclude another owner of a pin, timer, bus, driver or hub resource |
| Typed arguments and immutable intended effect | Prevent reinterpretation after admission |
| Ordinary or bounded-loss mode and permitted effect | Keep stopping/reconciliation authority distinct from new work |
| Clock domain/epoch and exclusive effect cutoff | Refuse a handoff that is no longer timely |
| Required result, quiescence and verification evidence | Define what can actually settle the operation |

The provider MUST recheck applicable authority at the actual register, bus, native queue or execution gate handoff. Checking only before an asynchronous enqueue does not authorize a later physical dispatch. If the native facility cannot enforce the identity and cutoff at that later boundary, the adapter MUST advertise that limitation and refuse requirements it cannot meet.

A standing deployment can acquire inputs while preparing, before any output activation exists. Its acquisition identity and source epoch/sequence MUST remain distinct from output activation receipts. The installed acquisition contract defines which attempt and observation evidence must be retained; this does not require a durable event record for every sample. An activation identity does not replace the deployment's current lease, cumulative accounting or retained ownership. Renewal, suspension and resume follow the [standing lifecycle contract](../artifacts/design/standing-endpoint-programs/LIFECYCLE.md); they cannot erase an uncertain effect or release its claims implicitly.

A queued driver MUST retain the original identity through execution and reconciliation. A retry for the same retained identity cannot create another queued effect. A revised parameter, provider, resource mapping or intended effect is new work and requires new admission. A missed deadline or lost reply does not grant permission to retry an uncertain effect.

A result that settles one request MUST NOT clear a separately recorded request's uncertainty without that request's declared settlement evidence. STATUS, STOP and common REVOKE records remain distinct obligations when the installed protocol represents them separately.

The check-to-handoff interval and any interrupt, queue or transport delay are part of the timing qualification. Clock labels or a successful software comparison alone do not establish a physical deadline. An operation that may already have acted MUST retain uncertainty when the adapter cannot prove the required outcome.

## Resource aliases and driver lifecycle

Resource resolution MUST include transitive aliases. A PWM pin can depend on a timer used by a clock service; analog inputs can share a converter/reference; a device driver can depend on a bus, service process and hub memory. Admission MUST resolve those dependencies before effects and retain the required claims through settlement. An implementation may conservatively claim a whole peripheral when finer sharing has not been qualified.

Physical footprint proofs and logical execution/lifecycle claims MUST remain separately typed. A logical driver slot MUST NOT be presented as a physical pin or timer footprint merely to include it in admission. When a capability needs both, admission MUST validate their dependency binding and reserve the combined claims under the same owner.

Initialize, configure, reset, suspend, resume, replace and unload are managed driver operations when they can affect hardware or another owner. They MUST identify affected resources, configuration generations and outstanding operations. Resetting a software object does not establish device quiescence. Removing a provider cannot erase the history or claims of uncertain work.

An operation that disables its own hub, driver, clock, transport or management service MUST have an installed ownership and recovery contract. Dependencies needed for stopping and reconciliation must survive through settlement, or authority must explicitly pass to an independently surviving qualified owner before those dependencies are removed. The handoff must preserve operation history and outstanding claims; it cannot authorize conflicting work before settlement. An acknowledgement from the terminating caller cannot prove completion after that caller disappears. For a host-process binding, a persisted PID or process-group number is association data and does not recreate signaling authority.

For the current AVR composition, Timer1 clock and UART ownership are installed runtime dependencies. A future Arduino I/O adapter cannot call a startup routine that overwrites those resources or expose their aliases without an explicit compatible ownership contract. This is a target-specific consequence of the shared rule, not a universal fixed pin map.

## Bounded local service and loss evidence

Installed driver steps MUST have declared work, memory and service bounds. A standing controller MUST retain its local observation, lease, feedback, accounting and loss policy independently of the agent's response time. An unbounded conversion/bus wait cannot be presented as a bounded cooperative step. The adapter needs a finite start/poll/collect or equivalent native facility with explicit timeout and unknown-outcome handling.

Quiescence evidence MUST match the original footprint and required installation predicate. When settlement depends on a commanded transition, the evidence MUST establish the required ordering relative to that actual handoff. A cached observation from before the command cannot prove its result. A full ordinary event ledger cannot discard the evidence or capacity owed to stopping/reconciliation.

Physical stopping remains an independent commissioned function where the installation requires it. Loss of the model, hub process, transport or ordinary control storage MUST NOT be treated as proof that the device stopped. The fixed Linux guardian controls establish their declared host-process slice; process reaping is not mechanical or GPU settlement.

## Prompt-to-PAT use

A natural-language request selects or synthesizes behavior over these installed capabilities. A recurring context may use a qualified PAT only while its current device, driver, hub, configuration, evidence and resource guards hold. The PAT retains the same effect-boundary and recovery rules as newly planned work.

New intent or an unsupported but evidenced context can return to the agent for planning. Missing evidence, a stale binding, exhausted capacity or an uncertain previous effect MUST follow the declared refusal/reconciliation path; those conditions are not proof of novelty. Learning may propose a revised PAT, but observed repetition alone cannot establish its physical applicability or promote it past qualification.

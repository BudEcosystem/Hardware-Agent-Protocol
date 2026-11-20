# Device I/O, drivers and intelligence-hub control

Status: required architecture with topology, persistent resource admission and an explicit
shared-board I/O simulation profile, 2026-11-07. Most domain bindings remain proposed.
The current executable adapters remain SQLite and native-C simulations; actual GPIO, buses, operating-system drivers and GB10 management
are not implemented by this document.

The user's scope includes control of device I/O and drivers, and of whichever
device hosts intelligence. The registry must describe the whole operating graph:
site, hub, compute service, adapter, bus, controller, peripheral, input/output
channel and physical capability. A hub is both an execution host and a managed
resource. Hosting the agent does not grant that agent unrestricted host control.

## Resource and capability domains

| Domain | Representative observations | Representative operations | Essential binding facts |
|---|---|---|---|
| Digital/analog I/O | Pin state, ADC sample, continuity/error state | Configure direction, bounded digital output, PWM/setpoint, timed capture | Electrical mode/range, pin multiplexing, ownership, sampling/actuation timing |
| Device buses | Device identity, health, errors, queue state | Addressed transaction, configure bus, recover/reinitialize | Bus controller, device address, framing, bandwidth, arbitration and shared dependencies |
| Sensors and actuators | Measured position, temperature, images, force, status | Acquisition, bounded motion, valve/fan/light control | Units, frames, calibration, limits, evidence and local failure response |
| Drivers and adapters | Installed version, supported features, state, diagnostics | Install verified artifact, configure, start, drain, restart, replace, remove | Artifact digest, compatible firmware/OS/ABI, configuration revision and affected resources |
| CPU/GPU/accelerators | Utilization, memory pressure, job progress, temperature | Admit compute job, allocate bounded capacity, select supported model/runtime, cancel/reconcile job | Actual hardware/software profile, quotas, deadlines, dependency and result provenance |
| Storage and data | Capacity, integrity, artifact/stream inventory | Allocate/write/read artifact, retain/export/delete under policy | Ownership, quota, integrity, retention, atomic publication and data lineage |
| Network and service I/O | Link/service health, queue/drop counters | Configure permitted interface/service, route stream, enforce bandwidth | Endpoint identity, permissions, dependency paths and disconnect consequences |
| Hub lifecycle | Boot/session identity, installed services, power/thermal state | Managed service changes, shutdown/reboot/update when supported | Active dependent work, recovery policy, local fallback and new session/generation |

Names above are semantic categories, not promises that every board or operating
system implements every operation. Providers advertise concrete supported
capabilities. A GB10-class hub, another GPU system, an SBC and an on-device AI
processor can all implement different subsets behind the same lifecycle model.
The [GB10 evidence review](gb10-deployment-evidence.md) records actual source
constraints separately from this hardware-neutral design.

## I/O contracts and ownership

I/O configuration is an effectful operation. A pin cannot independently belong to
a GPIO writer and an active PWM or SPI peripheral. Bus transactions and device
actions need an ownership graph that resolves aliasing: two capabilities that
touch the same pin, timer, bus address or DMA channel must share the appropriate
resource claim. Aliases must not permit a raw bus write to bypass the resource
claimed by a higher-level motor or camera capability.

Distinguish desired output, controller-reported output and measured physical
state. Reading back an output register does not establish that a motor moved or
that an electrical output reached its load. Observation records include source,
acquisition clock/epoch, age bounds, uncertainty, sequence and continuity gaps.
Raw access, when supported, is a separately scoped capability with a concrete
resource/effect envelope and the same durable operation rules.

Long-running data acquisition needs a stream contract: format, rate and burst
bounds, buffer ownership, backpressure/drop policy, sequence gaps and retained
artifact references. The command plane controls acquisition and lifecycle; the
data plane moves images, samples and tensors through an appropriate transport.
A transport completion is not an acquisition-quality claim or physical outcome.

## Driver and hub lifecycle

A driver change may invalidate every dependent capability. Before a permitted
change, compute the affected dependency set, prevent incompatible new admission,
and apply the declared drain/stop policy to existing operations. Unknown physical
outcomes remain unresolved; a restarted process does not clear them. Installation
and configuration produce a new generation and compatibility record. Existing
PATs must be rechecked against it before reuse.

Driver lifecycle commands require their own authority, distinct from permission
to invoke an ordinary device action. The runtime resolves requested changes into
concrete verified artifacts and configuration. Host package managers, service
managers or driver APIs are implementation providers. Their stdout or exit code
must be mapped into the specific lifecycle and recovery contract.

The intelligence hub's own dependencies need explicit treatment. Restarting its
network or inference service can remove the actor waiting for the reply. Record
the admitted operation durably, expose reconciliation after reconnect, and retain
endpoint autonomy and local response behavior for the outage. A hub reboot gets
a new session; it does not imply that remote devices stopped or forgot commands.

Compute placement is selected from declared capabilities and budgets. A PAT can
run deterministic orchestration on a hub, a local control loop on an MCU, and a
pinned perception stage on an accelerator. CPU/GPU memory and I/O queues are
admitted resources, while watchdog and stop servicing need qualified capacity
independent of model load. GPU availability alone says nothing about supported
driver APIs, real-time scheduling or memory-allocation paths.

## One application across the graph

For microscope inspection, a PAT can reserve a stage and camera, configure
acquisition, move through a finite scan, publish images, run a pinned hub analysis
job and return measurements tied to sample and calibration identities. Changing
the camera driver or hub inference runtime produces a dependency change visible
to the same PAT catalog. A camera stream gap or inconclusive analysis affects
the result and continuation policy instead of silently becoming a successful scan.

For an Arduino application, the agent maps the user's intent to installed I/O and
control capabilities, then lowers an eligible [PAT](prompt-to-pat.md) to endpoint
instructions and hub jobs. Wiring, modes, output budgets and resource conflicts
become concrete binding data. Repeated operation uses the admitted deterministic
program; novel conditions produce structured context for the agent.

## Implementation and acceptance work

The [first resource-slice design](../artifacts/verification/io-driver-hub-resource-design/DESIGN.md)
now specifies closed topology, electrical, alias, consumer and generation
documents. Its proposed initial original synthetic provider has finite GPIO
pulses, PWM bursts and driver/service generation changes. Typed footprints make
GPIO and PWM on the same pad share a claim; structural containment alone never
locks a whole hub. A lifecycle change reserves the affected consumer atoms and
refuses while they are busy. It retains those claims until receipt reconciliation
and binding publication finish. That lifecycle path has reviewed, unexecuted
source preparation. The finite GPIO/PWM slice is now mounted separately as an explicit
simulation profile; neither establishes real I/O control.

The integrated `hms/resource_topology.py` library now validates the closed graphs
and derives binding proofs and lifecycle claim sets. Its
[21-test integration proof](../artifacts/verification/resource-topology-integration/index.json)
covers shared GPIO/PWM pads, dependencies, bounded parsing and generation changes.
The [design addendum](../artifacts/implementation/resource-topology/DESIGN-ADDENDUM.md)
clarifies a lifecycle requirement: when a dependency change rebinds an instance,
the change reserves the resources of all that instance's actions, including
sibling actions that do not directly use the changed dependency. Independent
instances remain unaffected.

The integrated [resource-admission library](../artifacts/verification/resource-admission-live-integration/README.md)
passes 32 focused tests using the original Journal and Registry. It persists
managed route/instance requirements, verifies proof and generation history on
admission and dispatch recheck, and publishes quiescent configuration changes
atomically. Shared GPIO/PWM/raw-timer claims conflict across routes; unrelated
pads can progress. A resource-aware storage profile makes the original older
Registry refuse the database. Metadata and record sizes are checked before host
fetches, inventories are exact and bounded, and original binding scalar-type
refusals are preserved. The failed-before reproductions remain retained. This
library is now used by the explicitly selected I/O runtime profile. Its
administrator generation publication is still a quiescent configuration change,
not an admitted driver restart. Receipt-gated lifecycle settlement remains
separate work.

The [synthetic provider stage](../artifacts/implementation/io-synthetic-provider/README.md)
passes 24 tests on its own copied sources. GPIO pulses and PWM bursts share one
durable board state across routes, with canonical atom ownership, retained
activation/terminal receipts and conservative recovery. Its clock and electrical
state are simulated. A separate [current-baseline check](../artifacts/verification/io-provider-current-integration/index.json)
passes the same 24 tests with 146 stable copied inputs, including the new
admission library. Those two proofs describe their retained pre-mount sources.

The [live I/O profile](io-simulation.md) now exposes the provider through an
explicit runtime factory and daemon initialization/reopen flags. Discovery,
preparation, invocation, observation, cancellation and finite procedures use the
same CLI/UDS/MCP surface. One board arbitrates GPIO/PWM aliases across routes;
missing or changed board identity refuses instead of resetting effect history.
The installation pins the actual source and a generated example makes the
configuration reviewable without importing test fixtures.

Public results use a typed I/O profile separating activation, cycle completion
and historical idle state. A canceled pulse can retain `activationCommitted:true`
and `mayHaveActed:true`. The first public integration run exposed an incompatible
legacy result check and an invalid example topology profile; both were corrected
without relaxing the original simulator checks or request timing. The retained
[diagnosis](../artifacts/verification/io-response-contract-diagnosis/README.md)
records all four original rejected public results. This profile executes only
the original SQLite board model, with no physical driver or hub lifecycle changes.

The next [lifecycle settlement design](../artifacts/implementation/io-lifecycle-settlement-design/DESIGN.md)
keeps the complete affected claim set through receipt validation, generation and
binding publication, and terminal Journal settlement. It uses a separately
installed management capability and permits a later catalog revision only when
every affected dependency remains exact. Its [state-preservation amendment](../artifacts/implementation/io-lifecycle-settlement-design/AMENDMENT-01.md)
prevents historical settlement from reactivating a currently disabled device.
Its [binding-history amendment](../artifacts/implementation/io-lifecycle-settlement-design/AMENDMENT-02.md)
separates current generation support from exact historical receipt validation.
The [independent review](../artifacts/verification/io-lifecycle-settlement-review/review.json)
finds no remaining blocker in that amended design scope. Isolated implementation
source preparation is in progress; its required review and execution tests remain
open. No lifecycle effect has been executed.

The preliminary [draft01 source review](../artifacts/verification/io-lifecycle-preliminary-review/01/review.json)
found incorrect historical publication association, scalar/mapping type gaps and
a database lookup after the final timing check. The targeted
[draft02 review](../artifacts/verification/io-lifecycle-preliminary-review/02/review.json)
finds those source issues addressed while preserving the original binding and
release bodies. Its 30 drafted tests remain unexecuted, and public lifecycle
result support remains unfinished. These static reviews are not lifecycle
qualification.

The separate [harness review](../artifacts/verification/io-lifecycle-source-preparation-review/FINDINGS.md)
found gaps in child ownership, failure retention, import provenance and result
gating before any lifecycle tests ran. Frozen snapshots preserve those findings
and subsequent corrections. The [snapshot05 review](../artifacts/verification/io-lifecycle-harness-remediation-review/05/review.json)
finds the narrow harness corrections addressed in source, including bytecode-cache
handling and raw-state retention after a close failure. All lifecycle effect
source remains unchanged from snapshot03. Controlled harness probes and the
first lifecycle smoke test are still unexecuted; the
[acceptance plan](../artifacts/implementation/io-lifecycle-settlement/review-inputs/05/ACCEPTANCE-PLAN.md)
records their order and limits.

Build domain schemas and explicit support matrices, then implement providers for
actual target/OS combinations. First tests must exercise pin/timer alias conflicts,
bus sharing, invalid electrical modes, stream overruns, driver replacement with
active operations, hub loss and restart, compute/memory pressure and cross-device
dependency recovery. Test unauthorized driver/host changes separately from
ordinary device permissions. Measure actual sampling, control and stop behavior
under combined CPU/GPU/network/storage load; passing a synthetic model cannot
replace those target measurements.

The existing registry, claims, historical binding routes and operation journal
are foundations. Physical driver providers, receipt-gated lifecycle settlement,
stream/data contracts, compute scheduling and self-management recovery remain
required work.


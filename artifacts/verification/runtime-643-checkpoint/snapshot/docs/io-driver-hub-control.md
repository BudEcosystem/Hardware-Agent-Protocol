# Device I/O, drivers and intelligence-hub control

Status: required architecture with a pure resource-topology library, 2026-11-07.
Most domain bindings remain proposed. The current executable adapters remain SQLite and native-C
simulations; actual GPIO, buses, operating-system drivers and GB10 management
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
and binding publication finish. This is a design with pinned source inputs;
it is not an installed provider or evidence of real I/O control.

The integrated `hms/resource_topology.py` library now validates the closed graphs
and derives binding proofs and lifecycle claim sets. Its
[21-test integration proof](../artifacts/verification/resource-topology-integration/index.json)
covers shared GPIO/PWM pads, dependencies, bounded parsing and generation changes.
The [design addendum](../artifacts/implementation/resource-topology/DESIGN-ADDENDUM.md)
clarifies a lifecycle requirement: when a dependency change rebinds an instance,
the change reserves the resources of all that instance's actions, including
sibling actions that do not directly use the changed dependency. Independent
instances remain unaffected.

A [separate resource-admission stage](../artifacts/implementation/io-resource-admission/index.json)
passes 26 tests using the original Journal and a copied Registry. It persists
managed route/instance requirements, verifies proof and generation history on
admission and dispatch recheck, and publishes quiescent configuration changes
atomically. Shared GPIO/PWM/raw-timer claims conflict across routes; unrelated
pads can progress. A resource-aware storage profile makes the original older
Registry refuse the database. This stage is not integrated into the live Runtime
and executes no I/O effects. Its administrator generation publication is not an
admitted driver restart. Provider execution and receipt-gated lifecycle settlement
remain separate work.

Build domain schemas and explicit support matrices, then implement providers for
actual target/OS combinations. First tests must exercise pin/timer alias conflicts,
bus sharing, invalid electrical modes, stream overruns, driver replacement with
active operations, hub loss and restart, compute/memory pressure and cross-device
dependency recovery. Test unauthorized driver/host changes separately from
ordinary device permissions. Measure actual sampling, control and stop behavior
under combined CPU/GPU/network/storage load; passing a synthetic model cannot
replace those target measurements.

The existing registry, claims, historical binding routes and operation journal
are foundations. Hierarchical resource ownership, driver providers, stream/data
contracts, compute scheduling and self-management recovery remain required work.


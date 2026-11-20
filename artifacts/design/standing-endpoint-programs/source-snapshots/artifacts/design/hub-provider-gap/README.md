# Host-provider gap review

This is a source-grounded design review, not an implementation or qualification
result. It identifies the next locally testable host capability needed for the
user's common device, driver and intelligence-hub control system. No public
source, schema, service, device or host configuration is changed. No test,
candidate, native module or model is executed.

The public runtime currently mounts simulation providers. The next useful real
host effect is an isolated owned-process CPU-job provider with start, poll,
cancel and reconciliation behavior. This is a component toward hub management;
it does not replace the required driver/service administration, GPU providers,
persistent endpoint controllers or physical qualification.

## Current source boundaries

- [Installation parsing](../../../hms/installations.py) recognizes only the
  original SQLite and compact simulation drivers. [Runtime selection](../../../hms/runtime.py)
  separately accepts the explicit [synthetic I/O runtime](../../../hms/synthetic_io_runtime.py).
  An arbitrary adapter document cannot install code or name a new driver.
- [Registry](../../../hms/registry.py) accepts binding modes `simulation` and
  `uncommissioned`; its live policy refuses non-simulation execution and its
  historical execution-evidence check requires simulation evidence. A real host
  process must not be relabeled as simulation to pass these checks.
- The [resource schema](../../../schemas/resource-topology.schema.json) gives
  hubs empty properties. Atom purposes are hardware exclusion and lifecycle;
  [resource resolution](../../../hms/resource_topology.py) implements GPIO, PWM,
  timer and bus footprints. It does not implement compute-capacity accounting.
- The [resource catalog](../../../hms/resource_catalog.py) publishes quiescent
  configuration and proofs. It is not an OS driver/service lifecycle provider.
  The current [PAT contract](../../../hms/pat_contracts.py) likewise restricts
  effect scope and evidence to simulation.
- The [qualification supervisor](../../../hms_qualification/supervisor/qualification_supervisor.py)
  retains live Popen/pidfd ownership and launch association, but executes one fixed
  qualification worker. Its `stop_owned` method explicitly is not concurrent
  cancellation while `execute` collects. It supplies patterns to inspect and
  qualify, not an already generic host-job provider.
- The [native retention component](../../../hms_qualification/supervisor/retention_native.py)
  is a scanner with an explicit Linux/CPython 3.12/x86-64 profile. The fixed
  [worker's network veto](../../../hms_qualification/supervisor/worker_entry.py)
  explicitly does not form an OS security sandbox.

## Proposed next implementation

First define a separate host execution, installation, resource and evidence
profile. Pin executable and dependency identities, typed input/output formats,
host and owner-session identities, supported operating-system/ABI combinations,
and finite CPU, address-space, output and descriptor limits. The caller selects
an installed typed capability; it does not supply a shell command or executable
path. New support must not weaken the existing simulation profiles.

Implement an isolated process-owner library with start, poll, cancel and
reconciliation operations. Only retained live ownership handles authorize
signaling. Preserve the admitted operation's original key and immutable launch
association; a retained PID alone cannot be used to regain authority. Keep
interrupted starts, lost responses and unresolved child/descendant activity
explicit rather than launching replacement work. Exit status alone does not
establish valid output, task completion or settled ownership.

The resource profile must represent managed compute capacity and its dependency
on installed services and driver/runtime generations. Per-process limits are
not guaranteed host capacity or reserved stop/control capacity. Admission,
result validation and PAT applicability need explicit supported host profiles;
current simulation-only predicates must remain intact. Initial verification can
use fixed owned CPU test children on the current host without system service,
network, device or GPU operations. Public mounting remains a later integration
gate, not implied by a successful private process test.

Meaningful tests should cover exact replay without relaunch, changed intent
under the same key, cancellation before and after start, supervisor loss across
launch boundaries, forged/reused process identifiers, output flooding, resource
limits, retained descendant writer leases, invalid artifacts, dependency drift
and refusal when required capacity/evidence is unavailable. Actual kernel
termination and retained receipts must be inspected; a mock return code cannot
prove process settlement. An arbitrary-code sandbox is outside this proposed
trusted fixed-artifact initial profile and must not be claimed.

## Storage and GB10 limits

The [storage contract](../../../docs/control-storage.md) still requires caps
before recovery mutation, aggregate enforcement for all writers/sidefiles and
backed capacity for owed control continuations. The proposed host provider does
not bypass those public-admission requirements. The private candidate can
establish process and receipt semantics while the storage work continues.

The [GB10 review](../../../docs/gb10-deployment-evidence.md) records a dated
candidate ARM64 inference-hub assessment, not an executed HMS deployment. Its
unit/SKU, installed dependency closure, shared-memory budgeting, data-path and
outage obligations remain future deployment evidence. This gap review does not
refresh the vendor pages or claim current package compatibility, ARM64/GPU
execution, model capacity, real-time guarantees or universal hardware support.

[Evidence](evidence.json) records exact source hashes and the line ranges read;
partial reads are explicitly labeled. The original public baseline receipt was
hash-verified and all **244 public inputs** matched. The existing **866-test**
result is referenced, not rerun. The artifact index excludes itself and seals
only this review's files. No implementation is added by this packet.

# Registry, runtime, security and performance

Implementation boundary: [the local runtime profile](09-local-runtime.md) now supplies a versioned registry, installation envelopes, authorization, indexed discovery, fresh observations and durable dispatch for three synthetic primitives. Linux socket peer credentials authenticate one Unix-user principal. The broader identity, isolation, physical commissioning, stop and performance requirements below remain design obligations.

## Registry records

Keep five separately versioned records: published device type; enrolled physical instance; live presence; commissioned deployment binding; operation/resource authority. The first two persist across restarts. Presence expires unless renewed by an authenticated party. A type update does not mutate a running operation's pinned descriptor. Expired devices stay searchable as unavailable assets but cannot receive commands.

Enrollment binds a device/gateway key to a site, owner and allowed capability types. Discovery traffic is a hint, never an authentication mechanism. DNS-SD/mDNS, USB enumeration, vendor discovery, Matter commissioning and static inventories can all feed candidate records. An enrollment decision selects which candidates become trusted instances. Prevent an advertisement from replacing a commissioned device by reusing its friendly name.

Signed metadata establishes authorship and integrity, not physical truth. Store evidence class for each claim: vendor declared, installation configured, measured, or independently assessed. An effective operating envelope is the intersection of device, installation, procedure and delegated authority constraints. The agent cannot enlarge it through request parameters. Updating geometry, load, attachments or calibration invalidates incompatible bindings and requires revalidation.

Admission must also prove that the selected installed adapter implements the pinned type, instance, action, resource mapping and argument encoding. A valid registry description or presence report cannot install a handler. Perform this check in the same authority transaction as new admission and repeat it before dispatch. Retained operation replay and historical receipt reconciliation remain independent of current installation support; removing a handler cannot erase an uncertain previous effect. The local Runtime enforces this boundary across coexisting installed SQLite and compact C simulation routes. Queues, faults, mappings and endpoint counters are scoped by adapter; operation recovery resolves immutable binding history. Resource claims/fences and authority remain shared. The [implementation profile](../docs/multi-adapter-runtime.md) does not provide process isolation, real-time independence or arbitrary driver loading.

Federation exchanges catalog summaries and scoped routing references. A site remains the authority for its devices and may operate offline. Global discovery cannot override local denial. During a partition, no new remote writer may assume ownership solely because the prior site stopped responding. Catalog caches may serve descriptions but must expose stale presence and cannot mint authority.

## Tool manager and agent context

Use a stable small tool vocabulary over a large capability registry. The first response gives relevant summaries; fetch exact schemas/descriptions only for selected devices. This avoids loading thousands of instrument tools into every model request. Preserve stable IDs and result schemas even when the model-visible summary is shortened. Audit which descriptor and evidence reached the model.

A workflow planner chooses capabilities using constraints, not prose similarity alone. A centrifuge with the wrong rotor, a camera with the wrong spectral response, or a robot with insufficient reach is not a substitute. Capability compatibility includes physical units, coordinate transforms, uncertainty, material/sample requirements, timing and protection prerequisites. Resource planning includes shared physical spaces and consumables.

Treat manuals, tags, camera OCR, error strings and device-supplied code as untrusted data. They must not alter tool authority or runtime policy. Generated code can access only the runtime's delegated resource handles. An on-device LLM receives the same scoped permissions as a hub agent; proximity to hardware is not an authorization bypass.

## Runtime services

A proposed implementation comprises `registry`, `admission`, `operation-store`, `resource-manager`, `procedure-engine`, `adapter-supervisor`, `event-router`, `data-store`, and `harness-gateway`. They are responsibilities, not a requirement for nine network services. A single-host deployment can share a transactional local database; distributed deployments need a documented authority model rather than arbitrary multiwriter replication.

The operation store durably records intent, request digest, authority, versions, transition sequence, timestamps, worker ownership, endpoint receipts, evidence and unresolved effects. Use a transaction for admission plus dispatch-outbox ownership. This prevents losing intent but does not make a physical side effect atomic with the database. Recovery tests must cover every crash interval around send/ACK/verification.

The experimental [single-owner host journal](08-host-contract.md) is now embedded in the registry and authenticated local Unix-UID service, with synthetic policies and crash tests. The compact host binding separately maps full host resource fences to endpoint-local fences and retains exact commands before handoff. This does not commission physical resources, qualify a real adapter or create remote/per-agent authority. The authority database's writer lock must not become the separate bounded stop path.

Adapters run with least privilege and only the ports/devices they need. Allocate workers per blocking domain: one serial bus may need one owner; several independent instruments should not share a worker that a vendor SDK can stall. Worker restart does not automatically restart an experiment. Bound memory, pending requests, subscriptions, outstanding data references and all wait durations. Report overload before accepting work that cannot meet its budget.

A controller service supervises local watchdogs, but the ultimate disconnect behavior resides at the device or a suitable independent protection layer. The event router never blocks a watchdog waiting for log delivery. If mandatory durable logging fails before dispatch, deny ordinary new mutations; preserve the separately commissioned bounded-stop admission path with degraded audit as defined in the execution specification; after dispatch, preserve the configured local behavior and report degraded observability.

## Identity and lifecycle

Use authenticated encrypted host connections and scoped short-lived credentials. Tiny endpoints may rely on a trusted gateway, but that trust boundary must be explicit. Bind authorizations to site, resource/action, time window, limits and procedure digest. Human approval is a signed or otherwise authenticated decision from the interaction system, bound to the exact request; an agent-supplied `confirmed=true` is insufficient.

Separate observe, invoke, stop, configure, enroll, calibrate and firmware-update privileges. Operator stop access may be broader than normal actuation access within a bounded site policy; it cannot depend on the original actor remaining connected. Provision and rotate keys; revoke compromised gateways; rate-limit commands and discovery independently. Keep registry URLs and data references within configured routing/access rules rather than fetching arbitrary metadata URLs with privileged credentials.

Firmware and model updates identify artifact hashes, publisher, hardware compatibility, install conditions and rollback behavior. Drain or stop incompatible work before updating. Preserve audit and invalidate calibration when the change affects measurement or mechanics. Rollback of software does not roll back physical state. Updating a safety-relevant deployment needs its own engineering validation; no general runtime can assert this automatically.

## Performance design and measurements

Do not publish a universal latency target. Negotiate an action's timing class: best effort supervision, bounded local execution, or native hard real-time control. Each binding declares admission overhead, dispatch budget, execution deadline, observation age and stop-response expectations with measured evidence. A model's average inference speed does not establish a worst-case bound.

Measure separately: discovery latency/cold cache; schema retrieval; admission/journaling; transport; controller scheduling; physical actuation/settling; sensor acquisition; verification; event delivery; model reasoning. Report p50/p95/p99/max, sample count, hardware, OS, payload, concurrency, thermal state and failure load. Deadline misses and unknown outcomes matter more than median RPC latency.

Optimizations to evaluate: local prevalidated procedures, compact wire frames, batch observations, preallocated MCU queues, hardware triggers, zero-copy shared memory for large local streams, frame/reference selection before model inference, and connection reuse. Each optimization must preserve local per-step admission within the durably admitted procedure envelope and report partial execution; it need not make a host RPC for every control step. Batch acceptance must not imply all-or-nothing physical effects.

Planned benchmark matrix: AVR over serial; connected ESP32-class MCU; Linux SBC; hub under competing GPU inference; blocked vendor SDK; high-rate camera stream; many idle devices; concurrent control of independent devices; shared bus contention; restart/network partition during motion. These are required experiments, not measured performance claims.

## Interoperability and extension policy

Keep core action/observation/operation semantics small. Add domain profiles for home devices, imaging, lab liquid handling, positioning, industrial cells and energy systems. Each profile owns units, reference frames, equipment-specific state and conformance fixtures. Preserve native error codes alongside normalized codes. Never replace missing source semantics with invented guarantees.

Mappings to WoT, OPC UA, ROS, MQTT, Matter, SCPI, Firmata and future official MHS must name what is preserved, what is unavailable, and what requires gateway augmentation. Example: broker delivery QoS does not certify physical effects; a canceled ROS goal does not necessarily de-energize equipment; a pin-state response may be a command echo. A translation is conforming only to its advertised supported features.

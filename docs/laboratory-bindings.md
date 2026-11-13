# Laboratory bindings and evidence — proposed design

Use SiLA 2 as a native instrument binding, LabOP as a protocol/workflow interchange candidate, and Bluesky as an execution/data-acquisition integration. These systems address overlapping but different responsibilities. Their names must not be treated as interchangeable proof of durable execution, sample correctness or physical completion. The [SiLA review](../research/laboratory/notes/sila-full-review.md) and [LabOP/Bluesky review](../research/laboratory/notes/labop-bluesky-review.md) separate source claims from original design deductions. The rules below are proposed HMS adapter requirements, not a statement that any adapter has been implemented or qualified.

## Integration boundaries

| Native facility | Preserve | HMS responsibility or limitation |
|---|---|---|
| SiLA Feature Definition | Native identifiers, descriptions, types, constraints, full version and bytes | Bind to a commissioned physical instance and compatible action/evidence profile |
| SiLA property read/subscription | Read-only behavior, initial current value, error and stream termination | Source age, evidence kind, reset continuity and gap reporting; do not invent a sensor timestamp |
| SiLA observable command | Native execution UUID, status, result, estimated progress and handle validity | Durable caller key, replay protection, resource ownership, physical effect evidence and retained outcome |
| SiLA unobservable command | Native return/error semantics | Explicit post-dispatch ambiguity; no automatic retry of an effectful call |
| SiLA metadata feature | Declared affected calls, native lock/auth token and errors | Establish actual enforcement; unknown metadata can be ignored by the native server |
| SiLA binary transfer | Native chunking, transfer UUID, position and validity | Artifact digest, capture identity, durable retention and access policy |
| LabOP protocol and execution | Distinction between intended protocol and execution evidence | Compatible binding/compilation report; material identity and live decision barriers |
| Bluesky plan and run documents | Plan messages, acquisition metadata, data/event references and native run status | Durable operation correlation, physical-effect-aware replay and explicit cleanup authorization |

The host exposes a WoT/HMS description of the commissioned binding. The original feature definition remains available by digest; an adapter must report constraints it cannot express rather than silently omit them. Tiny endpoint support can live behind a gateway; these sources do not establish that a complete gRPC/HTTP2/TLS SiLA server fits an AVR-class board.

## SiLA binding admission

Enrollment records the server UUID, vendor/type/version, approved trust material, endpoint routing, feature definitions and an installation binding. Server UUID survives restart, so a separate session-continuity assessment is required. When continuity is unknown, invalidate inferred state and reconcile pending work. mDNS announcements can nominate a candidate, not replace enrolled identity. A discovered CA certificate is untrusted input until explicitly approved by installation policy.

Each mapped command declares whether it is observable, native concurrency/queue behavior, expected result-retention behavior, cancellation/stop support, admitted disconnect behavior, physical effect class and available evidence. A default assumption that every SiLA command is atomic, deduplicated or stoppable is prohibited. Configuration features that alter reverse connections, authentication, simulated mode or device behavior require corresponding management privileges and binding invalidation.

The adapter checks constraints using the pinned native definition and HMS profile. It retains units and quantity conventions, uses exact int64 transport where required, and validates finite physical values. Unit conversion has a declared affine transform and error budget; the runtime must not silently change the user's request. XML regular-expression and schema semantics need an explicit mapping or a native validator. Missing required message fields remain missing, never zero-filled into plausible physical settings. Coordinate frame, calibration, material identity and uncertainty come from the domain profile or commissioning; they are not implied by a numeric type.

SiLA client metadata is supplied only where the native feature defines it. The adapter verifies the affected-operation list before relying on a lock or authorization feature. A metadata field carrying an HMS operation key does not create server deduplication unless a supported feature specifies and tests it. Result and status access receive HMS authorization checks even though native metadata applies only at initiation. If another native client or vendor GUI can actuate independently, the binding must demonstrate native exclusion or advertise that control authority cannot be guaranteed. A host database lease alone is insufficient.

## Dispatch, recovery and native queues

For normal commands, persist the HMS intent and adapter dispatch ownership before native initiation. The separately commissioned bounded-stop route follows the execution core's narrow degraded-audit admission exception and must not wait for a failed normal journal. Record the native server identity, binding/feature digest, request bytes or canonical digest and any execution UUID returned. A transport reply and a durable host record are different stages. SiLA Part A requires certainty that the client received the UUID before observable execution starts, but the depicted mappings do not specify an explicit durable receipt/commit exchange. Qualify the actual implementation's receipt mechanism and crash behavior; otherwise preserve uncertainty in the send/response/persist window.

After an execution UUID has been recorded, reconnect uses that UUID to retrieve state and results while still valid. Do not reinvoke the physical command merely to regain a handle. Advertised handle lifetime must account for response transit delay and subsequent updates; it is not an execution deadline. Retrieve and preserve required results before native expiry. An invalid UUID can mean expiry, restart or another invalid reference; it does not establish that no effect occurred.

Native waiting/running/success/error states are retained alongside HMS state. Native success proves only the feature's specified success condition. A motion command may finish under controller tolerance without independent position measurement; a dispense may return a command-derived estimate. Promote to verified physical completion only when the commissioned evidence requirement is met. Native execution errors preserve partial effects, outputs and uncertainty.

The ordinary mapping carries several SiLA error classes using gRPC `ABORTED` and a serialized error detail. Decode and retain that detail: this transport status does not mean a physical process was successfully aborted. The reverse stream carries errors inside its own messages and needs equivalent normalization.

SiLA accepts implementation-specific queuing and requires accepted observable commands to continue through connection loss. Therefore HMS may map only a disconnect/authority policy that the binding can actually enforce. If a queued command cannot recheck an expired lease or new control generation at physical start, either use a native guarded feature or restrict the workflow to an exclusive controller and a bounded continuation policy that has been assessed. Do not claim immediate remote revocation during a partition. A command already buffered in a native server must be reconciled or brought to a demonstrated quiescent state before handing control to another actor.

Subscription cancellation and transport teardown stop observation delivery; they do not prove physical termination. `cancel` is unsupported unless a native feature provides a documented operation-level action. `stop(resource)` maps only to an installed stop procedure with current authority and evidence. Never implement stop solely by closing the reverse channel, killing the adapter or abandoning a gRPC future.

## Observations, streams and artifacts

An initial property value is useful for establishing present reported state. It does not recover missed transitions. The adapter marks reconnect and overflow gaps and supplies a new stream epoch where ordering continuity was lost. A local adapter sequence numbers received messages only; it cannot prove that the native server emitted no unreceived events. A native timestamp lacking known acquisition semantics or sufficient resolution cannot satisfy a stricter HMS age/synchronization requirement.

Scientific data that must be complete must not rely solely on SiLA intermediate responses or best-effort subscriptions. Use a retrievable final artifact or a separately qualified acquisition stream with frame/sample counts and gap evidence. Retain native partial results when available, with their completeness limits. An image or spectrum references the command, sample/container/location, calibration, settings and capture evidence separately from subsequent analysis.

SiLA binary transfer UUIDs and lifetime extensions are transport handles. Copy required data into an authorized HMS artifact store, calculate its digest and validate completeness before claiming durable availability. A chunk transfer completion does not establish that the acquisition itself succeeded. Bound chunk concurrency, memory, disk and idle retention; bulk transfers cannot starve stop/status handling.

## Workflow and material implications

Importing a LabOP protocol produces a compatibility report and bound procedure; it does not produce a physical execution record. A branch requiring a measured value cannot use a placeholder generated during compilation. Record limitations when exporting live branches into a less expressive scheduler.

A Bluesky checkpoint can replay messages within a run, but HMS replay protection must remain attached to the underlying physical operations. Exposure, dispense, transfer and sample transformation need declared repetition behavior. Cleanup can move hardware and requires current geometry/material checks; it is not automatically safe because it appears in an exception handler. Native stopped/aborted run labels remain native outcomes, not proof of scientific success or cessation of all energy.

Materials are resources across instruments. Barcodes, plate coordinates and task parameters must resolve to physical instances and location generations. A plate move with an ambiguous response blocks conflicting transfers until source/destination evidence is reconciled. Paused experiments retain elapsed time and environmental effects; a sample can become invalid while the software is idle. These requirements are developed in the [workflow/material proposal](../spec/06-workflows-materials.md).

## Compatibility issues and required evidence

The pinned SiLA v1.1 PDFs contain unresolved differences in discovery disabling, private-network certificate acceptance, metadata examples and timestamp resolution. [Detailed notes](../research/laboratory/notes/sila-full-review.md) retain both clauses. Choose and disclose a tested implementation profile; do not claim full standard conformance by silently choosing convenient interpretations.

Required adapter tests include lost initiation response; client crash before UUID persistence; server restart with unchanged server UUID; result expiry; concurrent foreign native client; queued command after authority change; subscription disconnect/overflow; corrupted or expired binary transfer; absent authentication metadata; unauthorized result lookup; physical stop unsupported; and partial-effect execution error. Add int64 extremes, millisecond timestamp requirements, affine-unit conversion, missing required protobuf messages and native/normalized progress scale checks. Then demonstrate sample swap, expired specimen during pause and nonrepeatable checkpoint replay across the workflow boundary.

None of these runtime, interoperability or physical tests has run. Current evidence is complete reading of the retained SiLA PDFs, selected implementation reading for other laboratory systems, and proposed contracts. The next implementation step requires pinned SiLA XML/XSD/protobuf definitions and an inspected reference/server implementation before claiming support.

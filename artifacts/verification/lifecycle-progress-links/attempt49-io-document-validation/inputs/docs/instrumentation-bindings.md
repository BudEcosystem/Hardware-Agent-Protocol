# Instrumentation bindings: Modbus and SCPI

Status: proposed HMS binding requirements, not an implemented driver or a device certification. The Modbus application/TCP documents were read completely, including every PDF page. The serial guide now has a separate [full-reading receipt and critique](../artifacts/verification/modbus-serial-full-read/README.md), covering all 44 pages and preserving its earlier partial receipt. SCPI remains selected-only: the [original reading ledger](../research/instrumentation/reading-instrumentation.json), [header follow-up](../research/instrumentation/scpi-headers-followup/README.md) and [parameter follow-up](../research/instrumentation/scpi-parameters-followup/README.md) together cover 2,780 of 42,293 LF lines. Exact source versions, acquisition limits, and unresolved specification examples are in [the research notes](../research/instrumentation/notes/instrumentation-review.md).

The goal is to expose a power supply, furnace, pump, motion controller, or measurement instrument through the same HMS operation lifecycle without flattening their physical differences. A register write or command string becomes a typed capability only after a device-specific binding states its meaning, authority, completion evidence, and stopping limits. The generic protocol is insufficient to supply those facts.

## Evidence and authority boundaries

The [Modbus application specification](https://www.modbus.org/file/secure/modbusprotocolspecification.pdf) defines data access and response formats. The [TCP implementation guide](https://www.modbus.org/file/secure/messagingimplementationguide.pdf) defines transport mapping and an implementation example. Neither supplies HMS operation keys, durable dispatch records, physical resource leases, fencing epochs, physical completion evidence, or a bounded safety stop. The [IVI SCPI page](https://www.ivifoundation.org/About-IVI/scpi.html) establishes SCPI as an instrument command language; the [official SCPI-99 download](https://www.ivifoundation.org/downloads/SCPI/scpi-99.pdf) is available. Its selected sections inform the proposed requirements below, but the whole SCPI standard and any particular instrument manual remain unreviewed.

Distinguish these observations in the operation journal:

| Evidence | What it supports | What HMS must still establish |
| --- | --- | --- |
| Bytes accepted by a local socket | Local dispatch progressed | Remote receipt, device action, physical outcome |
| Correlated normal Modbus write response | The addressed protocol operation completed as described by that function | Meaning of the register, controller-cycle behavior, actuator response, settling |
| Modbus exception | The server or gateway returned a specified error category | Whether the category and device profile exclude prior physical effects |
| SCPI completion event/query | Completion of the instrument's documented pending-operation set | Coverage of the intended action and independently measured physical postconditions |
| Register/status readback | A value was returned at a particular observation time | Whether it is a command echo, cached state, estimate, or fresh physical measurement |
| Independent sensor or interlock evidence | Its calibrated and time-bounded physical claim | Whether it covers the full required postcondition and all affected resources |

HMS must not promote protocol receipt into physical completion. Every operation retains its binding version, device session, resource ownership generation, original intent, native request/response evidence, and postcondition evaluation. These are HMS requirements, not features supplied by either protocol.

## A typed register binding

A Modbus binding requires an approved device model, firmware range, and register-map source. A holding-register address alone cannot describe an instrument operation. The descriptor needs at least:

| Field group | Required meaning |
| --- | --- |
| Routing | Transport, endpoint, gateway path, unit identifier, and whether the path is direct TCP or a serial bridge |
| Address | Table, zero-based PDU address, extent, and separately the human manual notation |
| Representation | Width, signedness, encoding, byte order, order of words across registers, bit definitions, invalid sentinels, and reserved values |
| Physical quantity | Unit, scale, offset, reference frame/channel, range, resolution, calibration identity, and uncertainty where applicable |
| Behavior | Read/write permission, side effects, edge-trigger or latch semantics, persistence, controller scan behavior, and whether reading consumes or clears anything |
| Evidence | Measurement versus setpoint/echo, refresh rule, cache/scan limits, timestamps, freshness bounds, and completion postconditions |
| Control | Resources affected, conflicting operations, ownership path, admissible transitions, stop method, watchdog, and recovery procedure |

The generic four-table model does not determine a vendor's physical layout. Even tables may share backing data. Modbus specifies byte order inside the transported register; a multi-register floating-point or integer layout still needs the vendor map. A conventional manual label such as `40001` must be interpreted by that manual's addressing convention, not sent as a wire address by assumption. Validate quantity, extent, encoding, and physical bounds before producing a request. Exception `03` is not a substitute for this validation: the application specification expressly distinguishes malformed protocol data from an out-of-range application value (§7, p.48).

Prefer named capabilities such as `temperature.set_target` or `axis.move_to` over an unrestricted register-write interface. A diagnostic raw-access capability, if offered, must declare all potentially affected resources and use a separately commissioned policy. Discovery may use approved read-only identification on known endpoints; it must not enumerate arbitrary function codes or assume every read is side-effect free.

## Modbus transaction handling

The TCP binding must parse a byte stream using bounded MBAP framing, validating protocol ID, length, unit routing, function, response size, and request correspondence. A TCP receive call need not contain exactly one complete ADU. Function-specific limits apply inside the overall PDU bound. Reject malformed or unexpected data without turning it into successful operation evidence.

The transaction identifier correlates outstanding requests within a TCP connection. It is not a durable operation identifier and does not provide duplicate suppression across reconnects or controller restarts. Keep a local connection generation and avoid reusing identifiers while a request is outstanding. Late, unmatched, or old-session responses cannot settle a new HMS operation. A successful implementation-level “positive confirmation” may contain a Modbus exception, so inspect the PDU itself (TCP guide §4.4.1.3, p.24).

The following rules apply after physical dispatch could have occurred:

| Result | HMS treatment |
| --- | --- |
| Normal write response | Record native acceptance/completion evidence; evaluate the commissioned physical postcondition |
| No response, disconnect, timeout, or controller reboot | Retain `outcome_unknown` unless independent evidence resolves the operation; do not blindly repeat the write |
| `01`, `02`, or `03` | Record the function/address/structure rejection. Resolve only the correlated attempt; do not erase earlier ambiguous attempts |
| `04` | Failure may arise during execution; investigate possible partial effects |
| `05` | Acceptance of the specified long-running programming request is not its completion |
| `06` | Interpret the profile-specific busy/rejection context; any later attempt requires current admission and retained correlation |
| `08` | Preserve the file-memory consistency failure and use a device-specific recovery procedure |
| `0A` or `0B` | Preserve gateway/path context; a downstream missing response does not prove non-execution |

These categories do not replace a model-specific error policy. A structurally rejected current request does not retroactively disprove an earlier lost request. Application-level retries differ from retransmission within the existing TCP connection. “Set a value” is not inherently safe to retry: a write can retrigger a run, clear a fault, latch a transition, or change an output after conditions have changed.

Multiple-register writes do not create an HMS transaction across instruments. The specification supplies no general physical simultaneity, rollback, or cross-resource commit contract. Mask-write operates on the addressed register; it is not an ownership lock. Read/write-multiple-registers performs its write before its read; it is not compare-and-swap, an isolated procedure, or evidence that an actuator reached its target. Treat device-specific atomicity or coherent-snapshot claims as additional qualified capabilities.

## Ownership, gateways, and broadcasts

An HMS lease or fence token does not protect a controller that never receives or enforces it. A legacy binding needs one authoritative gateway for the affected physical resources, with competing network paths excluded or explicitly arbitrated. The gateway must serialize conflicting operations across connections, channels, and aliases of the same register or physical asset. A PLC program, front panel, another supervisory station, or a second gateway may still change the state; either include those paths in the authority model or report the limitation.

TCP routing needs explicit profiles. A unit identifier used by a serial bridge identifies a downstream server. A direct TCP device has different unit-identifier guidance, so do not interpret zero as a universal broadcast. Keep gateway identity, configured endpoint identity, reported product identity, and physical asset identity separate. Modbus device-identification objects can aid compatibility checks, but do not authenticate the asset or establish a boot epoch. Reconnect and identity changes invalidate continuity assumptions until reconciled.

The reviewed serial sections define address zero as a write broadcast with no response, one active controller, and one outstanding transaction. A broadcast is therefore not a collection of acknowledged per-device operations. HMS should disable it by default in individual-device bindings. An explicit commissioned cohort capability must enumerate affected assets, authorize every resource, fix compatible maps, define turnaround timing, and collect per-device verification separately. The expected lack of a response is never a reason to resend. Broadcast delivery supplies no quantified bound on physical synchronization.

Classic Modbus/TCP access control in the guide is optional and IP based. It is not cryptographic identity or resource fencing. The current Modbus site lists a separate security specification; that specification was not read in this work. A deployment cannot claim its security properties merely because the binding uses TCP or because the gateway is authenticated upstream.

## SCPI session requirements from the reviewed sections

A future SCPI binding must be qualified against the exact instrument programming manual and transport. This review does not establish GPIB, HiSLIP, VXI-11, USBTMC, VISA, device-clear, remote/local control, or transport-lock behavior. Those are separate dependencies. SCPI syntax alone does not make measurements interchangeable; range, accuracy, connectors, timing, and calibration still matter.

The reviewed compliance chapter distinguishes sequential from overlapped commands and ties `*OPC`, `*OPC?`, and `*WAI` to documented pending-operation flags. The binding must identify which operations participate and which do not. Query responses require ordered, session-aware consumption so a stale completion reply cannot satisfy a new operation. A timeout after a command or completion query can leave both device effects and response-stream state uncertain.

Treat the session as an owned command/response stream. Serialize interdependent command sequences and all consumers of destructive status or error evidence. Do not insert generic setup commands into an unrelated running operation. In particular, the reviewed semantics of `*CLS` clear evidence and cancel pending completion-reporting states without necessarily finishing the underlying action. Reset and clear commands must be named operations with explicit effects, not transparent reconnect hygiene.

The selected error-queue section defines a finite FIFO whose reads remove entries. The gateway should journal consumed entries and expose its retained history to multiple clients. A crash between a native pop and durable journaling remains an evidence gap; the protocol does not offer an atomic pop-and-external-log transaction. Record queue overflow, filters, clear/reset events, and ownership changes. An empty queue does not establish that no earlier error occurred. A count query followed by a drain is not a stable snapshot if another actor can consume entries.

Preserve instrument, logical-channel, and trigger-sequence identity in status observations. Operation status and questionable-data status can inform evidence quality and progress; their actual implemented masks and model-specific meanings require the manual. A completion bit alone is not a calibrated measurement of position, temperature, voltage, or transferred quantity.


The [complete header-chapter review](../research/instrumentation/scpi-headers-followup/NOTES.md) further constrains native dispatch. Default nodes do not alter the parser's remembered path, so omitting a node can change a later relative command. A compound message can execute an earlier command before rejecting a later header; syntax failure does not establish rollback. Providers should validate the complete typed sequence, generate supported native forms and serialize the command/response session. Those measures cannot make physical effects atomic or resolve a lost reply.

A query marker does not establish a read-only operation: measurement queries have explicit exceptions, and status/error operations need their own consumption semantics. Declare actual effects, units and coupling dependencies in the capability contract. Keep electrical ports, independent capabilities and separately addressed logical instruments distinct; the latter have separate buffers and status models despite shared physical infrastructure. Do not append a numeric suffix indiscriminately, since a single-capability instrument need not accept one.


The [parameter/coupling chapter review](../research/instrumentation/scpi-parameters-followup/NOTES.md) requires explicit quantization and accepted-value evidence. Native numeric inputs may be rounded; an out-of-range error does not establish preservation of the prior setting. Relative `UP`/`DOWN` operations and context-sensitive limits cannot be treated as idempotent absolute writes. Optional parameter forms must be advertised per command.

Native special numeric values need explicit quality classification: the chapter specifies large finite-looking encodings for infinity and NaN. A binding must preserve the native representation and distinguish these sentinels from ordinary measurements; it must not substitute zero or invalid JSON numbers. The chapter's range/NaN wording discrepancy and unspecified NaN cause remain unresolved without additional profile evidence.

Value/function coupling can change other settings, while an explicit setting may disable an automatic mode. `ONCE` returning to an off state is not proof that the requested action completed. Declare these affected resources and resulting modes in the operation contract. Units, reference impedance and peak/peak-to-peak/RMS conventions belong to the binding and evidence; a driver must not guess waveform conversions or collapse ratios, percentages and logarithmic differences into one unit.

## Stop and cancellation

Do not map `hctl cancel` mechanically to socket close, Modbus diagnostic mode, `*CLS`, `*RST`, or `ABORt`. Socket closure may leave outputs active. Modbus listen-only behavior concerns communication processing. The TCP guide supplies no mandatory transaction response-time bound. SCPI `ABORt` in the reviewed section returns trigger sequences to idle and aborts related trigger activity, but does not establish energy removal or a universal physical stopping deadline.

A binding must document the physical stop action, command path, whether it can overtake queued work, worst-case device response supported by qualification, external observation of the stopped condition, and behavior if the command path is unavailable. A blocking synchronization command can delay a later stop on the same stream. Reserved gateway capacity helps only if the downstream device and transport also provide the required priority. If a credible bounded stop cannot be achieved through the instrument channel, use the independent interlock/watchdog architecture required by HMS and state the remaining physical limitations.

Cancellation is a request that triggers this policy; it does not guarantee reversal of effects already produced. Keep cancellation acceptance, stop dispatch, stop observation, and final physical disposition as separate evidence. Returning a trigger engine to idle, setting an output to zero, disabling its output stage, opening a contactor, and proving stored energy is dissipated are distinct capabilities.

## Integration with `hctl`

These steps describe the proposed command families, not an executable CLI or an implemented driver:

1. `describe` returns the qualified typed capabilities, source map/manual version, routes, calibration dependencies, observation quality, retry classification, ownership restrictions, and stop limits.
2. `discover` inventories approved endpoints and identity evidence without mutating diagnostic state. An unqualified model remains unqualified after discovery.
3. `observe` returns values with units, provenance, session, and freshness. Setpoint reads are labelled as setpoints; consumed SCPI errors are served from the gateway journal with any known gaps.
4. `invoke` admits a typed operation under its resource leases, validates physical constraints, records durable intent and the client operation key, then dispatches through the qualified binding.
5. `operation` and `watch` distinguish dispatch, native response, instrument progress, physical postcondition, evidence loss, and unknown outcome. Repeating a client operation key retrieves the existing operation; it does not cause another native write.
6. `cancel` invokes the defined stopping policy and reports the observed result. Procedure composition reserves resources and defines recovery without pretending that several instruments share an atomic commit.

The same lifecycle can coordinate a manufacturing controller through Modbus and a laboratory supply through SCPI. The shared portion is admission, ownership, evidence, and recovery; the device bindings retain their specific physics, units, timing, and stopping behavior.

## Qualification still required

No physical devices were contacted or changed in this research. Before enabling effects, complete the exact firmware/manual review and use inert protocol fixtures to exercise malformed lengths, split/coalesced frames, late replies, identifier reuse, reconnect, lost write responses, gateway failures, and multi-client conflicts. Validate map conversion with known examples and boundary cases rather than assuming a register number encodes its unit.

Device commissioning then needs authorized, controlled evidence for scan coherence, output behavior after disconnect/reboot, replay effects, external actors, broadcast recipients if enabled, and every claimed stop bound. SCPI commissioning additionally needs transport recovery, pending-operation coverage, error/status consumption, trigger/output distinctions, and query-stream resynchronization. Until those are established, this document is a design and research basis, not a universal promise that any Modbus or SCPI instrument is safe to control.

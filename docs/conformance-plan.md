# HMS conformance and validation plan

Status: requirement/test design with scoped implementation evidence below, not a certification scheme. Requirements and profile names must be bound to the finalized normative specification before publishing a conformance release. A green JSON-schema validator or simulator does not establish device safety, timing, interoperability, or universal support.

## Evidence model

Report four separate dimensions: specification validity, implementation conformance, interoperability, and measured physical behavior. Each implementation declares exactly which profiles, transports, device families, operations, security modes and failure behaviors it supports. Unsupported combinations are explicit. Avoid a single badge implying every physical device has been validated.

Each test record contains the requirement/test id; implementation and schema commit; dependency lockfiles; device model, board revision and firmware hash; hub/OS/driver versions; topology and transport settings; fixture/calibration version; run seed; inputs and fault schedule; complete ordered result/event traces; relevant device-side receipts; instrument capture/artifact hashes; verdict; and limitations. Record wall-clock and monotonic time domains separately, including clock uncertainty. Strip secrets without stripping the identities and authorization decisions needed to assess the test.

A skipped test is neither passed nor evidence of support. A device whose physical effects are not observable may still conform to a profile that reports uncertainty, but it must not claim measured completion. Every implementation claim links to an artifact that independently demonstrates it. Keep failures and timeouts as first-class results, with their exact reproduction commands.

## Functional and failure test matrix

| ID | Requirement under test | Stimulus and observation | Acceptance evidence |
|---|---|---|---|
| AUTH-01 | Caller-bound authority | Submit the same command as an authorized operator, an unauthorized agent and a spoofed principal in arguments | Only the authorized request reaches dispatch; denied requests expose no forbidden inventory, tokens or private artifacts |
| AUTH-02 | Scope remains effective through all surfaces | Attempt the same device action through native tool, PTC, MCP and direct runtime API | The runtime makes equivalent authorization decisions; hiding a tool is never the only control |
| AUTH-03 | Revocation and expiry | Revoke a grant while a plan queues, while it runs and before a renewal | New admission is denied; in-flight disposition follows declared operation policy; neither a cached schema nor a stale token restores authority |
| DESC-01 | Manifest identity and versions | Replace a procedure schema or calibration after a plan is prepared | A version-pinned request is rejected or explicitly revalidated under the defined negotiation procedure; no silent reinterpretation |
| DESC-02 | Typed units and domains | Wrong units, missing unit conversion, nonfinite numbers, excessive integer values, unknown enum and conflicting parameters | Request rejected before actuation; no numeric wraparound or silent truncation |
| OBS-01 | Fresh measured state | Delay sensor data beyond the requested maximum age, then replay old samples | Age/quality is explicit; precondition-dependent motion is not admitted from stale evidence |
| OBS-02 | Honest observation semantics | Supply commanded position while the encoder is disconnected | Runtime does not label the command as a measured position; quality and missing evidence are visible |
| OBS-03 | Time uncertainty | Step wall clock backwards; introduce hub/device drift and reset device clock | Freshness and deadline logic follow specified clock semantics; invalid ordering/uncertainty is surfaced |
| LEASE-01 | Exclusive conflict resources | Two principals request overlapping microscope axes or a shared collision zone | Conflicting work is serialized or rejected according to policy; independent resources may still proceed |
| LEASE-02 | Fencing survives failover | Partition hub A; hub B acquires a newer epoch; replay A's old motion packets | Controller/gateway rejects stale epochs where fencing is claimed; unsupported endpoint fencing is accurately disclosed |
| LEASE-03 | Reboot and wraparound | Reboot controller, restart hub and exhaust small sequence counters in a test configuration | No old command is accepted as a new one; identity/epoch resets follow the profile, including any required re-enrollment |
| OP-01 | Same-key idempotency | Concurrent identical requests using the same principal/key | One logical operation and the same receipt; effects occur at most as promised by the declared device semantics |
| OP-02 | Key/payload conflict | Reuse an accepted key with changed procedure, arguments or target | Explicit conflict; no second effect |
| OP-03 | Crash-window recovery | Crash before ledger commit, after commit/before dispatch, after dispatch/before device acknowledgment, after acknowledgment/before reply, after reply/before tool log commit | Each window has an evidenced result: no dispatch, reconciled receipt, or explicit unknown outcome; no unjustified retry |
| OP-04 | Physical effect and receipt ordering | Drop the acknowledgment after an observable relative move or dispense | Status reconciles device evidence or retains uncertainty; repeated network retries do not repeat the physical effect |
| OP-05 | Durable receipts and retention | Retry within retention and after receipt/key retention expires | Deduplication promise is honored within its declared window; expired history is explicit and cannot silently authorize a repeat |
| CANCEL-01 | Cancellation is not stopping | Cancel a running move, drop the stop acknowledgment and disconnect the sensor | Output says requested/unconfirmed or equivalent; never reports stopped without the specified evidence |
| CANCEL-02 | Caller lifetime differs from operation lifetime | Abort submit concurrently with acceptance; close PTC worker; dispose the Agent | Operation remains discoverable by authorized key/owner; declared owner-loss policy executes; no orphaned authority |
| CANCEL-03 | Local loss-of-contact response | Kill hub power or isolate the network during motion | Controller reaches its declared bounded fallback with independently measured timing; a software heartbeat log alone is insufficient |
| MCU-01 | Bounded executor | Maximum instruction count, loop count, duration, recursion depth if any, memory use and queue fill | Invalid or oversized program rejected before execution; admitted work remains within declared resource bounds |
| MCU-02 | Deterministic controller separation | Saturate host LLM inference/network while local control runs | Local timing stays within the implementation's declared budget; missed deadlines trigger declared behavior |
| MCU-03 | Unsafe dynamic operations | Attempt out-of-range pins, reserved buses, invalid pulse duration, unauthorized firmware upload and forbidden raw writes | Profile restrictions apply before execution; no bypass through generic command primitives |
| MCU-04 | Firmware interruption | Interrupt authorized update, corrupt image, boot previous firmware with stale manifest | Supported rollback/recovery and identity rules work; runtime refuses incompatible schemas; motion does not resume implicitly |
| REG-01 | Registry expiry and liveness | Miss heartbeats, expire TTL and replay an old announcement | Registry distinguishes last-known inventory from currently admissible device state; expired registration cannot authorize dispatch |
| REG-02 | Identity and registration conflict | Duplicate logical id with different hardware identity; registry failover | Explicit conflict or verified ownership transfer; no silent replacement of the target |
| WIRE-01 | Packet faults | Drop, duplicate, reorder, delay, fragment and corrupt packets; inject malformed lengths/CRC/authentication tags | Parser is bounded, corruption rejected, replay handled, sequences/gaps exposed; no unsupported exactly-once claims |
| WIRE-02 | Backpressure | Saturate telemetry, command and artifact channels independently | Queues remain bounded; critical control paths keep their declared budget; loss is signaled, not hidden |
| STREAM-01 | Event resumption | Resume from valid, stale and nonexistent cursors after restart | Ordered replay or explicit gap/retention error; never invent a continuous history |
| ART-01 | Scientific artifact integrity | Corrupt image bytes; separate metadata from data; revoke access; interrupt upload | Hash/size/type checks and authorization fail visibly; incomplete artifacts cannot be mistaken for complete acquisition |
| PLAN-01 | Composite workflow partial effects | Fail after an irreversible step and during parallel independent steps | Completed effects stay recorded; compensation is a new declared action, not fictional rollback |
| AGENT-01 | Model-visible evidence is logged | Resume/fork/replay a Session with hardware results, images and notifications | Reconstructed model context matches durable observations; fork grants no parent's live device ownership |
| AGENT-02 | Stable semantic result | Compare native, PTC and MCP reads of the same runtime result | Operation ids, units, uncertainty and error classifications remain available; prose parsing is unnecessary |
| SCALE-01 | Bounded discovery | Load a large inventory with authorization filters and churn | Bounded response/page size and memory; pagination completeness or truncation is explicit; no device-per-pin prompt explosion |

A serial CRC protects against accidental corruption; it is not authentication. For isolated serial links, declare the trusted physical boundary and gateway controls. For network profiles claiming hostile-peer resistance, include authenticated messages, enrollment and replay tests appropriate to that profile. Do not label one security profile as suitable for every deployment.

The full-reading work adds profile-specific obligations: [WoT descriptions](wot-reuse-decision.md), [MQTT/Sparkplug](transport-guarantees.md), [learned control](learned-control-profile.md), [materials/workflows](../spec/06-workflows-materials.md), [laboratory bindings](laboratory-bindings.md), [Modbus/SCPI](instrumentation-bindings.md) and [planning/grounding](planning-and-grounding.md). Assign stable binding test IDs when their wire contracts are finalized.

The current [Python receipt](../artifacts/verification/local-runtime.json) records 289 passing tests, including real daemon, CLI and compact C endpoint process boundaries. These results cover portions of the matrix; they do not assign a global pass to its broader physical, security or timing requirements.

| Boundary now exercised | Relevant matrix portions | Exact evidence and remaining limit |
|---|---|---|
| Host registry, admission, journal and checked API | AUTH-01/03, DESC-01/02, OP-01/02/03/05, REG-01/02, LEASE-01 | [Full local suite](../artifacts/verification/local-runtime.json); same-UID local authority and synthetic fixtures, not remote/per-agent delegation or all physical resource conflicts |
| Installed executor support | AUTH-01, DESC-02, OP-03 portions | Nine runtime regressions and five [independent compact-C probes](../artifacts/verification/installed-support-review/review.json); unsupported routes refused before admission/dispatch, pre-ARM timing/state checked, replay preserved; multiple coexisting adapters and physical profiles remain unfinished |
| Observation timing and continuity | OBS-01/03 | [Compact host review](../artifacts/verification/compact-host-review/review.json); stale acquisition ticks, clock interval incompatibility and disputed samples are tested; sensor/clock electrical qualification and OBS-02 hardware disconnection remain absent |
| Compact endpoint executor and stream | LEASE-02/03, WIRE-01/02, MCU-01 portions | [Native cases](../artifacts/verification/endpoint-native.json) and [framed integration](../artifacts/verification/endpoint-integration.json); bounded parser/slots, fences and synthetic callback failures, not a qualified UART or real-time device |
| Native/PTC tools through host authority to native C | AUTH-02, AGENT-02, OP-01/02/03, CANCEL-02 portions | [Current Harness compact receipts](../integration/harness/installed-support/verification.json); six scenario executions including three host SIGKILL/reopen cases after endpoint acceptance, exact-frame evidence and no OP retransmission; no physical effect count for fan/focus, live model reasoning or outer admission-reply-loss claim |
| Modern and legacy MCP through host authority to native C | AUTH-02, AGENT-02, OP-01/02/03, CANCEL-02 portions | [Earlier detailed MCP captures](../artifacts/verification/compact-mcp/verification.json), with both tests passing on current sources in the full suite; six scenario executions, exact replay, a gated host-crash window and MCP close versus explicit pre-dispatch cancel; not a physical stop test |
| Finite boot reservation | LEASE-03 portion | [Boot fault-model receipt](../artifacts/verification/boot-epoch.json) and [independent review](../artifacts/verification/boot-epoch-review/review.json); interrupted reservation software model and old-domain refusal, not electrical EEPROM durability or arbitrary rollback protection |
| AVR memory/build boundary | MCU-01 portion | [Endpoint cross-link](../artifacts/verification/endpoint-avr.json) and [boot object build](../artifacts/verification/boot-epoch.json); distinct compiler/static reservation evidence, no executed MCU, timing or combined production-firmware fit claim |
| Harness Session persistence | AGENT-01 portion | [Current built SDK/profile tests](../integration/harness/installed-support/verification.json); settled-work reopen and history visibility, not interrupted active-work takeover, all persistence providers or inherited device authority on fork |

The earlier [33-test host artifact](../artifacts/verification/host-journal.json) remains historical; current versions of those tests also run in the full suite. The complete STREAM-01, ART-01 and PLAN-01 extensions, domain workflows, independent stop, remote authority and measured physical matrix remain unfinished. No MCU-02 timing conformance or physical scenario gate is established by these results.

## Microscope physical fixture

Begin with a disconnected mechanism or non-sensitive optical fixture. Measure the existing knob before selecting a motor or setting limits. Record diameter, travel, direction, torque versus position, load variation, concentric coarse/fine coupling, backlash, slip behavior, mounting stiffness and expected manual use. No generic numerical torque or speed value is a valid acceptance threshold for an unknown microscope.

Use independent position evidence where feasible: a linear indicator/encoder on stage or focus motion is stronger than motor steps alone. A motor-shaft encoder cannot by itself detect a slipping coupler or prove sample clearance. Capture motor/encoder/limit/stop signals with an external instrument suitable for the timing being claimed. Fixture limits and test targets must be determined from actual hardware and risk analysis before energized testing.

| ID | Fixture test | Required evidence |
|---|---|---|
| MICRO-01 | Bidirectional motion and approach from both directions | Distribution of actual displacement and repeatability, including backlash and direction reversals |
| MICRO-02 | Coupler slip, stall, obstruction and detached drive | Detection evidence; bounded configured behavior; no false position certainty |
| MICRO-03 | Encoder disconnected, frozen and implausible | Invalid measurement detected; unsafe feedback-dependent procedures refused |
| MICRO-04 | Manual movement with motor idle and active | Manual override policy and loss/re-establishment of position reference demonstrated |
| MICRO-05 | Travel limit, maximum duration and lost hub | Independent traces of stop/fallback timing and final state; test each configured motion profile |
| MICRO-06 | Power interruption and restart at arbitrary position | No spontaneous motion, stale-zero reuse or false homing; reference recovery follows the procedure |
| MICRO-07 | Focus scan | Actual positions paired with frame timestamps, focus metric and settling intervals; compare requested, commanded and measured location |
| MICRO-08 | Autofocus failure | Low contrast, saturation, blank field, moving sample and multiple focus peaks produce bounded search and an honest uncertain result |

Physical testing must include the complete path: Bud tool call → runtime → hub → firmware → coupler → measured motion → image acquisition → durable result. Testing the stepper alone proves only the stepper path.

## Three end-to-end scenario gates

**Home IoT:** discover a sensor and an actuator through two different adapters; request a bounded comfort/lighting change; verify the authorization, occupancy/freshness condition and achieved state. Interrupt cloud/model access while local rules continue according to their declared policy. Include manual wall-switch override, device offline behavior and conflicting agent requests. Prove equipment with stronger constraints cannot inherit a permissive lighting policy merely because both expose a generic `set` operation.

**Scientific automation:** perform a bounded microscope scan, acquire frames, retain calibration and unit metadata, analyze quality and select the next bounded scan. Inject motor slip, camera failure and network loss at different points. Verify every image is associated with its operation, sample identifier, measured or explicitly estimated position, timestamps and uncertainty. Include failed/aborted experiments in the record rather than retaining only successful images. Simulated autofocus success is not evidence of real specimen safety or useful focus quality.

**Manufacturing:** orchestrate a simulated or appropriately instrumented cell with a controller, sensor and shared work envelope. Test scheduling, operator takeover, maintenance state, stale PLC readback, communication loss and competing requests. The conventional controller retains the fast loop and safety functions. The agent can request authorized procedures and inspect results. Require cycle-time distributions and actual controller traces before claiming production latency; successful API calls do not establish production throughput or a safety integrity level.

Each gate runs through the same operation semantics and ledger. Domain adapters may expose different capabilities, units and recovery procedures. A universal core is demonstrated by shared semantics with honest specialization, not by forcing every device into identical commands.

## Performance evaluation

Report p50, p95, p99 and maximum observed latency, sample counts, warmup, run duration, clock source and workload. State whether a deadline is an observed target or a proven bound; maximum observed latency is not a hard-real-time guarantee. Separate discovery, validation, durable acceptance, hub-to-device dispatch, controller acknowledgment, measured physical response, status delivery and LLM inference. Never combine network acknowledgment and settled motion under one unlabeled latency number.

Test cold and warm paths; one device and many; small and maximum-size manifests; idle and saturated CPU/GPU/network; native and PTC invocation; direct runtime and MCP projection; local hub and remote hub; telemetry enabled/disabled. On MCU profiles measure flash, static RAM, worst observed stack/heap, queue limits, CPU budget, packet overhead, watchdog jitter and power where instrumentation permits. On GB10 or another hub, measure inference contention and memory pressure alongside driver scheduling rather than assuming the accelerator isolates control workload.

Publish raw samples and a reproducible benchmark configuration. Numerical acceptance limits must come from the selected device/procedure requirements and implementation profile. Set limits before measuring, and explain any later change. Generic targets such as a sub-millisecond API call are useful only when the measured interval, persistence guarantee and hardware are explicit.

## Release gates

A release claiming support for a profile requires its bound requirement list, schema corpus, valid/invalid vectors, independent parser/client interoperability, failure-injection results, and measured resource limits. A release claiming a physical device requires the matching hardware fixture and calibration evidence. A release claiming Bud integration requires a supported profile launch, native/PTC Session snapshots, persistence/restart recovery, and the relevant repository checks.

Retain a requirements-to-evidence table where each row is `not implemented`, `implemented but untested`, `failed`, `passed in simulation`, `passed on named hardware`, or `not applicable with reason`. No global pass should erase a missing row. [Current progress](../PROGRESS.md) and [local runtime evidence](../artifacts/verification/local-runtime.json) record scoped synthetic tests. The three simple simulation primitives do not complete the scenario gates above; multiple adapters, manual intervention, imaging/material workflows and physical measurements remain required.

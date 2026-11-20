# First executable I/O and service-resource slice

Design only, based on the 13 copied inputs in `inputs.json`. `reading.json` distinguishes four complete files, selected source ranges and acquired schema context. No schema, Runtime, test, operating-system provider, hardware or model was executed. This is one implementation milestone within the user's broader device I/O, driver and intelligence-hub goal; it does not replace that goal with fan qualification.

## Concrete milestone

Implement an original `synthetic-io-hub/0.1` provider with finite `gpio_pulse`, `pwm_burst` and `advance_generation` operations in separate synthetic state. Demonstrate raw GPIO/PWM alias exclusion, independent pads proceeding concurrently, and a synthetic driver/service generation change invalidating dependent bindings and PAT qualification. The last operation changes a simulated generation record; it does not restart Linux services, install drivers or manage real hub hardware.

Keep Journal's existing atomic, sorted, exclusive claims and fences. A trusted bounded resolver supplies canonical claim atoms before admission and dispatch checks. Structural containment is never implicitly expanded into claims. Sharing a hub, board, driver or service therefore does not itself serialize ordinary operations.

The first lifecycle policy is `refuse_if_busy`: a generation-change operation reserves all affected consumer atoms plus its own lifecycle atom. If any are held, admission refuses; it neither cancels work nor waits while claiming success. A later durable drain/stop workflow is a separate extension.

## Proposed closed documents

Use independently versioned documents; do not add permissive fields to the existing closed schemas.

`hms.resource-topology/0.1` has exactly `profile`, `topologyId`, `deployment`, `nodes`, `atoms`, `aliases`, `consumers`. Proposed initial bounds: canonical UTF-8 at most 65,536 bytes, 128 nodes, 128 atoms, 256 aliases, 128 consumers, graph depth at most 16, and at most 32 distinct expanded claim atoms per executable operation. Reject overflow rather than truncating. These are proposed limits, not measured capacity.

`nodes` is an ID-keyed map. Every node has exactly `kind`, `contains`, `requires`, `properties`. All references must exist. `contains` describes location/organization and is an acyclic single-parent forest. `requires` describes availability/generation dependencies and is a separate acyclic graph. Validate the two graphs separately: a service can be contained by a hub and depend on that hub without creating an ownership relationship. Neither relation grants permission or creates an exclusive claim.

Closed node-property variants:

| Kind | Properties and meaning |
|---|---|
| `hub`, `board` | Empty object in this synthetic slice; no implied host-control API. |
| `service` | `serviceProfile`, restricted to one installed synthetic profile. |
| `driver` | `driverProfile`, `implementationDigest`; installed reviewed code computes the digest. A caller-supplied digest is not attestation. |
| `pin` | `electrical`: `{evidenceMode, nominalMilliVolt, maxSourceMicroAmp, maxSinkMicroAmp, modes, idleMode}`. Only `simulation` evidence; exact bounded integers; modes drawn from `digital_input`, `push_pull_output`, `pwm_output`; initial idle is `high_impedance`. These are invented fixture limits, not specifications for a board. |
| `timer` | `minFrequencyHz`, `maxFrequencyHz`, `resolutionBits`; bounded integers and ordered bounds. |
| `timer_channel` | `timer`, `pin`; exact existing timer and pin references. This declares the installed synthetic mux route. |
| `bus` | `busProfile`, `pins`, `minRateHz`, `maxRateHz`, `addressBits`; only a closed synthetic I2C-like profile initially. Bus transaction execution is deferred; this shape supports closure/refusal tests. |
| `bus_address` | `bus`, `address`; bounded integer fitting the declared address width, unique within that controller. |
| `gpio_access` | `pin`. |
| `pwm_access` | `channel`. |
| `timer_access` | `timer`. |
| `bus_access` | `bus`, `addressNode` (an existing matching address node or null for raw-controller access). |

Use exact integers, never booleans or integral floats. For this proposed synthetic schema, voltages are 1..5000 mV, source/sink limits 0..20000 microamp, frequencies/rates 1..1000000 Hz, timer resolution 1..16 bits and bus addresses exactly 7 bits. The installed fixture can narrow these values. Its concrete pulse/burst envelope is `durationMs` 1..5000, GPIO `level` in `{0,1}`, and PWM `dutyPermille` 0..1000 with frequency/resolution within both installed envelopes. Units are field-defined and no implicit conversion is allowed. These engineering/test ceilings do not authorize connection to actual hardware.

An atom record has exactly `node` and `purpose`. The purpose is `exclusive_hardware` for a pin, timer, timer channel, bus or address, or `lifecycle` for a service/driver. Require a unique canonical atom per `(node,purpose)`, stable across generations. IDs must not be derived from generation numbers. No ordinary consumer implicitly claims a service/driver lifecycle atom or the hub itself.

An alias has exactly `node` and `includes`: a nonempty list of atom or alias IDs. Alias and atom namespaces are disjoint. Resolve recursively with cycle detection, memoization and the bounds above; reject missing references, duplicate IDs/list members and an empty closure. Deduplicate converging atoms into a sorted set. Alias order cannot affect identity.

Alias completeness is checked against typed footprints, not trusted merely because a list was supplied. `gpio_access` requires its pin atom. `pwm_access` requires its channel, that channel's timer and its pin atoms. `timer_access` requires the timer atom. `bus_access` requires its controller and every bus pin, plus the address atom for addressed access. Every executable consumer's root alias closure must exactly equal the derived footprint union. Installed handlers independently verify the same hardware/mux route and claim set. An omitted pad in a PWM alias must refuse provisioning, not produce a smaller claim set.

A consumer has exactly `instanceId`, `actionId`, `rootAliases`, `requires`. Its roots identify the concrete functions used by that installed action. Dependency identity is the transitive `requires` closure of both the consumer and all touched nodes. The action/type schema and installation still determine supported arguments/effects. A registry description cannot install a new consumer or provider. The synthetic handler allowlist must match all installed consumer records; unknown actions/roots/extra mappings refuse.

Keep current node generations in a separate authority document/table with profile `hms.resource-generations/0.1`: exactly `topologyDigest`, `revision`, `nodes`, where `nodes` maps every topology node to a non-reused generation token. A revision increment is provenance, not an automatic lock or reason to invalidate unrelated consumers. Static topology/installed-code changes require explicit reprovisioning in this first slice; hot replacement and alias remapping are deferred.

For each immutable binding generation retain `hms.resource-binding-proof/0.1`: exactly `profile`, `instanceId`, `bindingGeneration`, `topologyDigest`, `actionRoots`, `expandedClaims`, `dependencies`, `closureDigest`. `dependencies` maps the relevant node IDs to their captured generations. `closureDigest` covers the relevant typed nodes, aliases, footprints, stable atom IDs and dependency generations, with a domain-separated canonical digest. The complete topology digest is retained for audit; the closure digest governs relevant dependency equality. Keep historical proofs with historical bindings.

## Claims and generation-change semantics

For example, raw GPIO on pad D5 claims `{pad:D5}`; PWM on timer T0 channel A routed to D5 claims `{pad:D5,timer:T0,channel:T0A}`. GPIO on D6 can proceed alongside PWM on D5. PWM on another channel sharing T0 is conservatively exclusive through `timer:T0`, even if frequencies happen to match. Compatible shared timer reservations are not implemented by this milestone. Raw timer writes conflict with every active PWM using that counter.

An addressed bus action and raw controller action both include the controller and bus pins. Raw pin access therefore cannot bypass bus ownership. The initial model serializes transactions on a controller; it makes no bandwidth/arbitration/concurrent-read claim. Merely placing unrelated peripherals under one structural hub adds no claim.

Resolve `advance_generation(target,expectedGeneration)` from the installed topology, never from caller-supplied affected resources. Find all consumers whose transitive dependency closure includes the target driver/service. Its exact claims are the union of those consumers' atoms plus the target lifecycle atom. Refuse a union exceeding 32 atoms. A dependency-free service still claims its lifecycle atom. Ordinary consumers do not claim it; the reverse dependency union is what excludes incompatible work. Unaffected services and pads remain available unless they share a physical atom with an affected consumer.

Admission atomically establishes the lifecycle operation and all claims using existing Journal logic. Current generation must match `expectedGeneration`; keys/replay retain existing lookup-first semantics. Recheck dependencies at dispatch and immediately before the synthetic effect. On accepted/pending lifecycle work, competing generation changes are excluded by the lifecycle atom. An already admitted old-generation consumer would hold an affected atom, so lifecycle admission refuses. A consumer waiting outside admission must later use the new binding or refuse its stale intent.

The original synthetic provider commits its new generation and operation receipt together, with no external effects. Retain lifecycle claims until host publication has durably advanced the authority generation and installed exact new binding/control generations for every affected consumer. Clear or invalidate their old presence/observations using existing registry rules. Publication must be idempotent for the same operation receipt and refuse a different generation/receipt. Perform Journal clock checkpoints before publication writes and preserve one transaction for its authority rows. Reconcile a crash between the provider commit and authority publication through the retained receipt; do not emit the effect again or release claims first.

Generation identity must be checked by installed support even while old registry rows exist. A provider/authority generation mismatch is unavailable, not a reason to route elsewhere. A stored old-generation receipt remains valid historical reconciliation evidence. Unknown outcomes and claims survive owner restart. They must not be cleared by invalidating a binding, changing generation or deleting a simulation database.

GPIO/PWM operations are finite pulses/bursts. Validate exact integer mode/level/duration and PWM frequency/duty/resolution against the pin, route and timer envelopes at admission and provider execution. While active, keep the pad/timer claims. At completion/cancellation the synthetic model disables PWM and returns the pad to high impedance, retaining explicit `resources_quiescent` evidence before releasing claims. If quiescence is unknown, preserve claims and unresolved status. A permanently driven pin or standing PWM controller needs a later persistent ownership/lease contract; ordinary completed setpoint operations cannot provide that guarantee.

## Integration surfaces and limitations

Current `RegistryPolicy._check` maps each abstract action resource role to one `resourceMap` string and builds a flat tuple (registry line 725). Keep the wire map's string shape: new-profile values denote topology roots, and a mandatory trusted resolver expands them before `_installed_support`. Existing legacy installations keep their exact current flat-ID meaning. Never guess a root from string syntax or fall back to flat interpretation for a missing new-profile resolver/proof. `validate_bound`, admission and recheck must share this resolution; dispatch compares the resulting tuple with retained admission claims as today. Resolve under the authority transaction without I/O or external callbacks.

The current optional installed-support hook alone cannot return a larger claim set. Add an explicit pure resource-resolution seam, then preserve installed support as an independent rejection check. A registry-only model may retain legacy behavior; a mounted new-profile Runtime must refuse if the resolver/catalog is unavailable. Replay uses retained operation identity before new eligibility, while fresh work requires current proof.

`Registry.bind` blocks claims for the same instance only. A topology/generation update must account for all reverse-dependent consumers and aliases, not just that SQL predicate. Reuse/extract its existing transaction-internal validation/publication body if atomic multi-binding publication needs it; do not duplicate binding checks or call nested public transactions. Historical binding routing and evidence remain unchanged.

`normalize_installations`, the adapter-installations schema and `AdapterCatalog` currently support exactly three primitive slots and two original simulation drivers, and the catalog rejects descriptor changes on reopen. Add an explicitly versioned installation branch for this installed provider and its topology/proof references; retain version 1 behavior. Do not relabel GPIO as a fan or claim that the existing `SimulatedPlant` supports it: its admission and receipt checks require one claim and hard-coded fan/focus/inspection primitives. The new provider must validate every atom fence and implement its own original finite synthetic state/receipts. Reuse Journal, ProcedureStore and adapter lifecycle contracts, not an acquired controller or OS command runner.

PAT changes need no new learning claim. Derive affected binding/control generations from their relevant dependency closure; existing `bindingDigest` then changes. Static topology/driver-code changes also change the installed descriptor digest. Keep unrelated service generation changes out of an otherwise unchanged consumer's closure so they do not invalidate every PAT on the hub. Extend `RegistryPatBindings`' installed-profile inventory and semantic registrations explicitly; its current map logic does not recognize this new provider. New compiler output/eligibility must see changed relevant binding or installation identity and refuse old qualification. Already admitted instances preserve original pins and follow normal interruption/cancel/reconciliation rules. The current fan-only qualification policy cannot qualify GPIO/PWM or hub programs; use scoped original test evaluators only for an invalidation test until separate executable policies exist.

Use existing read and exact action grants on separate lifecycle instances. A grant to drive a pad must not imply `invoke:advance_generation` on its driver/service. Topology publication remains administrator-only. Graph discovery/containment never expands user grants.

## Smallest implementation sequence and acceptance

1. Add `hms/resource_topology.py` and `schemas/resource-topology.schema.json` for the closed parser, canonical digest, typed footprint/alias/dependency closure and detached proofs. Add a separate generation/proof schema. Pure tests cover cycles/missing refs, alias omission, duplicate/canonical ordering, overflow, type/bool/float refusal and electrical/mux incompatibility. Schema acceptance alone is not executable support.
2. Add a small `hms/resource_catalog.py` with immutable topology/history and current generation records; add the explicit resource resolver to RegistryPolicy. Extend versioned installation parsing/catalog and Runtime setup for one original provider. Keep the Journal claim/fence engine and old profiles unchanged. Test raw GPIO/PWM contention, independent-pad progress, cross-route shared atoms, wrong/omitted fences, stale proofs, extra registry descriptions and a new-profile route missing its resolver.
3. Add `hms/synthetic_io_hub.py` with the finite SQLite synthetic operations and receipts. Test no effects on electrical/schema/authority refusal, exact replay/key conflict, cancellation before/after handoff, safe idle before release, and unknown quiescence retaining all atoms. Do not infer waveforms, sampling accuracy, electrical behavior or real-time guarantees from virtual state.
4. Add driver/service generation scenarios: busy refusal with no mutation, unrelated consumer progress, explicit generation advancement after quiescence, stale queued intent refusal, changed PAT eligibility, unaffected PAT eligibility retained, repeated lifecycle request causing one generation effect, and loss/reopen on both sides of provider and authority commits. Verify lifecycle claims remain until idempotent publication finishes. Verify unauthorized lifecycle requests create no operation/claim/effect.

Meaningful tests should use the existing Journal/Registry/ProcedureStore path plus the new original synthetic provider; a model that only tests set intersection would not establish integration. No tests were executed for this design. Public schema/result projections for topology/proofs require a later deliberate API extension; existing CLI/MCP discovery must not imply fields or providers it cannot expose.

Deferred: bus execution/arbitration, ADC/streams and loss/backpressure, persistent pin/controller ownership, compatible shared reservations, driver installation/removal/verified artifact loading, OS service control/reboot, compute capacity/placement/quotas, cross-owner distributed claims, real target calibration, watchdog/stop capacity and combined-load measurements. These remain part of the full requested system.

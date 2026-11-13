# Checked local API contracts — experimental v0.1

The local API now has a retained [JSON Schema](../schemas/local-api.schema.json), [semantic validator](../hms/api_contracts.py) and [Python client](../hms/client.py). The Runtime checks requests and results; the CLI uses the checked client. These contracts preserve the existing `hctl.local/0.1` wire shapes. They are not a remote transport, a complete sensor-stream protocol or physical evidence qualification.

The schema is self-contained: every reference is a local `$defs` fragment. [The generator](../scripts/build_api_schema.py) incorporates the retained host invocation schema and explicit method tables. Regeneration equality is tested. No supplied schema URL is fetched. The host's 65,536-byte, depth, node and numeric limits apply in addition to JSON Schema. The in-memory preflight also bounds container expansion and aggregate string bytes before canonical serialization; it does not first copy arbitrarily large caller values.

The compact host binding extends this experimental draft's closed enums with `rejected_before_start`, `disputed` verification and the `start_excluded` evidence assertion. Positive endpoint exclusion after a possible handoff differs from the host's pre-dispatch rejection; historical running evidence cannot be erased by that assertion. Disputed terminal evidence retains the execution/result audit and prevents remaining claim release. Generated clients must use the updated schema; older closed-enum clients will conservatively reject these added outcomes. This is not a claim of negotiated backward compatibility.

## Method and result mapping

| Method | Result definition | Correlation checked by the client |
|---|---|---|
| `discover` | `discovery` | Requested page limit, strictly ordered distinct instance IDs, coherent binding/presence fields |
| `describe` | `description` | Instance and optional expected digest, recomputed bundle digest, full published type profile and binding relationships |
| `observe` | `observation` | Instance/property, requested evidence kind and maximum age; unit/uncertainty and freshness consistency |
| `namespace` | `namespace` | Requested expiry and token authority/epoch relationship |
| `prepare` | `prepared` | Original replay namespace/key, target/action, arguments, timing and required effect; recomputed intent digest |
| `invoke` | `operation` | Original intent digest and target/action |
| `operation`, `cancel` | `operation` | Requested operation ID |
| `events` | `events` | Operation ID, requested cursor/page size, contiguous sequences, head/next consistency and ordered audit timestamps |
| `procedure_submit` | `procedureStatus` | Recomputed envelope digest, exact child digests/order, parent timing and coherent compact state |
| `procedure_status`, `procedure_resume` | `procedureStatus` | Procedure ID, child states, cursor/linked prefix, claims/effect/verification summary |
| `procedure_cancel` | `procedureCancel` | Procedure ID, durable stop latch and internally consistent child cancellation delivery |
| `procedure_events` | `procedureEvents` | Procedure ID, contiguous cursor/page, closed event payloads and consistent cancellation delivery |

The outer socket response has no method field. A client must choose the result definition using its own pending request and verify the echoed request ID; recognizing some valid result shape is insufficient. `hms.client.Client(socket_path).request(method, params)` does this through the existing authenticated socket client. Raw `hms.ipc.call` remains a framing/transport primitive and is not the checked application SDK.

Optional parameters must be omitted when unused; explicit null is not a substitute. Unknown fields, method names and version labels fail. Shape validation accepts only explicitly supported variants. Clients must negotiate a future profile before interpreting new event kinds or a retention-gap representation; this version's event pages require `gap: false` because the local journal does not prune events.

## Operation evidence

An operation carries separate execution, cancellation and effect-verification states, possible-dispatch knowledge, event sequence, remaining resource claims and an optional adapter result. Completion does not by itself release claims. Before-dispatch rejection and confirmed before-dispatch cancellation have no possible effect and no retained claims. Confirmed cancellation belongs to a canceled execution; it cannot be attached to completed execution. A verified effect requires an attached sensor/controller result; simulation cannot establish physical verification.

The optional `result` is adapter receipt content. It is not a rewrite of `executionState`. In the interval between the separate plant and journal commits, a running or `outcome_unknown` operation can already have a durable synthetic receipt with `effectCommitted: true` and retained claims. This combination is valid and tested through restart. Only journal reconciliation advances its execution projection and explicit quiescence evidence releases its claims. A caller must not infer completion, stopping or authority to start conflicting work merely from receipt content.

Resource claims are bounded, distinct and ordered, with exact positive integer fences. Execution event payloads need the assertion corresponding to the claimed transition, and runtime-only evidence cannot establish execution. Resource-release, cancellation-acknowledgment and dispute events require their respective assertions. These checks establish internal consistency; they cannot authenticate a sensor independently of the runtime's policy or prove that equipment behaved as reported.

## Descriptions and observations

The client recomputes the type-bundle digest and applies the same pure validation function used for publication. A self-consistent hash alone does not excuse contradictory TD forms, action flags, units, predicates or executable schemas. The supported schema keywords must apply to their declared type; irrelevant object keywords on a scalar are rejected. Reference resolution, required properties, predicate values and installation bindings remain explicit checks. Description text and TD metadata remain untrusted data, even when correctly hashed.

The prototype retains some existing internal-style names in its public description/event records, such as `instance.type_digest`, `presence.expires_ms` and `event.operation_id`. The schema pins these names for this draft. They must not be guessed from other methods' camel-case fields or silently changed by an adapter.

An observation records acquisition and receipt clocks separately. Unknown age requires unknown quality. A numeric age upper bound cannot be smaller than its stated acquisition-latency and clock-uncertainty contributions. Measurement uncertainty uses the property's unit. When a fresh read was requested, a successful response must also satisfy that maximum age, valid quality and the requested evidence kind. Full dimensional algebra, coordinate transformations and physical sensor calibration remain domain-profile obligations.

## Client failure and recovery

The checked client validates caller parameters before JCS normalization, snapshots them before transport, validates that snapshot, sends once and validates the returned body against it. Pre-normalization validation matters: JCS converts `1.0` to `1`, but exact-integer fields must reject the floating-point input. The Runtime separately snapshots in-process parameters before policy and result correlation. Changing an aliased caller object after dispatch cannot change the retained correlation parameters. These snapshots do not grant authority or reserve resources.

`ResponseError` means the reply cannot be used as domain evidence. The CLI reports it as `INVALID_RESPONSE`. Such a failure can occur after durable admission or even after an effect: it does not establish that nothing happened. A transport timeout, truncated reply or interrupted client has the same recovery obligation. Preserve the original request and replay key or operation ID. Query status or deliberately resubmit the identical retained envelope under the journal's replay rules; the SDK never retries automatically.

Domain errors retain their bounded uppercase code. Internal exception messages, paths and credentials do not become public diagnostics. The current carrier does not provide a general retryability or no-effect classification. Harness integration adds its own typed `unconfirmed` delivery outcome while preserving the underlying HMS code; that carrier is distinct from the local RPC body and from physical execution state.

## Verification and remaining work

[Adversarial contract tests](../tests/test_api_contracts.py) and [independent review regressions](../tests/test_api_review.py) cover substituted identities, altered descriptions, false simulation verification, malformed schema bodies, evidence/sequence contradictions, oversized in-memory values, caller mutation and single-attempt delivery. Real CLI/daemon tests continue through the checked client. The retained full-suite receipt is [local-runtime.json](../artifacts/verification/local-runtime.json); an earlier receipt is historical once its source hashes change.

The [bounded ordered procedure profile](../docs/bounded-procedures.md) extends the
checked API with atomic child linking, restart interruption and compact status.
[Procedure boundary tests](../tests/test_procedure_api.py) check contradictions
and request correlation independently of the scheduler tests. General PAT
parameterization, control flow, data-reference, stream-subscription/gap-recovery
and remote delegation contracts remain unfinished. The JSON schema describes
control-plane data and does not define a real-time execution environment.
Per-call process startup, schema validation and durable storage all contribute to
latency; no universal performance or physical timing claim follows from these tests.

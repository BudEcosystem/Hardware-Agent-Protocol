# Device description reuse and profile — draft decision

Adopt W3C WoT Thing Description 1.1 as the host-facing discovery/affordance description. Add a versioned HMS profile and namespaced physical metadata; define the operation and authority protocol separately. This replaces the direction of making the initial custom description JSON the universal interchange format. The original examples remain exploratory inputs, not compatibility fixtures. See the [full-reading analysis](../docs/wot-reuse-decision.md) for rationale and unresolved details.

The choice reuses a published description model while leaving device-native transports intact. A tiny endpoint need not parse JSON-LD or a TD; its gateway can publish the TD and bind it to the endpoint's compact descriptor digest and commissioned identity. A reusable type artifact may use a WoT Thing Model, but a template is not a commissioned instance. Registry inventory/presence and resource authority remain distinct services.

## Mapping

| WoT term | HMS meaning | Additional requirement |
|---|---|---|
| Thing ID | Stable enrolled instance or gateway-exposed instance | Authenticated binding; no identity inferred from URL alone |
| Properties | Readable state/configuration affordances | Observation envelope, acquisition age, evidence kind, calibration and clock data |
| Actions | Operations with input/output descriptions | Durable operation identity, authority, versions, timing and effects |
| Events | State/operation notifications | Sequence, producer epoch, retention and gap/snapshot handoff |
| Forms | Transport access instructions | All mutating forms use admitted runtime endpoints; effective security checked per form |
| Security definitions | Connection/authentication mechanisms | Delegated resource/action authorization remains required at runtime |
| Profile and namespaced terms | HMS semantic expectations | Required-feature negotiation enforced by the server, not merely interpreted by an LLM |

WoT already includes `invokeaction`, `queryaction` and `cancelaction`. Preserve those operation names; do not invent `hms.execute` as a new `forms.op`. The HMS mapping must still define operation handles, retrieval and cancellation semantics. A valid TD does not itself supply durable jobs, physical interlocks or exactly-once effects.

TD `safe` is an interaction characteristic, not a physical safety assertion. `idempotent` must describe the actual operation semantics, not be set true merely because requests carry deduplication keys. Read-only state properties avoid a second raw setpoint path; if a deployment exposes writable properties, its binding must specify equivalent admission/evidence semantics and test them.

TD data schemas use the supported WoT vocabulary aligned with a subset of JSON Schema draft 7. Do not inject arbitrary JSON Schema 2020-12 keywords and assume all consumers understand them. HMS may use a different declared schema dialect for its own envelopes, but translation must preserve expressible constraints and reject unsupported required constraints. Structural checks must not silently strip them.

In particular, `additionalProperties` has no meaning in the base TD context. The fixtures omit it; strict command-envelope validation belongs to the separately declared HMS contract and runtime. The present static lint does not enforce request payload strictness. Action parameter units are stated on the input itself; an observation's unit does not supply a missing action unit. Motion additionally identifies its draft coordinate frame, whose geometry must be commissioned before use.

## Host invocation projection

Each exploratory action input projects the complete [host invocation schema](../schemas/invoke.schema.json): `protocol`, `replayNamespace`, `operationKey` and `intent`. Intent carries `instanceId`, `endpointSession`, `controlGeneration`, `actionId`, `descriptionDigest`, `bindingGeneration`, `calibrationRevision`, `arguments`, `timing` and `requiredEffect`. Action-specific parameters now live at `intent.arguments`; their numeric bounds, units, recipe enum and microscope coordinate-frame annotation remain intact. The [host profile](08-host-contract.md) defines the execution meaning of these fields.

The TD projection expands referenced schemas into supported `type`, `properties`, `required`, `const`, `enum`, `pattern`, `minimum` and `maximum` terms. It does not embed `$ref`, `$defs`, `additionalProperties` or the host schema's 2020-12 dialect declaration. `const` pins individual identity and generation fields; the complete intent is not constant because arguments, timing and requested evidence vary. `protocol` is pinned to `hms.invoke/0.1`. Replay namespace and operation key retain bounded identifier syntax; their strings alone prove neither server issuance nor authority.

`instanceId` equals the TD id and `actionId` equals the enclosing action name. Endpoint session, control generation, binding generation and calibration revision equal their explicit root `hms:` metadata. The synthetic `hms:descriptionDigest` is SHA-256 over the exact UTF-8 bytes of the corresponding retained `examples/<name>.json` physical-contract input, including its trailing newline. It is not a digest of the TD that embeds it, an intent digest, or a commissioning attestation. The fixture checker verifies the artifact bytes and every input constant independently. A deployed description must instead identify the admitted immutable physical contract and current commissioned generations; the deliberately uncommissioned fixture values cannot authorize equipment.

All four timing fields and both host `requiredEffect` values are described. The TD scalar constraints do not express the cross-field timing order, bounded JSON parsing rules, generic unknown-field rejection or live admission checks. The host parser enforces its own stricter syntax and timing rules; runtime admission must also enforce capability duration limits, argument semantics and supported evidence. Fixture tests validate sample complete envelopes with both the TD input schema and the host parser, and demonstrate that the host parser still rejects an unknown envelope member permitted by the TD projection.

## Security and semantic negotiation

A form's `security` replaces top-level security. Checking only the top level misses an insecure action override. The runtime verifies the authenticated actor, required semantic features, description/binding generation and physical authority for every mutation, regardless of which form is used. Unsupported required features are a refusal, not a downgraded best-effort execution.

Descriptions and external contexts are untrusted input. Publishing an HMS profile URI does not make a generic WoT client enforce HMS semantics. A generic client may discover/read public metadata, but cannot bypass required envelope fields and runtime checks when invoking a physical action. Pin trusted contexts/schemas locally for validation; avoid network fetching arbitrary metadata as part of privileged admission.

A conforming generic TD consumer has forward-compatibility behavior for additional returned members. The HMS implementation must preserve that distinction: reject undeclared generated request fields; accept/retain or ignore noncritical additional response metadata as required by the base semantics; refuse an unknown required execution feature. An HMS-specific validator must not call its stricter rejection policy universal WoT conformance.

## Checked exploratory fixtures

`examples/wot/` contains synthetic host HTTPS descriptions for home ventilation, microscope focusing and an inspection cell. Their URLs and vocabulary use `example.invalid`; there is no live server or published profile at those addresses. They use bearer authentication as one host-profile example, not the sole authentication choice for all devices.

`check_wot_profile.py` runs the pinned official **informative** TD JSON Schema and selected HMS static checks: exact draft fixture context, expected profile/feature declarations, read-only state, supported secure forms, the complete invocation projection, artifact digest and pinned semantic generations. It rejects unsupported unqualified keywords within these action inputs and checks the host identifier, timing and evidence constraints. Property forms explicitly use `readproperty`; action forms use `invokeaction`. These are fixture/lint checks, with a deliberately narrower context/form vocabulary than generic WoT. They neither verify runtime negotiation nor grant physical authority, and cannot establish complete TD normative conformance or physical safety. The schema itself is informative in the W3C specification and its fetched version must remain hash-pinned.

Outstanding: a controlled vocabulary/context, deployed TD-to-operation binding, WoT binding/error fixtures, actual runtime negotiation and server enforcement, generic-consumer compatibility tests, alternate transports and constrained-device mappings. Matching input fields does not turn the example HTTPS forms into a live transport or establish operation-response/query/cancel behavior. The independent HMS draft makes no claim of compatibility with Anthropic's preview.

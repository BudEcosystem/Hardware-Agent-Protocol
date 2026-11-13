# Decision: use WoT descriptions and preserve the HMS execution contract

Status: accepted research direction; implementation and physical validation remain separate milestones. Date: 2026-11-06. Scope: the independent HMS draft in this workspace, not official Anthropic MHS.

Use a conforming W3C WoT Thing Description 1.1 as the public device-description format. Put HMS physical semantics in an explicitly versioned execution profile, namespaced vocabulary and/or a digest-pinned linked physical contract. Keep an independent HMS invocation envelope and operation journal. The present bespoke device-description schema should become a transitional physical-contract input, not a competing public discovery standard.

This decision follows full readings of the [TD 1.1 Recommendation](https://www.w3.org/TR/2023/REC-wot-thing-description11-20231205/) and [WoT Discovery Recommendation](https://www.w3.org/TR/2023/REC-wot-discovery-20231205/), including their appendices and eleven figures. [Review and source mapping](../research/protocols/notes/wot-full-review.md) and [coverage receipts](../research/protocols/reading-wot-full.json) preserve the evidence and limits.

## Why this boundary

TD already supplies typed property, action and event affordances; forms; security descriptions; semantic annotations; version metadata; and reusable Thing Models. Reimplementing those concepts would make adapters, catalogs and tooling more expensive without strengthening physical guarantees. Conversely, a TD alone does not implement durable admission, replay protection, fencing, calibration validity, bounded procedures, physical completion evidence or recovery from ambiguous dispatch. HMS's useful work is to specify and enforce those semantics.

WoT's existing `invokeaction`, `queryaction` and `cancelaction` vocabulary should be reused when their binding meaning is specified. Do not claim that generic WoT has no asynchronous operation support. Explain instead which operation-lifecycle guarantees the HMS profile adds.

| Option | Assessment |
|---|---|
| Continue the bespoke public descriptor | Rejected as the long-term direction: duplicates established description concepts and limits reuse. Retain only as a migration input while the physical contract is stabilized. |
| TD with optional decorative HMS annotations | Insufficient: generic consumers may ignore extensions, so a profile label alone cannot require physical admission semantics. |
| TD plus explicit HMS profile, required-feature gate and separate execution envelope | Selected: preserves interoperable description structure while making the stronger physical contract explicit and enforceable. |
| Adopt the entire WoT service stack immediately | Deferred: direct TD retrieval and gateway-hosted descriptions are enough for the first slice. TDD, semantic search and extra bindings need independent justification. |

## Required description changes

1. Publish TD JSON with its proper context and mandatory root fields. Use maps of named `properties`, `actions` and `events`; do not retain the bespoke array shape under those core TD names. Give the TD a stable revision/digest under the HMS artifact policy.
2. Put a URI in TD `profile`. The current `P0`–`P6` hardware/deployment classes are HMS metadata and must move to a namespaced field. Use a clearly identified draft namespace until the project controls and publishes a durable public namespace; a placeholder does not imply a registered or endorsed standard.
3. Map read-only observations to properties containing structured measurement data or references. Carry evidence kind, freshness policy, clock domain/uncertainty, calibration, frame and source in the physical contract and returned observation envelope. A scalar `unit` field alone is insufficient.
4. Map effectful operations to actions. Represent input/output using the TD DataSchema vocabulary where possible. Explicitly declare any additional schema dialect and require support; do not treat arbitrary 2020-12 schemas as equivalent to TD's draft-7-compatible vocabulary.
5. Keep core `forms.op` values unchanged. Publish explicit href, media type, method and effective security for each supported binding. Use `invokeaction` for an HMS action rather than adding a new core operation word. Define operation-instance selection and status/result schemas before advertising query/cancel forms as implemented.
6. Add versioned HMS terms for resource claims, preconditions, effect class, duration policy, cancellation/disconnect behavior, evidence thresholds and enforcement attestations. Each embedded extension term needs meaningful context mapping. A linked physical contract with media type, dialect and digest is preferable to an unscoped nested blob whose meaning disappears during semantic expansion.
7. Keep TD `version.instance` and `version.model` for document/model versions. Firmware, endpoint session, calibration, binding generation, control generation and replay namespace remain separate HMS facts. A changing IP address is not a new asset; a rotating public TD identifier is not evidence that a private enrolled asset changed.
8. Use Thing Models for reusable capability shapes only after dependency resolution rules are implemented. Resolve placeholders/imports before issuing a TD. Pin the complete model dependency closure, detect cycles and bound resource usage. Commissioning remains a separate installation artifact.

## Mandatory semantic negotiation before effects

The proposed HMS execution gate must establish the following before dispatch. The concrete field names and wire encoding still need a versioned binding specification.

1. The service advertises its exact HMS profile/version, required features, accepted envelope dialects and immutable physical-contract digest. A consumer can discover these through read-only metadata.
2. The caller selects a supported version and identifies every required feature it will use. The runtime verifies the supported intersection; unknown required semantics deny admission before any effect. Optional descriptive metadata can be ignored without silently enabling execution.
3. The server binds that negotiation to authenticated caller/delegation context and the commissioned device/binding. A client-supplied boolean such as `supportsSafety: true` is not evidence or authority. A reusable negotiation reference must have a defined lifetime and invalidation rule.
4. Each invocation binds the selected contract and operation intent: instance, action, typed arguments, descriptor digest, binding/calibration generations, endpoint session, timing policy, required evidence and resource authority. The gateway validates these against its actual state and durable journal.
5. Every effectful form reaches this gate. Missing negotiation, changed contracts, weaker alternate forms and stale generation references must fail closed before dispatch. A generic TD consumer may inspect the interface or use permitted read-only operations; parsing the TD alone does not authorize physical work.
6. The runtime emits operation evidence independent of transport acknowledgement. Accepted, running, completed, canceled and unknown-outcome semantics remain those of the HMS contract. Cancellation receipt is not cancellation completion, and cancellation completion is not a universal assertion of physical safety.

This gate protects required semantics, not merely schema syntax. A client that correctly implements the binding may execute through a generic transport library; no brand-specific client is required. The decision is about demonstrated protocol behavior and authority, not a proprietary client identity.

## Preserve these WoT meanings

`safe` means the action does not modify resource state; it is not a safety rating. `idempotent` does not mean exactly-once physical execution. `synchronous` must match the described action's actual completion behavior. Property observation does not imply a lossless stream or an initial sample. `profile` is a conformance declaration, not an attestation or negotiation transcript.

Form security overrides root security. Check every effective configuration, including combo alternatives, and keep secrets out of the TD. The TD may describe a legacy interface's limitations, but an HMS protection claim requires the gateway actually to control access to that interface.

TD consumers must accept additional returned object properties and tuple items under §8.2. The HMS response layer should tolerate ordinary extra metadata while explicitly rejecting unsupported required semantics at admission. Do not make blanket `additionalProperties: false` response rejection part of a claim to generic TD-consumer conformance. Strict command-envelope validation is a separate concern and can remain conservative.

## Discovery and constrained-device scope

Start with direct authenticated HTTPS retrieval of a TD and a gateway serving descriptions for constrained endpoints. Follow the applicable TD Server GET/HEAD/status/media-type requirements. Do not require a full JSON-LD processor, RDF database or TDD implementation on a microcontroller. The tiny device still needs its bounded native protocol and identity/session handshake; TD does not replace those.

If a registry later claims TDD support, implement the applicable standardized listing, error, enrichment and optional-feature behavior explicitly. Directory expiry is metadata expiry, not resource-lease expiry or proof of liveness. TDD pagination and SSE notifications do not establish HMS's stronger snapshot/watch handoff or event-retention guarantees. Do not reuse a registration TTL as an execution lease.

## Validation and acceptance boundary

The official current [TD validation schema](https://www.w3.org/2022/wot/td-schema/v1.1) is archived at `research/protocols/wot-artifacts/td-schema-1.1.json`, version `1.1-12-March-2025`, SHA-256 `fd44f319f94c6f16f66978860ef2f9f4e0e9fd7fc5835a2f3840b9cf2002e0f1`. TD Appendix B labels it non-normative. Use this pinned schema as one structural check, then separately check references, context terms, default semantics, effective security and supported bindings. Network fetching must not silently change the validator during a test.

The migration's first tangible slice is three valid TD descriptions for the existing home-ventilation, manufacturing-inspection and microscope-focus cases, plus a narrow profile-aware validator/admission model. Acceptance should cover:

- All three descriptions pass the pinned TD structural schema and explicit HMS profile checks; their physical evidence limitations remain visible.
- Unsupported required features, a changed contract digest and a missing execution envelope are rejected before simulated dispatch.
- Every advertised effectful form shares the required gate; an explicit weak form override cannot bypass it.
- Ordinary extra output metadata remains acceptable, while missing required observation/effect evidence prevents dependent actuation.
- Query/cancel behavior is either explicitly specified and tested or honestly marked unimplemented; empty placeholders do not count as a binding.
- The same invocation intent survives transport retries without new dispatch in the model, and uncertainty after possible dispatch remains uncertainty.

These are proposed acceptance criteria, not a claim that the corresponding implementation or physical tests already exist. The complete runtime still needs persistent admission, lease/fence enforcement, crash recovery, actual adapter contracts and hardware validation. The decision can be implemented incrementally without implying those later milestones are done.

## Claims that must not be made

HMS must not claim official Anthropic MHS compatibility, W3C endorsement, complete WoT runtime conformance from schema acceptance, safety certification from a TD, universal interoperability from a capability label, or exactly-once physical execution from an idempotency flag. It must not claim a TD proves installation calibration, a network acknowledgement proves a physical effect, directory registration proves liveness, or a cancellation reply proves stopped equipment.

A defensible initial claim is: **“This independent HMS research draft uses WoT TD 1.1 description structure and adds proposed physical-execution semantics. Structural fixtures and simulation checks are reported separately from behavioral conformance and hardware evidence.”**

# BHMS changelog

## Unreleased

Hardening round (Task 7b). Each entry names the evidence that caused it.

- **BHMS-LSE-014 (new, MUST, profile `leases`)**: while a lease is `active` on a resource, every action that declares the
  resource is refused with `LEASE_CONFLICT` (`field: "leaseId"`, `bound`: the leased resources, no holder) unless the request
  presents that lease, whether or not the action declares `requiresLease` and whoever asks; a `leaseId` supplied with any action
  is validated as in BHMS-LSE-010; both at admission and before dispatch; program steps present the program's lease when it
  covers their resources. Requirement index: 251 rows. Evidence: Task 11 report, hostile suite "lease theft", issues T1a (the
  Python gateway dropped a `leaseId` supplied with an action that does not require one: three of four attempts reached the
  device) and T1b (LSE-010 checked leases only for `requiresLease` actions: the fourth reached it).
- **BHMS-DEV-033 is a MUST** (was SHOULD): an action with `effect: "hazardous"` declares `requiresLease: true`; the schema
  (`ActionDescription`, `if effect = hazardous then requiresLease = true`) and the new example
  `invalid-action-hazardous-without-lease.json` enforce it, and the Python SDK refuses the declaration when the description is
  built. Evidence: Task 10 report, SDK gap 8 (the centrifuge twin's hazardous `spin` ran without a lease) and its spec learning
  "hazardous should imply a lease". Decision: MUST, because with BHMS-LSE-014 a lease is what keeps every other caller off the
  resource while the hazardous effect runs; a SHOULD would leave that to each device author.

### TS SDK to follow

- BHMS-LSE-014 in the TypeScript device server (admission and pre-dispatch) and the conformance check
  `leases.held-lease-blocks-everyone`; `stop.not-blocked-by-load` now presents the lease it holds.
- BHMS-DEV-033 as a MUST: refuse a hazardous action without `requiresLease` when a description is built (the shared schema
  already rejects it).

## 2026-11-13 (v0.1)

Conformance round 4 (Task 7): §13.3 states how the BHMS-SEC-021 bounds are counted (root at depth 0, the count includes the root and boolean schemas, the list of
subschema keywords, `$dynamicRef` treated like `$ref`); no requirement changes.

Conformance round 3 (Task 7): BHMS-CNF-006 is an `inspection` row (the implementation's validator is a library that cannot be driven over the wire); `capabilities.authority` carries no members; EVT-013 is not applicable in v0.1 (read is one global scope).

Conformance round 2 (Task 7): profile `authority` (capability `capabilities.authority`, required by `gateway`; the multi-principal and scope-policy rows moved out of `core` so that a single-principal server can claim `core`), CNF-004 blocks on rows no check can prove, generic reports never claim.

Conformance round (Task 7): §14.5 and the shared vectors `spec/bhms/conformance/vectors/`; the requirement-index total is corrected.

Agent-surface round (Task 6): BHMS-AGT-014 (default read age) and AGT-051 (self-contained input schemas, top-level `oneOf` removed and enforced by the bridge); function results
may carry `signature` (`bhms_describe`); `LEASE_REQUIRED` names the needed resources in `bound`.

Gateway round (Task 5): BHMS-AUTH-014 pins the upstream key formula and states that the gateway's own key lookup precedes
policy; scope `operations:read`; §7.6 (gateways); BHMS-TRN-040 rejects a missing header too; BHMS-DEV-002 says a gateway
serves its own description.

First normative version.

- JSON-RPC 2.0, stateless requests with `params._meta["bhms/protocolVersion"]`;
  `server/discover` instead of a handshake; `subscriptions/listen` for
  notifications; `resultType: "complete"` on every result (aligned with MCP
  2026-07-28).
- Eleven core methods; `leases`, `events`, `programs` and `programs.registry` as
  capabilities.
- Durable, keyed operations with an eight-state machine, evidence-backed `effect`
  and explicit `unknown`.
- Leases with a server-wide monotonic fence; `stop` as a separate, lease-free path
  that revokes leases.
- Bounded programs (six step kinds, 256 steps, repeat ≤ 1000, declared and
  enforced worst-case duration) registered and run by digest.
- Error table: the seventeen codes of the build plan plus `UNSUPPORTED_VERSION`
  (-32015), `UNVERIFIED` (-32016) and `DEVICE_FAULT` (-32017).
- BHMS-Compact v1 byte layouts over the existing `HM` serial frame.
- Agent surface of eight tools (`bhms_find` … `bhms_run_program`).

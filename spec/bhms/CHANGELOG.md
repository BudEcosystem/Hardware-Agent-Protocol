# BHMS changelog

## 2026-11-13 (v0.1)

Compact round 3 (Task 9b fix 3): BHMS-Compact version 2: STOP carries a token and both STOP_ACKs echo it (hardware-stop acks use token 0), so a late ack of an earlier stop can never confirm another (BHMS-CMP-050); endpoints and gateways of different versions refuse each other.

Compact round (Task 9b fix 1): `device.epoch` `data` members `persistent` and `purged` documented (9.2, BHMS-OPS-042); BHMS-CMP-022 defines the endpoint incarnation; BHMS-SEC-050 is enforced by the gateway (networked compact links are refused).

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

# BHMS changelog

## Unreleased

Hardening round (Task 7b). Each entry names the evidence that caused it.

- **BHMS-LSE-014 (new, MUST, profile `leases`)**: while a lease is `active` on a resource, every action that declares the
  resource is refused with `LEASE_CONFLICT` (`field: "leaseId"`, `bound`: the leased resources, no holder) unless the request
  presents that lease, whether or not the action declares `requiresLease` and whoever asks; a `leaseId` supplied with any action
  is validated as in BHMS-LSE-010; both at admission and before dispatch; program steps present the program's lease when it
  holds any of their resources, and **BHMS-PRG-006** then requires it to cover all of that step's resources (refused at
  `programs/run`, naming the step). The rule concerns actions; fresh `transaction` reads stay under BHMS-OBS-011 and
  retained reads are never blocked by a lease. Requirement index: 251 rows. Evidence: Task 11 report, hostile suite "lease theft", issues T1a (the
  Python gateway dropped a `leaseId` supplied with an action that does not require one: three of four attempts reached the
  device) and T1b (LSE-010 checked leases only for `requiresLease` actions: the fourth reached it).
- **BHMS-DEV-033 is a MUST** (was SHOULD): an action with `effect: "hazardous"` declares `requiresLease: true`; the schema
  (`ActionDescription`, `if effect = hazardous then requiresLease = true`) and the new example
  `invalid-action-hazardous-without-lease.json` enforce it, and the Python SDK refuses the declaration when the description is
  built. Evidence: Task 10 report, SDK gap 8 (the centrifuge twin's hazardous `spin` ran without a lease) and its spec learning
  "hazardous should imply a lease". Decision: MUST, because with BHMS-LSE-014 a lease is what keeps every other caller off the
  resource while the hazardous effect runs; a SHOULD would leave that to each device author.
- **BHMS-OPS-008 amended (result outside its declared range)**: a well-formed result whose number violates `minimum`/`maximum`/
  `exclusive*` of the `output` schema ends the operation `failed` with `OUT_OF_RANGE` (`field: "result.<member>"`, `bound`,
  `mayHaveActed: true`, `retry: "after-reconcile"`), `effect`/`evidence` as the completion evidence supports, the value in
  `error.message` and in an `evidence` history entry; §10 says how to tell it from a refusal. Decision: reuse `OUT_OF_RANGE`
  with `field`/`bound` rather than add a code (no new number, and "which member, which bound" is exactly what the code already
  carries). Evidence: Task 11 report, S8 (a measured 200.138 uL against `Range(0, 200)` was reported as `INTERNAL` "returned a
  result that cannot be recorded" although the device had acted).
- **Unit registry (§4.5, BHMS-DEV-042)**: added `{rev}/min`, `{rev}/s` (rotational speed, its own dimension), `mol/L`, `mmol/L`,
  `umol/L` (substance concentration), `W`, `mW`, `kW` (power), `[ppm]` (dimensionless, 10⁻⁶), `m3` (volume) and `L/h` (flow).
  Choice for revolutions per minute: the UCUM annotated unit `{rev}/min`, not `{rpm}` and not a bare `/min`, so the code says
  what is counted and is not convertible to `Hz`. Evidence: Task 10 report, SDK gap 2 (centrifuge speeds had to be declared in
  Hz; concentrations, power and ppm had no unit).
- No requirement change, Python SDK only: property getters receive the device by declaration (Task 10 gap 4);
  `BhmsError.bhms_code` is the one name of the code, `BhmsError.code` a deprecated alias for one release (gap 7); `DeviceLost`
  (Task 11 S9); `units.convert` overflow is `OUT_OF_RANGE` and `BhmsError` pickles (Task 1 minors); a stdio connection releases
  its child process and tasks on every close path (controller verification of the suite under `-W error`).
- **BHMS-DEV-013 (new, MUST, core)**: the `devices/list` `text` filter is a word search: any word, ignoring case, over
  `deviceId`, `name`, `summary`, tags and capabilities (one-character words are ignored beside a longer word); `capability: "*"`
  lists every device (schema: `DevicesListFilter.capability`, `AgentFindInput.capability` carry the pattern). Was: one
  case-insensitive substring over name, summary and tags. **BHMS-AGT-015 (new, MUST, agent)**: a `bhms_find` that matches no
  device carries `totalDevices` (`AgentFindData`) and says in its summary how many devices exist and that `bhms_find` with no
  arguments lists everything; the tool description says so too. Evidence: Task 11 report, S1 (`bhms_find "facility-1"` and
  descriptive queries returned "0 devices"; three models then answered `cannot_do`) and S3 (`capability: "*"` was refused by a
  pattern error).
- **BHMS-DEV-014 (new, SHOULD, core)**: an `UNKNOWN_DEVICE` refusal names the visible devices whose id differs from the request
  only in case or by a gateway namespace (`hint`, and `bound` as a list). Evidence: Task 11 report, S2 (`notice-1` was refused
  with "no device" although `notice/notice-1` existed). Requirement index: 254 rows.
- **BHMS-AGT-016 (new, MUST, agent)**: `bhms_describe` takes `{device_id | topic}`; `topic: "program-grammar"` returns the
  program grammar (`AgentDescribeInput` gains `topic` and the exactly-one rule; new `AgentTopicData`, `AgentDescribeData`;
  examples `agent.bhms_describe.topic.input.json`, `agent.bhms_describe.topic.result.json`, `invalid-agent-describe-both.json`).
  The tool texts name the call instead of the MCP resource URI. The eight definitions total 1,456 tokens at the end of this round (ceiling 1,500).
  Evidence: Task 6 review (minor, deferred to 7b): the OpenAI function-tool text named `bhms://grammar/program`, which a
  function-tool host cannot read.
- No requirement change, agent bridge: a failed or rejected operation's summary keeps its `bhmsCode` in the protected head,
  and the cancel-pending summary keeps its next step whole (Task 6 review, minors).
- **BHMS-AUTH-015 (new, SHOULD, authority)** and the *default agent policy* (§7.4): a principal that may invoke effectful
  actions on a device should also hold `stop:<that device>`; §12.7 says that `bhms_stop` is the safe action on a fault, and
  the `bhms_stop` tool description says so. The Python SDK ships `bhms.runtime.authority.agent_scopes` and
  `bhms gateway check-policy <config>` (what every scope matches; warnings for scopes that match nothing and for principals
  that can act but not stop). Evidence: Task 11 report, S5 (four `scope:stop` refusals: the agents reacted to a fault with
  `bhms_stop` and were left with no safe action) and S7 (`invoke:knob/*` matched nothing behind a gateway, silently).
- **BHMS-OPS-064 (new, gateway)**: `Operation.upstream = {server, operationId}` (schema `OperationUpstream`). MUST NOT be
  given to a principal without `admin`, nor in notifications; SHOULD be given to `admin` in `operations/get`, `wait` and `list`.
  Evidence: Task 11 report, S6 (the upstream operation id was only in gateway internals, so a gateway record could not be
  joined to the device's own log). Requirement index: 257 rows.
- **BHMS-DEV-035 (new, SHOULD, core)**: a measurement-like action result carries a validity indicator (`quality` as in an
  observation, or a boolean `valid`, with the deciding quantity) and omits or nulls the numbers when it is not valid. Spec
  only; no SDK behaviour. Evidence: Task 11 report, S10 (the microscope twin's `snap` returns `focus_score` and `mean_counts`
  with nothing that says "no specimen"; three model tiers reported a focus plane on an empty field, `uc1-blank-field`).
  **Learning for SimLab (Task 10/11 twins)**: `snap`, plate-reader and balance results should declare `quality`/`valid` (and
  the capture time Task 10 already asked for), and the blank-field case should return `quality: "invalid"` with null scores;
  agent tasks should then be judged on whether the model reads the indicator. Requirement index: 258 rows.
- **BHMS-OPS-082 (new, MUST, core)**: a server with a reconciliation path attempts reconciliation of a device's `unknown`
  operations whenever the device returns to `online` (once per return, bounded, never assuming success). BHMS-DEV-012 gains a
  SHOULD: probe reachability periodically, and let evidence that the device does not answer end `online` at once. Python SDK:
  the reconcile hook runs on every return; `@device.liveness(interval_s=...)` / `DeviceServer(liveness_interval_s=...)`
  (default off) probes periodically, a failed probe makes the device `offline`, and any evidence of life brings it back;
  conformance fault `amnesia` and check `operations.reconcile-on-return`. Evidence: Task 11 report, S11 (54 of 67 power-cut
  drills stayed `unknown` with power restored; 0 of 67 once the twin triggered reconcile itself) and Task 10 report, SDK gap 6
  (liveness ran only at server start, so a bridge whose instrument died kept its last status).
- **`operations/resolve` (new method, capability `operations.resolve`; §6.10, BHMS-OPS-100, 101, 102; profile `authority`)**:
  `{operationId, resolution?}` → `{operation}`. Scope `operations:resolve` (or `admin`); the device is asked first and its
  evidence wins; without `resolution` the call only asks again; an operator's `resolution` (`state`, free-text `basis`,
  optional `effect`, `mayHaveActed`, `result`) is recorded as a `reconciliation` entry carrying
  `operator: {principal, basis}` after the unchanged history; every resolution is an `operation.resolved` event. An
  operator's statement is a report: the recorded effect is at most `unverified` and the evidence is `{"kind": "reported"}`;
  `verified`/`measured` come only from the device's own evidence during the resolve; `resolution.effect` is `none` or
  `unverified`, there is no `observations` member, and an operation that required a verified effect cannot be resolved as
  `completed` (review of Task 7b, Ruling R38: a first version let typed-in observations stamp `verified`). Schema:
  `OperationsResolve*`, `OperatorResolution`, `OperatorMark`, `HistoryEntry.operator`, `Scope`, `ServerCapabilities.operations.
  resolve`; examples `operations.resolve.request.json`, `operations.resolve.response.json`,
  `invalid-resolve-no-effect-claims-proof.json`, `invalid-resolve-claims-verified.json`. A gateway forwards it and, when the upstream cannot be asked, records the
  resolution on its own operation. Not on the agent surface. Chapter 6: "Operation notifications" is now §6.11. Evidence:
  Task 10 report, SDK gap 5 and its spec learning (an `unknown` the device cannot prove kept its resources inhibited with no
  operator path: "a dead bridge keeps its resources inhibited"). Requirement index: 262 rows.
- No requirement change, Python SDK packaging: the build hook `sdk/python/setup.py` copies the schema and the conformance
  vectors (one source: `spec/bhms`) into every wheel and sdist and fails the build when they are missing; a dangling schema
  link in a copied source tree is reported with what to do. Evidence: Task 10 report, SDK gap 3 (a copied package failed at
  `DeviceServer.start()` with `FileNotFoundError`; a wheel built from such a copy was produced without the schema, silently).
- Example `server.discover.response.json` advertises `capabilities.operations.resolve`.
- **Refusal field of a resolution (Ruling R45, review of Task 8c)**: when an `OperatorResolution` breaks one of its
  consistency rules, the refusal's `field` names the member at fault (`resolution.effect`, `resolution.mayHaveActed`,
  `resolution.result`); `resolution` alone only when the object itself is wrong. The example
  `invalid-resolve-no-effect-claims-proof.json` now carries `effect: "unverified"` with `mayHaveActed: false`, and its
  `expect` points at `/params/resolution/effect` (`const`). Evidence: the Python SDK reported `resolution` (its model
  validator) where the TypeScript SDK, following the schema path, reported `resolution.effect`; both now report the member.

### TS SDK to follow (done in Task 8c)

All items below are implemented in `sdk/typescript` (Task 8c, commits `a860d95..`; fix round 1 of its review); the
TypeScript conformance device claims the same profiles as the Python one with the same check results.

- BHMS-LSE-014 in the TypeScript device server (admission and pre-dispatch) and the conformance check
  `leases.held-lease-blocks-everyone`; `stop.not-blocked-by-load` now presents the lease it holds.
- BHMS-DEV-033 as a MUST: refuse a hazardous action without `requiresLease` when a description is built (the shared schema
  already rejects it).
- BHMS-OPS-008: a result outside its declared output range ends `failed` with `OUT_OF_RANGE` (`field: "result.<member>"`), not
  `INTERNAL`.
- The unit registry additions, if the TypeScript SDK grows a unit registry (it has none today: nothing to implement).
- BHMS-DEV-013 (`text` word search, `capability: "*"`) and BHMS-DEV-014 (candidate ids in the `UNKNOWN_DEVICE` hint) in the
  TypeScript device server; conformance checks `descriptions.list-text-filter` and `descriptions.unknown-device-hint`.
- Regenerate `src/generated/types.ts` (`npm run gen-types`): `AgentFindData.totalDevices`, the capability filter pattern, and
  every schema change of this round listed above and below.
- Nothing in the TypeScript SDK (it has no agent bridge); the regenerated types carry `AgentDescribeInput.topic`,
  `AgentTopicData` and `AgentDescribeData`.
- Nothing to implement for BHMS-OPS-064 and BHMS-AUTH-015 (no TypeScript gateway); the regenerated types carry
  `Operation.upstream`.
- BHMS-OPS-082 (reconcile when a device returns), the conformance fault `amnesia` and, if the TypeScript server is to claim
  `authority` with `capabilities.operations.resolve`, `operations/resolve` (BHMS-OPS-100..102) with the `resolver` role of the
  conformance fixture. A server that does not advertise `operations.resolve` is not applicable for those three rows.

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

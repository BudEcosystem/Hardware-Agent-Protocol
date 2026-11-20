# BHMS changelog

## v0.2 — 2026-11-15

Protocol version `2026-11-15`. Servers of this version also serve `2026-11-13` requests with v0.1 behaviour (BHMS-LIF-026).
Task 15a harvested every "spec learnings" section of Tasks 1–14, the benchmark and agent reports and the ledger's deferrals;
the triage of each learning is in `.superpowers/sdd/2026-11-13-bhms-build-plan/task-15a-report.md`. Each entry names the
evidence that caused it. Requirement index: 285 rows (23 added, §14.6).

- **Versions (§3.3, BHMS-LIF-026, new, MUST, core; Ruling R55).** The version string is `2026-11-15`; servers list both
  versions and answer each request with its version's messages: a 2026-11-13 request is never shown
  `capabilities.authority.budgets`, `capabilities.programs.grants`, `principal.budgets` or a program-scoped grant among its
  scopes, and is held to every limit all the same (a budget refusal is `OUT_OF_RANGE`, a code v0.1 defines). BHMS-LIF-024
  now reads "per principal and version". Python: `bhms.protocol.version.SUPPORTED_VERSIONS`, `discover_for`; the client
  retries with the newest shared version. Evidence: Ruling R55.
- **Cumulative budgets (§7.4.1, BHMS-AUTH-030..035, new, MUST, authority; schema `Budget`, `BudgetState`,
  `PolicyPrincipal.budgets`, `Principal.budgets`, `ServerCapabilities.authority.budgets`; Ruling R50).** A grant may carry
  budgets (action pattern, JSON Pointer to a numeric argument with a unit, total, optional rolling window). Admission reserves
  the charge in the one admission path, atomically and in the same write as the operation (a gateway: as its pending-forward
  record); a request that would exceed a budget is refused `OUT_OF_RANGE` with `bound = {maximum, budget}` before anything is
  dispatched; a reservation is released only when the outcome proves nothing happened (`rejected`, `failed` with
  `mayHaveActed: false`, `canceled` with `effect: none`, or an upstream refusal before anything was created); `unknown`
  counts as consumed; the ledger is durable (store table `budget_ledger`); `server/discover` shows what remains. BHMS-AUTH-010:
  what remains narrows the effective envelope. Decision: `OUT_OF_RANGE` with a structured `bound`, not a new code — the
  remaining budget *is* an envelope bound (AUTH-010), a v0.1 peer already reads that code, and the precedent of BHMS-OPS-008
  (reuse the code that carries "which member, which bound"). Python: `bhms.runtime.budgets` (device server `Executor.admit`
  and gateway `Router._admit` call the same `BudgetLedger.charges`; no second implementation). Evidence: Task 14 report §4
  learning 1 (live gpt-5.4-mini, "dispense 600 uL; if not possible, dispense nothing": 500 uL then 100 uL against a 500 uL
  per-call bound); `tests/test_budgets.py`, `tests/test_gateway_budgets.py`, conformance `authority.budget-total`,
  `authority.budget-survives-restart`.
- **Program-scoped grants (BHMS-PRG-023, new, MUST, authority; BHMS-PRG-006 amended; schema `Scope`
  `programs:run:sha256:<hex>`, `ServerCapabilities.programs.grants`; Ruling R51).** `programs:run:<digest>` authorizes exactly
  the reviewed program's steps without `invoke` scope on them; a changed program (another digest) is `UNAUTHORIZED`; leases,
  envelopes, budgets and hazard rules still apply to each step (the digest names every step's action literally, which is
  what BHMS-AUTH-003 asks of a hazardous one). Programs can now be an agent's safety boundary. Evidence: Ruling R46 (in v0.1
  running a program needed `invoke` on every step, so the agent could call the action directly); `tests/test_program_grants.py`,
  conformance `authority.program-grant`.
- **Late terminal reports (BHMS-OPS-072, new, MUST, core; BHMS-OPS-004 and OPS-071 clarified; event type
  `operation.late_report`; Ruling R52).** Terminal states stay immutable; a terminal report that arrives after the server ended
  the operation is journaled (`correction` entry with outcome and evidence kind) and surfaced as an `operation.late_report`
  event (`data: {outcome, evidence, state}`) to reconcile from. Python: the executor (duration bound, deadline, lease loss)
  and the compact bridge (a RESULT that contradicts an ended operation). Evidence: Ruling R41 (a slow-link success read as
  `failed DEADLINE_EXCEEDED` with no trace of the device's report); `tests/test_compact_v02.py`, conformance
  `operations.late-terminal-report`.
- **Compact bounds over a link (§11.12, BHMS-CMP-052, new, MUST, compact; Ruling R53).** A compact action's `maxDurationMs` is
  the endpoint's execution bound; the bridge bounds the operation by it plus a link allowance computed from its link (baud,
  largest frame, retransmissions, one QUERY period) or configured (`link_allowance_ms`). Evidence: Ruling R41, Task 9b round 5.
- **Measured compact completion (BHMS-CMP-036, new, MUST, compact).** A RESULT `completed`/`measured` makes the effect `verified`
  only through fresh, valid, measured `verifiedBy` readings, which become the operation's evidence. Evidence: Task 14 §3
  deferred 2 and learning 3 (`move_joints`/`enable` of the BHMS Arm always completed `unverified`).
- **Bounded reading latency (BHMS-CMP-061, new, SHOULD, compact).** An endpoint reports the age of values it acquires (0 for a
  FRESH READ); the gateway adds the time since the READ left; unknown age still fails every freshness requirement. Evidence:
  Task 14 learning 8 (every LedAnalog reading had unknown age, so no `requiresFresh` action could be admitted).
- **STOP tokens (BHMS-CMP-053, new, MUST, compact).** A token of an unconfirmed stop is not reused before the next HELLO (the
  8-bit space wraps after 255 stops); with every token taken the STOP goes out with token 0 and a HELLO is asked for; a STOP sent
  again after a HELLO carries that HELLO's session. Compact version unchanged (2): no layout changed. Evidence: Task 9b review
  minors deferred to v0.2.
- **Action duration cap (BHMS-DEV-036, new, MUST, core; schema `ActionDescription.maxDurationMs` `maximum` 86 400 000; Ruling
  R54).** Evidence: Task 12b report spec learning 3 (an action's bound was unbounded while the program's and the stop's were not).
- **Request credential carrier (BHMS-SEC-005, 006, new, MUST, core; BHMS-SEC-007 a scheme is a promise, new, MUST, inspection;
  `_meta` key `bhms/authorization`; TRN-021 and TRN-031 amended; Ruling R56).** One standard carrier, `"Bearer <token>"`, for raw
  TCP, a loopback WebSocket without the header, and stdio; refused beside a transport credential; never logged or forwarded; sent
  only over TLS or local transports. Python: `DeviceServer.listen("tcp://...")` (and `tcps://` with TLS) now serves, the client
  sends the carrier on TCP. The TypeScript SDK's `_meta["org.bhms.sdk/bearer"]` moves to it in Task 15b. Evidence: Task 8
  deferral (SDK-private carrier; Python had none); Task 14 learning 10 (`wss://` on loopback served plain text).
- **TLS model (BHMS-SEC-004 amended).** Native TLS (gateway `[gateway] tls_cert`/`tls_key`; a device server's `SSLContext`) or
  the proxy model (plain loopback behind a TLS-terminating proxy); an MCP bridge on Streamable HTTP is a server too. The gateway
  refuses a TLS scheme without TLS configuration, TLS options no listener uses, and TLS under a plain scheme. Evidence: Task 14
  learning 9, SDK/DX issue 11.
- **Hints never contradict proof (BHMS-ERR-007, new, MUST, core; checked by the observers over all traffic).** Evidence: Task 14
  §3 deferred 1 and learning 7 (a `DeviceFault` with proof kept "partial effects are possible").
- **Agent surface.** BHMS-AGT-017 (new, MUST): `bhms_describe` lists the caller's budgets that apply, with what remains (Task 14
  learning 1; the refusal's hint already says how much may still be asked for). BHMS-AGT-033 (new, SHOULD): `bhms_stop` waits a
  bounded 5 s so an asynchronously confirming device is reported `confirmed` (Task 14 learning 6). BHMS-AGT-011 amended: a failure
  summary keeps the code and the first clause of the message before the hint, and cuts at word boundaries (learning 13, DX issue
  5); BHMS-AGT-015: matched programs are named (learning 15); the signature block shows long enums as `...(N values)` and
  property bounds (learning 14). The eight tool definitions are unchanged.
- **Stdio hosts (BHMS-TRN-013, new, SHOULD).** Hosts pass `BHMS_STATE_DIR`/`BHMS_TOKEN`; the Python server warns when it serves
  stdio on the default state directory. Evidence: Task 14 learning 2.
- **Unit spellings (§4.5).** The refused common spellings (`rpm`, `ppm`, `mM`, `degC`, ...) and the code to write instead are
  listed for every SDK. Evidence: Task 14 learning 12, commit daac70e.
- **Stop reader (BHMS-AUTH-027, new, SHOULD; Ruling R48).** A stop path independent of the journal's sync is recommended; the
  current measured bound is stated. Not implemented in v0.2.
- **Schema bound counting (BHMS-SEC-021)** is normative (Ruling R34: "Task 15 makes it normative").
- **Conformance (BHMS-CNF-007, new, MUST, inspection; §14.6).** A run tests one version (the newest shared, or
  `--protocol-version`) and marks rows added later not applicable; the runner's own `compact-gateway` fixture is a declared
  fixture, so the compact profile is claimable from it; a gateway `.toml` target's further processes get their own journal
  (`BHMS_GATEWAY_STATE_DIR`). Evidence: Task 14 learning 11 and DX issues 9, 10.
- **Examples.** `actions.invoke.response.json` and eight other examples carried a `requestDigest` their own content does not
  produce; all regenerated, and `sdk/python/tests/test_example_digests.py` recomputes every digest of the corpus (Task 8b spec
  learning; Task 8 learning 12). `error.out-of-range.json` no longer advises splitting a dispense into two (the advice that
  defeats a total). New: `error.out-of-range-budget.json`, `policy.gateway-budgets.json`, `event.operation-late-report.json`,
  `invalid-action-max-duration-above-a-day.json`, `invalid-policy-budget-without-quantity.json`,
  `invalid-scope-program-grant-short-digest.json`, `invalid-meta-authorization-not-bearer.json`; request examples carry
  `2026-11-15`; `server.discover.response.json` shows budgets and a program grant.
- No requirement change, Python SDK only (carried from the Task 12b review): a queued operation whose dispatch sync fails is
  answered with its execution's outcome, not `dispatching`; a program whose creation sync and rejection both fail is refused
  `BUSY` (no unrun `accepted` program is handed out); a committed but not durable barrier leaves memory and journal in agreement
  (a program whose first-step barrier is not durable ends `failed`, nothing sent; gateway mirrors and recovery write their
  `dispatching` without a barrier). The `wrap-an-instrument` guide's liveness probe uses `*IDN?`, so an injected lost `*OPC?`
  no longer makes the device offline under load.

### TS SDK to follow (Task 15b)

Port in progress: action declarations now enforce BHMS-DEV-036. Late terminal reports append
correction history and `operation.late_report` events; a lease revoked under `onLeaseLoss: hold`
ends the operation immediately, preserving that outcome when its handler later returns.
Regression coverage includes duration boundaries, late returns after duration expiry, and
terminal immutability after lease hold. Version negotiation remains v0.1 until the rest of
this port is complete.

Every row of §14.6, the version list (`2026-11-15` and `2026-11-13`, BHMS-LIF-026), budgets in the device server
(BHMS-AUTH-030..035; the same rules, the same refusal), program-scoped grants (BHMS-PRG-023), late reports (BHMS-OPS-072),
BHMS-DEV-036 at description build, the carrier (BHMS-SEC-005/006, replacing `org.bhms.sdk/bearer`), hints (BHMS-ERR-007) and
the `tcps://`/`wss://` refusals (BHMS-SEC-007). Until then the TypeScript SDK serves and speaks `2026-11-13` only
(`SDK_PROTOCOL_VERSION`); its types are regenerated from this schema.

### Also in v0.2: the Task 7b and 12b rounds (formerly "Unreleased")

Performance round (Task 12b). Each entry names the evidence that caused it.

- **BHMS-OPS-003 clarified (no new requirement)**: a `dispatching` record that was written but could not be made durable
  (the journal's sync failed) counts as not written: nothing is dispatched, and since the record already reads `dispatching`
  the operation ends `failed` with `mayHaveActed: false` and `effect: "none"` (the server proves nothing was sent);
  concurrent intents may share one sync (group commit) provided none is dispatched or reported before the sync covering its
  own record has completed. Evidence: Task 12a measured one fsync per intent capping durable throughput at about 550
  operations per second whatever the number of clients; group commit in the Python SDK (Task 12b) separates the commit from
  its sync, which made the "written but not durable" case reachable and in need of a defined outcome (a `dispatching` record
  cannot become `rejected`).
- **"Reported" in OPS-003 means any observer** (Task 12b fix round 1, Ruling R47): the invoker's answer, operation
  notifications, `operations/get` and `operations/list` (and so a gateway mirroring the server) all wait for the sync covering
  the record. Evidence: the Task 12b review probe — a second client subscribed to the device's operations heard `accepted`
  then `dispatching` while the sync had not completed; after a power loss that operation id would have vanished.
  Observability is per record and monotonic (fix round 2, Ruling R57): once shown, a record stays visible, as its last
  durable state, while a later barrier write (a queued operation's `dispatching`) waits for its sync; only that write's
  notification waits. A queued `accepted` record is durable before it is answered or observed (§6.5 step 10, "Durably
  record `accepted`"): both SDKs now make it a barrier. (Fix round 1 said here that a queued `accepted` "recovers
  `rejected`" without one; that held after a process crash but not after a power loss, where it could vanish after being
  answered. Withdrawn.) The `stop` result is exempt (Ruling R58): it may name operations whose intent sync has not
  completed; it cancels them and each ends `canceled` with `effect: "none"`.
- **Learning, v0.2 idea (Ruling R48)**: on a durable server a synchronous or inline sync runs on the server's one event loop,
  so a `stop` arriving meanwhile is read only when that sync returns: stop latency is bounded by one `fdatasync` in flight
  (about 1.3 ms typically on Task 12b's shared host; inline-sync loop stalls of up to 261.7 ms measured there, 356.9 ms in a
  variant without the start-up heap freeze). A reader for `stop` that does not share the
  loop with the journal (a separate thread or process that reads the connections and dispatches the stop procedure) would
  remove that bound; not done in v0.1.
- **Gateway pending-forward barrier kept, with its reason stated (§7.6 *Operations*)**: the pending-forward record must be on
  stable storage before a forward leaves; concurrent forwards may share the sync. Decision: keep it (Task 5's note that the
  gateway needs no barrier is withdrawn). Evidence: without it a power loss after the send loses the record, so the gateway
  can neither report the forward `unknown` nor inhibit its resources, and a client's same-key retry re-sends it; the upstream
  deduplicates by key only while it keeps its own journal (BHMS-OPS-081), so an upstream whose epoch changed (a reset store,
  a non-durable simulator) would act twice. Cost measured in Task 12b: one fsync per lone forward (unchanged); with group
  commit concurrent forwards share it (`bench/scenarios/gateway_forward.py`).
- **`SafetyDescription.stopMaxDurationMs` is at most 86 400 000** (one day, the bound of a program's `maxDurationMs`; §4.7
  table, schema `maximum`, new example `invalid-safety-stop-bound-above-a-day.json`). Evidence: Task 9b review (deferred to
  12b): a closing server waits for a running stop up to its declared bound (BHMS-AUTH-024), and an unbounded integer let a
  description make that wait arbitrarily long. Both SDKs refuse such a bound when the stop procedure is declared. (The
  action's `maxDurationMs` has no upper bound in the schema; see the Task 12b report.)
- **§7.5 wording**: a `failed` stop's `message` (not `error`) says which kind of failure it was. Evidence: Task 9b review.
- No requirement change, SDKs only: the Python store syncs barriers itself (one connection at `synchronous=NORMAL`, no
  safety-level switching) and shares syncs between concurrent intents; the TypeScript journal fsyncs only the `dispatching`
  record (and fences), as the Python one does; a Python server closing with a stop procedure running warns when it waits
  beyond `close_timeout` and honours a ceiling (`stop_shutdown_ceiling_s`), recording the ended stop as `failed`.

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

#### TS SDK to follow (done in Task 8c)

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

Compact round 5 (Task 9b fix 5): BHMS-CMP-050: a gateway sends a stop in progress again, with a new token, after adopting a HELLO, so a re-HELLO without a reboot does not leave it unconfirmable. BHMS-AUTH-024: a closing server waits for a running stop procedure at least until its declared bound (`stopMaxDurationMs`) has passed before ending it. Section 7.5: a `failed` stop also means "dispatched, outcome unknown" (the procedure failed or timed out, or was ended at shutdown; the device may or may not be stopped).

Compact round 4 (Task 9b fix 4): BHMS-CMP-050: the endpoint forgets the token of a stop in progress at every HELLO it sends (the confirming ack then carries token 0), and the gateway starts its tokens at a random value and ignores acks whose token it has not sent since the last adopted HELLO, so a restarted gateway is never confirmed by its predecessor's stop; token 0 is defined as "endpoint-originated stop" (the stop input, or a stop begun before the last HELLO); the hardware stop input during a gateway stop makes that stop end `failed` (the device may be stopped; stated as the safe under-claim); a closing gateway ends its stops in progress `failed` at once. BHMS-AUTH-024: a server that closes while a stop procedure runs waits for it (bounded), then records it as a `failed` stop event. A refused compact version is logged at ERROR once, then at DEBUG. No layout change, compact version stays 2.

Compact round 3 (Task 9b fix 3): BHMS-Compact version 2: STOP carries a token and both STOP_ACKs echo it (hardware-stop acks use token 0), so a late ack of an earlier stop can never confirm another (BHMS-CMP-050); endpoints and gateways of different versions refuse each other.

Compact round (Task 9b fix 1): `device.epoch` `data` members `persistent` and `purged` documented (9.2, BHMS-OPS-042); BHMS-CMP-022 defines the endpoint incarnation; BHMS-SEC-050 is enforced by the gateway (networked compact links are refused).

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

# BHMS Build Plan: Protocol, SDKs, Tools, Simulation, Benchmarks and the Universal Actuator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Bud HMS (BHMS) as a protocol that physical-AI developers can adopt the way they adopt MCP. That means a normative spec with JSON Schema, reference SDKs in Python, TypeScript and C, a gateway, a CLI, an MCP bridge, a conformance suite, a simulated lab with agentic tests, and benchmarks. Learnings flow back into the spec. Finally, design an open universal actuator (an arm with interchangeable end effectors) with CAD, a controller PCB and firmware that speaks BHMS.

**Architecture:** BHMS is JSON-RPC 2.0, like MCP, carried over interchangeable transports, plus a compact binary binding for microcontrollers. Every BHMS *device server* gets durable operations, idempotent replay, leases and honest evidence from the SDK, so a driver author writes only the device logic. A *gateway* is a server that is also a client of many device servers: it aggregates them, adds authority, policy and cross-device leases, and bridges compact MCU links. Agents reach BHMS natively, through the MCP bridge, or through generated tool schemas for function-calling APIs.

**Tech Stack:** Python ≥3.11 (asyncio, orjson, pydantic v2, websockets, typer, rich, sqlite3), TypeScript (Node ≥20, zod-free hand-written types from the JSON Schema), C11 (no heap) with an Arduino wrapper, MuJoCo for simulation, pytest and hypothesis, simavr, build123d/CadQuery for CAD, programmatic KiCad file generation for the PCB, OpenAI API and llama.cpp (on the AMD machine) for agents.

**Spec:** The normative spec is produced by Task 2 at `spec/bhms/`. Until it exists, section 2 of this plan (the protocol design) is the authority. Semantic foundations come from the existing HMS work: `spec/02-execution.md` (operation states, evidence, replay, cancellation), `spec/12-io-driver-boundary.md`, `docs/conformance-plan.md`, `docs/prompt-to-pat.md`.

## Global Constraints

- **No stubs, no mock product code.** Every function ships complete. Test doubles exist only in tests.
- **No duplicated logic.** Search before writing. Within `sdk/python`, one module owns each concern (JSON canonicalization, error codes, units, schema validation). Reuse `protocol/serial/frame.{c,py}` for byte framing in the compact binding unless the task report justifies a replacement.
- **Everything integrates.** Every module is reachable from the SDK's public API, the CLI, or a test of the public API.
- **The protocol is the contract.** `spec/bhms/schema/bhms.schema.json` is the single machine-readable source. Python and TypeScript types and the MCP/OpenAI tool schemas are generated from it or checked against it in tests. A message that fails the schema is a bug.
- **Honest semantics never weaken for convenience.** A transport ACK is not completion. A lost reply after dispatch becomes `unknown`, never success or failure. Unsupported means refuse. A model-supplied boolean never grants authority.
- **Performance budgets** (local loopback, release build, measured on the AMD machine):
  - p50 `actions/invoke` round trip, Python server over Unix socket, ≤ 1 ms; p99 ≤ 5 ms with durable journaling.
  - Gateway aggregates ≥ 1,000 device servers; `devices/list` of 10,000 devices pages in ≤ 50 ms.
  - Compact binding frame ≤ 64 bytes for a typical invoke.
  - If a budget is missed, report the measured number and the cause. Never hide a miss.
- **Developer experience bar:** a new device server in ≤ 15 lines of Python; `bhms dev <file>` gives an interactive inspector; every error message names the field, the bound and a fix.
- **Agent experience bar:**
  - At most eight model-facing tools.
  - Every result has a one-line human summary plus structured content.
  - Every refusal says why and what to do next.
  - Descriptions are compact: a device summary ≤ 400 tokens.
- **Machines.**
  - *Workstation* (`/home/bud/Desktop/bud/hms`): code lives here. **No local models.** Agent models come from the OpenAI API, with the key loaded from `~/.config/hms/openai.env`. The key is never written into the repo, logs or reports. The disk has only 16 GB free, so no large installs.
  - *AMD machine* (`ssh bmh-worker`, Ryzen AI MAX+ 395, 91 GB, Radeon 8060S with ROCm, XDNA NPU, 392 GB free): heavy runs go here — simulation, benchmarks, local models (llama.cpp HIP at `~/amd-ai/src/llama.cpp/build/bin`), CAD kernels. Work only inside `~/hms-lab` and Docker objects named `hms-lab-*`, under `nice`. No sudo. The machine is shared with benchmark jobs, so cap CPU use.
  - *Network:* about 0.1–0.5 MB/s on both machines. Avoid downloads over about 300 MB, and say so in the report when something cannot be fetched.
- **Python packaging:** `sdk/python` is an installable package named `bhms`. Runtime dependencies: `orjson`, `pydantic>=2`, `websockets`, `typer`, `rich`, `jsonschema`. Optional extras: `mcp` (bridge), `sim`, `openai`. Tests run with `pytest -q` from `sdk/python`.
- **Commits:** small, conventional (`feat(sdk-py): …`), each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Work happens on branch `feat/bhms`.
- **Reports** list what was learned that should change the spec. Task 15 harvests these.

## Review Focus

1. **A crash between dispatch and the result record.** The device may have acted. *Pinned by Task 4: `test_crash_after_dispatch_becomes_unknown` (kills the server process mid-operation and restarts).*
2. **Retrying with the same key after a timeout.** It must never act twice. *Pinned by Task 4 `test_same_key_same_operation` and the conformance suite in Task 7.*
3. **Agents sending out-of-bounds or invented arguments.** *Pinned by Task 6 (MCP bridge refusal content) and Task 11 (`violations_reaching_device == 0`).*
4. **Slow or dead device servers behind a gateway.** One must not stall the others. *Pinned by Task 5 `test_stalled_server_isolated`.*
5. **Two clients contending for one resource.** *Pinned by Task 4 lease tests and Task 5 cross-device lease tests.*

---

## 1. Repository layout (created across the tasks)

```
spec/bhms/                    normative spec (Markdown), schema/, examples/, CHANGELOG.md
sdk/python/                   package `bhms`
  src/bhms/
    protocol/                 generated types, error codes, canonical JSON, schema validation
    jsonrpc/                  session, request routing, notifications, cancellation
    transport/                stdio, unix/tcp (newline-delimited), websocket, compact serial
    server/                   DeviceServer, Device, property/action decorators, units and ranges
    runtime/                  operation store (SQLite), leases, events, evidence and observations
    client/                   Client, typed helpers
    gateway/                  Gateway (aggregation, policy, cross-device leases, compact bridge)
    bridges/                  mcp (MCP server), openai (function-tool schemas + agent loop)
    cli/                      `bhms` command
    conformance/              runner + checks (importable; also used by the TS SDK through the CLI)
  tests/
sdk/typescript/               @bhms/sdk: client, server, transports
sdk/c/                        bhms-c compact endpoint library; arduino/ wrapper; examples
simlab/                       simulated lab: world, twins as BHMS device servers, adapters, agents, oracle, tasks
bench/                        benchmark harness and results
hardware/actuator/            universal actuator: cad/, sim/ (MJCF), pcb/, firmware/, bom/, docs/
docs/bhms/                    quickstart, concepts, guides, reference
```

The existing `hms/` package stays as the HMS research prototype. BHMS is the product; it borrows HMS semantics, not its code paths (see Ruling R1 in the ledger).

## 2. Protocol design (authority until Task 2 lands)

**Roles.**
- *Client:* an agent, program or human tool.
- *Server:* exposes one or more devices.
- *Gateway:* a server that also acts as a client of many servers.
- Every server speaks the same protocol, so a client cannot tell a gateway from a direct server except through declared capabilities.

**Wire.** JSON-RPC 2.0, UTF-8 JSON, one message per frame.
- *Transports:*
  - stdio (newline-delimited, as in MCP).
  - Unix and TCP sockets (newline-delimited).
  - WebSocket (one message per frame).
  - Streamable HTTP (POST requests; Server-Sent Events for notifications). Optional in v0.1; the gateway implements it.
- *BHMS-Compact:* a binary binding for microcontrollers, carried in the existing HDLC-style frames (`protocol/serial/frame.c`). It is not JSON-RPC, and a gateway translates it into JSON-RPC.

**Lifecycle.**
1. The client sends `initialize {protocolVersion: "2026-11-13", clientInfo, capabilities}`.
2. The server answers `{protocolVersion, serverInfo, capabilities, instructions?}`.
3. The client sends `notifications/initialized`.
4. Either side may send `ping`. Version negotiation follows MCP: the server answers with the version it supports, and the client may disconnect.

**Server capabilities:**
- `devices` (with `listChanged`).
- `observations` (with `subscribe`).
- `operations` (with `durable` and `cancel`).
- `leases`.
- `stop`.
- `programs`.
- `events`.
- `compact` (on gateways that bridge MCU links).

**Methods (v0.1).**

| Method | Params → Result |
|---|---|
| `devices/list` | `{filter?: {capability?, tag?, text?}, cursor?, limit?}` → `{devices: DeviceSummary[], nextCursor?}` |
| `devices/describe` | `{deviceId}` → `DeviceDescription` (immutable, with `digest`) |
| `properties/read` | `{deviceId, property, maxAgeMs?, fresh?: bool}` → `Observation` |
| `actions/invoke` | `{deviceId, action, arguments, operationKey?, leaseId?, deadlineMs?, require?: {effect?: "verified"}}` → `Operation` |
| `operations/get` | `{operationId}` → `Operation` |
| `operations/wait` | `{operationId, timeoutMs}` → `Operation` (returns when terminal or on timeout, never fails because of the timeout) |
| `operations/cancel` | `{operationId, reason?}` → `Operation` (with `cancel.state`) |
| `operations/list` | `{deviceId?, state?, cursor?, limit?}` → `{operations, nextCursor?}` |
| `leases/acquire` | `{resources: string[], ttlMs, wait?: ms}` → `Lease {leaseId, resources, fence, expiresAt}` |
| `leases/renew` | `{leaseId, ttlMs}` → `Lease` |
| `leases/release` | `{leaseId}` → `{}` |
| `stop` | `{deviceId? \| scope?: "all", reason}` → `{stops: StopResult[]}`. A separate path that never waits on leases or queues |
| `observations/subscribe` / `unsubscribe` | `{deviceId, property, minIntervalMs?}` → `{subscriptionId}`, then `notifications/observation` |
| `events/read` | `{after?: cursor, limit?, deviceId?}` → `{events, cursor, gap?}` |
| `programs/run` | `{program: Program, arguments, operationKey?}` → `Operation`. A bounded sequence of steps (invoke, read, wait-until with timeout, assert), validated before any step runs |

**Notifications:** `notifications/operation` (state change), `notifications/observation`, `notifications/devices/listChanged`, `notifications/event`, `notifications/cancelled` (as in JSON-RPC/MCP).

**Device description.**
- *Identity:* `deviceId`, `name`, `description`, `capabilities` (namespaced, e.g. `bhms.axis.linear`, `bhms.camera`, `bhms.liquid.dispense`), `tags`, `digest` (sha256 of the canonical JSON), `resources` (strings naming exclusive resources).
- *`properties`:* each has `schema` (JSON Schema with `unit`, `minimum`/`maximum`), `evidence` (one of `measured`, `reported`, `commanded`, `estimated`, `simulated`), `maxRateHz`, `observable`.
- *`actions`:* each has:
  - `input` and `output` JSON Schemas, with `x-unit` on numbers.
  - `effect`: `none`, `reversible`, `irreversible` or `hazardous`.
  - `idempotency`: `idempotent`, `absolute`, `relative` or `toggle`.
  - `cancel` (`supported`/`unsupported`).
  - `completionEvidence`: `measured`, `reported` or `none`.
  - `typicalDurationMs`, `maxDurationMs`.
  - `requiresLease: bool`, and the resources it uses.
- *`streams`*, if any. *`safety`:* a free-text summary of the stop behaviour.

**Operation.**
- Fields: `operationId`, `operationKey`, `deviceId`, `action`, `arguments`, `state`, `cancel`, `effect`, `result?`, `error?`, `createdAt`, `updatedAt`, `history`.
- `state` ∈ `accepted | dispatching | running | completed | failed | canceled | rejected | unknown`.
- `cancel.state` ∈ `none | requested | acknowledged | refused | confirmed`.
- `effect` ∈ `none | verified | unverified | unknown`.
- *Transition rules* (from `spec/02-execution.md`): terminal states never change; corrections are new history entries; `unknown` may move to a terminal state only through reconciliation evidence; a completion that requires `verified` cannot complete without measured evidence.

**Idempotency.**
- `(principal, operationKey)` maps to exactly one operation.
- The same key with the same canonical request returns the existing operation.
- The same key with a different request returns error `KEY_CONFLICT`.
- Keys are retained for a declared window, `capabilities.operations.keyRetentionS`, of at least 24 h.
- If the client omits `operationKey`, the server generates one and returns it. Such a call is not deduplicated across retries, and the result says so.

**Observation.** `{value, unit?, evidence, quality: "valid"|"stale"|"invalid"|"unknown", acquiredAt, receivedAt, ageMs, uncertainty?, sequence, epoch}`. A missing measurement is `quality: "invalid"` with `value: null`, never zero.

**Errors.** A JSON-RPC error `{code, message, data: {bhmsCode, field?, bound?, mayHaveActed: bool, retry: "never"|"same-key"|"after-reconcile"|"backoff", hint}}`.
- *Codes:*
  - `INVALID_ARGUMENT`, `OUT_OF_RANGE`, `UNIT_MISMATCH`, `UNKNOWN_DEVICE`, `UNKNOWN_ACTION`, `UNSUPPORTED`.
  - `LEASE_REQUIRED`, `LEASE_CONFLICT`, `LEASE_EXPIRED`, `FENCED`.
  - `KEY_CONFLICT`, `STALE`, `DEVICE_UNAVAILABLE`, `UNAUTHORIZED`, `BUSY`, `DEADLINE_EXCEEDED`.
  - `INTERNAL`.
- *Numeric JSON-RPC codes:* `-32602` for argument errors, `-32001…-32020` for the BHMS range (mapping table in the spec).

**Authority.**
- Transport-level identity: a Unix peer credential, a bearer token on WebSocket/HTTP, or a stdio parent process (trusted).
- A gateway policy file grants principals scopes: `read`, `invoke:<capability or action glob>`, `lease`, `stop`, `admin`. It may also narrow action bounds per principal (an effective-envelope intersection).
- Models never assert authority in arguments.

**Leases and fencing.** A lease holds named resources exclusively, with a TTL. Every acquire increments a monotonically rising `fence` per resource. Actions that need a lease carry `leaseId`, and the server checks it is current at dispatch. When a lease expires, actions in flight follow the action's declared policy: by default the operation finishes and its result is recorded, but no new step starts.

**Programs (bounded).**
- A JSON program contains `steps`. Step kinds: `invoke`, `read`, `waitUntil {property, predicate, timeoutMs}`, `assert`, `sleep`, `repeat {times ≤ 1000}`.
- Variables are referenced as `${name}`.
- There are no unbounded loops and no arbitrary code.
- The server validates the whole program and computes worst-case duration before running it.
- One operation represents the program; step results appear in its history. This is the vehicle for Programs-as-Tools reuse.

**BHMS-Compact (MCU binding).**
- Frame payloads are CBOR-like fixed layouts:
  - `HELLO` (device digest, boot epoch, capability table hash).
  - `INVOKE` (op handle u16, action index u8, args as fixed-width little-endian).
  - `STATUS`, `RESULT`, `CANCEL`, `READ`, `VALUE`, `STOP`.
- The MCU keeps a small ring of recent operation handles, so retransmits are answered and not re-executed.
- The gateway holds the full description, keyed by the digest the MCU reports, and does all JSON-RPC work.

**Agent surface.** The MCP bridge and the OpenAI tool adapter expose exactly:
- `bhms_find_devices`, `bhms_describe`, `bhms_read`, `bhms_invoke` (accepts `wait_ms`, returns the final or current state), `bhms_operation`, `bhms_cancel`, `bhms_stop`.
- `bhms_run_program` when the server supports programs.

Results are a one-line summary plus structured content. Refusals carry the `hint`.

## 3. Tasks

Ordering and parallelism: tasks run in the listed order. The ledger records any task run in parallel in its own worktree; only tasks marked **[parallel-safe]** may do so, because they touch disjoint directory trees.

### Task 1: Python package skeleton, canonical JSON and the schema pipeline
**Files:** `sdk/python/pyproject.toml`, `src/bhms/__init__.py`, `src/bhms/protocol/{canonical.py,errors.py,units.py,version.py}`, `tests/test_canonical.py`, `tests/test_errors.py`, `tests/test_units.py`.
- RFC 8785 canonical JSON and `digest(obj) -> "sha256:<hex>"`. Use the PyPI `rfc8785` package if it installs; otherwise wrap the vendored copy at `hms/_vendor/rfc8785` by import, not by copying.
- `errors.py`:
  - `BhmsError(code, message, *, field=None, bound=None, may_have_acted=False, retry="never", hint="")`.
  - `to_jsonrpc() -> dict` and `from_jsonrpc(dict) -> BhmsError`.
  - The full code table from section 2, with JSON-RPC numbers.
- `units.py`: the UCUM subset used by the spec (length, angle, time, temperature, volume, mass, pressure, flow, current, voltage, frequency, percent). Provides `convert(value, from_unit, to_unit)` and `compatible(a, b)`. Incompatible units raise `UNIT_MISMATCH`. Never convert silently: conversion happens only when a caller explicitly asks.
- **Acceptance:** `pip install -e sdk/python` works; tests pass; `python -c "import bhms; print(bhms.PROTOCOL_VERSION)"` prints `2026-11-13`.

### Task 2: Normative spec v0.1 and JSON Schema (architecture, most capable model)
**Files:** `spec/bhms/README.md` (overview, like MCP's spec landing page); `spec/bhms/{01-overview,02-transports,03-lifecycle,04-devices,05-observations,06-operations,07-leases-and-authority,08-programs,09-events-and-streams,10-errors,11-compact-binding,12-agent-surface,13-security,14-conformance}.md`; `spec/bhms/schema/bhms.schema.json`; `spec/bhms/examples/*.json` (one valid example per message type plus invalid examples); `sdk/python/src/bhms/protocol/types.py` (pydantic models matching the schema); `sdk/python/tests/test_schema_examples.py`.
- Write section 2 out normatively (MUST/SHOULD/MAY), carrying over the HMS semantics it cites. Each normative statement gets an ID (`BHMS-OPS-012`) so conformance checks can point at it.
- Include the mapping tables: BHMS ↔ MCP, BHMS ↔ WoT TD, BHMS ↔ OPC UA methods, BHMS ↔ ROS 2 actions, BHMS ↔ Home Assistant services. Each states what is preserved and what is lost.
- **Acceptance:** every example validates or fails exactly as labelled; pydantic models round-trip every valid example; a test asserts every method in the spec appears in the schema's method map.

### Task 3: JSON-RPC session, transports and client
**Files:** `src/bhms/jsonrpc/{session.py,dispatcher.py}`, `src/bhms/transport/{base.py,stdio.py,stream.py,websocket.py}`, `src/bhms/client/client.py`, tests.
- An asyncio session supports concurrent requests, notifications, request cancellation (`notifications/cancelled`), per-request timeouts, a bounded outbound queue with backpressure, maximum message size (default 4 MiB), and clean shutdown.
- Transports: stdio (subprocess spawn on the client side), Unix socket, TCP, WebSocket. Every transport presents the same `Transport` interface: `send(bytes)`, `receive() -> bytes`, `close()`, `peer` identity.
- `Client` provides `connect(url_or_command)` with URL forms `stdio:<cmd>`, `unix:<path>`, `tcp://host:port`, `ws://…`; `initialize`; typed methods for every section-2 method; and `subscribe(...)` as an async iterator.
- Use `orjson` for speed.
- **Acceptance:** a loopback test drives 10,000 concurrent pings without loss; a malformed frame gets a JSON-RPC parse error and the session survives; an oversize frame is refused.

### Task 4: Device server SDK and durable runtime (the heart; most capable model)
**Files:** `src/bhms/server/{server.py,device.py,decorators.py,validation.py,context.py}`, `src/bhms/runtime/{store.py,operations.py,leases.py,events.py,observations.py,programs.py,stop.py}`, tests including `tests/test_crash_recovery.py` with a real subprocess.
- *DX target:*

```python
from bhms import DeviceServer, Range
srv = DeviceServer("bench-stage")
stage = srv.device("stage-z", capabilities=["bhms.axis.linear"], resources=["stage-z"])

@stage.property(unit="um", evidence="measured")
def position() -> float: ...

@stage.action(effect="reversible", idempotency="absolute", requires_lease=False,
              completion_evidence="measured", max_duration_ms=5000)
async def move_to(ctx, target: Range(0, 200, unit="um")) -> {"position": "um"}:
    ...
    await ctx.progress(0.5)
    return {"position": ...}

if __name__ == "__main__":
    srv.run()        # stdio by default; srv.run("ws://0.0.0.0:8765") etc.
```

- Descriptions are built automatically from the decorators and type hints, with a stable `digest`.
- Arguments are validated before anything is recorded: type, range, unit, enum, required fields. Out-of-range arguments are refused with `OUT_OF_RANGE`, the field name, the bound and a hint. They are never clamped.
- *Operation store:* SQLite in WAL mode. The intent is committed before the handler starts. Every state transition is recorded. Same-key replay and `KEY_CONFLICT` are handled. On startup, any operation found in `dispatching` or `running` becomes `unknown`; the device can supply a `reconcile(op)` hook to resolve it from measurements.
- `operations/wait` uses events, not polling. Cancellation reaches the handler through `ctx.cancelled` (an `asyncio.Event`) and records the cancel states.
- *Leases:* TTL and per-resource fences; checks happen at dispatch; expiry follows the declared policy.
- *Observations:* evidence label, age, quality; `maxAgeMs` enforced; subscriptions rate-limited.
- *Events:* an append-only log with cursors and explicit gaps.
- *Programs:* a validator (bounded steps, total worst-case duration) and an executor that uses the same operation machinery.
- *`stop`:* a separate fast path that calls each device's `on_stop` handler without waiting for queues or leases.
- **Acceptance:**
  - Unit tests for every transition.
  - `test_crash_after_dispatch_becomes_unknown` (real process kill).
  - `test_same_key_same_operation` under 50 concurrent identical requests.
  - Lease contention tests.
  - A program whose step fails mid-way records partial effects.
  - A 15-line example server works through `bhms` Client over stdio and WebSocket.

### Task 5: Gateway
**Files:** `src/bhms/gateway/{gateway.py,upstreams.py,policy.py,router.py,journal.py}`, `examples/gateway.toml`, tests.
- *Configuration* (TOML): upstream servers (`stdio` commands, URLs), each with a namespace prefix; principals with tokens and scopes; per-principal bound narrowing.
- *Aggregation:* device ids are namespaced `ns/deviceId`; descriptions are cached by digest; `listChanged` is propagated.
- *Routing:* invoke, read, cancel and wait are forwarded. The gateway journals each forwarded operation (gateway key → upstream key, derived deterministically, so a gateway restart re-sends the *same* upstream key and the upstream deduplicates).
- *Cross-device leases:* the gateway is the lease authority for resources it names; upstream leases are acquired on behalf of the holder.
- *Isolation:* each upstream has its own task and bounded queue, and upstream calls have timeouts. A stalled upstream marks its devices unavailable without blocking others (`test_stalled_server_isolated`).
- *Stop:* fans out to all upstreams concurrently, with a deadline, and reports per-device results.
- *Policy:* scope checks and the effective-envelope intersection are applied before forwarding.
- *Serving:* the gateway listens on Unix socket, WebSocket (bearer token) and stdio.
- **Acceptance:** three example servers behind one gateway; kill an upstream mid-operation and the operation becomes `unknown`, then is reconciled after the upstream restarts; 1,000 in-process upstreams list correctly.

### Task 6: CLI, inspector, MCP bridge and OpenAI tool adapter (developer and agent experience)
**Files:** `src/bhms/cli/*.py`, `src/bhms/bridges/mcp.py`, `src/bhms/bridges/openai_tools.py`, `src/bhms/templates/` (for `bhms new`), tests.
- *CLI commands:*
  - `bhms new <name>` scaffolds a device server and its test.
  - `bhms dev <server.py | url>` starts the server and an interactive inspector (rich TUI: devices, describe, read, invoke with argument prompts from the schema, live operations and events).
  - `bhms ls`, `describe`, `read`, `call <device> <action> key=value…`, `ops`, `wait`, `cancel`, `stop`.
  - `bhms gateway <config>`, `bhms mcp <url | config>`, `bhms conformance <url>`, `bhms bench …`.
  - `bhms doctor` checks the environment and connectivity.
- *MCP bridge:* uses the official `mcp` Python SDK. It serves the tool set from section 2 over stdio and Streamable HTTP, and also exposes each device description as an MCP resource (`bhms://device/<id>`). Tool results include `structuredContent`, and refusals are `isError` with the hint.
- *OpenAI adapter:* `tools_for_openai(client) -> list[dict]` covers both Responses and Chat Completions shapes. `run_agent(client, model, task, budget)` is a minimal tool loop used by SimLab, with the API key taken from the environment.
- **Acceptance:** `bhms new demo && bhms dev demo/server.py` works end to end in a pseudo-terminal test; the MCP bridge passes a round trip with the official MCP client; a recorded-response test of the OpenAI loop passes; the token size of every tool definition is measured and listed in the report.

### Task 7: Conformance suite and test vectors
**Files:** `src/bhms/conformance/{runner.py,checks/*.py}`, `spec/bhms/conformance/vectors/*.json`, a `bhms conformance` CLI entry, tests.
- Each check cites spec IDs. Checks cover: lifecycle and version negotiation; schema validity of every response; describe digest stability; argument refusal (range, unit, missing field, unknown action); idempotency (same key, conflict); cancellation states; `wait` timeouts; lease exclusivity and fencing; observation age and evidence; event cursors and gaps; stop; program validation.
- Runs against any URL. It needs a conformance test device, which every SDK ships as `conformance-device` (a deterministic simulated axis plus counter).
- Output: a table (pass, fail or not-applicable with reason) and JSON.
- **Acceptance:** the Python reference server passes 100%; deliberately broken fixtures fail the right checks.

### Task 8: TypeScript SDK [parallel-safe after Task 7]
**Files:** `sdk/typescript/{package.json,tsconfig.json,src/**,test/**}`.
- Types generated from `bhms.schema.json` by a small generator script committed in the package.
- `Client`, `DeviceServer` (with the same decorator-free builder DX), and stdio, WebSocket and socket transports.
- An in-memory operation store, plus an optional SQLite store if `better-sqlite3` is already cached. Otherwise a JSON-file journal with fsync.
- **Acceptance:** the TypeScript conformance device passes `bhms conformance`; a Python client drives a TypeScript server and a TypeScript client drives a Python server in tests; `npm test` passes offline after install.

### Task 9: C compact binding and Arduino library [parallel-safe after Task 4]
**Files:** `sdk/c/{include/bhms.h,src/*.c,tests/*.c,CMakeLists.txt}`, `sdk/c/arduino/BHMS/{library.properties,src/*,examples/*}`, `src/bhms/transport/compact.py`, `src/bhms/gateway/compact_bridge.py`, tests.
- *C library:* no heap; a static capability table declared with macros (`BHMS_ACTION(move_to, BHMS_F32_RANGE(0,200), …)`); the operation-handle replay ring; HELLO with digest and boot epoch (the epoch kept in EEPROM through a platform hook); hooks for reading the stop pin.
- Reuse `protocol/serial/frame.c` for framing, and borrow from `protocol/endpoint` where it fits; the report says what was reused.
- *Gateway compact bridge:* turns an MCU into a BHMS device server, building its full description from a sidecar JSON keyed by the digest.
- *Tests:* native unit tests under ASan/UBSan; an end-to-end test that builds the Arduino example for ATmega328P, runs it in simavr (Docker on the AMD machine, or the simavr already used there), and has the gateway drive it over a pseudo-terminal.
- **Acceptance:** an Arduino sketch of about 20 lines exposes an LED action and an analog-read property; `bhms call` works against it through simavr; the flash and RAM sizes are reported.

### Task 10: SimLab, the simulated lab [parallel-safe after Task 6]
**Files:** `simlab/pyproject.toml`, `simlab/src/simlab/{world.py,ledger.py,faults.py,oracle.py,scene/*.xml}`, `simlab/src/simlab/twins/{arm.py,microscope.py,liquid_handler.py,plate_reader.py,thermal.py,centrifuge.py,balance.py}` (each a BHMS device server built with the Python SDK), `simlab/src/simlab/adapters/{modbus.py,opcua.py,scpi.py,home_assistant.py,mcp_client.py,micromanager.py}` (BHMS servers that bridge existing ecosystems), tests.
- *World:* a MuJoCo scene (bench, the SO-ARM100 from Menagerie until Task 13's arm model exists, microscope body with knob joints, plate, slide, cameras); a material ledger (containers, wells, volumes, solutes); a world clock; an effect log; a fault plane; and an oracle that turns the effect log and world state into verdicts on operation claims. The design is in `docs/superpowers/plans/2026-11-13-hms-full-validation-plan.md` §3 and §11.
- *Twins:* real physics and imaging models (focus-dependent blur over a specimen image; Beer-Lambert absorbance from ledger concentrations; first-order thermal model), with every effect recorded to the world.
- *Adapters:* prove universality. Wrap Modbus TCP, OPC UA, SCPI, Home Assistant (WebSocket API) and any MCP server (each MCP tool becomes a BHMS action with `completionEvidence: none` and `idempotency: relative` unless annotations say otherwise) as BHMS servers. Pin `pymodbus==3.8.6`.
- *Runs on the AMD machine:* the repo is synced to `~/hms-lab/repo` through a bare git remote, and the existing environments in `~/hms-lab/venvs` are reused where possible.
- **Acceptance:** every twin and adapter passes `bhms conformance` (not-applicable rows justified); a scripted multi-device run (the arm loads a slide, the microscope autofocuses, images are recorded) passes with oracle verdicts all consistent; fault injection produces honest `unknown` and refusal outcomes.

### Task 11: Agentic validation [after Task 10]
**Files:** `simlab/src/simlab/agents/{runner.py,scripted.py}`, `simlab/tasks/*.yaml` (the use cases UC1–UC7, UC10, UC11 and UC13 from the validation plan), `simlab/reports/`.
- Agents: scripted; OpenAI API (`gpt-5.4-mini` for the bulk tier, `gpt-6.1-sol` for the capable tier, `gpt-4.1-mini` as the deliberately weak tier); a local model on the AMD machine through llama.cpp's OpenAI-compatible server (Qwen3-4B-Instruct-2507, downloading to `~/hms-lab/models`).
- Every agent reaches SimLab through the gateway, natively or through the MCP bridge.
- *Metrics:* task success (oracle-judged); false certainty, duplicate effects, violations reaching a device, silent ambiguity, fabricated support (all five must be 0); tool calls; tokens; wall time.
- A hostile scripted agent supplies at least 100 violation attempts.
- The API spend is capped per run.
- **Acceptance:** a report with the metric table per agent and use case; all five zero-metrics hold; failures are analysed and turned into issues for the spec or SDK.

### Task 12: Benchmarks [after Task 9]
**Files:** `bench/{run.py,scenarios/*.py,README.md}`, `bench/results/<date>/*.json`, `docs/bhms/performance.md`.
- *Scenarios:*
  - Invoke round trip per transport (stdio, unix, tcp, websocket), with and without durability.
  - Throughput with 1/10/100 concurrent clients.
  - Gateway overhead and fan-out to 1,000 upstreams.
  - `devices/list` at 10,000 devices.
  - Subscription fan-out.
  - Compact binding over a pseudo-terminal into simavr.
  - Crash-recovery time.
  - Comparison: the same action via MCP (bridge) and via native BHMS.
- Report p50/p95/p99/max, samples and hardware.
- Runs on the AMD machine with CPU pinning and `nice`.
- **Acceptance:** results committed; every budget in Global Constraints shows pass or fail with the measured number.

### Task 13: Universal actuator hardware [parallel-safe; starts after Task 2]
**Files:** `hardware/actuator/{README.md,cad/*.py,cad/out/*.stl|.step,sim/bhms_arm.xml,pcb/*,firmware/*,bom/bom.csv,docs/*}`.
- *Design:* "BHMS Arm" — a 5-axis desktop arm plus a tool flange. Joints use serial bus servos (STS3215 class, 12 V, magnetic encoders, current feedback), the same class as SO-100/SO-101, for cost and availability. The quick-change tool flange carries power, a 2-wire bus and a tool-ID resistor. The end-effector library has a parallel gripper, a knob turner (a compliant collet with an output encoder), a button presser with a force-sensing tip, and a slider pusher.
- *Mechanical:* parametric CAD in build123d (or CadQuery) run on the AMD machine. Export STL for printing (PLA/PETG; parameters for printer tolerance) and STEP. Include a printed base clamp and cable routing.
- *Simulation model:* an MJCF generated from the same CAD parameters (masses and inertias from the CAD volumes), loaded by SimLab as the arm twin, so the designed arm is the simulated arm.
- *Controller PCB:*
  - RP2040.
  - USB-C.
  - 12 V input with reverse-polarity and TVS protection.
  - Half-duplex servo bus (74LVC1G125 class buffer).
  - A hardware E-stop loop that cuts servo power through a high-side switch, independent of firmware.
  - Current sensing.
  - 4 GPIO / 2 ADC tool connector.
  - Status LED.
- *PCB deliverables:* a KiCad 8 project generated programmatically (a Python script writes `.kicad_sch` and `.kicad_pcb` s-expressions with real footprints, placement and routing), a netlist, a design-rule check by script (clearances and widths for the chosen fab class), Gerber and drill files if a generator is available offline, and a BOM with manufacturer part numbers. If KiCad cannot be installed within the network limits, the report states which steps were verified by script and which need KiCad.
- *Firmware:* RP2040 C (pico-sdk if it can be obtained; otherwise portable C with a hardware-abstraction layer tested natively). It speaks BHMS-Compact over USB CDC, exposes joints as actions with limits, the tool as a sub-device, and the E-stop state as a measured property.
- **Acceptance:** CAD exports exist and are watertight (checked with trimesh); SimLab loads the MJCF and runs a pick-and-place; the PCB rule check passes; firmware native tests pass; the BOM is costed; the docs include assembly steps.

### Task 14: Documentation and examples [after Task 9]
**Files:** `docs/bhms/{index.md,quickstart.md,concepts.md,guides/*.md,reference/*.md}`, `examples/bhms/*`, root `README.md` section.
- Quickstart: install, write a server, inspect it, connect Claude/any MCP client through the bridge, connect an OpenAI agent, put a gateway in front. Each step is copy-paste runnable and executed in a test (`tests/test_docs_examples.py`).
- Guides: wrapping a real instrument (SCPI, Modbus, OPC UA); Arduino; writing programs; leases and safety; deploying a gateway; designing descriptions agents understand.

### Task 15: Learnings into the spec (v0.2) [after Tasks 11 and 12]
- Harvest the "spec learnings" sections of every task report, the benchmark results and the agentic report.
- Amend `spec/bhms/*` and the schema, record each change with its evidence in `spec/bhms/CHANGELOG.md`, bump the version, update the SDKs and re-run conformance in both languages.

### Task 16: Final verification
- Full test suites (Python, TypeScript, C, SimLab), conformance in all SDKs, benchmarks re-run, docs examples run, and a final validation report at `docs/bhms/validation-report.md` stating exactly what passed, at which evidence tier, and what is still unverified (above all, nothing physical has run).

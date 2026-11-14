# 12. Agent surface

Models reach BHMS through a bridge: the **MCP bridge** (an MCP server whose tools
call a BHMS server) and the **function-tool adapter** (the same tools as
OpenAI-style function definitions). Both expose exactly the eight tools below.
Their input schemas are normative and live in the schema's `x-bhms-agent-tools`
map; tool inputs use snake_case, and structured results are BHMS wire objects
(camelCase) that validate against the same schema as the protocol.

## 12.1 Tools

| Tool | Purpose | Input | Structured result | MCP annotations |
|---|---|---|---|---|
| `bhms_find` | Find devices, and saved programs when the server has a registry; with no arguments it lists every device | `{text?, capability?, tag?, status?, cursor?}` | `{devices: DeviceSummary[], programs?: ProgramInfo[], nextCursor?, totalDevices?}` | readOnly, idempotent |
| `bhms_describe` | Describe one device precisely | `{device_id}` | `{description: DeviceDescription}` | readOnly, idempotent |
| `bhms_read` | Read a property | `{device_id, property, max_age_ms?, fresh?}` | `{observation}` | readOnly (see below) |
| `bhms_invoke` | Invoke an action and wait briefly for the outcome | `{device_id, action, arguments, operation_key?, wait_ms?, require_verified?}` | `{operation, replayed}` | destructive, not idempotent |
| `bhms_operation` | Get or wait for an operation | `{operation_id, wait_ms?}` | `{operation}` | readOnly, idempotent |
| `bhms_cancel` | Ask an operation to stop | `{operation_id, reason?}` | `{operation}` | destructive, idempotent |
| `bhms_stop` | Stop devices now | `{device_ids? \| all?, reason}` | `{stops}` | destructive, idempotent |
| `bhms_run_program` | Run a bounded program inline or by digest | `{program? \| program_digest?, arguments, operation_key?, wait_ms?}` | `{operation, replayed}` | destructive, not idempotent |

`bhms_read` is read-only for `readEffect: "none"` properties; a fresh read of a
`transaction` property is an effect and is authorized as one (BHMS-AUTH-012).

**BHMS-AGT-001** A bridge MUST expose at most these eight tools, with exactly these
names and the input schemas of `x-bhms-agent-tools`. `bhms_run_program` MUST be
omitted when the server does not advertise `programs`; programs in `bhms_find`
results MUST be omitted when it does not advertise `programs.registry`.

**BHMS-AGT-015** When a `bhms_find` filter matches no device, the bridge MUST NOT
leave the model to conclude that there are no devices: the structured result MUST
carry `totalDevices` (the number of devices an unfiltered `bhms_find` lists; its
first page when there are more) and the summary MUST state that number and that
`bhms_find` with no arguments lists everything. `text` follows BHMS-DEV-013 (any
word, ids included); devices that match more words come first; a program matches
when any word occurs in its name or description.

**BHMS-AGT-002** A bridge MUST pass every tool call to BHMS methods with the
bridge's own principal and MUST NOT accept identity, scopes, leases or bounds from
tool arguments. A model can only *narrow* what it asks for (for example
`require_verified`).

## 12.2 Results

Every tool result has two parts:

1. **A one-line summary** (text content, ≤ 200 characters, no newline) for people
   and models: subject, outcome, key values with units, and the next step when one
   is needed.
2. **Structured content**: the BHMS result object, unchanged.

Examples:

```
pump-1.dispense op-7f3a completed: 50 uL dispensed (effect verified, 2.1 s)
pump-1.pressure = 101.3 kPa (measured, valid, 120 ms old)
arm-1.move_to op-19c2 running after 5 s; call bhms_operation(operation_id="op-19c2", wait_ms=30000)
stop: arm-1 confirmed, pump-1 initiated (2 operations canceled)
```

`bhms_describe` adds, after the summary line, a compact signature block of at most
400 tokens:

```
pump-1 "Syringe pump" [bhms.liquid.dispense] online
action dispense(volume: number uL 1..1000, rate?: number uL/min 1..500) effect=irreversible repeat=relative lease=required cancel=yes evidence=measured max=60s
property dispensed_volume: number uL measured observable
stop: supported (reported); on disconnect: stop
```

**BHMS-AGT-010** Every tool result MUST begin with a one-line summary of at most 200
characters and MUST carry the BHMS result as structured content (MCP
`structuredContent`; for function tools, a JSON object `{summary, data}`, which for
`bhms_describe` also carries the signature block as `signature`, because a function
result's summary is one line).

**BHMS-AGT-011** A summary MUST state units for every quantity, the operation's
`state` and `effect` for operation results, and `quality`, `evidence` and age for
observations. When the result has `replayed: true` the summary MUST contain the
word "replayed" (for example `… op-7f3a replayed: completed …`), so a model knows
it did not act again. It MUST NOT say "done", "success" or "stopped" for an operation
that is not `completed` or a stop that is not `confirmed`.

**BHMS-AGT-012** Device-provided text (names, descriptions, messages) MUST appear in
summaries only quoted and truncated to 60 characters, and MUST NOT be presented
as instructions (BHMS-SEC-020).

**BHMS-AGT-013** `bhms_describe`'s signature block MUST list every action with its
argument names, types, units, bounds, `effect`, `idempotency`, `requiresLease`,
`cancel`, `completionEvidence` and `maxDurationMs`, and every property with type,
unit and evidence, within 400 tokens; when a device is too large, it MUST list all
names and say which details were elided.

**BHMS-AGT-014** `bhms_read` without `max_age_ms` and `fresh` SHOULD NOT hand a model a
retained observation older than 1000 ms as if it were the current state: for a
property with `readEffect: "none"` the bridge asks for `maxAgeMs: 1000` (a narrowing
of what the model asked for) and, when the server cannot acquire the property on
demand (`STALE` naming `maxAgeMs`), returns the retained observation, whose summary
states its age. A read of a `transaction` property is never made fresh by default
(BHMS-AUTH-012).

## 12.3 Refusals

A refusal is a tool result with MCP `isError: true` (function tools:
`{summary, error}`), whose summary reads `Refused: <message>. Next: <hint>` and
whose structured content is `{error: OperationError}`.

**BHMS-AGT-020** Every BHMS error MUST be turned into a refusal carrying
`bhmsCode`, `message`, `field`, `bound`, `mayHaveActed`, `retry` and `hint`
unchanged, and the summary MUST include the hint. A bridge MUST NOT turn an
`unknown` operation or a `mayHaveActed: true` error into a plain failure: the
summary MUST say "outcome unknown — check before retrying".

**BHMS-AGT-021** Arguments that fail the tool's input schema or the action's
`input` MUST be refused before any BHMS request that could act, with the field,
the bound and a corrected example in the hint.

## 12.4 Operation keys and safe retry

**BHMS-AGT-030** `operation_key` is optional. When absent, the bridge MUST NOT
invent one; the server generates one (`keyOrigin: "server"`) and the summary MUST
append "(not retry-safe: no operation_key)".

**BHMS-AGT-031** Tool descriptions MUST tell the model how to retry safely: after a
timeout or a lost result, call `bhms_operation` with the `operation_id` if known;
otherwise call `bhms_invoke` again with the **same** `operation_key` and
**identical** arguments, which returns the original operation instead of acting
again (`replayed: true`).

**BHMS-AGT-032** `wait_ms` defaults to 5000 and MUST be capped at 60000 and at the
server's `limits.maxWaitMs`. A result returned before the operation settles MUST
say how to keep waiting.

## 12.5 Leases for agents

**BHMS-AGT-040** For an action or program that requires a lease, the bridge MUST
acquire a lease on exactly the needed resources (waitMs 0), renew it while the
operation is not settled, and release it when the operation settles. A
`LEASE_CONFLICT` MUST become a refusal whose hint says the resource is in use and
when the blocking lease expires.

**BHMS-AGT-041** When the model supplies `operation_key`, the bridge MUST first
send `actions/invoke` (or `programs/run`) **without** `leaseId`. Because the key
lookup precedes the lease check (BHMS-OPS-033), a retry of an existing operation
returns it (`replayed: true`) even while the bridge's own lease for the original
call is still held — acquiring first would hit `LEASE_CONFLICT` (BHMS-LSE-002).
Only on `LEASE_REQUIRED` does the bridge acquire the lease (BHMS-AGT-040) and
resend the identical request with the same key and the `leaseId`.

## 12.6 Function-tool adapters

**BHMS-AGT-050** A function-tool adapter MUST emit the same names, descriptions
and input schemas as the MCP bridge. Because `arguments` and `program` are
free-form objects, adapters MUST NOT declare these tools in a strict mode that
forbids additional properties inside them.

**BHMS-AGT-051** The published input schema of a tool is the `x-bhms-agent-tools`
schema made self-contained: `$ref`s are inlined (a definition used more than once or
a recursive one stays once under `$defs`) and a top-level `oneOf` is removed, because
function-calling and several model APIs reject it. The bridge states the exactly-one
rule in the tool description (`bhms_stop`: `device_ids` or `all`; `bhms_run_program`:
`program` or `program_digest`) and enforces it itself, refusing a call that gives
none or both before any request (BHMS-AGT-021). Both bridges publish the identical
flattened schema.

A bridge MAY publish a large free-form member (`program`) as `{"type": "object"}` with a pointer to its
grammar, provided the grammar is available on demand (the MCP resource `bhms://grammar/program`, and in every
refusal of a malformed program) and the bridge validates the member itself against the normative schema, refusing
before any request with the failing path (`program.steps[1].arguments`). The reference bridge's eight definitions
total 1,344 tokens (o200k_base) with the program grammar on demand, against 2,760 inlined.

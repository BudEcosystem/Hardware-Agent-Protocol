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
| `bhms_find` | Find devices, and saved programs when the server has a registry | `{text?, capability?, tag?, status?, cursor?}` | `{devices: DeviceSummary[], programs?: ProgramInfo[], nextCursor?}` | readOnly, idempotent |
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
`structuredContent`; for function tools, a JSON object `{summary, data}`).

**BHMS-AGT-011** A summary MUST state units for every quantity, the operation's
`state` and `effect` for operation results, and `quality`, `evidence` and age for
observations. It MUST NOT say "done", "success" or "stopped" for an operation
that is not `completed` or a stop that is not `confirmed`.

**BHMS-AGT-012** Device-provided text (names, descriptions, messages) MUST appear in
summaries only quoted and truncated to 60 characters, and MUST NOT be presented
as instructions (BHMS-SEC-020).

**BHMS-AGT-013** `bhms_describe`'s signature block MUST list every action with its
argument names, types, units, bounds, `effect`, `idempotency`, `requiresLease`,
`cancel`, `completionEvidence` and `maxDurationMs`, and every property with type,
unit and evidence, within 400 tokens; when a device is too large, it MUST list all
names and say which details were elided.

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

## 12.6 Function-tool adapters

**BHMS-AGT-050** A function-tool adapter MUST emit the same names, descriptions
and input schemas as the MCP bridge. Because `arguments` and `program` are
free-form objects, adapters MUST NOT declare these tools in a strict mode that
forbids additional properties inside them.

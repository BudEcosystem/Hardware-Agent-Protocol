# 8. Programs

A **program** is a bounded, validated sequence of steps over device actions and
properties. It is plain JSON, has no unbounded loops and no arbitrary code, and
is validated in full — structure, references, authority, envelopes, resources and
worst-case duration — before its first step runs. One operation represents the
run; each action step is its own child operation.

Programs are the vehicle for **programs as tools**: a validated program is
content-addressed by its digest, can be registered once, and is then invoked by
digest with new arguments. Its `name`, `description` and `input` schema are
exactly what a model needs to use it as a tool.

## 8.1 Capability

`capabilities.programs = {registry: bool, limits: ProgramLimits}` enables
`programs/run`. With `registry: true` the server also implements
`programs/register`, `programs/get` and `programs/list`.

*Why registration is a capability, not core:* running an inline program needs no
storage beyond the operation journal every server already has. A registry needs
a durable, content-addressed catalog and a listing surface, which belongs on
gateways and larger servers, not on every device server. Inline runs and
digest-based runs have identical semantics, so nothing a client can express
depends on the registry.

`ProgramLimits` (servers MAY advertise lower values, never higher):

| Limit | Value | Meaning |
|---|---|---|
| `maxSteps` | 256 | Step objects in the program after flattening nested bodies: every step object, including `repeat` containers, counted once |
| `maxRepeat` | 1000 | Upper bound of any `repeat.times` |
| `maxDepth` | 4 | Nesting depth of `repeat` |
| `maxExecutedSteps` | 4096 | Worst-case number of step executions with every repeat multiplied out (repeat containers themselves are not counted) |
| `maxVariables` | 64 | Inputs, `saveAs` names and repeat indices together |
| `maxProgramBytes` | 65536 | Canonical JSON size of the program |
| `maxDurationMs` | server-defined, ≤ 86 400 000 | Largest declared `maxDurationMs` accepted |

## 8.2 Program format

```json
{
  "bhmsProgram": "2026-11-13",
  "name": "focus_scan",
  "description": "Step the focus axis and record sharpness at each position.",
  "input": {
    "type": "object", "additionalProperties": false,
    "required": ["start", "steps"],
    "properties": {
      "start": {"type": "number", "x-bhms-unit": "um", "minimum": 0, "maximum": 5000},
      "steps": {"type": "integer", "x-bhms-unit": "1", "minimum": 1, "maximum": 50}
    }
  },
  "maxDurationMs": 120000,
  "steps": [
    {"kind": "invoke", "deviceId": "focus-1", "action": "move_to",
     "arguments": {"position": "${start}"}},
    {"kind": "repeat", "times": "${steps}", "as": "i", "steps": [
      {"kind": "invoke", "deviceId": "focus-1", "action": "move_by",
       "arguments": {"distance": 10}},
      {"kind": "read", "deviceId": "camera-1", "property": "sharpness",
       "fresh": true, "saveAs": "s"},
      {"kind": "assert", "predicate": {"op": "ne", "left": "${s.quality}", "right": "invalid"},
       "message": "sharpness unavailable"}
    ]}
  ],
  "output": {"lastSharpness": "${s.value}"}
}
```

| Member | Type | Required | Meaning |
|---|---|---|---|
| `bhmsProgram` | string | yes | Protocol version the program is written for |
| `name` | `^[a-z][a-z0-9_]{0,63}$` | yes | Tool-friendly name |
| `description` | string ≤ 1000 | yes | Untrusted text |
| `input` | JSON Schema (closed object) | yes | Schema of `arguments` |
| `maxDurationMs` | integer ≥ 1 | yes | Declared worst-case duration; enforced |
| `steps` | `Step[]` (1–256) | yes | |
| `output` | `{name: Value}` | no | The run's `result` |

Step kinds:

| `kind` | Members | Worst-case duration |
|---|---|---|
| `invoke` | `deviceId`, `action`, `arguments`, `saveAs?` | action `maxDurationMs` |
| `read` | `deviceId`, `property`, `maxAgeMs?`, `fresh?`, `timeoutMs?` (default 1000, ≤ 60000), `saveAs` | `timeoutMs` |
| `waitUntil` | `deviceId`, `property`, `predicate`, `timeoutMs` (≤ 3 600 000), `pollMs?` (≥ 10), `saveAs?` | `timeoutMs` |
| `assert` | `predicate`, `message` | 0 |
| `sleep` | `durationMs` (1–3 600 000) | `durationMs` |
| `repeat` | `times` (1–1000 or `"${input}"`), `as?`, `steps` | `times` × body |

Every step MAY carry `id` (`^[a-z][a-z0-9_]{0,63}$`, unique) for diagnostics.

**Values and references.** Inside `arguments`, predicate operands, `output` and
`repeat.times`, a string that is exactly `${path}` is a reference and is replaced
by the referenced value (type preserved). `path` is a variable name followed by
`.member` or `[index]` selectors. There is no string interpolation; a literal
string that starts with `${` is written with a leading `$` doubled (`"$${x}"`).
Variables are: program inputs, `saveAs` names (an `invoke` saves the action
`result`; a `read` or `waitUntil` saves the `Observation`), repeat indices (`as`,
0-based integers) and, inside a `waitUntil` predicate only, `observed` (the
latest observation).

**Scope.** Inputs and `saveAs` names share one program-wide namespace. A
`saveAs` inside a `repeat` body is one definition that is reassigned on every
iteration: later steps of the same iteration see this iteration's value, and
after the `repeat` the variable holds the value from the last iteration (a
`repeat` always runs at least once, BHMS-PRG-003). A `saveAs` is visible only to
steps after it in document order (including steps after its enclosing
`repeat`), never to earlier steps of the next iteration before it is reassigned.
A repeat index (`as`) is visible only inside its own body. `observed` is visible
only inside its `waitUntil` predicate.

`deviceId`, `action` and `property` are always literals, so devices, resources
and durations are known before the run.

**Predicates.** `{op, left, right}` with `op` ∈ `eq`, `ne`, `lt`, `le`, `gt`, `ge`;
`{op: "within", left, right, tolerance}` (|left − right| ≤ tolerance);
`{all: [P…]}`, `{any: [P…]}` (1–16 members); `{not: P}`. Nesting depth ≤ 4.
`eq`/`ne` compare canonical JSON; the ordering operators and `within` require
numbers.

## 8.3 Validation

**BHMS-PRG-001** A server MUST validate the whole program and its arguments before
starting any step, and MUST refuse an invalid program with a JSON-RPC error
(`INVALID_ARGUMENT` or `OUT_OF_RANGE`, `field` as a path into the program such as
`program.steps[1].steps[0].arguments.distance`) without creating an operation.

**BHMS-PRG-002** Validation MUST reject: unknown step kinds or members; unknown
devices, actions or properties; references to undefined variables or variables
defined later; a variable name defined twice (including shadowing an input);
predicates nested deeper than 4; and any limit of §8.1 exceeded.

**BHMS-PRG-003** A `repeat.times` reference MUST name a required integer input
whose schema `minimum` is at least 1 and `maximum` at most `maxRepeat`;
validation MUST use that maximum for worst-case calculations. (An input that
allows 0 is refused, so every `repeat` body runs at least once and variables
saved inside it are always defined after it.)

**BHMS-PRG-004** The server MUST compute the worst-case duration as the sum, over
the flattened steps with repeats multiplied out, of the per-kind durations in
§8.2, and MUST refuse the program with `OUT_OF_RANGE`
(`field: "program.maxDurationMs"`, `bound` the computed value) when it exceeds the
declared `maxDurationMs`, or when the declared value exceeds
`limits.maxDurationMs`.

**BHMS-PRG-005** For every literal argument the server MUST check the action
`input` and the caller's effective envelope at validation time. For every argument
that is exactly a reference to a program input, the input's bounds MUST lie
inside the action's effective envelope for that argument; otherwise validation
MUST fail with `OUT_OF_RANGE`. Arguments built from saved results MUST be checked
when the step is admitted.

**BHMS-PRG-006** Before the first step, the server MUST verify that the caller has
`programs:run` and an `invoke` scope for every `invoke` step and every fresh
`transaction` read, and that `leaseId` (when any step's action requires a lease)
is an active lease of the caller covering the union of those steps' resources.

**BHMS-PRG-007** The program `digest` MUST be the BHMS digest of the program
object. Two programs are the same program exactly when their digests are equal.

## 8.4 Execution

**BHMS-PRG-010** Steps MUST execute strictly in order, one at a time. Each
`invoke` step MUST create a child operation with `parentOperationId` set,
`keyOrigin: "derived"` and `operationKey` = `"d-"` followed by the first 40 hex
digits of sha256(`parentOperationId + "/" + executionPath`), where
`executionPath` lists step indices and repeat iterations (`"1/3/0"`).

**BHMS-PRG-011** When a step fails, the program MUST start no further step. The
program operation ends `failed` with the step's error (`mayHaveActed: true` if any
effectful step was dispatched), or `unknown` if the failing step is `unknown`.
Completed effects are never rolled back; compensation is a new program.

**BHMS-PRG-012** A server MUST enforce the declared `maxDurationMs` at run time:
when it elapses, no further step starts, a running step is cancelled where
supported, and the program ends `failed` with `DEADLINE_EXCEEDED` (or `unknown`).

**BHMS-PRG-013** A `waitUntil` step MUST evaluate its predicate only on
observations with `quality: "valid"`, and MUST fail the program with
`DEADLINE_EXCEEDED` (`mayHaveActed` per earlier steps) when `timeoutMs` elapses.
An `assert` whose predicate is false MUST fail the program with `STALE` and the
assert's `message` as `hint`.

**BHMS-PRG-014** `operations/cancel` on a program operation MUST stop further
steps and forward the cancellation to the running child. `stop` of a device used
by a running program MUST stop the program in the same way.

**BHMS-PRG-015** The program operation's `history` MUST contain a `step` entry for
every started step (with `stepIndex` and, for `invoke`, `childOperationId`), and
`progress` MUST report steps completed and the worst-case total.

**BHMS-PRG-016** The program operation's `effect` MUST be `none` if no effectful
child was dispatched, `unknown` if any child is `unknown`, `verified` if every
effectful child is `verified`, and `unverified` otherwise. Its `result` is the
evaluated `output` (or `{}`).

**BHMS-PRG-017** A server MUST NOT resume a program after a restart. On restart,
after children have been handled per BHMS-OPS-080, each program operation that
was not settled MUST be settled from its step history:

- if no step had started (`accepted`), the program becomes `rejected` with
  `INTERNAL` and `mayHaveActed: false`;
- if a child is `unknown`, the program becomes `unknown` (error per
  BHMS-OPS-004);
- otherwise (a crash between steps, or the current child is terminal) the program
  ends `failed` with `INTERNAL`, message "server restarted during the program",
  `mayHaveActed: true` if any effectful child was dispatched, and a hint naming
  the last completed step (`stepIndex`). It never ends `completed` after a
  restart, because saved variables and `output` are not durable in v0.1.

When the `unknown` children of an `unknown` program are all reconciled, the
server MUST settle the program the same way (a `reconciliation` entry, then
`failed` with `INTERNAL`). A program therefore never stays `unknown` longer than
its unknown children.

## 8.5 Methods

- `programs/run {program | digest, arguments, operationKey?, leaseId?, deadlineMs?, waitMs?}`
  → `{operation, replayed}`. Exactly one of `program` and `digest`.
- `programs/register {program}` → `{info: ProgramInfo}`; validates exactly as
  `programs/run` would (using the caller's authority for envelopes) and stores
  the program. Registering an already registered digest returns the same info.
- `programs/get {digest}` → `{program, info}`.
- `programs/list {cursor?, limit?}` → `{programs: ProgramInfo[], nextCursor?}`.

`ProgramInfo = {digest, name, description, input, effect, worstCaseDurationMs,
maxDurationMs, stepCount, maxExecutedSteps, devices, resources, requiresLease}`,
`effect` being the most severe action effect class among its steps.

**BHMS-PRG-020** A `digest` that is not registered MUST be refused with
`INVALID_ARGUMENT`, `field: "digest"`. Registered programs MUST be immutable.

**BHMS-PRG-021** Registration MUST NOT grant authority: running a registered
program re-checks the runner's scopes, envelope and lease (BHMS-PRG-005,
BHMS-PRG-006) at each run.

**BHMS-PRG-022** Idempotency for `programs/run` follows §6.4 with the intent
`{method, digest, arguments, deadlineMs?}`; an inline program and its registered
digest with the same arguments are the same intent.

# Running conformance and claiming profiles

This guide shows how to run the BHMS conformance suite (`bhms conformance`) against your own server, a gateway, an
agent bridge, a microcontroller endpoint or another SDK, how to read the report, and what it takes to claim a profile.
The rules are in [spec 14](../../../spec/bhms/14-conformance.md). The quick blocks below are executed by the docs test;
the full claims take one to two minutes each and run in the slow test (`python3 -m pytest -m slow`).

## Claims and reports

A **claim** names the protocol version (`2026-11-15`; a run tests the newest version the target and the runner share,
or the one given with `--protocol-version`, and marks requirements added after it not applicable, BHMS-CNF-007) and the
profiles it covers: `core` (every server), `leases`,
`events`, `programs`, `registry`, `authority`, `gateway`, `compact`, `ws`, `http`, `agent`. The runner always checks the
profiles the server advertises in addition to the ones you ask for with `--profile`.

Every requirement of a claimed profile gets one status: `passed`, `failed`, `skipped` or `not-applicable` (with a
reason). A profile is supported only when every row passed or is not applicable: **a skipped row is not a pass**. The
checks that prove "no effect" and "exactly one effect" need the **conformance device**, a fixture that counts every
physical command it receives and declares itself with the `org.bhms/conformance` extension. Against other devices the
runner produces a **generic report**, which never supports a claim.

| Exit status | Meaning |
|---|---|
| 0 | no MUST requirement failed, and nothing a check could have proven was skipped |
| 1 | a MUST requirement failed |
| 2 | the target could not be reached (the message ends with what the server wrote to stderr) |
| 3 | nothing failed, but MUST rows were left unproven: the claim is not supported (`--allow-unproven` exits 0 anyway) |

`--coverage` prints, for every requirement of the index, which checks cover it or why none does (for example
`inspection` rows that need review evidence):

```sh run
bhms conformance --coverage --profile leases
```

```text output
ID LEVEL PROFILE METHOD STATUS CHECKS / REASON
BHMS-LSE-014 MUST leases wire covered leases.held-lease-blocks-everyone
covered: 9
```

## Your own server: the generic report

Point the runner at your server (a script, a URL or a gateway TOML). The generic checks use only your descriptions:
digest stability, refusals of bad arguments that cannot execute, unknown members and actions, framing. Checks that would
execute actions are skipped unless you say the devices may move (`--allow-effects`; for physical devices also
`--physical --physical-ok`):

```sh run exit=3
bhms conformance examples/bhms/pump_server.py
```

```text output
requirements: ... passed, 0 failed, ... skipped, ... not-applicable MUST failures: 0
generic report: the target does not host the conformance device ...
claim core: NOT supported (0 MUST failed, ... MUST unproven); 19 MUST rows need review evidence
```

`0 MUST failed` is what a generic report can tell you: nothing your server answered contradicts the protocol. It is not
a claim. Use it in CI for every device server you write.

## Claims against the conformance device

Claims are made against an implementation hosting the conformance device. The runner has built-in fixtures that start
it (and gateways, bridges and endpoints around it) in a temporary workspace and can kill and restart them for the fault
checks:

| Target | Profiles it can support | Typical time |
|---|---|---|
| `conformance-device` (also `:unix`, `:ws`) | core, leases, events, programs, registry (and ws) | 30 s |
| `conformance-device:principals` | the same plus authority, over WebSocket with several principals | 1 min |
| `gateway` (also `:stdio`, `:http`) | core, leases, events, authority, gateway (and ws or http) | 2 min |
| `compact-gateway` | compact, with `--profile compact` (builds `sdk/c` with cmake) | 15 s |
| `agent-bridge`, `mcp:<bridge command>` | agent | 5 s |

The agent profile, for the reference MCP bridge:

```sh run timeout=300
bhms conformance agent-bridge --json agent-report.json
```

```text output
requirements: 22 passed, 0 failed, 1 skipped, 0 not-applicable MUST failures: 0
claim agent: supported
```

The JSON report (`--json FILE`, or `--json -` for stdout) has the claim per profile, every requirement with its status,
the schema digest, the seed and the exact command, so a claim can be reproduced:

```python run
import json

report = json.load(open("agent-report.json"))
meta = report["conformance"]
print(meta["protocolVersion"], meta["reportKind"], meta["devices"], meta["command"])
print({profile: claim["claimable"] for profile, claim in report["claims"].items()})
print(report["exitCode"])
```

```text output
2026-11-15 conformance simulated bhms conformance agent-bridge --json agent-report.json
{'agent': True}
0
```

The full device and gateway claims (slow test):

```sh run slow timeout=600
bhms conformance conformance-device
```

```text output
claim core: supported; 17 MUST rows need review evidence
claim leases: supported
claim events: supported
claim programs: supported
claim registry: supported
```

```sh run slow timeout=600
bhms conformance conformance-device:principals
bhms conformance gateway
```

```text output
claim authority: supported
claim ws: supported
claim gateway: supported
```

"17 MUST rows need review evidence" are `inspection` requirements (documentation, configuration, code review): no test
run can pass them, and a claim must attach the review.

## The compact profile

The `compact-gateway` fixture builds the C library's host endpoints and runs a real gateway bridge against them over
fault-injecting serial lines:

```sh run requires=cmake timeout=600
bhms conformance compact-gateway --profile compact
```

```text output
requirements: ... passed, 0 failed, 5 skipped, ... not-applicable MUST failures: 0
claim compact: supported; 4 MUST rows need review evidence
```

The fixture's endpoints are the reference C endpoints the runner builds and drives itself, so the run is a declared
conformance run and the compact profile is claimable from it (v0.2). The rows that need review evidence are
`inspection` rows: BHMS-SEC-050 (an exclusive link is a deployment fact) and three v0.2 gateway rules the reference
endpoints cannot provoke (BHMS-CMP-036, 052, 053; the Python SDK's tests show them).

## Another SDK: `--device-command`

To test an SDK in another language, implement the conformance device in it (the Python one is
`sdk/python/src/bhms/testing/conformance_device.py`, the TypeScript one `sdk/typescript/src/testing/conformanceDevice.ts`)
and let the runner start it with `--device-command`. The command must accept `[URL] [--state-dir DIR] [--memory]
[--principals FILE]` (and `--gateway`): no URL means stdio. Paths in the command are relative to where you run
`bhms conformance`. The TypeScript SDK's claims (slow test):

```sh run slow requires=node timeout=900
bhms conformance conformance-device --device-command "node sdk/typescript/dist/src/testing/conformanceDevice.js"
bhms conformance conformance-device:principals --device-command "node sdk/typescript/dist/src/testing/conformanceDevice.js"
```

```text output
claim core: supported; 17 MUST rows need review evidence
claim authority: supported
```

## Other options

| Option | Use |
|---|---|
| `--profile/-p P` | add a profile to the claim (repeatable) |
| `--only NAME` | run only checks whose name contains `NAME` (repeatable); the claim is then unproven |
| `--strict` | validate every message against the JSON Schema |
| `--allow-effects` | let generic checks execute actions on devices that are not the conformance device |
| `--physical`, `--physical-ok` | state that devices are physical; allow checks that move or change them |
| `--conformance-device ID` | behind a gateway: assert that a device is a conformance device (repeatable) |
| `--upstream NS=TARGET` | behind a gateway: reach the conformance device directly to inject faults |
| `--device TARGET` | agent profile: the BHMS target the bridge fronts (fault injection, counters) |
| `--function-tools FILE` | agent profile: the OpenAI function-tool definitions of your adapter |
| `--seed`, `--commit`, `--keep-state DIR` | reproduce a run; record the commit; keep the fixtures' state |

All options are in the [CLI reference](../reference/cli.md#bhms-conformance). A passing run against simulated devices
says nothing about physical behaviour (how fast a stop really stops, whether `measured` evidence is real): the report
says `devices: simulated`, and a physical claim needs runs on the hardware.

# Durable compact endpoint host binding

The local Runtime now dispatches its home fan, microscope focus and inspection
scenarios through the original native C compact endpoint. Admission, replay
keys, claims and recovery remain in `authority.db`. The nine checked host tools,
`hctl`, and their existing authentication boundary remain the entry points.
This binding is explicitly synthetic. It opens no serial device or physical
port and grants no physical verification.

The implementation is [endpoint_binding.py](../hms/endpoint_binding.py), with a
[bounded local stream](../hms/endpoint_transport.py) and the existing
[packet validator](../hms/endpoint_wire.py). The separately installed
[scenario manifest](../protocol/endpoint/scenario-manifest.json) pins three
primitive IDs, argument/result encodings, resource positions and the synthetic
firmware label. Exact executable hashes are in the
[scenario build receipt](../artifacts/verification/endpoint-scenarios.json);
the firmware label itself is not executable attestation.

The [multi-adapter installation profile](multi-adapter-runtime.md) permits several independently identified compact endpoints alongside SQLite plants. The names and fixed manifest below describe the legacy installation; new installations derive exact per-endpoint manifests and retain route-scoped state under the shared authority.

## Installed scenario envelope

| Host capability | Endpoint primitive | Installed arguments | Completed result |
|---|---|---|---|
| `sim:home-fan.set_level` | `0x1001` | Integer 0–100, unit `percent` | Synthetic committed level |
| `sim:microscope.move_absolute` | `0x1002` | Integer 0–100, unit `um`, frame `sim:microscope` | Synthetic committed position |
| `sim:inspection-cell.inspect` | `0x1003` | Recipe 1 or 2; nonempty part ID up to 16 Unicode characters and 64 UTF-8 bytes | Synthetic inspection counter |

These are narrower binding envelopes on the existing type descriptions. A
completed result contains the endpoint's original acquisition tick and value;
the inspection counter is not evidence of measured part identity. The fixture
commits after 100 ms and establishes quiescence in a separate poll. Neither
timing is a physical service guarantee. Other installed primitives need their
own description, codecs, limits and evidence interpretation.

## Durable handoff and recovery

`Journal.claim_dispatch` invokes the installed reservation inside its own SQLite
transaction. The reservation stores the exact OP payload and framed bytes,
full host intent and digest, dispatch attempt, owner epoch, admission, claims,
context and clock witness. It also allocates the endpoint call and local fences.
Only after commit can transport write bytes. A failure before transaction commit
rolls back the mapping and dispatch ownership together.

Host fences retain their full interoperable integer range. Local 32-bit fences
are independently allocated and explicitly mapped to them; they are never
truncated. One durable endpoint slot serializes all three instance bindings,
including operations whose host resource sets are disjoint. Pending host work
still expires without dispatch at its start cutoff.

Every transmit sequence is reserved before handoff and every accepted inbound
frame sequence is retained before semantic consumption. A lost reply or owner
restart never resends OP. Recovery queries the exact retained reference. A
refusal, `NOT_SEEN`, or a forgotten record does not prove that a possibly sent
command had no effect. Missing mappings, changed identity or boot, conflicting
receipts and unexpected counter movement inhibit new execution.

Receipt revision, terminal result, start evidence, cancellation progression and
remaining claims are checked against earlier receipts. The endpoint's own
`OUTCOME_UNKNOWN` cannot return to ordinary running or completion; the host's
transport uncertainty can resolve to a valid retained endpoint receipt. These
are distinct state histories.

The receipt, host execution transition, result and proven claim release commit
together. A queued receipt preserves `dispatching`, or `outcome_unknown` after
owner recovery; it does not invent a running event. Positive no-start evidence can produce
`rejected_before_start`, or canceled execution with `mayHaveActed=false`.
Historical running evidence prevents a later exclusion from erasing that fact.
Disputed verification is persistent and prevents remaining claims from being
released or the record from being retired.

RETIRE requires retained terminal, undisputed evidence with zero endpoint and
host claims. Its intent is recorded before transmission. If its reply is lost,
QUERY resolves the retained intent; `OLD_OR_FORGOTTEN` is accepted only with the
already retained terminal/quiescence proof and retirement intent. A lost BIND
reply similarly resolves by HELLO matching the exact desired context. No new
BIND is inferred from reconnecting. ARM intent is retained and resolved by its
reply or a fresh HELLO before any OP admission.

## Clock and observation meaning

This installation asserts that the original native fixture and host use the
same `CLOCK_MONOTONIC` rate. HELLO is bracketed independently in host monotonic
and deadline clocks. The whole scheduling/transport bracket is uncertainty;
the host does not pretend the clock reads were simultaneous. Intersections of
successive retained offset intervals detect an incompatible rate or jump.
Witnesses expire, belong to one owner epoch and boot, and are retained in each
mapping. They are not rederived for an already reserved OP.

If endpoint tick minus host deadline clock lies in `[lo, hi]`, the binding maps
not-before using `hi` and exclusive start/completion/lease cutoffs using `lo`.
It rejects collapsed windows, overflow, unsupported horizons and unqualified
clock state. The native fixture's rate assertion and a stable host deadline
clock are explicit installation assumptions, not a qualification for a remote
oscillator, NTP, MCU timer or physical deadline. The supported public sample
ticks also remain within the exact JSON integer range.

Before a completed sample exists, `value` is missing. Completed samples can be
rehydrated after a host crash, including a crash between receipt persistence
and observation publication, but keep their original acquisition tick. Age is
computed from the earliest possible acquisition time at the registry's actual
receipt clock read. Repeated HELLO, QUERY and reopen do not freshen the sample.
The `ready` property describes fresh synthetic control eligibility, and remains
separate from the last sampled value.

Loss of current execution eligibility does not by itself discard exact-reference
recovery. When identity and receipt correlation remain usable, the host can
retain cancellation, failure and quiescence evidence. An incompatible route,
boot, replayed/corrupt stream or clock-rate mapping retains uncertainty and
requires explicit resolution.

## Running and verifying

Build the original fixture before the full Python suite:

```sh
python3 scripts/check_endpoint_scenarios.py
python3 scripts/check_runtime.py
```

A trusted launcher supplies a connected Unix stream socket whose peer is the
same Unix UID. The original fixture uses the same duplex socket for stdin and
stdout. Initial host creation is explicit:

```sh
python3 -m hms.cli --socket /private/path/control.sock serve \
  --state-dir /private/path/state --init-compact-simulation --endpoint-fd 7
```

Descriptor `7` in that example must actually be inherited from the launcher;
the command does not create a connection. Reopening uses the same state directory
and live endpoint connection, without `--init-compact-simulation`. Deployment is
`simulation:compact`. An existing compact authority cannot reopen through the
SQLite plant backend. The launcher owns endpoint lifetime and must not replace
it with a fresh process claiming the old boot. Runtime close closes its own
descriptor; it does not reset the endpoint. Stale IPC socket reclamation remains
an explicit owner task under the existing IPC rules.

[Host binding tests](../tests/test_endpoint_binding.py),
[independent recovery/receipt tests](../tests/test_endpoint_binding_review.py),
[Journal regressions](../tests/test_endpoint_journal.py), and
[real CLI process-loss tests](../tests/test_endpoint_cli.py) cover the new boundary.
The CLI test holds endpoint lifetime outside the host, gates an actual OP reply,
kills the host process and checks a matching recovery QUERY plus exact frame
counts. The CLI relay and the deterministic tests' independent counter/control channel are test infrastructure,
not host observation sources or a production transport extension.

The [full runtime receipt](../artifacts/verification/local-runtime.json) pins
tested sources and binaries, with
[compact host packet/mapping traces](../artifacts/verification/compact-host-traces.json).
The [historical archive](../artifacts/verification/endpoint-host-before/index.json)
preserves the earlier 241-test baseline. Hash reconstruction of one additive
schema-builder edit is explicitly labeled there.

No device or MCU program was executed. Physical commissioning, qualified boot
storage and clock mapping, UART/platform drivers, independent stop, remote or
per-agent authority, adapter isolation, quotas and retention remain unfinished.
The current SQLite assumptions still forbid restoring authority state independently
of its replay/endpoint history. This implementation does not claim immunity to
arbitrary database rollback or power loss.

The same backend is now exercised through [native/PTC Harness tools](../integration/harness/compact-endpoint/verification.json) and [modern/legacy MCP clients](../artifacts/verification/compact-mcp/verification.json). Those separate receipts retain exact endpoint frame evidence and their specific crash/cancellation scopes. They do not extend the physical qualification of the endpoint.

The installed-support update now checks the exact desired binding and supported argument encoding during admission and again inside command reservation. Before ARM, the dispatcher holds the authority mutex, reloads accepted state, checks the start window and current policy, then performs the bounded handoff. Future, canceled or expired work cannot reach ARM through a stale selected operation. [Independent probes](../artifacts/verification/installed-support-review/review.json) cover these boundaries and retained replay. Holding the authority mutex during this local exchange is not an independent stop path or a physical latency guarantee.

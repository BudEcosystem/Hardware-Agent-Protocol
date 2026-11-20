# Shared-board GPIO/PWM simulation

The runtime has an explicitly selected I/O simulation profile. It uses the same
14 local API/MCP methods as the other simulation profiles. Its four installed
instances share one durable SQLite board across two adapter routes:

| Instance | Action | Shared resources |
|---|---|---|
| `sim:gpio5` | `gpio_pulse` | Pin 5 |
| `sim:gpio5:other-route` | `gpio_pulse` | The same pin 5, through another route |
| `sim:gpio6` | `gpio_pulse` | Independent pin 6 |
| `sim:pwm5` | `pwm_burst` | Pin 5, timer 0 and its channel |

GPIO/PWM use of pin 5 conflicts even across different instance names and routes.
Pin 6 can progress independently. Driver, service and hub nodes describe
resource dependencies; this profile does not execute their lifecycle changes.
No physical pin, Arduino, OS driver or hub service is opened.

## Start an explicit installation

From the project root, create a new private directory and generate an installation
pinned to the current project source. The blueprint is intentionally incomplete;
it is not accepted directly by the daemon. The generator fills source digests
and the derived topology digest, validates the complete configuration, and refuses
to overwrite an existing output file.

```sh
mkdir -m 700 /tmp/hms-io-example
python3 scripts/build_io_example.py --output /tmp/hms-io-example/installation.json
python3 -m hms serve --state-dir /tmp/hms-io-example/state --socket /tmp/hms-io-example/control.sock --init-io-simulation --io-installation-file /tmp/hms-io-example/installation.json
```

Wait for the foreground daemon's JSON readiness record. In another terminal:

```sh
python3 -m hms --socket /tmp/hms-io-example/control.sock discover
python3 -m hms --socket /tmp/hms-io-example/control.sock describe sim:pwm5
python3 -m hms --socket /tmp/hms-io-example/control.sock observe sim:gpio5 value --max-age-ms 10000 --evidence-kind simulation
```

Use the [local control walkthrough](local-control.md) to obtain a replay namespace,
prepare an invocation, persist the returned request and invoke it. Substitute one
of these action arguments:

```json
{"instanceId":"sim:gpio5","actionId":"gpio_pulse","arguments":{"durationMs":100,"level":1}}
```

```json
{"instanceId":"sim:pwm5","actionId":"pwm_burst","arguments":{"durationMs":100,"frequencyHz":1000,"dutyPermille":500,"resolutionBits":8}}
```

These snippets are action fields, not complete invocation envelopes. Preparation
also requires a replay namespace, operation key, declared timing and
`requiredEffect:"capability_completion"`. Durations are integer milliseconds from
1 through 5000; frequency and resolution must fit the installed timer contract.
Successful start also requires elapsed validation time plus duration to be
strictly less than `maxRunMs`, whose installed ceiling is 5000. Consequently the
5000 ms carrier boundary is refused before activation; smaller durations still
need sufficient remaining budget. The examples use 100 ms. These checks preserve
the original request bounds rather than extending them when execution is late.
The ordinary [procedure API](bounded-procedures.md) can sequence these actions.
The [MCP projection](mcp-integration.md) connects to this same daemon socket and
discovers the same generic tools; there are no separate per-pin MCP tools.

## Reopen and recovery

After stopping the daemon, reopen the existing installation explicitly:

```sh
python3 -m hms serve --state-dir /tmp/hms-io-example/state --socket /tmp/hms-io-example/control.sock --io-simulation
```

An optional `--io-installation-file` on reopen must match the installed document.
Initialization requires the file. Mixed I/O and legacy route/endpoint settings
are refused. Selecting the wrong stored profile does not try another provider.
Source changes invalidate the stored driver pin; regenerating a file does not
migrate or reset existing state. A migration mechanism is not implemented.

Exact invocation replay returns the existing operation without another output
activation; changing its intent under the same key conflicts. A missing or
identity-mismatched board store is an error, including after an earlier completed
effect. Startup never reconstructs that history from an empty board.

Reopening rotates the board session. An interrupted procedure whose unstarted
child names the old session therefore refuses resume with `IO_SESSION_CHANGED`;
the original procedure and child request stay unchanged. Explicit cancellation
is still available. A deliberately new execution needs fresh binding and its own
identity; resume never silently rewrites an old request. Exact replay of already
completed operations remains available.

On owner reopen, a retained pending pulse is conservatively canceled and the
modeled resources are made idle before its claims are released. Its activation
fact remains true: `mayHaveActed:true` is not erased by cancellation. Missing or
contradictory receipts retain uncertainty and resource claims. Current device
inactivation or loss of an administrator grant does not erase historical evidence
needed for recovery.

The model advances when host code runs. A requested 100 ms pulse is not proof of
a physical 100 ms waveform, autonomous timer, bounded stop latency or watchdog.
Graceful daemon close alone does not settle a pending pulse; explicit cancellation
and terminal status, or conservative reopen recovery, perform that settlement.
The operation result reports simulation evidence and physical verification remains
`unverified`. The observed `value` counts activations, not measured voltage.

The output uses `profile:"hms.synthetic-io-result/1"`. Its typed result separates
`activationCommitted`, `cycleCompleted` and `safeIdle`, with a reason when the
cycle did not complete. `safeIdleState` describes the retained receipt, not the
current pad state: a later operation may own that pad. A terminal board receipt
can also be visible while the journal still holds an unresolved operation and
its claims. The checked API validates this profile separately from the older
simulator's `effectCommitted` field; it does not relabel a canceled activation as
having caused no effect.

The same private-directory, Unix-UID principal and stale-socket ownership rules
as [local control](local-control.md) apply. Opening a wrong profile can advance the
Journal owner epoch before the catalog rejects it; refusal does not promise that
every authority-database byte is unchanged.

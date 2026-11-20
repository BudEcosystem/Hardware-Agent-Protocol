# Forward-time GPIO/PWM challenge results

All **94 distinct selected methods pass across three bounded invocations** on
the [corrected source](../../implementation02/README.md): nine GPIO methods in
105.290 test seconds, eight PWM methods in 96.032 seconds, and 77 unchanged
configuration/refusal regressions in 125.960 seconds. Elapsed times are 121.134,
112.353 and 142.452 seconds respectively. Every invocation keeps the original
180-second deadline and 16 MiB scratch limit. This is test verification, not a
qualification-group run or a performance measurement.

The worker validates the complete trusted combined plan before opening a runtime,
then executes one supported fixed challenge by its exact case identity. Explicit
adapter/procedure phases preserve the requested delay; the nominal scheduler
does not substitute a different history. The independent checker reconstructs
the fixed program, case, calls and clocks, and composes the complete configuration,
authorization, board, operation, parent, observation and outcome checks.

Each row runs once for GPIO and once for PWM:

| Challenge | Observed response per primitive |
|---|---|
| Not-before boundary | No early handoff; one activation and completion |
| Just before latest start | Starts before the upper bound and completes at it |
| Latest-start equality | No handoff, receipt, board fence or activation |
| Run-completion equality | One activation, canceled by execution deadline |
| Wall-completion equality | One activation, canceled before completion; wall deadline takes precedence over equal lease expiry |
| Just before waiting lease expiry | Wait consumes the original lease; one completed cycle before expiry |
| Waiting lease equality | No handoff or activation, although latest start has not expired |
| Late parent reporting | Historical child completion remains true; parent reporting misses the strict deadline and nominal timing is false |

All 16 terminal cases are settled and quiescent. The aggregate is 12 activations,
eight completed cycles and four canceled activations, with four no-handoff expiry
cases and 68 scheduler ticks. Eight completion contracts are satisfied and eight
fail with their expected refusal/stop response. A correct fault response does not
make a failed completion contract successful. Claims are released and authority
ownership floors remain; unstarted expiry creates no driver dispatch ticket.

The new tests also reject 11 rehashed case alterations, four rehashed expiry
reason/effect alterations, a coherent history substituted for the wrong named
challenge, and four unsupported/altered plans before runtime construction. The
pure checker passes with filesystem, SQL and clock access vetoed. The 77 existing
regressions use unchanged tests and historical data, with no SQL connections.

The [initial attempts](../attempts01-02/README.md) remain failed: each had two
expiry-inspection errors. Their raw records already showed correct refusal.
Only the independent configuration/refusal readers and the new timing test file
changed. Runtime, provider, compiler, worker and original tests remain unchanged.
The corrected readers derive `start_or_lease_expired` from actual timing and state;
they do not accept an arbitrary reported reason. A separate launcher-preparation
syntax error was caught before project execution and remains retained.

The [acquisition proof](proof.json) rechecks actual methods/origins, stable 7,070
project files, 7,073 frozen preparation entries, six active harness files and 159
selected external pins. All 731/723/683 origins match; 229/225/205 bytecode reads
are refused. Compiler/driver receipts remain stable. Complete copied attempts
contain 8,248, 8,247 and 7,104 files. Original raw directories retain their recorded
identities: 1,144 files/6,553,997 bytes, 1,143 files/6,704,918 bytes, and an empty
regression directory. The [data audit](data-audit.json) separately cross-checks
raw final tables and the aggregate claims without importing project code.

This stage covers eight of the planner's fixed challenges for each primitive.
In-phase guard delay, clock faults/new epochs, binding and full-read withdrawal,
explicit auxiliary actors, complete candidate matrix execution and aggregate
wall/output/storage enforcement remain open. Current-source/configuration
attestation and the compiler identity gap remain separate. All qualification,
full-matrix, physical-measurement and aggregate-storage success flags stay false.
This was primary-agent review; helpers were unavailable due to their usage limit.
No physical device, MCU/emulator, live model, public service or acquired controller
ran. Persistent prompt applications, learning/promotion, physical drivers and
intelligence-hub lifecycle/compute management remain required unfinished work.

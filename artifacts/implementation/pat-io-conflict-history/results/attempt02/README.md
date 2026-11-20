# 48 transcript/conflict tests pass with retained evidence

All 48 selected methods pass in 64.370 test seconds and 72.786 elapsed seconds:
39 unchanged transcript methods and nine new original-runtime cases. The
original 180-second deadline and 16 MiB scratch limit remain unchanged. This
run retains 1,336 raw files totaling7,335,715 bytes, including 939 execution
records, 352 configuration records and 152 paired checkpoints. All 7,067 project
inputs, 7,070 preparation entries, six active harness files and 159 external pins
remain stable. All 721 origins match; 224 bytecode reads are refused and no
prohibited attempt is recorded. Compiler/driver receipts match within the run.

The new internal trial profile 0.2 records one deterministic changed first argument
while preserving the original namespace, parent key and every child key. GPIO
level toggles; PWM duty advances within 0..1000, wrapping at 1000. The original
compiled request remains unchanged. Legacy readers reject 0.2 unless explicitly
enabled. The independent checker reconstructs the change, derives read and
namespace/parent precedence, checks unchanged execution/configuration tables,
and composes the board, operation, parent, permission and observation histories.

Cases cover accepted multistep GPIO, pending PWM, completed GPIO/PWM, GPIO level 0,
PWM duty 1000, canceled parent, completed reopen, elapsed namespace wall expiry
without pruning, and retained-read permission withdrawal. Nine cases exercise
these combinations. Across them, nine original activations complete; the
canceled parent starts none. Nine replay/conflict probe pairs add zero activations
or child operations, preserve all 29 execution and 15 configuration tables, and
leave no unresolved operations. See the [root data audit](probe-audit.json).
Fifteen rehashed false claims, two private-guard checks and the pure-reader I/O
veto check also pass within the selected methods.

The [proof](proof.json) rechecks source and dependency pins, actual methods,
origins, exact 18 database paths and 7,000 retained table-page references. It
acquires all 8,437 attempt files and verifies the original raw directory and
its copied bytes. Original raw scratch remains
`/tmp/hms-io-conflict-history-conflict48-kwo52n0s`.

Together with [four separate legacy tests](../attempt03/README.md), this is 52
distinct passing methods across two successful invocations. The original
[combined invocation](../attempt01/README.md) remains failed because its output
exceeded the collection bound. Splitting test verification does not change any
qualification-group budget or constitute a passing qualification group.

The complete candidate fault/resource matrix, current-source/configuration
attestation, group storage/time enforcement, public qualification tools,
physical providers and hub control remain unfinished. No PAT is qualified or
promoted by this result. No acquired controller, physical device, MCU/emulator,
inference service or adjacent project executes or changes.

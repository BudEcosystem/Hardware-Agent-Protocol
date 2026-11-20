# Native worker process-accounting diagnostic

The preceding turn made concrete progress: an isolated native scanner was
integrated and observed in the complete qualification scope, with retained
controls and failures. That scope still timed out. It did not measure process
resource usage, so it cannot establish why completion differed from earlier runs.

This diagnostic keeps every one of the 291 frozen project files and all
producer/consumer identities unchanged. It composes the existing controlled
resource observer with the native-aware execution harness. The native load,
sealed-image and scan checks remain exact. No worker code is instrumented.

The observer uses the original Popen object, inherited descriptor identities and
the first existing poll/wait that reports termination. It adds no wait, poll,
signal, scheduler change or PID-based counter read. Before/after test and
launch/reap snapshots capture self and waited-child usage plus three bounded
global pressure files. The retained ledger and lease are needed to validate that
association after the actual scope terminates.

All fifteen original observer controls plus six new composition cases pass.
The new cases use fake process objects and prevalidated image-state fixtures;
they do not create a native image or launch a worker. They verify AST fidelity,
separate scan/launch bookkeeping, native veto propagation, original subprocess
refusal, duplicate-launch refusal and terminal attribution. The earlier real
sealed-image controls remain the evidence for that separate component.

Original bounds remain: thirty cases, 60-second worker, 180-second parent, six
parent SQLite opens, 16 MiB file, 256 MiB scratch, 8192 files, 8 MiB log, five-second
held snapshot and 15 MiB vault. No physical provider, MCU, model, live service or
acquired controller code runs. Interrupted case databases remain unopened.

The [fully read process-accounting sources](../../../research/host-contract/worker-accounting/README.md)
define interpretation. Additive CPU and operation counters may be differenced;
peak RSS remains a raw high-water value. Block counts are not bytes or time.
Global pressure cannot attribute a stall to this worker. Accounting does not
measure a scheduler wait cause, remove observer overhead or establish a matched
performance comparison. The diagnostic is not a deadline qualification.

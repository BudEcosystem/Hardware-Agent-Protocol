# Interrupted chunk-store operations

Stage 85, 2026-11-09. The preceding turn made verified implementation progress:
the persistent adapter passed 54 checks and its read-only retained-state audit.
Reverify its 141-file exact index and the 244-file public baseline before use.
No candidate or public runtime source is changed in this experiment.

Run all 22 predeclared cases in cases.json, in order, stopping after the first
failed or inconclusive case. Exercise create, staged namespace writes, namespace
publication, extension, partial multi-chunk overwrite, shrink, grow with a retained
truncated tail, rename-over-target, unlink, final-reference reclamation and
interruption of recovery itself. Two cases terminate a second recovery owner,
making 24 selected owner interruptions in total. These selected boundaries do
not exhaust every callback, byte offset or physical power-loss state.

The original adapter and native library are copied exactly from sealed stage 84.
Original test instrumentation wraps native call boundaries and uses the existing
callback injection point without editing candidate sources. The selected owner
records and fsyncs its checkpoint outside the image, then stops itself with
SIGSTOP. The parent verifies the original PID, start identity, intent digest and
stopped state, sends SIGKILL through its pidfd, and waits for terminal -SIGKILL.
Unreached checkpoints, unexpected exits and timeouts fail the case; they do not
trigger another attempt or a changed checkpoint.

Retain each interrupted image byte-for-byte. Under read-only object locks, create
a fresh fully allocated image with new host object anchors, copy the exact raw
block bytes and prove the copy hash. Only that copy is reopened for recovery.
It retains the logical image identity for this private research lineage; it is
not a second live deployed authority. Recovery interrupted again gets another
fresh derived copy. Never recover, repair, reformat or mutate the originals.

After recovery, compare actual adapter reads and a separate read-only reconstruction
to the original expected inode IDs, names, lengths, payload digests and next ID.
Require no orphan records, extra directories, stale staging files or unreferenced
chunks after the final successful recovery. Partial overwrite has an explicitly
declared mixed-chunk outcome, since the adapter does not claim atomic multi-chunk
writes. A cut before rename sync permits only complete old or new namespace states.

Each outer case retains the existing 60-second wall, 40-second CPU, 512 MiB address
space, 128-descriptor and 16 MiB per-file limits. Nested owners have a 15-second
wall observation limit and 10-second CPU limit. The new matrix has a predeclared
1 GiB retained-file ceiling: at most 46 fully allocated 16 MiB images, or 736 MiB
backing, plus bounded metadata/logs. Earlier stages and their ceilings are untouched.
This finite research inventory is not an aggregate service quota. Preserve any
failure and all previous case evidence; never restart because observation yielded.

No upstream build scripts, new acquired code, physical hardware, mount, SQLite
database or public service is run. Process termination preserves the host kernel
and its caches; this is not physical power loss. Actual storage exhaustion,
every-writer confinement, backed continuations, SQLite DELETE/EXTRA recovery and
physical device/driver/hub providers remain required after this gate.

# Pre-execution review

Primary-agent review only. Stage 84's exact index and all 244 public runtime inputs
were reverified. This matrix changes no candidate source or binary. It copies the
qualified adapter, corrected C bridge/library, fixed block provider and reviewed
core dependencies, and uses the existing native callback injection seam solely
for selected process stops. The previous read-only image class is copied exactly.

Every case declares the fixture, operation, checkpoint and admissible inode/name/
length/digest outcome before any image is created. Preparing the last-close cases
unlinks the named file while the selected owner still holds its handle, before
arming the close checkpoint; that preparation is explicit in the original case.
The operation intent is durable outside the image and its digest joins every
owner start, stop, kill, clone and final readback association.

Instrumentation calls the original native operation exactly once. It observes
successful return boundaries, or the existing before-callback seam at the second
program call / first rename sync. The selected process stops itself only after
the checkpoint file and directory are synchronized. The parent verifies the PID,
Linux start ticks, expected phase/ordinal and stopped process state. A pidfd binds
SIGKILL to that original process. Terminal -9 is required before reading its image.
An absent checkpoint or expired observation is a failed/inconclusive case, never
authorization to restart the owner or move the checkpoint.

The original interrupted images are read-only locked, hashed and inspected through
the native read interface without adapter recovery. Clones are explicitly created,
fully allocated, supplied with fresh host object anchors and filled from the exact
source block bytes under locks. Original metadata and payload files remain exact.
Only the derived copy undergoes normal adapter recovery. Two cases repeat this
sequence after terminating a recovery owner; final inspection requires no leftover
orphan/staging/unreferenced objects and the exact original expected state.

The final actual adapter reads and a separate reconstruction of chunk maps/bytes
must agree with the declarative oracle. This is stronger than accepting successful
mount alone. The snapshots do not execute _recover, _chunk or other adapter
business methods. Read-only callbacks refuse program, erase and sync, and before/
after hashes prove that inspection changed no image bytes.

The native binary already passed stage 84 and is not rebuilt or instrumented at
the C level. Fifteen source, binary, plan and test inputs are frozen. All process,
file and retained-inventory bounds are declared in PLAN.md; the 22-case matrix is
never narrowed after a failure. No existing fixture is repaired. Host process
termination is explicitly distinct from hardware power loss and cache loss.

This gate covers selected interruption boundaries, not every mutation phase or
the final service filesystem contract. Exhaustion, bounded continuation backing,
SQLite DELETE/EXTRA recovery, service confinement and physical device/driver/hub
qualification remain unfinished even if every declared case passes.

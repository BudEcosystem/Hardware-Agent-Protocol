# Qualify a real storage backend and continue providers

FUSE mounting is now observed to work on this host. Preserve this single passing
probe and do not repeat it as if that advanced writable storage qualification.
Keep the current 866-test/244-input runtime baseline unchanged unless production
actually changes. The full HMS goal remains active and incomplete.

The next storage decision must identify the actual allocator, durable metadata
format and physical backing. Prefer a reviewed existing filesystem/backend when
its crash and space guarantees satisfy the service; otherwise treat a new
allocator as substantial new implementation requiring its own failure matrix.
Do not promote the read-only probe into a quota provider by changing its reported
capacity or adding path-based byte counters.

For any FUSE-backed candidate, qualify aggregate blocks and inodes across all
writers, sidefiles, temporary files, code images and open-unlinked allocations.
Backing must cover metadata, recovery writes and control continuations, not just
logical main-file sizes. Preserve the 16 MiB per-file and 256 MiB scratch bounds
and state an explicit sum across control/bulk domains; splitting files does not
multiply the budget. Keep original attempts, admission charges and unknown
effects across owner loss.

The provider's code, logs and backing handles must be outside its served mount.
Control-only recovery must not depend on a failed bulk daemon. Define mount
identity, propagation and replacement behavior before service use: the probe's
mode-private path was in a shared mount tree, not an isolated mount namespace.
Exercise actual fsync/rename/unlink/lock/SQLite sidefile semantics, daemon death,
reopen and exhaustion before claiming a backed persistent store. Interrupted
I/O is not automatically rolled back or safe to repeat.

Then compose the installed supervisor, reducer, vault, catalog and execution
libraries under trusted service ownership, with caps enforced before startup
mutation/recovery and current evidence held through admission commit. Expose the
typed PAT tools through Runtime/CLI/MCP and the native Harness only once their
declared storage and recovery behavior is executable. Caller paths, arbitrary
commands and supplied pass claims remain excluded.

Independent work remains required on actual device I/O/bus providers, driver and
hub lifecycle, local timing/stop paths, persistent MCU execution, prompted
candidate generation and evidence-based learning. The user describes behavior;
commissioned endpoint primitives execute it, validated PATs handle familiar
contexts and structured novelty returns to the agent. Driver/hub changes must
invalidate affected applicability without erasing original operation history.
Microscope commissioning, home/laboratory/manufacturing scenarios, remaining full
source reading and portability beyond this Linux host stay in scope.

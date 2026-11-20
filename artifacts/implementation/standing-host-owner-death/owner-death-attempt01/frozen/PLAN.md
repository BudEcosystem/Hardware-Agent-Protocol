# Fixed thirteen-cut implementation and bounded run

Status: source-only; root review is required before executing the fixed runner.
The complete original design is preserved in originals/design/PLAN.md. This
implementation joins its revision04 assumptions to the final tested freeze07
source manifest, rather than running an obsolete fixture. There is no smaller
fallback matrix or cap increase on failure.

Run only the reviewed run_checks.py with assertions enabled under python3 -I -B.
It exclusively creates owner-death-attempt01, freezes its indexed inputs, and
launches one fixed inner control command. It performs no compile, native
qualification rerun, evidence relocation or rewritten original receipt. The
producer consumes the exact original host-attempt04/qualification root, whose
reservation/receipt/manifest binds its original absolute argv. The native image
is the original host-attempt04/standing-host-pipe.

Before and after the command, the runner verifies every indexed byte and exact
file inventory of the sealed host parent, all public244 inputs, copied source
and original provenance, current/frozen harness bytes and held interpreter
identity. The exact Guardian/helper bytes are verified before import. The held
native FD is checked against its fixed reviewed SHA before each fork and again
after native reap. Installation separately requires that same image identity.
The interpreter ELF and source/helper/image pins do not claim full Python/loader/
validation-package closure or a hostile same-user sandbox.

The outer process owns a single control process with 30 seconds observed wall,
30 CPU seconds, 512 MiB address space, 1 MiB file size, 64 descriptors and core0.
Each owner, recovery host and native endpoint keeps Guardian's original 5 CPU
seconds /256 MiB profile. The full matrix must fit the unchanged outer bound;
each owner must reach its selected cut within five observed seconds. Cleanup
uses the original three-second TERM grace and eight-second settlement bound.
Limits are per-process and observed deadlines, not aggregate kernel quotas.

For each of thirteen sequential cases, the inner parent creates the native wire
and control socketpairs, starts the pinned native image, and keeps only the host
wire/control ends. It has no Journal or SQLite/owner-lock descriptor. It then
forks an original owner that opens a fresh Journal only in that child. Host
children close the private native control socket and every unrelated descriptor;
LocalEndpointStream duplicates the inherited raw wire FD, which is immediately
closed. The owner never forks after Journal creation.

Fixed setup stages occur after host methods return and release policy, driver,
producer and catalog leases. The parent acknowledges its exact native commands
before opening the stage gate. At the selected committed cut, the owner writes
and fsyncs bounded original snapshot bytes and sends a small notice. That death
gate never resumes; EOF is failure. The parent checks case/phase/opcode/deployment/
mutation association and exact snapshot bytes, observes native counters, then
signals only its already registered direct child through the retained pidfd.
It requires SIGKILL reap and the native-only live set before recovery.

A separately forked recovery owner opens the same Journal create=False while the
parent/native remain alive. This demonstrates owner-lock release without deleting
or replacing a lock file. It checks the immutable row, keyed records, claims,
original catalog identity and exact permitted reopen field changes. It replays
original identities and observes endpoint state without sending an effect.
At a second barrier, after all leases are released, the parent independently joins
the outgoing body/opcode/sequence/hash audit and observed snapshot, and verifies
unchanged native state except response sequence. Only then can the explicitly
specified new action run. Native counters and exact accepted records check those
new actions separately from historical replay.

The cases are prepared/possible/reply boundaries for OPEN, START, ACK and RETIRE,
plus collection committed before ACK reservation. Prepared-only settlement retains
old original bodies; possible sends never retry. RETIRE reply joins retained
terminal proof with the same-boot empty descriptor, accounting for reset native
standing counters. Common REVOKE is absent; its existing independent uncertainty
guards remain unchanged.

Snapshots are capped at 128 KiB and include one deployment and its original
canonical bytes, at most eight keyed mutations, two keyed activations, four keyed
versions, two keyed loss episodes, three claims and two owner-instance aliases,
plus route, authority/epoch and required catalog identities. SQL keys such as
version and episode_key are retained alongside original document bytes. Notice
records are at most 4096 bytes; outgoing audits at most 64 entries. These are
fixture limits, not reductions of production capacities.

Each case retains checkpoint.json, reopened.json, observed.json,
read-only-audit.json, recovery.json, stage/native observations, joined start and
reap identities, role logs and CASE-RESULT.json or failure evidence. A role failure
retains a bounded traceback before Guardian's exit90 wrapper. Per-case success is
published only after descriptor cleanup and signal unmask succeed. Normal cleanup
reaps recovery, closes parent wire/control keepers, then requires native cleanEOF
exit0; killing the native is failure cleanup only. No global settle runs while
the native peer is intentionally surviving.

Inner and outer reducers independently join the exact expected families/exit
classes, attempt all cleanup actions, preserve errors, and fail on pending or
deferred interrupts. Unexpected children are registered only through kernel
child relation and settled; they fail the expected family count. No PID from
persisted evidence supplies signaling authority. A failed attempt is preserved
and stops this run. The complete 13-case evidence remains unqualified until the
root-reviewed execution and independent retained-data audit pass.

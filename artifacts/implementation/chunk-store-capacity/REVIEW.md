# Pre-execution review

Primary-agent review only. The new bridge enumerates directory name, type and
regular-file size together, with an explicit 72-byte ABI, bounded output capacity,
directory-close error propagation and zero for undefined directory size. Python
checks the ABI before loading and keeps all prior root/inode/chunk validation.
The inventory consumes these entries instead of repeating a path lookup for every
name. No data, namespace, ownership, recovery or admission policy is relaxed.

The six original semantic scopes and all 22 original interruption oracles remain
selected. The latter harness changes only its library path/hash configuration
to explicit environment inputs; checkpoint, signal, clone and outcome logic is
unchanged. Their original limits stay fixed. Candidate changes justify repeating
these controls, while the unchanged public 866-test suite is not repeated.

The original seed tool compiles only the fully read littlefs core/utilities and
the new original bridge. It has two fixed 16 MiB arrays, finite 4,096-chunk loops,
aligned/range-checked callbacks and erased-bit program checks. RAM sync only
counts calls. It retains the exhausted RAM state and the latest completed snapshot
with at least 32 block slots of headroom. The latter is explicitly a placeholder
fixture until a separate copied RAM image receives a canonical namespace.
The exhausted RAM state is never repaired or used as a valid adapter image.

An independent native read mode mounts the retained raw bytes in read-only RAM,
checks every declared 4 KiB payload against the original A/B pattern and forbids
program/erase/sync. Finalized bytes are copied into fresh fully allocated host
backing before any actual adapter capacity observation. Full 16 MiB geometry is
preserved throughout; fixture construction is not a host durability result.

Host append intents are synchronized outside the bulk image before each original
operation. There are at most 64, with no retry after the first error. Actual
NativeError(-28), no injected callback fault and poisoned-owner refusal are required
for an exhaustion result. The failing native path distinguishes data allocation
from namespace publication. Published state is read separately; in-memory state
after failure is explicitly not authoritative.

Control writes use a separate preallocated image, including a real ENOENT attempt
on a missing bulk path. That verifies this example's storage-domain independence,
not complete service recovery or reserved continuations. The failed bulk image is
retained under its original identity and only an exact anchored copy is recovered.
Cold recovery and a later metadata allocation are measured outcomes; failure stays
failure and does not become a passing service claim. All data readback is bounded.

The runner stops after unexpected failure/timeout, retains the original process
handles and results, freezes inputs before compilation and verifies unchanged
public/prior-stage sources. No original failed image or worker database is repaired.
No mount, hardware, driver, hub service, upstream scripts or public runtime changes
are involved. Every remaining gate in PLAN.md remains required after this work.

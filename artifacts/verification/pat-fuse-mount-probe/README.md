# Private FUSE mechanism verified

Stage 81, 2026-11-09: the original bounded read-only mount probe **passes all
14 checks**. [Exact result](attempt01/RESULTS.json), [plan](PLAN.md),
[preparation review](REVIEW.md), [source](probe.c), [harness](run_probe.py).

The installed libfuse 3.14.0 and fusermount3 helper mount a fixed document at a
new owned path, with ro,nosuid,nodev,noexec and default_permissions. The client
checks directory contents, ownership/modes, exact document fields, offset and EOF
reads, missing paths, refused create/write/unlink and unchanged content. Ordinary
unmount succeeds; the server and client exit zero, the mount disappears and the
underlying directory is empty. The server records kernel protocol 7.45. There
are no cleanup errors; the whole compile/mount/client/unmount scope takes about
0.315 seconds. This observation is not a service timing guarantee.

The native probe uses only original callback code and the fully read matching
public headers. The acquired example and implementation are not executed. The
[research packet](../../../research/host-contract/fuse-storage-boundary/README.md)
retains 12 completely read source/license/manual files, totaling 4,378 LF lines.
The original empty libfuse_config.h is an explicit probe configuration, not a
replacement generated distribution header. The three selected public calls do
not depend on its symbol-version selection; acquired ABI structures are intact.

All 14 recorded inputs remain exact before/after, and all **244 public runtime
inputs** still match the prior **866-test passing receipt**. No production file,
public API, worker bound or original qualification attempt changes. That full
suite and the unchanged thirty-case worker were not rerun. Compilation uses
warnings as errors. Primary-agent review only; no independent reviewer is claimed.

The current user can use this installed filesystem mechanism without changing
host quotas or installing software. However, this mount has no writable allocator
or persistent backend. `totalDiskQuotaEnforced`, `backedControlCapacity` and
`durableStorage` remain **false**. Its mount record also shows shared propagation;
the experiment supplies no private-namespace or arbitrary-owner-loss guarantee.
It is not mounted in the HMS service and implements no physical device provider.

[Next work](NEXT.md) preserves the full device I/O, driver, hub and learning
requirements while turning this mechanism into a qualified storage choice.

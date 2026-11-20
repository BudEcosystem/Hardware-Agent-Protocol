# Current mount identity candidate

The isolated provider fixes the reproduced mountinfo selection error and reduces
cost in a paired local screen. **The complete storage gate still fails its
180-second deadline. No public runtime installation is made.**

The new explicit `hms.block-image.linux-ext4.statx-mount/0.1` profile uses a bounded
native helper to query both the held directory and current pathname. Admission
joins the actual legacy mount ID to one bounded binary mountinfo inventory for
exact ext4 type, bracketed by boot-unique identity queries. Every block read,
write, erase and sync queries current identity again. Missing fields and changed
identity refuse. The old provider's ownership, allocation, inventory, metadata,
range, fork, lock, poison and fsync behavior remains unchanged. Old manifests
are not silently migrated.

[Source review](../../../research/host-contract/mount-predicate-source/README.md)
covers complete selected Linux and glibc files and explicitly lists unread
namespace.c ranges. The reference revisions are Linux v7.0 and glibc 2.39; they
are not an audit of the running Ubuntu binaries. The compiled helper hash is
`450f1d2bfd948ca0f7292884e753ccc11fd9f82dc285e150cf535864b75572bd`.
The hierarchy, base adapter and littlefs binary are unchanged. The subclass only
selects the new provider source hash; patches document all adaptations.

All **69 native synthetic controls**, **52 Python mount controls**, **24 original
provider tests**, and **96 hierarchy controls** pass in their original bounded
scopes. Actual unprivileged descriptor/path queries are exercised, including
closed descriptors, different directories and symlinks. Mount-race and missing
syscall fields use explicit substitution; no actual mount or namespace changes
are performed.

The paired coarse screen creates 40 files / 623,624 bytes and 20 directories on
each fresh 128 MiB image, then reads all bodies through warm and cold owners.
All 426 logical steps, per-step callbacks, full bodies and filesystem chunk bytes
match. Only the provider manifest profile differs.

| One local pair | Original | Candidate |
| --- | ---: | ---: |
| Process CPU, seconds | 10.398886 | 3.072819 |
| Workload wall, seconds | 16.622683 | 8.981686 |

This is a local comparison, not an established production speedup. Neither
checks nor fsyncs are disabled. The subsequent complete writer retains the
original 4,270 files / 35,508,922 bytes, 169 directories, 128 MiB geometry and
180-wall/120-CPU limits. It is killed and reaped at **180.085309 wall seconds**,
with **43.709646 CPU seconds**. It reports no capacity error; capacity fit remains
unknown. The dependent full cold reader does not run. No unchanged retry occurs.

The [independent read-only audit](EVIDENCE-AUDIT.json) verifies 21 filesystem
images, including the original interrupted image. All 169 directories and
**1,277 completed file bodies / 5,868,766 bytes** match the exact dataset prefix.
There are no additional published files, incomplete physical inodes, pending
entries or unlinked nodes in that observed image. The auditor does not run
adapter recovery or SQLite; write/erase/sync callbacks are forbidden. It passes
in 5.018239 wall seconds and leaves every backing byte unchanged. Raw provider
fixtures and the partial-creation fixture remain retained separately.

The 244 public inputs still match the existing 866-test baseline, which is not
rerun unchanged. The earlier hierarchy and cost-diagnostic seals remain exact.
Source, process, input and output receipts are frozen under `attempt01` and
`audit-process01`. Primary-agent review; no independent helper-agent review was
available. See [next work](NEXT.md) for the unmet gate and unchanged broader scope.

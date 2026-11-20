# Isolated inline512 hierarchy candidate

Stage 95, 2026-11-09. **192 focused checks and the paired logical comparison
pass; the complete writer still misses its original deadline.** This candidate
is not installed publicly and does not qualify service storage.

The [source review](../../../research/host-contract/littlefs-inline-review/README.md)
supports a bounded inline-file experiment. The production changes are exactly
one bridge initializer, enabling inline files up to 512 bytes, and the explicit
hierarchy profile `hms.hierarchical-chunk-store.inline512/0.1`. The upstream core
and hierarchy methods remain unchanged. The prior statx block provider remains
byte-exact, including full fsync of every backing chunk at every block barrier.
The separate tracked-sync candidate is not combined with this change. Old
anchors and old on-disk profiles refuse; no migration occurs.

The [plan](PLAN.md), [review](REVIEW.md), source patches and frozen inputs retain
the pre-execution scope. The new native library has SHA-256
`6b48f9b9c9a829a8c5c71236c309e7e78f55f096e7c627542a739095ff57ec7a`;
the original comparison library remains
`7049dc14940b0f686f5cbe682e85f70944a8074936786e7f962c6ee29ed321de`.
The existing mount helper is unchanged. Compiler identity, bridge header
dependencies and host observations are retained. This is an explicit Linux
x86-64 host experiment, not an Arduino memory or flash-endurance profile.

| Scope | Result |
|---|---|
| Original native RAM probe | 12 cases pass, with 1,294 internal assertions |
| Original mount/provider checks | 52 mount controls and 24 provider tests pass |
| Explicit hierarchy-profile admission | 8 checks pass |
| Original hierarchy matrix | All 96 checks across nine scopes pass |
| Paired 40-file / 20-directory screen | All 426 logical operations and complete bodies match |
| Original 4,270-file writer | Deadline failure; killed and reaped |
| Dependent cold reader | Not run after writer failure |
| Independent retained-state audit | 23 filesystem images and two RAM snapshots verified read-only |

The native probe checks sizes 0, 1, 511, 512, 513, 4096 and 16384, then transitions
back to 512 and 0 through the bridge's truncate/write path. It checks actual
native inline flags and cold readback. Three hundred small files exercise
directory growth, rename and removal; 299 remain, alongside the empty boundary
file. Its live/durable RAM snapshots match exactly. The callback model is not a
physical power-loss experiment. Profile controls verify refusal before native
open for an old anchor, and before recovery for an old superblock, with no
mutation callbacks or changed backing bytes.

In the paired screen, original/candidate CPU is **4.852882 / 3.866312 seconds**,
and wall time is **11.409207 / 9.623607 seconds**. Native syncs fall from 1,714 to
1,572; full provider fsync calls fall from **13,724 to 12,588**. Every native
barrier still synchronizes all eight backing chunks. The screen uses the same
lightweight counters in both variants. It establishes logical equivalence for
that workload, not production speedup or the cause of the full replay timeout.
Inode metadata, links and complete bodies match; superblocks differ only in the
declared profile. Different physical encodings are expected and observed.

The complete workload keeps **4,270 files / 35,508,922 bytes**, 169 directories,
eight 16 MiB chunks and the original 180-wall/120-CPU limits. Its child is killed
and reaped at **180.049439 wall seconds**, using **63.282792 CPU seconds** and
23,844 KiB peak RSS. No capacity error is reported; complete capacity fit remains
unknown. No unchanged retry, reduced workload, repair or geometry change runs.

The [evidence audit](EVIDENCE-AUDIT.json) passes in **9.641889 wall / 9.565362 CPU
seconds** with 36,172 KiB peak RSS. It reconstructs **1,182 complete files /
5,429,966 bytes** and all 169 directories in the interrupted image, matching the
exact source prefix. There is no extra published file, incomplete physical inode,
pending entry, unlinked inode or partial progress tail. Read-only reconstruction
uses held O_RDONLY descriptors; write, erase and sync callbacks are forbidden.
The deliberately refused superblock fixture retains its exact sentinel. No
adapter recovery or SQLite is invoked, and all inspected bytes remain exact.

All 20 candidate child processes and the independent audit child are reaped and
absent. All **244 public inputs** match the existing **866-test** baseline; that
unchanged suite is not rerun. Implementation review is by the primary agent;
separate agents prepare/review the audit and review the device/driver/hub prose.
These scopes are distinct from physical or full-repository qualification.

The first final packaging check rejected the mount controls' intentional directory
symlink fixture. [That failure](seal-attempt01/failure.json) and its script are
retained. The final index records that one alias explicitly without following it;
the already-written result/audit reports must match exactly. No candidate or
read-only audit is rerun for this packaging correction.

[Next work](NEXT.md) requires measured attribution before another storage change.
The overall HMS goal remains active, including prompt learning, persistent
endpoint applications, actual I/O/driver/hub providers and physical validation.

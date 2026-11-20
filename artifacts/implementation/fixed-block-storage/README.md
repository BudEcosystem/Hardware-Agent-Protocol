# Fixed-capacity block image candidate

Stage 82, 2026-11-09. **All 24 controls pass** in
[attempt02](attempt02/RESULTS.json), after the retained
[attempt01 fixture setup failure](attempt01/RESULTS.json). The production
prototype is identical across both attempts. [Correction](CORRECTION.md),
[plan](PLAN.md), [pre-execution review](REVIEW.md) and exact frozen inputs preserve
the sequence. This is verified progress toward a hub storage provider, with no
public runtime change. The 866-test baseline's 244 inputs remain exact.

[fixed_block.py](fixed_block.py) is an original Linux/ext4 implementation. It
explicitly creates a finite image of one to eight 16 MiB regular-file chunks,
preallocates and initializes every byte, and syncs files and directories before
returning creation metadata. Existing-image access requires externally retained
device/inode anchors, exact geometry, private ownership, complete inventory and
exclusive locks. Missing/replaced/sparse backing refuses. The API permits aligned
bounded block reads, writes, erases and explicit sync; it never formats on open.

The [tests](test_fixed_block.py) cover actual fixed geometry, chunk boundaries,
neighbor preservation, cursor independence, synchronization/reopen, cross-process
exclusion, fork refusal before an inherited mutex, missing/replaced/symlinked or
hardlinked files, changed modes/manifest, sparse backing, unexpected inventory,
FIFO refusal and descriptor cleanup. Explicit syscall injections cover positive
short transfers, zero progress, partial writes, EIO, sync failure, interrupt and
allocation failure. The partial write is retained and verified, not rolled back.
The fork test intentionally triggers Python's multithreaded-fork warning and
verifies the child's prompt refusal and terminal settlement.

The independent control image remains usable while the main image's manifest is
missing. That is image independence, not qualified service recovery. One failed
creation retains its empty first chunk and owner without a completed manifest.
Attempt01 retains its 32 MiB initialized image; attempt02 retains 48 MiB. Total
backing is **80 MiB**, with each file at most 16 MiB. The wrapper uses finite
inventory plus post-run accounting under the 256 MiB scratch budget, not a global
filesystem quota. Successful scope elapsed time was about 1.15 seconds; this is
not a deployment performance guarantee.

The [source packet](../../../research/host-contract/fixed-block-storage/README.md)
completes eleven selected files / 7,802 LF lines and a supplemental manual page.
Neither acquired filesystem implementation was built or executed. The stock
littlefs wrapper needs a different contract; the reviewed fuse2fs lacks journaling
of new writes. The littlefs core/design/specification remain unread and must be
reviewed before integration.

This candidate assumes trusted code, owner and kernel. Advisory locks and path
checks do not confine hostile same-user writers. It does not authenticate payloads,
provide filesystem transactions, reserve continuation capacity, bound virtual
inodes, qualify power loss, or enforce aggregate service storage. There is no
filesystem mount, public qualification service, new physical I/O provider or hub
administration operation in this stage. [Audit](AUDIT.json) and [next work](NEXT.md)
record the exact evidence and remaining obligations. Review is primary-agent only.

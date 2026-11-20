# Pre-execution review

The flat adapter and fixed-block source are exact retained copies. The derived
adapter replaces namespace methods and copies only `pwrite` and `truncate` with
per-inode metadata commits. Data reads, shared handles, chunk reconstruction,
tail zeroing, owner serialization, poisoning and disposal retain the base methods.
The native adaptation changes the bounded name transport to 255 UTF-8 bytes and
a 264-byte entry ABI. No existing binary's qualification is inherited.

Each logical directory owns pointer files. Moving a pointer preserves the inode
and subtree identity. Metadata uses canonical checked bodies, and new identities
are reserved durably before allocation. Orphan allocation and last-reference
reclamation remove metadata before chunks, so partial deletion cannot leave an
orphan's committed metadata referring to deleted data. Recovery inventories all
objects and the complete single-parent graph before deleting any staged/orphan
state. Corrupt referenced data, mixed inode contents, unknown objects, cycles,
duplicate references and unreachable nonempty directories are refused.

Review found and corrected global path-size validation for handle-relative
creation and subtree rename. Recovery checks that same absolute depth/path bound.
Held empty unlinked directories support `info` and empty `listdir`; they cannot
be bases for creating unreachable children. File handles retain coherent shared
inode data after rename, replacement and unlink. Directory `writable` is not a
separate permission capability; private ownership supplies directory authority.
Only file data writes use the handle's writable flag. Root-relative paths are
canonical UTF-8 with no dot components, repeated slashes or normalization. Links
and arbitrary chmod/chown are outside this private API. It is not POSIX complete.

Limits are admission bounds, not a promise that 8,192 maximum-sized files fit.
The fixed backing provider can return NOSPC first. Successful native operations
are synchronous, but a multi-chunk write is not an atomic transaction. An error
poisons the owner; original state is retained and outcomes need separate recovery.
The native library is a pinned private test artifact loaded by pathname, not the
public supervisor's sealed native loader. No public installation is proposed.

The controls use actual images and distinct scopes. Four creation checkpoints
inject exceptions only after completed native calls. Each original is hashed and
left untouched; recovery runs on an exact byte copy with new host-object anchors.
Those controls are not arbitrary crash or physical power-loss qualification.
Owner-path replacement and corruption fixtures remain unrepaired. A full workflow
write is conditional on every semantic scope passing. Its cold reader is a
separate process and runs only after a complete writer receipt. No reduced data,
larger geometry, extended deadline or unchanged retry is authorized by this plan.

The initial authoring syntax command used unavailable `python`; `python3` parsed
the four sources successfully without importing the candidate. This was not a
build or runtime attempt. Review is by the primary agent; helper agents remain
unavailable under their previously reported quota. All sources and test code are
frozen before compilation and execution.

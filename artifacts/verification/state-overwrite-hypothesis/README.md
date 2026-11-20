# Existing-inode state overwrite: source-only hypothesis

The pinned source supports investigating same-file replacement of an **existing**
valid inode `state` record without a temporary-file rename. It does not establish
crash safety for this host stack or authorize adoption. No implementation, build,
control, acquired test or storage workload was executed for this investigation.
The compact candidate, its failed writer and its audit evidence remain unchanged.

The proposed boundary would be only later file-inode metadata updates. Keep
creation staging, `_save_super`, namespace publication, payload writes, 4 KiB
chunks, 128 MiB geometry, canonical envelopes, identity checks and every existing
sync/fsync call. A candidate would remove a separate temporary-file creation and
rename operation, while preserving the replacement file's normal littlefs
sync/close path. The number of avoided commits/barriers must be measured; metadata
compaction, relocation and recovery can perform extra work.

## Source basis

`source-reading.json` pins exact hashes and the selected line ranges actually
read, joined to the Stage 95 seal, the acquired littlefs source catalog and the
compact candidate's frozen inputs. This is a targeted review, not a claim to have
read or proved the entire littlefs implementation. The source is littlefs commit
`6cb4e86540eca0d9ba62500a298385c9d863c8be`, software 2.11 / disk format 2.1. The
current native binary is SHA-256
`6b48f9b9c9a829a8c5c71236c309e7e78f55f096e7c627542a739095ff57ec7a`.

| Pinned source | Relevant observation |
| --- | --- |
| `bridge.c:hm_write` | Bounds size at 16,384 bytes, opens RDWR/CREAT/TRUNC with a private 4 KiB cache, writes the entire buffer, checks its length, explicitly syncs, then closes and checks errors. |
| `lfs.c:3066–3245` | Existing-file TRUNC changes the open file's in-memory state to empty/dirty; it does not itself publish an empty struct. A missing CREAT path instead commits the empty named entry during open. Writable open can first perform native consistency work. |
| `lfs.c:3247–3497` | Close calls file sync unless ERRED. Sync flushes data, orders outlined data with a block-device sync, then commits either the inline body or CTZ head/size in directory metadata. |
| `lfs.c:3580–3706`, `2918–3018` | Outlined writes allocate/erase replacement blocks and extend the CTZ structure; file data is not simply overwritten at the old physical address. |
| `lfs.c:1605–1814`, `1930–2620`, `1106–1390` | Metadata commits append checksummed tags or compact into the other metadata block. Commit sync and readback checks precede success; fetch accepts completed CRC-qualified commits and uses revision/FCRC information. |
| `lfs.c:3969–4108` | Rename itself adds metadata publication work and may cross metadata pairs even when application paths share a directory. |
| `fixed_block.py:222–282` | Provider verification remains per operation. Sync fsyncs every backing chunk; this proposal does not replace it with tracked or delayed sync. |

The evidence suggests an old-or-complete-new **single native file** outcome for
an existing-state replacement under littlefs's storage contract. That is an
inference to test, not a proven guarantee against arbitrary torn host-sector
writes, collateral corruption of old commits or dishonest durability completion.
Metadata CRC and the outer SHA-256 envelope detect different corruption classes;
neither is permission to weaken validation or substitute for a persistence model.

## Creation and error boundaries

Directly creating `state` is unsafe to infer from the existing-file path. Open
with CREAT can durably publish an empty `state` before its content is written.
The hierarchy validates every existing `state`, including unlinked objects,
before cleanup. Such an empty committed state would fail the envelope parser,
preventing orphan cleanup. An incomplete `state.tmp` is already recognized as
staged evidence. Preserve staging for new inodes and initial records.

The current `hm_write` also includes CREAT when replacing an expected existing
record. A future replacement contract should fail if the expected native state
is missing, rather than recreate it silently. A dedicated native existing-only
open without CREAT is the clearest candidate to review; it would require a new
bridge/binary identity and its own controls. An existence check followed by the
current helper must explicitly prove its serialized-ownership assumption and
missing-state refusal. This note selects no implementation.

Errors remain uncertain outcomes. Some failures happen after data or metadata
has become durable. Close may attempt sync when the earlier sync failed before
marking ERRED; the current native callback fault is sticky and rejects subsequent
callbacks. The bridge's short-positive-write check also relies on this pinned
littlefs write path returning the full requested size or a negative error.
Review these paths explicitly and preserve owner poisoning, no blind retry and
retained raw evidence. A failing call must not be interpreted as rollback.

A clean explicit sync clears DIRTY, so the later close need not perform another
metadata commit in that path. That source observation does not authorize removing
either call or any native/provider barrier. Unexpected consistency work, dirty
state, error paths and future library changes require separate treatment.

## Proof obligations before a candidate replay

1. Define a durable-image model with separate volatile/durable bytes and explicit
   sync ordering. Enumerate cuts before/during/after every program, erase and
   sync, including partial program/erase effects and allowed reordering within a
   barrier interval. Drop the entire old native owner at a cut; an ordinary
   injected Python exception followed by normal close is not a power cut.
2. Start from a durably established existing canonical record with distinct old
   and new bytes/lengths. Cover inline-to-inline, inline-to-outline,
   outline-to-inline, outline-to-outline, zero/1/511/512/513 bytes and the 16 KiB
   bridge maximum, including multi-block CTZ writes. Actual compact metadata is
   smaller, but the native contract must not rely on a single-block accident.
3. Force metadata append, compaction, split/relocation, near-full allocation and
   injected read/program/erase/sync failures. Exercise the initial native
   consistency work and missing-existing-record refusal. Preserve originals and
   inspect them read-only before any clone recovery. Repeat cuts during clone
   recovery separately; a successful mount is not enough.
4. On every modeled crash, require the named existing record and exact namespace
   to select only old or complete new canonical bytes/size. After an acknowledged
   successful replacement, require new bytes on cold restart. Check unaffected
   siblings, referenced data, capacity accounting and raw retained evidence.
   Report finite coverage and storage-model assumptions, not universal proof.
5. Recheck hierarchy ordering: new payload chunks must be durable before larger
   size/map publication; shorter metadata must precede chunk reclamation. A
   single native metadata replacement does not make a multi-chunk logical
   pwrite atomic. Retain its current partial-overwrite and poison semantics,
   held handles, sparse tails, strict corruption refusal and clone-only recovery.
6. Only after a separately reviewed implementation and those controls, measure
   callbacks and run the original semantic screen and full 4,270-file / 169-dir
   writer/cold-reader with unchanged 180-wall/120-CPU limits and geometry.

The existing 12 native cases / 1,294 assertions already include successful
same-file replacement across inline and multi-block sizes and cold restart.
Their live/durable model copies all bytes on successful sync and does not cut
inside replacement. They are useful baseline evidence, not the missing cut
proof. Acquired upstream tests include reentrant writes, syncs and partial-program
corner cases, but they were only read here. Their model's atomic-program and
selected out-of-order modes are not exhaustive host power-loss coverage.

The Stage 97 writer still missed its original deadline. Its finite paired screen
showed 12,588 versus 12,012 fsync calls, which does not predict this different
hypothesis or a completed workload. Keep this note as a source-backed question
for the next bounded review; no durability weakening or storage adoption follows.

# Source behavior, implications and limits

The operative bounds are in `lfs_init`: inline_max must fit cache_size, attr_max,
and metadata_max/8 (or block_size/8). With the retained defaults, 512 satisfies
each. The design's more general discussion of a fraction of a metadata block
does not override these implementation checks.

`lfs_file_opencfg_` initializes new and truncated files as inline. The write
path outlines when the maximum of the resulting position and existing file
size exceeds inline_max. The bridge opens, truncates, writes, syncs and closes
each whole native file, using its own full cache. Consequently the return
transition from a large file to 512 bytes uses a fresh truncated representation.
It does not prove every open-handle shrink transition.

`lfs_file_flush` updates inline position and size without flushing a separate
data block. `lfs_file_sync_` includes the inline body in the directory's
INLINESTRUCT commit. Outlined files first synchronize their data before
publishing the CTZ reference. Both paths retain the metadata commit machinery:
`lfs_dir_commitcrc` commits the CRC, invokes the block-device sync path and
reads back the commit CRC. The explicit provider barrier remains a full fsync
on every backing chunk. No source sync, checksum or check is deleted.

Directory compaction and splitting copy inline attributes through the normal
traversal mechanism. The source also handles open inline files during relocation.
The bridge's closed-per-call policy and 512-byte bound below its 4096-byte cache
reduce the exercised cases; they do not establish correctness for a different
bridge, concurrent raw handles or cache configuration. Inline reads use
`lfs_dir_getread` to obtain metadata-backed data through the supplied cache.

The newly complete `test_files.toml` contains simple, large, rewrite, append,
truncate and reentrant cases, varied chunks and inline settings, and collections
of small files. Its reentrant harness semantics include formatting after a
failed mount in some cases. HMS does not adopt that recovery behavior. The file
is read as source evidence; its tests, emulator and scripts are not executed.
The HMS native probe is original code with a modeled live/durable RAM pair.
It tests boundaries, cold readback, directory splitting pressure, rename and
remove, but cannot establish physical power-loss behavior.

The candidate profile changes both the external anchor and canonical on-disk
superblock. Wrong anchors must refuse before opening the provider; a wrong
superblock must refuse before inventory recovery. The audit may inspect the
deliberately wrong-profile fixture with an explicitly selected expected value,
but the production adapter must not accept or migrate it. Paired comparison
must check logical state and full bodies; identical physical encoding or native
callback counts are inappropriate requirements after enabling inline records.

Host resource limits, disabled wear relocation, trusted local ownership and the
prototype native loader remain limitations. This source review does not qualify
Arduino RAM usage, flash endurance, an actual intelligence hub, SQLite semantics,
aggregate service reservations, or an independent physical stop mechanism.

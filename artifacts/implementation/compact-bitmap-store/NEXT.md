# Next storage review after compact bitmap

Preserve this candidate and its failed full-writer image. The 329 focused checks,
426-operation paired screen and successful 35-image audit establish the recorded
finite behaviors; the full 4,270-file writer still times out and its dependent
cold reader did not run. Keep audit-process01's expectation failure and the exact
reviewed correction in audit-process02. Do not rerun the unchanged candidate,
extend 180-wall/120-CPU limits, reduce the data, enlarge the 128 MiB image, change
4 KiB payload chunks, skip fsync or weaken identity checks.

The separate [existing-inode overwrite hypothesis](../../verification/state-overwrite-hypothesis/README.md)
and its source-reading.json pin a source-only question: could a later update to
an already valid inode `state` use littlefs's existing-file commit rather than
creating `state.tmp` and renaming it? The read source distinguishes the two paths:
TRUNC on an existing file changes memory until sync, while CREAT on a missing
file can commit an empty named record during open. An empty newly created
`state` would fail current inventory validation before orphan cleanup. Creation
must retain staging. Superblock and namespace publication remain separate.

Before any implementation or adoption, specify an existing-only replacement
contract that refuses a missing expected state and keeps the full write-length,
file-sync, close-error, provider-fsync and poisoned-owner behavior. Review the
exact bridge and native binary implications. Retain canonical compact metadata
and the full-memory bitmap, payload-before-growing-metadata ordering, and
shorter-metadata-before-reclamation ordering. Same-file replacement would not
make a multi-chunk logical pwrite atomic.

The next evidence needed is a bounded durability-model proof experiment, designed
and source reviewed first: separate volatile/durable bytes, cuts around and
inside program/erase/sync, allowed ordering within barriers, independent cold
inspection, and original-image retention. Cover existing inline/outlined records,
511/512/513-byte transitions, multi-block writes up to the native 16 KiB limit,
compaction/relocation, allocation failure, missing state and uncertain error
outcomes. Require exactly old or complete-new state for modeled crashes and
new state after acknowledged success; test recovery cuts only on clones. The
prior native controls and current Python checkpoint cases do not supply that
proof, and an acquired upstream test suite would require its own explicit source
review and bounded execution authorization.

Only a materially changed, separately reviewed candidate that passes those
controls should reach a fresh semantic comparison and the original complete
writer/cold-reader gate. The compact screen's 12,588-to-12,012 fsync reduction
is one finite observation, not a prediction for the next design. Keep physical
power-loss claims, SQLite/POSIX compatibility, locking, aggregate writer bounds,
pre-recovery resource caps and actually backed control continuations open until
their evidence exists. Persistent device applications, concrete device/driver/
hub I/O providers and independent local stopping remain part of the wider goal.

# Fixed block storage: source review

Stage 82, 2026-11-09. All eleven selected files in [sources.json](sources.json)
were read in full: **7,802 LF lines**. [Reading coverage](reading-coverage.json)
records exact hashes and ranges. The supplemental [fuse2fs manual](fuse2fs/fuse2fs.1.txt)
was also read in full; its original HTML and retrieval record are retained.
This covers the selected files, not either complete repository or the littlefs
core, design or on-disk specification. No acquired implementation was executed.

The original [block-image prototype](../../../artifacts/implementation/fixed-block-storage/README.md)
passes 24 retained controls. It supplies bounded, preallocated positional storage
for investigating a filesystem provider. Neither candidate wrapper reviewed here
is accepted as an HMS control-storage provider. [Detailed findings](NOTES.md)
separate upstream behavior, our inference and the remaining qualification work.

| Source | Pinned identity | Fully read scope |
|---|---|---|
| littlefs | `6cb4e86540eca0d9ba62500a298385c9d863c8be` | README and license, 367 LF lines |
| littlefs-fuse | `423fc8262965b02995fc891cf1eb6b94b281a07c` | README, license, wrapper and block interface, 1,067 LF lines |
| e2fsprogs fuse2fs | `d8e23af0b2dd87b3419d93fca1fef225011be253` | Entire `misc/fuse2fs.c`, 5,841 LF lines |
| Installed Linux man-pages 6.7 | Retained decompressed files and hashes | `posix_fallocate(3)`, `fsync(2)`, `pread(2)`, 527 LF lines |

The source inventory contains exact primary URLs. The supplemental web manual
identifies e2fsprogs 1.47.4 and a 2026-08-03 upstream snapshot; it is distinct from
the locally installed e2fsprogs 1.47.0 package and the pinned implementation file.
The host census found installed libfuse3 3.14.0 and no installed fuse2fs. A
noninteractive sudo privilege listing required a password; no administrator action
or package installation followed. The original experiment needs neither.

The littlefs and wrapper licenses are retained with their redistribution
conditions. The fuse2fs source retains its GNU Public License header. These
acquisitions are research inputs, not a redistributed filesystem implementation
inside the public runtime.

# Native retention traversal references

Nine primary Linux manual pages are retained and fully read: **2,311 LF lines**,
plus their headings and surrounding HTML text. [Acquisition](acquisition.json)
records the first eight downloads and [the close supplement](close-acquisition.json)
records the ninth. Their initial `unread` states remain immutable;
[the reading receipt](reading.json) records subsequent coverage and hashes.

The two recurring images are a book cover and an analytics pixel, not technical
figures. All code examples were read as text; none was executed. Linked references
and kernel/libc implementations remain separate reading work. These pages identify
Linux man-pages 6.19 and do not attest the installed kernel or libc implementation.

The [read-only scan evaluation](../../../artifacts/verification/pat-retention-scan-cost/README.md)
motivates a possible native prototype. The notes below define requirements for
evaluating that prototype, not a production implementation or timing guarantee.

## Source notes

The [open reference](https://man7.org/linux/man-pages/man2/open.2.html) distinguishes
descriptors from open file descriptions. Directory-relative access avoids repeated
ancestor pathname resolution, but `O_NOFOLLOW` protects only the trailing component.
`O_DIRECTORY` prevents opening another file type; `O_CLOEXEC` avoids a separate
close-on-exec setup race. `O_RDONLY` is an access-mode value, not an independent
bit. Nonblocking mode does not make ordinary file I/O bounded. Direct I/O has
filesystem, alignment and concurrency caveats and is irrelevant to this metadata
scan. Synchronized writes have distinct data/metadata guarantees; closing is not
a substitute. All 1,040 retained lines, including unrelated flags, errors and
examples, were read. No flags or system configuration were changed.

The [stat reference](https://man7.org/linux/man-pages/man2/fstatat.2.html) specifies
relative `fstatat` lookup and `AT_SYMLINK_NOFOLLOW`. A stat structure can combine
fields observed at different instants; it is not an atomic filesystem snapshot.
Sizes and inode values can overflow narrow application types. All 319 lines were
read. A native candidate must use adequate integer widths, preserve error handling,
check every entry's actual metadata and retain the original concurrency limitations.

The [readdir reference](https://man7.org/linux/man-pages/man3/readdir.3.html) says
that null can mean either end-of-stream or error; clear and inspect `errno` to
distinguish them. Returned entry storage can be reused by a later call. Directory
order is filesystem-dependent, and `d_type` can be unknown. Fixed-size assumptions
about `d_name`, even a customary 255-character limit, are unsafe across filesystems.
All 218 lines were read. The candidate should use each name synchronously, avoid
copying it into a fixed-size buffer, and call `fstatat` regardless of `d_type`.

The [fdopendir reference](https://man7.org/linux/man-pages/man3/fdopendir.3.html)
transfers successful descriptor use to the directory stream. Its close-on-exec
behavior differs from `opendir`; open with the intended flags first. All 128 lines
were read. Failure leaves an explicit cleanup obligation; ownership must change
only after successful stream creation.

The [dirfd reference](https://man7.org/linux/man-pages/man3/dirfd.3.html) returns
the stream's internal descriptor for operations that do not change its position.
It is borrowed and is closed by `closedir`. All 94 lines were read. The candidate
can use it for relative metadata and child-directory operations without separately
closing or repositioning it.

The [closedir reference](https://man7.org/linux/man-pages/man3/closedir.3.html)
defines stream and underlying-descriptor closure, including the error return.
All 75 lines were read. Each successful stream construction needs one close on
all return paths; a failure must not become a successful scan.

The [dup reference](https://man7.org/linux/man-pages/man2/dup.2.html) explains that
duplicates share offsets and file status flags, while close-on-exec flags differ.
Separate close-and-duplicate operations can race with descriptor reuse; `dup2`
and `dup3` have different same-descriptor behavior. All 179 lines were read. Any
future borrowed-root API must define whether scanning advances the shared offset
and how duplicated descriptors are owned; duplication does not create a fresh
directory position.

The [getuid reference](https://man7.org/linux/man-pages/man2/getuid.2.html)
distinguishes real from effective user identity and documents successful return
without modifying `errno`. All 73 lines were read. Preserve the original real-UID
comparison and per-entry call; caching or substituting the effective UID would
need a separate semantic justification.

The [close reference](https://man7.org/linux/man-pages/man2/close.2.html) warns
that Linux frees descriptor numbers early, so retrying a failed close can close a
reused descriptor. Other platforms differ for interruption, including the
POSIX.1-2024 rule described by this version. Closing can release record locks and
does not prove data durability. All 185 lines were read. The prototype must be
explicitly Linux-scoped, avoid close retries, preserve the primary failure during
cleanup, and avoid touching any original owner/writer-lock descriptor.

## Evaluation boundary

First compare a standalone original C prototype with the exact Python reference
on synthetic filesystem fixtures, including refusal paths. Then measure a fixed
number of scans under the original retained-tree locks. The prototype should
open directories only, inspect file metadata, skip only `.` and `..`, preserve
depth/count/byte and ownership/mode/link rules, and return structured failure.
No data file needs to be opened. Native calls bypass Python audit callbacks, so
source review and explicit syscall/operation evidence need their own treatment.

An in-process binding, cancellation/signal semantics, deployment artifact identity,
compiler/runtime provenance and non-Linux support are separate integration work.
A standalone timing improvement would not qualify the complete worker, storage
reservation, device I/O or learned PAT path.

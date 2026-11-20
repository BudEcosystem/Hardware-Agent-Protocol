# Compact bitmap hierarchy: focused controls passed, full writer incomplete

The explicit compact-bitmap profile passed 329 newly executed focused checks
and the paired 426-operation semantic screen. The unchanged full workload still
missed its original 180-second deadline. It is not qualified for service storage
or public-runtime adoption. The failed writer image, progress and all control
and audit receipts are retained.

The candidate keeps a full 512-byte bitmap in memory and serializes exactly
`ceil(ceil(size / 4096) / 8)` bytes in canonical base64. It rejects invalid sizes,
wrong lengths, noncanonical base64 and nonzero EOF bits before padding. Encoding
validates discarded bits and copies the inode without changing the caller's
map. The profile is `hms.hierarchical-chunk-store.compact-bitmap/0.1`; old profiles
are explicitly refused. Directory encoding, payload ordering and recovery logic
remain unchanged. PLAN.md, REVIEW.md, source-reading.json and exact diffs retain
the reviewed scope and source joins.

## Executed evidence

| Focused scope | Newly executed passing checks |
| --- | ---: |
| Compact codec, edges, malformed metadata and interruption | 149 (77 / 27 / 12 / 33) |
| Original hierarchy controls | 96 |
| Original mount-identity controls | 52 |
| Original fixed-block provider tests | 24 |
| Explicit previous-profile refusal | 8 |
| Total | 329 |

The exact unchanged native binary's prior 12 cases / 1,294 assertions were hash
revalidated, not rerun and not counted among the 329. They include successful
inline/outlined replacement and cold restart. The new target cases cover empty
and maximum sparse files, 7/8/9-chunk bitmap transitions, growth and shrink across
the native inline-size threshold, shared handles, valid-envelope malformed
maps, and four interrupted write/publication/shrink paths. Failed original
images are preserved; recovery controls operate only on exact-byte clones.
These injected boundaries do not constitute physical power-loss testing.

The paired 40-file screen used the same native binary, provider, workload and
geometry for both profiles. Full bodies, normalized inode metadata, namespace
and all 426 logical results matched. Physical encodings and native callbacks
were allowed to differ and did differ. Both retained the original provider
fsync relation.

| Finite screen observation | Prior inline profile | Compact profile |
| --- | ---: | ---: |
| Wall seconds | 7.876590 | 7.508320 |
| CPU seconds | 2.443374 | 2.361138 |
| Provider fsync calls | 12,588 | 12,012 |

The 576-call reduction is about 4.6% in this screen. These individual timings
include run variation and establish neither a general speedup nor full-workload
completion. No result is extrapolated to a different dataset or hardware.

## Full writer and retained-byte audit

The full writer used the original 4,270 files, 169 directories and 35,508,922
source bytes in an eight-chunk 128 MiB image. Its terminal receipt records
180.113868625 seconds wall, 39.073606 seconds CPU, 24,576 KiB peak RSS, return -9
and a wall timeout. The runner killed the still-owned group, reaped the child
and verified group absence. There was no writer stderr or monitor/cleanup error.
The dependent full cold reader was not launched.

The successful independent audit verified the exact ordered prefix of 1,814
complete files / 7,800,513 bytes and all 169 directories. It found no additional
published file, pending entry, unlinked inode, incomplete physical inode or
partial progress tail. Those findings describe the retained incomplete image;
they do not turn it into a complete workload result.

The audit inspected 35 retained images with read-only backing descriptors:
18 original hierarchy, two profile, two comparison, twelve new target images
and the writer. It reconstructed exact bodies, normalized only already-validated
compact maps, checked clone lineage and preserved all raw backing hashes. Each
of the three intentionally malformed bitmap images had to fail the normal
reader and match a separate exact malformed-state/sentinel inspection. No
adapter recovery was invoked by either audit.

The first audit stopped before image inspection because its source incorrectly
required provider stderr to be empty. That retained stderr contains the 24
successful unittest progress entries and summary, plus CPython's expected
DeprecationWarning from the deliberate multithreaded fork-refusal control.
Audit-process01 returned 1 cleanly after 2.965432638 seconds wall / 2.888785 CPU.
The original audit sources and process evidence are retained unchanged.

AUDIT-REVIEW02.md and audit-correction02.patch record the specific correction:
the second auditor joins the exact reviewed stderr SHA-256
`2b9c206ae57a84935b8e6671df5970b283455f72639845139455836c922011d2`
in place of that one empty-stderr assertion. All other assertions remain. No
candidate scope was rerun. Audit-process02 passed in 9.462870696 seconds wall /
9.290911 CPU with empty audit stderr. Its exact stdout, terminal receipt and
frozen audit sources were joined by the parent. EVIDENCE-AUDIT.json SHA-256 is
`3132f0c550b15a8d9815aa8a8642941531c6e2bf6f77928034c143f5ef705ff4`.
All 19 workload children and both audit children were reaped with absent groups.

## Boundaries retained

Every payload chunk remains 4 KiB; the native inline limit remains 512 bytes.
The native and mount binaries, statx identity checks, full provider fsync behavior,
canonical metadata checks and original replay source remain unchanged. Focused
children use 60 seconds wall / 40 CPU; the full writer/reader gate retains 180
wall / 120 CPU. All children retain 512 MiB address space, 128 descriptors and
16 MiB per-file limits. The public 244-file baseline is exact and unchanged.

This is private implementation evidence, not a mounted POSIX filesystem, SQLite
qualification, durable concurrent-writer proof or demonstrated hardware control.
The source-only follow-up in NEXT.md is unimplemented. This result does not
authorize weakening durability checks, extending deadlines, reducing the dataset
or adopting the candidate.

# Next work after the synchronization screen

Keep this profile isolated. Its error observation and acknowledgement controls
pass, but the full writer still misses the original deadline. Fewer fsync calls
are not sufficient evidence for public adoption or for another speculative
synchronization reduction. Preserve all current and earlier failed images;
no unchanged retry, repair, larger image, smaller workload or longer deadline.

The paired screen cuts full fsync calls from 13,724 to 3,467, while wall time moves
only from 9.82 to 8.77 seconds. Remaining cost therefore warrants a different
investigation. Counts do not establish where full-workload time is spent. The
new native wait path and bookkeeping also add complexity, so do not make this
profile the default merely because its focused tests pass.

Next inspect the hierarchy's physical representation and native publication
path. The current littlefs bridge disables inline files, while the hierarchy
stores many small directory-entry and state records as separate files. Read the
complete relevant littlefs inline/outline, file-sync and directory-commit paths
and the earlier reasons for disabling inline storage before changing anything.
This is a hypothesis about avoidable metadata work, not an established cause.
Do not remove a required internal littlefs sync or weaken publication ordering.

Use a bounded diagnostic of the real dataset's file shapes and current native
operation counts if the source review does not identify a sound change. A later
representation/configuration candidate must keep the original API, bounds,
namespace, full bodies, recovery behavior and durability obligations. Its
physical encoding may differ, so compare logical content and declared metadata
directly rather than demanding equal raw image hashes across different layouts.
Preserve exact bytes within each retained run and its audit.

Any next whole-workload attempt still requires frozen/reviewed inputs, all
original provider and 96 hierarchy controls plus targeted new controls, followed
by the original 4,270-file/169-directory, 128 MiB, 180-wall/120-CPU writer and cold
reader. Consider the simpler statx provider as the baseline unless measured
evidence justifies combining this separate synchronization candidate. Do not
silently migrate manifests or mix qualification identities.

The original goal remains active: complete filesystem/SQLite integration and
recovery; pre-recovery capacity checks, aggregate limits and backed control
continuations; natural-language learning into qualified deterministic PATs;
persistent Arduino applications; physical I/O, driver and intelligence-hub
providers; local stopping/outage behavior; microscope commissioning; native
Harness installation; remaining full-source research; and home, scientific and
manufacturing qualification. Missing evidence is not novelty or authority to
repeat an uncertain physical effect. No public runtime change is made here.

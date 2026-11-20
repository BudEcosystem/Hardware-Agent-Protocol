# Fresh configuration metadata consolidation

The preceding turn made verified progress: the current diagnostic and failed
qualification were sealed, and all 161 public-runtime inputs still matched the
861-test receipt. This experiment follows the measured SQLite work without
changing the complete qualification matrix or any original execution bound.

Keep schema inspection and the separate row-count limit check. Combining count
with cell aggregates could scan cell contents before rejecting an oversized
table; a conditional aggregate does not by itself preserve that early guard.
The legacy `_table` therefore remains unchanged. In `_configuration_table`,
combine only the subsequent storage-class and maximum-byte-length queries.
A minimum of the conjunction of exact `typeof(column)` comparisons is one iff
every row has every expected class. Empty input produces null, which the existing
zero-count condition accepts. Check count, then types, then sizes in the original
order. Keep public registry metadata filtering, ordered bounded row loading,
per-cell validation, page construction, locks, identity and durability unchanged.

Compare exact extracted baseline and candidate methods against fresh in-memory
SQLite fixtures. Use the original errors, JSON validation/canonicalization and
canonical-blob checker, with an explicitly substituted in-memory evidence sink.
The sink canonicalizes complete page envelopes and returns digest references;
it does not emulate durable publication, budgets or flush/fsync. No HMS runtime
package, interrupted database, qualification worker, physical endpoint, inference
service or network is opened. Retained configuration JSON is data only.

Cover all fifteen table specifications, all SQLite storage classes, empty and
paged data, row and byte boundaries, schema and registry-key changes, malformed
UTF-8/JSON, duplicate keys, mixed invalid conditions and exact refusal order.
Inject changes immediately before aggregate metadata acquisition and immediately
before row loading, and change data between captures. These are selected boundary
checks, not proof against arbitrary concurrent writers. The surrounding original
ownership/locking requirement remains mandatory.

Record actual SQL calls and exact returned structures, page bytes and refusals.
The original row guard must stop before either metadata query for over-limit data.
Source extraction and the unchanged method suffix must be checked independently
of executing the candidate. Keep every failure; do not rerun an unchanged
benchmark to obtain a better result.

One isolated child has 30 CPU seconds, 60 wall seconds, 512 MiB address space,
16 MiB individual file size, 64 descriptors and 4 MiB retained output. It may
connect only to `:memory:` SQLite and cannot write files. Use nine fixed
alternating timing pairs, each with sixteen captures of all fifteen retained
baseline table fixtures, after a fixed warmup. Report raw samples and ratios.
These timings exclude durable I/O and cannot qualify the complete worker.
Advancing to whole-worker integration requires all semantic checks, one fewer
SQL call per accepted table, median CPU ratio at most 0.95 and at least eight of
nine pairs faster. This is an engineering screening rule, not a statistical
confidence claim. Local success never constitutes production adoption.

The full objective remains active: installed public PAT qualification, backed
control capacity, Harness integration, prompt learning and deterministic reuse,
persistent MCU programs, device/driver/hub providers, microscope commissioning,
research completion and home/laboratory/manufacturing scenarios remain required.

# Exact page encoding after current SQL validation

The [previous group stage](../pat-io-group-history/results/README.md) independently
checks a complete historical group, but current capture still misses the original
deadline. The earlier [profile](../pat-io-group-efficiency/PROFILE-ANALYSIS.json)
identifies repeated page construction/encoding; the encoding stage removed the
second writer encoding but still encodes unchanged pages at every checkpoint.

This candidate keeps every current SQL schema, count, size, storage-class and row
read, as well as each cell check and the locks across both evidence streams.
Only exact canonical page bytes and their hash are memoized after those checks.
The key includes profile, stream/domain, table, columns, offset, total row count,
cell tags and exact typed immutable scalars. Caller lists/dictionaries are never
retained. Changed rows, types, projections, counts or profiles cannot inherit an
old page. Unsupported page shapes use the original canonicalization path.

Each engine retains at most 128 encodings and 1MiB of encoded bytes. This is a
cache capacity, not a raised evidence, input or execution limit. Eviction only
causes recomputation. Existing writer checks, reservation order, reference reuse,
record/byte charging, exclusive create, flush/fsync and failed-write retention
remain. No cached encoding asserts a published durable record or an outcome.

The new source contains all 225 current production/test inputs, with the prior
3972 historical fixture files and their dedicated retrospective test omitted
from this worker closure. Their exact exclusions and the original source index
are recorded; every original remains immutable. Full GPIO/PWM history tests keep
their complete original capture and independent-reader assertions.

No deadline, case, effect, protocol or storage ceiling changes. Physical devices,
MCUs, inference, external controllers, live HMS and the adjacent Harness are not
executed. This stage cannot establish public qualification, current process/run
attestation, hard aggregate quota or physical behavior.

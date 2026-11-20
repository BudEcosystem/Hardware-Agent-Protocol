# Source-grounded history-read cost hypothesis

This is a call-count derivation, not a runtime measurement or capacity result.
The original sealed boundary attempt timed out after 68 completed prepared-only
settlements. Its retained interruption stack names `pending()` and canonical
validation; one interrupted frame cannot establish where all elapsed time went.

The original `mutation_capacity` prefix prepares a new START under a distinct
key, interrupts after the durable reservation and before possible handoff,
explicitly abandons that prepared intent using STATUS evidence, and checks that
no pending mutation or endpoint mutation sequence remains. No SQL prefill is
used. For an iteration beginning with `n` settled rows, all at proposed endpoint
sequence1 while the actual endpoint mutation sequence remains0:

| Path | Calls to complete `mutation()` validation |
| --- | ---: |
| Reservation's `pending()` scan | n |
| Reservation's original same-sequence body-reuse check | n |
| Host abandonment selects the original row | 1 |
| Store abandonment selects the original row | 1 |
| Store abandonment's pending scan, including its repeated read of the prepared row | n+2 |
| Store abandonment returns the validated settled row | 1 |
| Original post-abandon pending assertion | n+1 |
| Total | 4n+6 |

The sequence-zero branch of `_known_sequence` performs no mutation-history scan;
that assumption is essential to this count. The distinct new key has no prior
row, so the earlier replay lookup adds no `mutation()` call. The formula predicts
2,176 validations for32 iterations, 9,520 for68, and 28,798 for119. Each such
validation currently performs two SELECTs in `_read_locked`, bounded parsing,
canonical-byte equality, typed record checks, wire parsing and body/field checks.
This predicts 4,352 SELECTs for the32-loop mutation reads alone, not total SQL.

`pending()` reads a settled row once. Its duplicate read applies only to selected
pending rows, so merely deleting that duplicate cannot remove the history-growth
cost. Reservation separately revisits all same-sequence original identities;
removing that check would change original-key semantics. Returned mutable Python
objects and callbacks also prevent assuming that a broad cached snapshot can
replace fresh validation throughout an operation.

The full250-line current `contracts.py` was reread. Its canonical encoder checks
dependency compatibility once per canonical call, not once per JSON node.
Parsing and canonicalization each validate their input tree. The existing
`pat_io_canonical_blobs.py` was also read in full: it reuses successful immutable
byte membership under bounded retention and compatibility guards, while callers
still read current storage. It retains only64 entries, not an entire128-record
history, and returns a canonicality Boolean rather than parsed mutation state.
That precedent does not establish the correctness or benefit of a new store cache.

The next evidence should come from a separately identified32-iteration diagnostic
over unchanged production, with nested method counts/times, authority/setup
costs and the original raw protocol/database evidence. Timing is intrusive and
includes its own measurement overhead. A complete32-loop result would validate
this count model and help select an optimization; it would not pass the original
128-record capacity test or change its thirty-second failure.

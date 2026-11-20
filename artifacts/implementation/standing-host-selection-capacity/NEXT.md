# Next gate and remaining source costs

The complete original capacity workload still fails the unchanged 30-second wall
bound despite the validated pure-compilation call-count reduction. The previous
32-loop timing diagnostic used the older host plus intrusive instrumentation;
this run is a different full workload without that instrumentation. Neither
68→110 settled records nor the final interruption at COMMIT establishes a general
speedup or identifies the dominant cost. No optimization is implemented here.

A source read of the unchanged current path identifies repeated work that can
be investigated without dropping the original semantics. In a completed
prepare→explicit abandonment→public pending assertion loop, let n be the prior
settled mutation count. The following are full `mutation()` validations, not
measured time or parser-only calls:

| Path | Validations | Current source |
| --- | ---: | --- |
| Reserve checks pending history | n | [standing_store.py](project/hms/standing_store.py#L476) |
| Reserve checks prior requests at the next endpoint sequence | n | [standing_store.py](project/hms/standing_store.py#L530) |
| Abandon reads the selected record in host/store and returns it | 3 | [standing_endpoint.py](project/hms/standing_endpoint.py#L397), [standing_store.py](project/hms/standing_store.py#L875) |
| Abandon checks pending history, reading its prepared record twice | n+2 | [standing_store.py](project/hms/standing_store.py#L458) |
| Original control's final public pending assertion | n+1 | [boundary_controls.py](boundary_controls.py#L330) |

Thus each completed prefix loop performs 4n+6 validations. The original 119-loop
preparation phase implies 28,798 validations; this is a static logical count,
not an executed full-phase observation or elapsed-time prediction. Each
validation performs two SQL SELECTs in [_read_locked](project/hms/standing_store.py#L94),
first checking storage type/length/cardinality, then retrieving the blob. It
parses bounded JSON, checks canonical bytes and the full mutation field/type,
key, wire reconstruction, digest and sequence/lease/ACK relationships in
[mutation](project/hms/standing_store.py#L432). Both parse and canonicalization
walk the tree in [contracts.py](project/hms/contracts.py#L106). Settled records
are currently revalidated too; their state is not permission to skip validation.

The same loop crosses eight Journal transactions: first STATUS reservation,
receive and state commit; the selection inventory transaction; mutation
reservation; abandonment STATUS reservation and receive; abandonment settlement.
Seven write business state and one reads selection inventory. Every one passes
the installed whole-table logical-capacity scan and commit boundary in
[journal.py](project/hms/journal.py#L293). The checker performs a table-list query,
three reads per actual table, row charge/partition checks and the applicable
aggregate ceilings in [standing_capacity.py](project/hms/standing_capacity.py#L30).
The journal retains DELETE/EXTRA durability settings. These scans and commits
are additional repeated work, not part of the 4n+6 JSON-validation count.

Fresh authority work also remains: `_selected` runs twice and `policy.fresh`
four times per completed ordinary reservation loop, including the registered
final commit check. `_extension` retains separate policy, driver and producer
holds. Source inspection counts 45 bounded file reads per loop: 13 host sources
plus interpreter; 13 driver sources plus native image; 12 qualification sources
plus five evidence files. These are scoped source/image/evidence checks, not a
single interchangeable cache. The exact selection and final guard path is in
[standing_endpoint.py](project/hms/standing_endpoint.py#L222),
[standing_pat.py](project/hms/standing_pat.py#L621) and
[standing_contracts.py](project/hms/standing_contracts.py#L231).

Repeated deployment-row parsing, immutable-field checks, route reads and wire
decoding are additional work. `_response_owner`, for example, reads a live row
for both its filter and result. The first 119 loops take `_known_sequence`'s
zero-sequence branch, which avoids another history scan. After the accepted
START, the original tail's STATUS/settlement paths take the nonzero branch and
validate candidate history again in
[standing_store.py](project/hms/standing_store.py#L335). Any subsequent analysis
must cover that tail and the separate common REVOKE, ACK and RETIRE semantics;
optimizing only the initial 119 loops cannot stand in for completing the case.

The narrow next source candidate is a bounded whole-history read within one
fresh pure call under the existing mutex/transaction, if exact validation order
and errors can be preserved. It should keep current type/length gates before
materializing record bytes, number ordering, 128-record overflow refusal, every
canonical/wire/key check, detached results, and the original first failing error.
A bulk read may reduce per-record SQL round trips and the duplicate prepared-row
read in pending; it does not by itself remove quadratic validation across calls
or guarantee completion within 30 seconds. Establish those equivalences before
claiming an optimization benefit.

Do not reuse the initial pending view across the admission callback/policy
freshness boundary before the late duplicate-control-key scan. Do not retain a
view across separate calls, transport, COMMIT, rollback, reopen, source/helper
changes or later mutation writes. Preserve final capacity scans, current
catalog/policy/evidence/image guards and every public-writer assertion. No
cross-call authority cache, skipped settled-row validation, SQL prefill, altered
synchronization, larger limit, reduced history or staged relabeling is proposed.

A separate reviewed candidate needs negative controls for malformed/noncanonical
or oversize rows, storage types and 128/129 cardinality, earliest-error order,
SQL/JSON/wire key disagreement, changed records between calls and at callback
boundaries, detached results, prepared/possible/accepted/refused/abandoned rows,
rollback and reopen. Keep original-key replay and common-REVOKE uncertainty
controls. Only after that review should root run the unchanged 119→120→126→128
case on the same peer under 30 seconds, 32 MiB per file and the existing CPU/memory/
FD/cleanup bounds. Preserve any next failure. Other reachable-capacity, physical
and deployment gates remain open; the halted replacement branch stays closed.

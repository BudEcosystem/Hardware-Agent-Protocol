# Repeated history-read model and diagnostic scope

The source analysis concerns the exact copied production at
`project/hms/standing_store.py`, SHA256
`f67b0518d7cbd3ec1cabf0dbe4b0cad2b30f4ea6923bdaf0fc9f234135837373`.
Its bytes match the sealed host and boundary parents. The failed boundary stack
was one sample inside `pending`; it does not establish the dominant time cost.

The exact original boundary loop is retained in the parent at
`boundary_controls.py:320–335`. Before iteration n there are n settled,
never-handed-off START records at endpointSequence1. For that loop:

| Original path | Mutation validations |
| --- | ---: |
| reserve: pending plus same-sequence history | 2n |
| explicit abandon: host lookup, store lookup, pending, returned mutation | n+5 |
| original final pending assertion | n+1 |
| complete iteration | 4n+6 |

Summing n=0..31 predicts 2,176 validations; the corresponding `_read_locked`
calls each issue two original SELECTs, predicting 4,352 stored-record SELECTs.
There is no independent SQL trace measurement. The arithmetic predicts 9,520
validations for 68 complete loops and 28,798 for 119; it predicts no wall time.
Initial setup and final verification reads are reported separately.

Source ranges actually examined for this model:

- Store91–105: mutex, type/size shape query before raw fetch, parse and canonical
  equality. Shape/type limits must remain fresh on every future optimized read.
- Store335–353: known-sequence zero fast branch avoids additional history reads.
- Store432–545: every mutation's exact field, type, wire/body/key validation;
  pending reads all numbers in order with the 129-entry capacity check before row
  decoding; reservation also scans same-sequence candidates. Pending decodes a
  pending entry twice, but a settled entry once.
- Store872–900: explicit never-possible settlement, pending singleton proof,
  STATUS association and immutable original mutation identity.
- Coordinator `standing_endpoint.py:245–319,381–406`: original-key lookup,
  prepare commit, injected pre-handoff boundary and explicit abandonment.
- Journal185–335,337–413: owner/mutex/transaction lifecycle and current commit
  checks. Reusing a view across a trusted callback, write, rollback or reconnect
  would require an independent freshness proof.
- Contracts106–190: exact parser restrictions, canonical equality and current
  encoder/function/default/constant checks. The diagnostic changes none of them.
- `standing_contracts.py:225–273`, `standing_pat.py:241–337,578–618` and
  `standing_endpoint.py:1–85`: actual image, driver, catalog and original-evidence
  context acquisition/check/release, included in diagnostic timing scope.
- Original Fixture1–160: immutable installed topology, real pipe process,
  original qualification publication, inherited descriptors and clean EOF close.

No optimization is applied. A future proposal must preserve error order and
all retained-row validation, including settled/refused/never-handed-off history;
must not fetch unbounded blobs before shape checks or cache mutable returned
objects; and must retain current parser/encoder/source/authority checks. Removing
only pending's second decode saves one validation per loop, not the full repeat.
Batch reads reduce query dispatch without proving that parsing or canonical
work dominates. Reuse within one fresh operation may remove more repeated work,
but must account for every callback and transaction boundary first.

The existing bounded `pat_io_canonical_blobs.py` is not adopted. Its guarded
successful-bytes memo has capacity64 and does not itself remove semantic decode
or prove a 128-history working set. Global canonical optimization would affect
other qualification paths and is not justified by this single failed stack.

Any later production optimization needs source review and meaningful controls
for malformed/oversized historical rows, 128/129 error ordering, changed helper
code/constants, returned-object mutation, writes/rollback/reopen and withdrawn
authority, followed by the original capacity semantics. The current diagnostic
is evidence gathering only; the full reachable-capacity gate remains open.

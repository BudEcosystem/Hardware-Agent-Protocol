# Retained-control validation correction

The independent read found that size bounds and selected run/digest associations
in `_row` do not close the stored control grammar. A corrupted archived record
could assert semantic qualification, an enforced disk quota, or zero unresolved
effects, or contradict known process failure through `transportComplete=true`.
An unknown state or an archive attached to a nonterminal record could also survive.
The parent full696 execution hold was respected. After release, attempt07
retained one test method with 11 failing corruption subtests against unchanged
attempt06 source. Attempt08 then passed all 19 tests on the corrected source.

The correction closes record and archive fields, enforces exact scalar
types and bounded identifiers, verifies legal state-history edges and terminal
association, and derives the only permitted `transportComplete` combination:
normal owned zero exit, no recovery/stop/validation failure, retained return and
complete byte integrity. Semantic qualification and quota flags stay false;
control unresolved effects stay null. Worker-specific facts remain in the raw
return and are separately reduced before any later qualification.

Malformed control metadata will raise `QUALIFICATION_LEDGER_INVALID`; reads will
not repair it, release a slot, relaunch a worker, or invent replacement keys.
Canonical request and return digests remain required. This is consistency and
bounded parsing, not authentication against a trusted UID rewriting all control
records; the original trust/root policy and later full evidence verification
remain explicit boundaries.

Meta/active-ID reads now check type and bounded row counts before fetching
variable-sized stored values. Schema matching uses fixed equality queries
instead of fetching arbitrary table names. Active/missing/partial schema
behavior stays fail-closed. All before-source and failed outputs remain retained.

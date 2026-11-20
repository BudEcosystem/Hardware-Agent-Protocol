# Next source decision after the diagnostic

The original 30-second mutation-capacity failure remains failed. This 32-loop
diagnostic supplies measurements; it does not satisfy the full 128-record gate,
authorize a larger execution cap or justify staged execution as an old-case pass.
No production optimization has been implemented here.

The reviewed retained-data audit has now passed. It independently joined the
original history, source-count model, closed metrics, actual wire and owned
cleanup. The next step is a source proposal, not another diagnostic execution.

The observations narrow the next source investigation. Loop-only current catalog
selection consumed about 1.929 seconds of measured exclusive wall time; image
context entry about 0.827 seconds; current policy/installation checks about 0.809
seconds. Mutation raw reads plus the remaining mutation validator span totalled
about 0.411 seconds for 2,176 validations. These intrusive measurements do not
prove which computation dominates a longer run, but they do not support treating
one captured `pending` stack as sufficient grounds for a broad canonical cache.

A concrete next hypothesis is repeated pure installation/artifact validation in
`_selected`, `_compiled` and `compile_artifact`. A private, already-validated,
detached snapshot restricted to one uninterrupted pure call chain may avoid
duplicate work. That is a source hypothesis: the measured `_selected` span is an
aggregate, not attribution to one inner parser. Source call counts and narrower
probes or equivalence controls may be needed before selecting an optimization.
The O(n²) history scans and 2.901843698 seconds outside the measured loop spans
also remain relevant; neither is explained away by the selection measurement.

The proposal must identify exact inputs, immutable compiled results, current
dependency/source identity and invalidation points before introducing bounded
reuse. Current
storage bytes, canonical/type/wire validation, owner/policy identity, enabled
state, held-evidence expiry, catalog decision and final transaction checks must
remain effective, including `Policy.fresh` and all commit checks. There must be
no cross-callback lease extension or cached authority. Reusing an earlier approval after a callback or across a write,
rollback, reconnect or owner change is not an acceptable optimization.

For a history-read change, preserve the 129-entry capacity check before row
decoding, original ordering/error behavior, validation of all retained terminal
and never-handed-off records, bounded blob reads and detached mutable results.
If the proposed change touches canonical/parser or whole-profile helpers, it
must account for their wider existing qualification scope. The current 64-entry
canonical-blob memo is neither a 128-record working-set solution nor semantic
decode validation by itself.

Any candidate must be isolated, reviewed and tested with meaningful negative
controls: changed source/helper identity, malformed or oversized historical
records, original-key/sequence conflict, returned-object mutation, storage
rollback/reopen, catalog or installation withdrawal and post-COMMIT evidence
expiry. Then run the complete original capacity semantics under the original
30-second profile, preserving every prior failed attempt. Do not lower the 128
record requirement, omit reserved settlement continuations, prefill by direct
SQL or release claims through unrelated STOP/RETIRE cleanup to make the test fit.

The separate unexecuted boundary profiles for episodes, activations, retained
keys, fixed public writers and the explicitly labelled arithmetic model remain
open. A future staged workload, if still needed, must separately bound total
guardian lifetime, aggregate storage and owner steps while joining original keys,
same live endpoint and epochs; it cannot be relabelled as the old 30-second case.
The halted existing-state-replacement branch remains closed.

All of this remains local synthetic qualification. Device I/O/driver and hub
control need their actual installed provider contracts, recurring authority,
physical qualification and protected storage/capacity evidence before a prompted
application can be eligible for real deployment. This diagnostic establishes
none of those external capabilities.

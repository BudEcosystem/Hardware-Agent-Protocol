# One-call topology and proof construction

Status: **63 pure controls pass; full actual scope fails before import**. This is
an isolated candidate, not a qualified end-to-end release. The full HMS goal is active.

Two production modules now share one detached topology/generation snapshot within
a pure installation-definition build. Each instance still receives its own complete
proof derivation, schema check, canonical bound and detached result. Public proof
and handler calls remain fresh, and current source, authority, session, resource and
effect checks are unchanged. See the [design](DESIGN.md),
[source review](implementation01/source-review.json) and [patches](patches).

All 63 selected pure methods pass: 21 definition/normalization controls, 21 topology
controls, 11 schema-memo controls and ten new differential/measurement controls.
The baseline function bodies and factored proof body are AST-checked. For the
four-instance fixture, topology and generation validation fall from four calls to
one, graph-index construction falls from eight calls to two, and all four complete
proof derivations remain. Seven fixed alternating measurement pairs show a median
CPU ratio of 0.6161 for definition building, about 38% lower; every pair is lower.
These are local pure-build observations, not whole-worker or deployment timings.
[Pure audit](PURE-RESULTS.json), [original receipt](harness01/attempts/attempt01-pure63/result.json).

The fresh actual vault-import trial still reaches the original 60-second worker
deadline. It requests all 30 cases and retains 20 directories and 19 manifests;
`late_parent_reporting` is incomplete. The supervisor archives exit code -15 with
no complete return, no transport completeness and unknown unresolved worker effects.
The test stops before import. The source authority has one original reservation
and handoff, zero import intents/publications and an empty 8,192-byte installed
vault. There is no source PAT invocation, catalog activation or cold-history result.
[Actual receipt](harness02/attempts/attempt01-actual/result.json), [audit](RESULTS.json).

The completed audit verified all 2,496 raw and copied scratch files (13,382,189
bytes), actual source/dependency origins, 262 producer-image files and independently
recomputed consumer identities. It acquired 37 original owner/writer locks and
verified unchanged bytes for four source databases. No interrupted worker case
database was opened or recovered. The observed spawn-to-settlement interval was
60,071 ms; this does not establish why the workload missed its deadline.

At continuation, the two original temporary trees were no longer present. The
[retention recheck](RETENTION-RECHECK.json) verifies their retained copies against
the original terminal inventories and audit hashes. It opens no database, recreates
no missing path, and makes no new original-inode ownership claim. The prior audits
and both original results remain unchanged.

A [post-run host snapshot](host-observation.json) is retained separately. It is not
contemporaneous process evidence and establishes no timeout cause. [Next work](NEXT.md)
is bounded whole-worker resource observation before another performance change.
No physical device, MCU, model, network or live service was executed; all actual
provider, persistent Arduino and prompt-learning requirements remain open.

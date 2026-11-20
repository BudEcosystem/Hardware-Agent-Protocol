# Pure validator evaluation

Status: **468 differential cases pass; candidate not adopted**. Production remains
unchanged. [Results](RESULTS.json), [scope and limits](REVIEW.md),
[one original attempt](attempt01/result.json), [raw measurements](attempt01/stdout.json),
[read-only audit](audit.py), [candidate diff](candidate.patch).

The [current worker profile](../pat-vault-worker-profile/README.md) identified
repeated JSON validation as a cost. This evaluation extracts the exact original
`check_tree` AST and compares a candidate that computes each item's exact type and
each container's child depth once. Only those two pure functions execute; no
project package, runtime, worker, authority, device or model runs.

The comparison covers numeric and Unicode boundaries, exact node/depth/string
limits, cycles, shared structures, refusal order, custom types without invoking
their hooks, 400 deterministically generated trees and four retained worker
documents. Success/refusal types, arguments and causes agree in all 468 cases.
Retained documents and all 16 frozen inputs remain unchanged. A syntax error in
one test fixture was caught before freezing or launching a child; its exact source
and failure record remain in [failed-preparation01](failed-preparation01/result.json).

Nine fixed alternating pairs run 256 checks each on the same four documents.
Median process CPU time is 279,935,853 ns for the reference and 269,924,645 ns for
the candidate: a ratio of 0.96423749, approximately 3.6% lower. The candidate is
slower in two pairs; paired ratios range from about 0.874 to 1.086. This modest,
inconsistent local observation is insufficient grounds to treat the change as a
fix for the worker deadline. No repeated success-seeking benchmark or new worker
attempt follows from it.

Public parser/canonicalizer integration, whole-worker performance and physical
behavior are untested here. The full HMS goal stays active. Next work should
evaluate repeated topology/generation/proof construction while preserving fresh
authority/source checks, refusal order and all original execution limits.

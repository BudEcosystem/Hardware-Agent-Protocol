# ASCII-field canonical encoder evaluation

**All 1,875 differential cases pass; the candidate is not adopted.** The
[audit](RESULTS.json) verifies exact current source extraction, 42 unchanged
inputs, 1,342 accepted cases and 533 matching refusals. The public parser,
validator, error wrapping and byte-limit definitions remain unchanged.

The candidate detaches integer-only containers and delegates ASCII field-name
sorting to the guarded C encoder. Non-ASCII field names retain the existing
UTF-16 ordering path, and floats retain the original vendored encoder. Six
observed routing cases and detached-container checks cover those boundaries.
The comparison also covers every Unicode scalar as a value/key, 200 additional
ASCII-field trees, all 128 ASCII field-name characters, 600 fixed bit-generated
floats, custom hooks and thirteen dependency-change fallbacks. Normal cases
also agree with the separate vendored encoder.

Nine fixed alternating pairs on eight retained documents measure a median
242,995,218 ns for the current guarded encoder and 224,000,427 ns for the
candidate: about **7.8% lower CPU time**. Three pairs are slower, and another is
nearly equal. Paired ratios range from 0.7796 to 1.0700. The inconsistent result
does not establish a worker-deadline improvement. No success-seeking repeat or
production integration follows from it.

The single pure child completed in 5.243 seconds within the original bounds.
No HMS package, qualification worker, database, physical endpoint, MCU, model or
live service ran. The prior actual qualification remains failed and unmodified.
The next diagnostic profiles the current complete worker, whose source has
changed since the older profile used to identify costs.

[Scope](REVIEW.md), [candidate diff](candidate.patch), [raw measurements](attempt01/stdout.json),
[original attempt](attempt01/result.json), [current-worker diagnostic](../qualification-current-profile/PLAN.md).

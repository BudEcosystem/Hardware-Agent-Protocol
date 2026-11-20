# Integer-only canonical serialization evaluation

**All 1,668 differential cases pass.** The guarded candidate preserves the exact
extracted validator, parser, error wrapping and output limit. Integer-only values
use fresh UTF-16-ordered containers and standard-library JSON; any float uses the
original RFC 8785 encoder for the complete value. No project code is changed or
HMS package imported by this evaluation.

Coverage includes every Unicode scalar value in bounded key/value chunks,
control escapes, UTF-16 ordering, numeric/string/node/depth/output limits, cycles,
aliases, custom types without hook invocation, parser refusals, 400 fixed generated
trees, 600 bit-generated floats and eight retained worker documents. All six
upstream vector pairs match the original library; the narrower host profile still
refuses the unsafe numeric `values.json` vector. Thirteen helper-change controls
exercise fallback, including in-place code and keyword-default changes.

Nine fixed alternating pairs each perform 256 calls on the same eight documents.
Median CPU time is 550,993,352 ns for the reference and 399,252,738 ns for the
candidate: ratio **0.72460536**, about **27.5% lower**. Every pair is lower; ratios
range from 0.67954609 to 0.74913313. These local observations justify a fresh
isolated integration candidate, not a whole-worker deadline or physical timing
claim. No adaptive repetitions or success-seeking reruns follow the measurement.

The [audit](audit.py) verifies all 37 frozen inputs, their originals, selected
installed runtime files, exact AST extraction and independently derived timings.
The parent owns one terminal child; there are no prohibited attempts or changed
inputs. [Results](RESULTS.json), [original receipt](attempt01/result.json),
[complete cases and measurements](attempt01/stdout.json), [scope](REVIEW.md),
[candidate helper](candidate_helpers.py), [call-site diff](candidate.patch).

The installed JSON Python encoder and selected JCS code are fully read; runtime
C-library closure and broader research are not thereby complete. Review is by
the primary agent only. The next integration must preserve the complete original
thirty-case worker, fresh identities, 60/180-second limits and all storage/effect
bounds. Actual vault import, catalog commit integration, public service mounting,
control capacity, learned PATs and physical I/O/driver/hub providers remain open.

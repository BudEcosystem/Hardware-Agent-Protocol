Historical PAT and resource combined proof

Attempt01 passes 179 tests at its retained source pins. This run is historical: it predates the final three catalog integrity corrections (bounded replay metadata, conflict original-run association, and impossible active-entry handling). It is not validation of the subsequently corrected source.

Only the source and compiler identities retained for each attempt are covered. This directory does not establish whole-suite or current-workspace coverage, production readiness, worker/service qualification, or physical verification.

| Attempt | Tests | Failures | Errors | Skipped | Result | Copied inputs | Seconds |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| 01 | 179 | 0 | 0 | 0 | pass | 129 | 173.687 |

Failure/error counts are the original unittest result counts; subtests can produce more failures than test methods. No report or failed specimen was normalized. Every pre-existing payload was preserved byte-identically.

The independent seal verifies every retained before/after input hash, equal input snapshots, matching compiler pairs, imported/current compiler manifest agreement, and each retained run.py against its reported runner digest. The index hashes all regular files under this directory except __pycache__ content and index.json itself. It includes this README and the root runner. No tests or retained programs were executed while sealing.

Actual worker output and closed scratch databases from the historical combined test run remain under attempts/01/worker-output. Intentional negative cases and contradictory byte/reference specimens are retained unchanged. This outer file index records their actual bytes; it does not repair their internal evidence references or turn expected failures into qualification. The original temporary execution directory in the report is provenance; retainedOutputDirectory identifies the saved copy.

The final three catalog corrections have a separate [independent resolution review](../pat-evaluation-integrity-review/resolution-01/review.json), SHA256 b8b7046f313f73c3de5c38fc63668554db78183b76b5b91a1575f80696ea1d38. Its seven-test producer proof is [integrity attempt04](../pat-evaluation-integrity/attempts/04/result.json); it does not retroactively update earlier attempts.

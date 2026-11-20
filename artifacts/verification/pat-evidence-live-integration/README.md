PAT evidence library integration proof

Attempt02 passes 46 focused tests in 392.586 seconds with 131 copied inputs and the compiler identity unchanged. All 131 retained attempt02 inputs matched current workspace bytes when sealed. This establishes the reviewed library/test/runner integration only; it does not mount a Runtime or public qualification service, authenticate worker execution, qualify current configuration, or verify physical hardware. The latest full 586-test proof is historical; the full 643-test run is pending at this seal.

| Attempt | Tests | Result | Seconds | Source scope |
| --- | ---: | --- | ---: | --- |
| 01 | 46 | pass | 342.270 | Initial copied inputs; child import-root and exceptional-retention limitations retained |
| 02 | 46 | pass | 392.586 | Corrected child provenance, retention handling and per-test SQLite backup setup |

Attempt01 remains an actual pass. Its crash child inherited the live checkout working directory ahead of PYTHONPATH; equal frozen bytes were observed during review, but copied-source child isolation was not established. Its runner also cleaned temporary evidence if retention failed. Attempt02 sets the child working directory and asserts its imported module path, and preserves the original output directory on copy/report failure. Three separate runner-only checks cover copy failure, report failure and success. Both attempts use their own retained run.py pins.

Each attempt retains fresh worker evidence and scratch databases: 27 cases/25 child operations and 10 cases/9 child operations passed with zero unresolved effects. A separate maxOutputBytes=1 run refused with PAT_SIM_OUTPUT_LIMIT, zero operations and unknown unresolved-effects attribution. Independently captured trust records, returned results, all 250 evidence files per attempt, and 11,669,504 scratch bytes per attempt remain byte-identical. File/reference hashes and scratch sizes were checked without rerunning workers.

StoreTests uses one genuine committed full-import template and a fresh SQLite backup per test. Explicit import, deduplication, quota, conflict, rollback and process-crash cases still exercise import. Cached result dictionaries are detached. The elapsed times are observations, not a latency guarantee or claimed performance improvement.

The [initial review](review/initial.json) and [separate resolution](review/resolution.json) preserve the findings and fixes. The [staged memo review](review/staged-memo/review.json) concerns separate historical-data staging and makes no live-integration claim.

The index hashes every retained regular file except __pycache__ content and this root index.json, including source snapshots, runners, reports, all raw worker/scratch/trust files, reviews and this README. Every pre-existing payload was preserved. Before/after input manifests and compiler records were verified; no tests, Runtime, worker or acquired programs were executed during review or sealing.

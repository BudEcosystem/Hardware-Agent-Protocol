# Exact-body evidence storage

All **19 new scopes pass**: 18 fixture controls and one actual bound-worker integration. The integration executes the complete **30-case** finite-I/O simulation, independently inspects its original output, imports the evidence, and replays the same receipt after configuration and session changes. Its authority database is **16,132,096 bytes**, within the unchanged 16 MiB single-file limit by **645,120 bytes**.

The new `evidence_compact` host package preserves all 4,011 run/path references while storing 2,798 exact bodies. Expanded evidence remains 15,355,663 bytes; unique bodies occupy 13,638,563 bytes. Every original body is recoverable byte-for-byte. The measured authority database is 1,459,200 bytes smaller than the preceding integration database; this is an observation from two separate original runs, not a universal capacity bound.

All 261 inherited project files are unchanged. Three production files implement a separate profile, source identity, metadata anchor and schema; two test files provide the new coverage. The legacy consumer identity and 262-file producer image are unchanged. Existing evidence is not migrated, repaired or replaced.

See the [results](results/README.md), [source review](REVIEW.md), [independent actual-data audit](actual-import-audit.json), [aggregate audit](RESULTS.json), [design](DESIGN.md), and [next integration work](NEXT.md). The [preceding retention failure](../pat-io-bound-import/README.md) remains immutable, including its original oversized database and forensic copies.

This is a host library candidate with simulated device effects. Historical replay does not establish fresh PAT eligibility under a changed configuration. Public catalog integration, protected control capacity, prompt learning, persistent Arduino applications, actual device and driver providers, and intelligence-hub management remain part of the active end-to-end goal.

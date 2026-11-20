# Retained fixture correction

Attempt01 terminates with a setup error before any test method. It creates the
two-chunk main image, then rejects the control fixture's 33-character identity.
The production identity validator is correct; the required fixture identity has
32 lowercase hex characters. The original five input files are copied exactly
under attempt01/frozen-inputs and match the original input receipt. Its result,
logs and 32 MiB main image remain unchanged.

Attempt02 corrects only that control identity literal in the test. The production
fixed_block.py is byte-for-byte unchanged. The runner accepts an explicit reviewed
attempt directory and still refuses existing directories. The same 24 methods,
limits and assertions apply; no method is dropped. Combined retained backing is
at most 32 MiB from attempt01 plus 48 MiB from attempt02, within the original
256 MiB scratch bound and 16 MiB per-file ceiling. No original worker, device
operation, qualification or runtime test is retried.

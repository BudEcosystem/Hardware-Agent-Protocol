# Audit correction02

The first read-only audit stopped before image inspection because it required provider stderr to be empty. Its exact retained output contains the 24 successful unittest progress entries and summary plus the expected CPython DeprecationWarning from the deliberately multithreaded fork-refusal control. This is an audit expectation error, not a candidate failure or a new test run.

Root read every stderr line and reviewed the corresponding successful structured stdout and process receipt. The second auditor retains all existing assertions and replaces only that empty-stderr assertion with the exact SHA256 of the reviewed bytes. No warning or diagnostic is suppressed. The original auditor, runner, audit-process01, candidate inputs and all images stay unchanged.

Audit-process01 returned1 after2.965432638 seconds, CPU2.888785, no timeout, clean reap and absent group. Audit-process02 uses new frozen sources and the same60s wall/40s CPU/512MiB AS/128FD/16MiB file bounds with the same anchored cleanup. It adds no images, does not replay any workload and invokes no adapter recovery. Passing the corrected audit cannot turn the writer timeout into a pass.

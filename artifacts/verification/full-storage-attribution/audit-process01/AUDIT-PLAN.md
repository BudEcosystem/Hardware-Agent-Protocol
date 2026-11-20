# Independent read-only state and observation audit

The retained reader and bounded audit runner are byte-identical to Stage 95.
Only the reader's library functions are used; its historical standalone main
does not execute. No hierarchy adapter, controls or tracer is imported, and no
adapter recovery is invoked. Frozen native.py retains its base-module import for
errors/constants; no adapter is constructed. It uses strictly read-only held descriptors;
write, erase and sync callbacks raise. The inline512 profile and library hash
remain explicit. Existing failed images are never repaired or passed to SQLite.

Verify the source/frozen-file joins, native and mount-library hashes, host file
identities, original dataset and public 244-file baseline. Revalidate the Stage
95 seal including its declared symlink and all 340 files; its 192 original
checks are retained evidence, not newly executed tests. Join every child start
and terminal receipt, require reaping and absent PIDs, and check original limits.

Reconstruct both screen images. Require all forty complete bodies, twenty
directories, inodes, links, callbacks and raw backing bytes to agree with the
original screen receipts and each other. Reconstruct the full writer if it ran;
join every complete progress line to the original dataset prefix, verify all
published bodies and directories, and report any partial progress tail, next
published file, pending entry, unlinked inode or incomplete physical inode.
The dependent cold reader is accepted only following a complete writer.

Parse complete attribution JSONL lines independently with exact field/label
validation and the original 64 KiB frame / 12 MiB log bounds. Retain the last
partial line length. Check sequence, elapsed time, root operation counts,
nonduplicated phase/label rows, completed call/error/inclusive-time monotonicity,
observer counters and native callback monotonicity within each owner sequence.
Self-time rounding is retained and is not required to be monotone. A cold owner
has a fresh callback counter set; no cross-owner monotonicity is assumed.

For every complete frame, verify that logical call counts equal completed root
calls and that inclusive logical wall/CPU totals equal the sum of all nested
self times, both overall and by phase. This establishes an additive self-time
partition for the recorded completed boundaries; inclusive categories overlap
and must not be summed as independent work. It does not prove timing accuracy
outside the instrumented execution or within an unobserved in-flight call.

METRICS.json contains per-phase and per-label inclusive/self totals, additive
self categories and completed-root totals. Native boundary self time includes
ctypes/native execution and tracing overhead; individual C allocation or metadata
traversal functions remain unmeasured. Provider verification self time contains
unwrapped ownership/inventory/stat work after its timed nested operations.

The last frame's elapsed wall clock ends before that frame is serialized.
Its observer totals cover earlier snapshot work only, which aligns with that
prefix clock. The prefix wall gap is elapsed minus completed-root wall time minus
that prior observer wall time. It includes unwrapped harness work, setup and
tracer bookkeeping outside timed spans; it is never called native work. No
prefix CPU clock was recorded, so no prefix CPU gap is invented. When a final
observer receipt exists, it includes the final frame's observation cost but not
its own later JSON publication. The terminal process envelope also includes
startup/teardown and parent observation delay. For an interrupted run, any
terminal-minus-prefix remainder includes the unobserved suffix and cannot be
assigned to the harness or a specific native function. No extrapolation to all
4,270 files or production throughput is made.

Record the paired screen's observed time delta as an instrumentation/run-variation
measurement for that one workload. The tracer substantially perturbs timings;
semantic/raw equivalence does not remove that timing limitation. An interrupted
run can have a valid observed prefix while its full-workload gate remains failed.

Freeze audit sources before one run under 60 wall/40 CPU seconds, 512 MiB address
space, 128 descriptors, 16 MiB per file and no core dumps. Save actual process
receipts and reports. The auditor writes reports only. No device, mount,
administrator operation, model inference or physical power-loss test runs.

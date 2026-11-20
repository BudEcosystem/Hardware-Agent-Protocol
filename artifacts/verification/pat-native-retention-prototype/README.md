# Native retention scan prototype

The standalone Linux C helper passes **20 differential filesystem controls**
against the exact original Python function. Seven fixed alternating timing pairs
on the original retained tree measure median CPU time of **22.694 ms** for Python
and **8.877 ms** for C per scan: about **61% lower**. All seven paired ratios favor
the native helper. [Results](RESULTS.json) retain the arithmetic and limits.

This is an isolated prototype. No production module, public runtime, qualification
worker, Arduino program or physical provider changes or runs. The previous full
worker remains failed before import; these timings do not establish a complete
worker speedup or a deadline guarantee.

The [source](scan.c) opens directories, enumerates names and checks each entry's
metadata. It retains the original depth/count/byte and owner/mode/link rules,
calls the real-UID function for each entry, handles unknown directory-entry types
through fresh stat calls, and distinguishes enumeration errors from end-of-stream.
It returns structured failure and performs no file-content reads. The standalone
CLI has an explicit bounded integer domain; it is not a replacement Python API.
Negative file sizes are refused, and cleanup errors cannot create success.

The [controls and timings](attempt01/result.json) cover valid and empty trees,
hidden and non-UTF-8 names, root failures, file/directory symlinks, hard links,
permission/special-mode refusals, a FIFO, depth boundaries and exact/exceeded
count and byte limits. All original 49 owner/writer locks are held during retained
tree measurements. Its 3,227-entry metadata inventory remains identical before
and after, and no interrupted case database is read or recovered. Each timing
process warms once, then measures five scans using self CPU accounting. Startup
is outside that CPU interval; raw outer elapsed times remain available.

The [syscall checks](trace02/result.json) pass five owned fixture scopes: ordinary
operation, FIFO refusal, injected foreign UID, injected directory-read failure
and injected child-directory open failure. In each observed scanner phase, all
opens are read-only no-follow directory opens, metadata calls address those
directories, no file data is read, and every acquired directory descriptor is
closed. Dynamic-loader reads precede the scanner phase and are reported separately.
Injected failures are not a substitute for every possible filesystem race or error.

The first [trace parser failure](trace01/failure.json) remains retained. It omitted
libc's directory `fstat` and descriptor-flag operations, plus stdout's `fstat`.
The fresh [checker correction](trace02.py.patch) recognizes only those specific
operations on the appropriate descriptors. The C source and binary are unchanged
across all scopes. No execution, storage or effect bound was relaxed.

The [build receipt](build01/build.json) pins the source, compiler executable and
16,616-byte binary, and records the installed platform and compiler version.
It does not attest the entire compiler/header/linker/libc closure. The separate
[audit](audit.py) verifies source fidelity, controls, timings, trace receipts and
the preserved failure. Review was by the primary agent, not a second reviewer.

Nine [primary manuals](../../../research/host-contract/native-retention/README.md)
were retained and fully read before this prototype. [Next work](NEXT.md) specifies
the remaining binding, failure and actual-worker integration work.

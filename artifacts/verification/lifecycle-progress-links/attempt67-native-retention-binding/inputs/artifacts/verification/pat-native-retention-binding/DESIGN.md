# Isolated in-process retention binding

This stage tests an original CPython 3.12 / Linux extension. It does not change
the public runtime, launch qualification, import evidence, install a PAT or
control physical hardware. The frozen standalone prototype and interrupted
worker states remain untouched.

The private ABI is `scan(path_bytes, max_files, max_bytes)`. Arguments must be
exact bytes and exact integers; no path or numeric conversion hooks execute.
The path is 1–4095 bytes without NUL. Limits are inclusive ranges 0–262144 entries
and 0–268435456 logical bytes. This deliberately specified ABI is not a drop-in
Python `tree_usage` replacement. A future trusted wrapper must resolve caller
compatibility and map structured failures to the supervisor's existing errors.

The entry count, byte sum, depth ceiling, no-follow entry metadata, real-UID,
directory mode, regular-file type/mode/link checks follow the original profile.
Opened root and child directories additionally need current UID and mode 0700.
An opened child must match the pre-open device/inode. These are explicit
strengthenings; the original Python implementation can accept an unsafe root
mode and does not reject a real-directory replacement between stat and open.
The traversal is not an atomic filesystem snapshot. Subsequent changes,
ancestor symlinks, arbitrary same-process code and external modification of a
loader artifact are outside the protections established here.

Every opened directory descriptor has exactly one owner. Successful `fdopendir`
transfers it to the stream; failures and pre-stream refusals close it directly.
The first policy or OS failure remains primary; the first cleanup errno is also
returned. A cleanup error cannot yield success. Linux close and closedir are
never retried by descriptor number. In particular, close EINTR is a conservative
failure here, whereas PEP 475 specifies that Python's close wrappers ignore it.
There is no blanket semantic-equivalence assertion.

Potentially blocking calls release the GIL. Errno is captured before restoring
the thread state. Signal handlers run after filesystem calls and between entries;
a Python exception propagates unchanged after all owned descriptors are released.
Open and stat EINTR are retried after the signal check. Stream construction and
enumeration errors, including EINTR, refuse instead of hiding missing evidence.
Python signal dispatch only occurs in the main thread/main interpreter. This is
not a cross-thread cancellation API or a hard bound on a stalled filesystem call.
Subinterpreters, interpreter shutdown and other Python versions are unqualified.

`hms.retention.scan.v1` carries exact path bytes and both limits before any
directory opens. A hook can veto. Native syscalls do not generate Python's usual
per-entry audit events. Future execution harnesses must explicitly authorize
the scanned root and binary origin; this event is a cooperative guardrail, not
an OS sandbox. The test loader verifies the pinned binary before using an
explicit ExtensionFileLoader path and verifies the file and origin afterward.
It assumes no concurrent modification of the retained build directory. No
untrusted path-search import or runtime build is used.

Production and instrumented DSOs are separate. `faultmodule.c` includes the same
scanner source but substitutes test functions at its native call sites. It can
inject errors and a precisely ordered replacement/disappearance in owned
fixtures. It is not production artifact evidence. The production DSO receives
ordinary differential controls, strict input checks, real descriptor exhaustion,
Python signals and a concurrent Python observer. Repeated failures check actual
descriptor inventories. The complete worker, actual syscall boundary and
whole-worker cost remain future checks; no original deadline or quota changes.

The six acquired official documentation files are retained under `research`.
Only the exact ranges listed in the reading receipt have been read so far.
Five API files are pinned to upstream v3.12.3, matching the installed version's
release number; that is not attestation of the distribution's patched build.
The installed ExtensionFileLoader source is retained in the build receipt.
